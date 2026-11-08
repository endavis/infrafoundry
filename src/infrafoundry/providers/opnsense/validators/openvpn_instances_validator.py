"""OpenVPN client-instance validator for OPNsense (#808).

Plan-time checks for ``openvpn.instances`` (no live-box access). Messages name the
resource and the field, never a value: ``username`` and ``password`` are secrets.

- Unknown keys are ERRORs; box-assigned (``uuid``, ``vpnid``) and refused keys
  (``role``, ``ca``, ``cert``, ``tls_key``, hyphenated wire spellings) carry a hint.
- ``remote`` and ``ca_ref`` are required; ``ca_ref`` must name a ``trust.cas`` resource.
- ``username`` and ``password`` must be ``secret://`` URIs; a literal is an ERROR.
- Enums, integer ranges and list shapes are checked with the parser's own rules.
- Duplicate descriptions within the type.
"""

from __future__ import annotations

import re
from typing import Any, override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.services import openvpn_instances as svc
from infrafoundry.providers.opnsense.validators._xref import resolve_xref
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

_SECRET_URI = re.compile(r"^secret://[^/]+/.+$")


class OpenVpnInstanceValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``openvpn.instances`` resources at plan time."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ``ValidationReport`` to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Validate all OpenVPN instance resources.

        Args:
            context: Context whose ``resources`` hold the instances; ``index``
                resolves ``ca_ref``.
        """
        resources = [r for r in context.resources if r.type == "openvpn.instances"]
        if not resources:
            return
        self._check_duplicates(resources)
        for resource in resources:
            self._validate_one(resource, context)

    def _error(self, check: str, message: str) -> None:
        self.report.add_check(
            check_name=check, passed=False, message=message, level=ValidationLevel.ERROR
        )

    def _check_duplicates(self, resources: list[ResourceConfig]) -> None:
        seen: set[str] = set()
        dupes: set[str] = set()
        for r in resources:
            description = svc.description_of(r.name, r.config)
            (dupes if description in seen else seen).add(description)
        if dupes:
            self._error(
                "openvpn_instances_unique_descriptions",
                f"openvpn.instances resources share descriptions: {sorted(dupes)!r}. "
                f"The description is the identity on the box; make each unique.",
            )

    def _validate_one(self, resource: ResourceConfig, context: OPNsenseValidationContext) -> None:
        name, config = resource.name, resource.config
        label = f"openvpn instance '{name}'"
        prefix = f"openvpn_instance_{name}"
        self._check_keys(prefix, label, config)
        self._check_secrets(prefix, label, config)
        self._check_ca_ref(prefix, label, config, context)
        if not config.get("remote"):
            self._error(f"{prefix}_remote_required", f"{label} requires a non-empty 'remote' list")
        for key in ("lock", "update_password"):
            if key in config and not isinstance(config[key], bool):
                self._error(f"{prefix}_{key}", f"{label} {key} must be a boolean")
        if config.get("update_password") is True and not config.get("password"):
            self._error(
                f"{prefix}_update_password", f"{label} sets update_password but no password"
            )
        description = config.get("description")
        if description is not None and not isinstance(description, str):
            self._error(f"{prefix}_description", f"{label} description must be a string")
        for key, spec in svc.FIELD_SPECS.items():
            if key not in config:
                continue
            try:
                svc.serialize_value(label, key, spec, config[key])
            except ValueError as exc:
                self._error(f"{prefix}_{key}", str(exc))

    def _check_keys(self, prefix: str, label: str, config: dict[str, Any]) -> None:
        for key in sorted(set(config) - svc.ALLOWED_KEYS):
            if key in svc.BOX_ASSIGNED_KEYS:
                message = f"{label} must not set '{key}': the box assigns it"
            elif key in svc.REJECTED_KEY_HINTS:
                message = f"{label} has refused key '{key}' ({svc.REJECTED_KEY_HINTS[key]})"
            else:
                message = f"{label} has unknown key '{key}'; allowed: {sorted(svc.ALLOWED_KEYS)}"
            self._error(f"{prefix}_unknown_key_{key}", message)

    def _check_secrets(self, prefix: str, label: str, config: dict[str, Any]) -> None:
        for key in svc.SECRET_FIELDS:
            value = config.get(key)
            if value is None or value == "":
                continue
            if not isinstance(value, str) or not _SECRET_URI.match(value):
                self._error(
                    f"{prefix}_{key}_literal_secret",
                    f"{label} {key} must be a secret:// reference, not a literal value",
                )

    def _check_ca_ref(
        self, prefix: str, label: str, config: dict[str, Any], context: OPNsenseValidationContext
    ) -> None:
        ca_ref = config.get("ca_ref")
        if ca_ref in (None, ""):
            self._error(f"{prefix}_ca_ref_required", f"{label} requires 'ca_ref'")
            return
        if not isinstance(ca_ref, str):
            self._error(f"{prefix}_ca_ref_type", f"{label} ca_ref must be a string")
            return
        try:
            found = (
                resolve_xref(ca_ref, "trust.cas", context.index, current_plugin="openvpn")
                if context.index is not None
                else None
            )
        except ValueError:
            found = None
        if found is None:
            self._error(
                f"{prefix}_ca_ref",
                f"{label} ca_ref '{ca_ref}' does not match any trust.cas resource",
            )
