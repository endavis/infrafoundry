"""Tailscale validator for OPNsense (#787).

Plan-time checks for ``tailscale.settings``, ``tailscale.auth`` and ``tailscale.subnets``
(no live-box access). Messages name the field, never a value: ``pre_auth_key`` is a
secret.

- Settings: unknown or refused keys are ERRORs (refused keys carry a hint); types and
  ranges use the service's own rules.
- Auth: unknown keys are ERRORs. ``pre_auth_key`` must be a ``secret://`` reference; a
  literal is an ERROR. ``update_pre_auth_key`` must be a boolean and needs a
  ``pre_auth_key``. ``login_server`` must be an ``http(s)://`` URL.
- Subnets: unknown keys are ERRORs (``uuid`` carries a hint). ``subnet`` is required, a
  valid network CIDR with no host bits. ``description`` must be a string and ``lock`` a
  boolean. Normalized CIDRs are unique within the type.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any, override

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.services import tailscale_auth as auth_svc
from infrafoundry.providers.opnsense.services import tailscale_settings as settings_svc
from infrafoundry.providers.opnsense.services import tailscale_subnets as subnets_svc
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

_SECRET_URI = re.compile(r"^secret://[^/]+/.+$")
_URL = re.compile(r"^https?://[^\s/]+\S*$")


class TailscaleValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``tailscale.*`` resources at plan time."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ``ValidationReport`` to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Validate all Tailscale resources.

        Args:
            context: Context whose ``resources`` hold the ``tailscale.*`` resources.
        """
        subnets: list[ResourceConfig] = []
        for resource in context.resources:
            if resource.type == "tailscale.settings":
                self._validate_settings(resource)
            elif resource.type == "tailscale.auth":
                self._validate_auth(resource)
            elif resource.type == "tailscale.subnets":
                subnets.append(resource)
        self._check_duplicates(subnets)
        for resource in subnets:
            self._validate_subnet(resource)

    def _error(self, check: str, message: str) -> None:
        self.report.add_check(
            check_name=check, passed=False, message=message, level=ValidationLevel.ERROR
        )

    # -- settings -----------------------------------------------------------------

    def _validate_settings(self, resource: ResourceConfig) -> None:
        config = resource.config
        label = "tailscale.settings"
        prefix = "tailscale_settings"
        for key in sorted(set(config) - set(settings_svc.FIELD_MAP)):
            if key in settings_svc.REFUSED_KEY_HINTS:
                message = f"{label} has refused key '{key}' ({settings_svc.REFUSED_KEY_HINTS[key]})"
            else:
                message = (
                    f"{label} has unknown key '{key}'; allowed: {sorted(settings_svc.FIELD_MAP)}"
                )
            self._error(f"{prefix}_unknown_key_{key}", message)
        for key in settings_svc.FIELD_MAP:
            if key not in config:
                continue
            try:
                settings_svc.serialize_setting(key, config[key])
            except InvalidConfigurationError as exc:
                self._error(f"{prefix}_{key}", str(exc))

    # -- auth ---------------------------------------------------------------------

    def _validate_auth(self, resource: ResourceConfig) -> None:
        config = resource.config
        label = "tailscale.auth"
        prefix = "tailscale_auth"
        for key in sorted(set(config) - auth_svc.ALLOWED_KEYS):
            self._error(
                f"{prefix}_unknown_key_{key}",
                f"{label} has unknown key '{key}'; allowed: {sorted(auth_svc.ALLOWED_KEYS)}",
            )
        key_value = config.get("pre_auth_key")
        if "pre_auth_key" in config and (
            not isinstance(key_value, str) or not _SECRET_URI.match(key_value)
        ):
            self._error(
                f"{prefix}_pre_auth_key_literal_secret",
                f"{label} pre_auth_key must be a secret:// reference, not a literal value",
            )
        if "update_pre_auth_key" in config:
            if not isinstance(config["update_pre_auth_key"], bool):
                self._error(
                    f"{prefix}_update_pre_auth_key",
                    f"{label} update_pre_auth_key must be a boolean",
                )
            elif config["update_pre_auth_key"] and not config.get("pre_auth_key"):
                self._error(
                    f"{prefix}_update_pre_auth_key",
                    f"{label} sets update_pre_auth_key but no pre_auth_key",
                )
        if "login_server" in config:
            server = config["login_server"]
            if not isinstance(server, str) or not _URL.match(server):
                self._error(
                    f"{prefix}_login_server", f"{label} login_server must be an http(s):// URL"
                )

    # -- subnets ------------------------------------------------------------------

    def _check_duplicates(self, resources: list[ResourceConfig]) -> None:
        seen: set[str] = set()
        dupes: set[str] = set()
        for r in resources:
            value = r.config.get("subnet")
            if not isinstance(value, str):
                continue
            key = subnets_svc.normalize_cidr(value)
            (dupes if key in seen else seen).add(key)
        if dupes:
            self._error(
                "tailscale_subnets_unique_cidrs",
                f"tailscale.subnets resources share subnets: {sorted(dupes)!r}. "
                f"The CIDR is the identity on the box; make each unique.",
            )

    def _validate_subnet(self, resource: ResourceConfig) -> None:
        name, config = resource.name, resource.config
        label = f"tailscale subnet '{name}'"
        prefix = f"tailscale_subnet_{name}"
        self._check_subnet_keys(prefix, label, config)
        subnet = config.get("subnet")
        if not isinstance(subnet, str) or not subnet.strip():
            self._error(f"{prefix}_subnet", f"{label} requires a subnet CIDR")
        else:
            try:
                ipaddress.ip_network(subnet.strip(), strict=True)
            except ValueError:
                self._error(
                    f"{prefix}_subnet",
                    f"{label} subnet must be a network CIDR with no host bits set",
                )
        description = config.get("description")
        if description is not None and not isinstance(description, str):
            self._error(f"{prefix}_description", f"{label} description must be a string")
        if "lock" in config and not isinstance(config["lock"], bool):
            self._error(f"{prefix}_lock", f"{label} lock must be a boolean")

    def _check_subnet_keys(self, prefix: str, label: str, config: dict[str, Any]) -> None:
        for key in sorted(set(config) - subnets_svc.ALLOWED_KEYS):
            if key in subnets_svc.BOX_ASSIGNED_KEYS:
                message = f"{label} must not set '{key}': the box assigns it"
            else:
                message = (
                    f"{label} has unknown key '{key}'; allowed: {sorted(subnets_svc.ALLOWED_KEYS)}"
                )
            self._error(f"{prefix}_unknown_key_{key}", message)
