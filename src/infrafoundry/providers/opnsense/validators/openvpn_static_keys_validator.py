"""OpenVPN static-key validator for OPNsense (#1319).

Plan-time checks for ``openvpn.static_keys`` (no live-box access). Messages name the
resource and the field, never a value: ``key`` is a secret.

- Unknown keys are ERRORs; the box-assigned ``uuid`` carries a hint.
- ``mode`` is required and one of ``auth``, ``crypt`` or ``crypt-v2``.
- ``key`` is required and must be a ``secret://`` URI; a literal is an ERROR.
- ``update_key`` and ``lock`` must be booleans; ``description`` a string.
- Duplicate descriptions within the type.
"""

from __future__ import annotations

import re
from typing import Any, override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.services import openvpn_static_keys as svc
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

_SECRET_URI = re.compile(r"^secret://[^/]+/.+$")


class OpenVpnStaticKeyValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``openvpn.static_keys`` resources at plan time."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ``ValidationReport`` to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Validate all OpenVPN static-key resources.

        Args:
            context: Context whose ``resources`` hold the static keys.
        """
        resources = [r for r in context.resources if r.type == "openvpn.static_keys"]
        if not resources:
            return
        self._check_duplicates(resources)
        for resource in resources:
            self._validate_one(resource)

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
                "openvpn_static_keys_unique_descriptions",
                f"openvpn.static_keys resources share descriptions: {sorted(dupes)!r}. "
                f"The description is the identity on the box; make each unique.",
            )

    def _validate_one(self, resource: ResourceConfig) -> None:
        name, config = resource.name, resource.config
        label = f"openvpn static key '{name}'"
        prefix = f"openvpn_static_key_{name}"
        self._check_keys(prefix, label, config)
        mode = config.get("mode")
        if mode is None:
            self._error(f"{prefix}_mode_required", f"{label} requires 'mode'")
        elif mode not in svc.MODES:
            self._error(f"{prefix}_mode", f"{label} mode must be one of {list(svc.MODES)}")
        key = config.get("key")
        if key in (None, ""):
            self._error(f"{prefix}_key_required", f"{label} requires 'key' (a secret:// reference)")
        elif not isinstance(key, str) or not _SECRET_URI.match(key):
            self._error(
                f"{prefix}_key_literal_secret",
                f"{label} key must be a secret:// reference, not a literal value",
            )
        for flag in ("lock", "update_key"):
            if flag in config and not isinstance(config[flag], bool):
                self._error(f"{prefix}_{flag}", f"{label} {flag} must be a boolean")
        description = config.get("description")
        if description is not None and not isinstance(description, str):
            self._error(f"{prefix}_description", f"{label} description must be a string")

    def _check_keys(self, prefix: str, label: str, config: dict[str, Any]) -> None:
        for key in sorted(set(config) - svc.ALLOWED_KEYS):
            if key in svc.BOX_ASSIGNED_KEYS:
                message = f"{label} must not set '{key}': the box assigns it"
            else:
                message = f"{label} has unknown key '{key}'; allowed: {sorted(svc.ALLOWED_KEYS)}"
            self._error(f"{prefix}_unknown_key_{key}", message)
