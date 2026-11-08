"""System users and groups validators for OPNsense (#805).

Static plan-time checks for the ``system.users`` and ``system.groups`` list
types. Secret-bearing user fields (``password``, ``authorizedkeys``, ``otp_seed``,
``apikeys``) must be empty or a ``secret://`` URI; a literal is an ERROR and the
message never echoes the value. Group ``member_refs`` must resolve to a
``system.users`` resource.
"""

from __future__ import annotations

import re
from typing import Any, override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.services.system_users import SECRET_FIELDS
from infrafoundry.providers.opnsense.validators._xref import resolve_xref
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

_SECRET_URI = re.compile(r"^secret://[^/]+/.+$")
_SCOPES = {"system", "user"}


class _AuthBase:
    """Shared helpers for the two validators."""

    kind = ""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ``ValidationReport`` to add results to.
        """
        self.report = report

    def _error(self, check: str, message: str) -> None:
        self.report.add_check(
            check_name=check, passed=False, message=message, level=ValidationLevel.ERROR
        )

    def _check_unique(self, resources: list[ResourceConfig], key: str, label: str) -> None:
        """Flag duplicate wire names, and duplicate ``key`` values (uid or gid)."""
        names: set[str] = set()
        values: set[str] = set()
        for r in resources:
            name = str(r.config.get("name", r.name))
            if name in names:
                self._error(
                    f"system_{self.kind}_unique_names",
                    f"Duplicate system {self.kind} name {name!r}.",
                )
            names.add(name)
            if key in r.config:
                value = str(r.config[key])
                if value in values:
                    self._error(
                        f"system_{self.kind}_unique_{key}s",
                        f"Duplicate {label} {value} (system {self.kind} '{r.name}').",
                    )
                values.add(value)

    def _check_common(self, r: ResourceConfig, id_key: str) -> None:
        config = r.config
        if id_key in config:
            raw = config[id_key]
            if isinstance(raw, bool) or not isinstance(raw, (int, str)) or not str(raw).isdigit():
                self._error(
                    f"system_{self.kind}_{r.name}_{id_key}",
                    f"system {self.kind} '{r.name}' {id_key} must be a non-negative integer",
                )
        scope = config.get("scope")
        if scope is not None and scope not in _SCOPES:
            self._error(
                f"system_{self.kind}_{r.name}_scope",
                f"system {self.kind} '{r.name}' scope must be one of {sorted(_SCOPES)}",
            )
        priv = config.get("priv")
        if priv is not None and not (
            isinstance(priv, list) and all(isinstance(p, str) for p in priv)
        ):
            self._error(
                f"system_{self.kind}_{r.name}_priv",
                f"system {self.kind} '{r.name}' priv must be a list of strings",
            )


class SystemUserValidator(_AuthBase, SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``system.users`` resources."""

    kind = "user"

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Validate all user resources.

        Args:
            context: Validation context carrying the resources to check.
        """
        resources = context.resources
        if not resources:
            return
        self._check_unique(resources, "uid", "uid")
        for r in resources:
            self._check_common(r, "uid")
            self._check_secrets(r.name, r.config)

    def _check_secrets(self, name: str, config: dict[str, Any]) -> None:
        for field in SECRET_FIELDS:
            value = config.get(field)
            if value is None or value == "":
                continue
            if not isinstance(value, str) or not _SECRET_URI.match(value):
                self._error(
                    f"system_user_{name}_{field}_literal_secret",
                    f"system user '{name}' {field} must be a secret:// reference, "
                    f"not a literal value",
                )


class SystemGroupValidator(_AuthBase, SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``system.groups`` resources."""

    kind = "group"

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Validate all group resources.

        Args:
            context: Validation context carrying the resources and the xref index.
        """
        resources = context.resources
        if not resources:
            return
        self._check_unique(resources, "gid", "gid")
        for r in resources:
            self._check_common(r, "gid")
            if "member_refs" in r.config:
                self._check_refs(r, context)

    def _check_refs(self, r: ResourceConfig, context: OPNsenseValidationContext) -> None:
        refs = r.config["member_refs"]
        check = f"system_group_{r.name}_member_refs"
        if not isinstance(refs, list) or not all(isinstance(x, str) and x for x in refs):
            self._error(
                check, f"system group '{r.name}' member_refs must be a list of non-empty strings"
            )
            return
        for ref in refs:
            if not self._resolves(ref, context):
                self._error(
                    check,
                    f"system group '{r.name}' member_refs entry {ref!r} "
                    f"does not name a system.users resource",
                )

    @staticmethod
    def _resolves(ref: str, context: OPNsenseValidationContext) -> bool:
        if context.index is None:
            return False
        try:
            return (
                resolve_xref(ref, "system.users", context.index, current_plugin="system")
                is not None
            )
        except ValueError:
            return False
