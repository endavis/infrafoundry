"""HA sync settings validators for OPNsense (#1389).

Two validators for the ``hasync.settings`` singleton:

- :class:`HasyncValidator` is offline (runs on ``infra plan`` and ``infra doctor``).
  Unknown keys, wrong types, IP formats, the ``pfsync_version`` enum, ``sync_items``
  shape, ``update_password`` without ``password`` and a plaintext password (WARNING,
  the ``virtual_ips`` convention) are checked from the YAML alone.
- :class:`HasyncLiveValidator` runs in ``infra doctor`` only. It checks
  ``pfsync_interface`` and ``sync_items`` against the option maps from one
  ``core/hasync/get`` fetch. With empty option sets (the fetch failed) it checks nothing.

Messages name fields, never the password value.
"""

from __future__ import annotations

import ipaddress
import re
from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

from ..services.hasync_settings import (
    ALLOWED_KEYS,
    BOOL_FIELDS,
    PFSYNC_VERSIONS,
    STRING_FIELDS,
)

_SECRET_URI = re.compile(r"^secret://[^/]+/.+$")


class HasyncValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``hasync.settings`` singleton resources offline."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Validate ``hasync.settings`` resources.

        Args:
            context: Validation context carrying the resources and managed assignment names.
        """
        for resource in context.resources:
            self._validate_one(resource, context.interface_assignment_names)

    def _add(self, check: str, message: str, level: ValidationLevel) -> None:
        self.report.add_check(check_name=check, passed=False, message=message, level=level)

    def _error(self, check: str, message: str) -> None:
        self._add(check, message, ValidationLevel.ERROR)

    def _validate_one(self, resource: ResourceConfig, assignment_names: set[str]) -> None:
        check = f"hasync_settings_{resource.name}"
        config = resource.config
        for key in sorted(set(config) - ALLOWED_KEYS, key=str):
            self._error(f"{check}_{key}", f"hasync.settings has unknown key '{key}'")
        for key in sorted(BOOL_FIELDS | {"update_password"}):
            if key in config and not isinstance(config[key], bool):
                self._error(
                    f"{check}_{key}",
                    f"hasync.settings {key} must be a boolean, got {type(config[key]).__name__}",
                )
        for key in sorted(STRING_FIELDS):
            if key in config and not isinstance(config[key], str):
                self._error(f"{check}_{key}", f"hasync.settings {key} must be a string")
        self._validate_ip(check, config, "pfsync_peer_ip", v4_only=True)
        self._validate_ip(check, config, "synchronize_to_ip", v4_only=False)
        self._validate_version(check, config)
        self._validate_sync_items(check, config)
        self._validate_password(check, config)
        interface = config.get("pfsync_interface")
        if isinstance(interface, str) and interface in assignment_names:
            self.report.add_check(
                check_name=f"{check}_pfsync_interface",
                passed=True,
                message=f"pfsync_interface '{interface}' resolved to a managed assignment",
                level=ValidationLevel.INFO,
            )

    def _validate_ip(
        self, check: str, config: dict[str, object], key: str, *, v4_only: bool
    ) -> None:
        value = config.get(key)
        if not isinstance(value, str) or value == "":
            return
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            self._error(f"{check}_{key}", f"hasync.settings {key} is not a valid IP address")
            return
        if v4_only and address.version != 4:
            self._error(f"{check}_{key}", f"hasync.settings {key} must be an IPv4 address")

    def _validate_version(self, check: str, config: dict[str, object]) -> None:
        if "pfsync_version" not in config:
            return
        value = config["pfsync_version"]
        text = str(value) if isinstance(value, int) and not isinstance(value, bool) else value
        if not isinstance(text, str) or text not in PFSYNC_VERSIONS:
            self._error(
                f"{check}_pfsync_version",
                f"hasync.settings pfsync_version must be one of {', '.join(PFSYNC_VERSIONS)}",
            )

    def _validate_sync_items(self, check: str, config: dict[str, object]) -> None:
        if "sync_items" not in config:
            return
        items = config["sync_items"]
        name = f"{check}_sync_items"
        if not isinstance(items, list):
            self._error(name, "hasync.settings sync_items must be a list of strings")
            return
        if not all(isinstance(i, str) and i.strip() for i in items):
            self._error(name, "hasync.settings sync_items entries must be non-empty strings")
            return
        if len(set(items)) != len(items):
            self._error(name, "hasync.settings sync_items has duplicate entries")

    def _validate_password(self, check: str, config: dict[str, object]) -> None:
        name = f"{check}_password"
        if config.get("update_password") is True and "password" not in config:
            self._error(name, "hasync.settings update_password requires a password")
        if "password" not in config:
            return
        password = config["password"]
        if not isinstance(password, str) or not password.strip():
            self._error(name, "hasync.settings password must be a non-empty string")
            return
        if _SECRET_URI.match(password):
            return
        self._add(
            name,
            "hasync.settings password is a plaintext string; consider using a "
            "'secret://env_secrets/<path>' URI instead so the secret is sourced "
            "from the encrypted env secrets file",
            ValidationLevel.WARNING,
        )


class HasyncLiveValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``hasync.settings`` references against the live option maps (doctor only)."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Check ``pfsync_interface`` and ``sync_items`` against the live option sets.

        Args:
            context: Validation context carrying the resources and the live option sets.
        """
        for resource in context.resources:
            check = f"hasync_settings_{resource.name}"
            self._check_interface(check, resource, context)
            self._check_items(check, resource, context)

    def _check_interface(
        self, check: str, resource: ResourceConfig, context: OPNsenseValidationContext
    ) -> None:
        interface = resource.config.get("pfsync_interface")
        if not isinstance(interface, str) or not interface:
            return
        if interface in context.interface_assignment_names:
            return
        if not context.existing_hasync_interfaces:
            return
        if interface in context.existing_hasync_interfaces:
            return
        self.report.add_check(
            check_name=f"{check}_pfsync_interface",
            passed=False,
            message=(
                f"hasync.settings pfsync_interface '{interface}' is neither a managed "
                f"interface assignment nor an interface the box offers for pfsync"
            ),
            level=ValidationLevel.ERROR,
        )

    def _check_items(
        self, check: str, resource: ResourceConfig, context: OPNsenseValidationContext
    ) -> None:
        items = resource.config.get("sync_items")
        if not isinstance(items, list) or not context.existing_hasync_sync_items:
            return
        for item in items:
            if isinstance(item, str) and item and item not in context.existing_hasync_sync_items:
                self.report.add_check(
                    check_name=f"{check}_sync_items",
                    passed=False,
                    message=f"hasync.settings sync_items entry '{item}' is not offered by the box",
                    level=ValidationLevel.ERROR,
                )
