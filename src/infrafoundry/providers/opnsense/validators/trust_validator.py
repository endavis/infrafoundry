"""Trust CA and certificate validator for OPNsense (#807).

Plan-time checks for the ``trust.cas`` and ``trust.certs`` types (no live-box access).
``context.resources`` holds both types; ``context.index`` resolves ``ca_ref``.

Messages name the resource and the field, never a field value: ``crt``, ``prv`` and
``csr`` can hold key material.

- Unknown keys (``descr`` hints ``description``; ``refid`` and ``serial`` are
  assigned by the box).
- ``crt`` is required.
- A literal ``prv`` is an ERROR; use a ``secret://`` URI. A literal ``crt`` or ``csr``
  is a WARNING (public material, but better kept in secrets with its key).
- Literal values must have PEM BEGIN/END markers.
- Duplicate descriptions within a type.
- A CA whose description looks AcmeClient-issued is an ERROR: the plugin owns it.
- ``ca_ref`` must name a ``trust.cas`` resource; ``type`` is server, client or combined.
"""

from __future__ import annotations

from typing import Any, override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.services.trust import (
    ALLOWED_CERT_TYPES,
    description_of,
    has_pem_markers,
    is_acme_issued_descr,
)
from infrafoundry.providers.opnsense.validators._xref import resolve_xref
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

_CA_KEYS = frozenset({"description", "crt", "prv", "lock"})
_CERT_KEYS = frozenset({"description", "crt", "prv", "csr", "ca_ref", "type", "lock"})
_HINTS = {
    "descr": "use 'description'",
    "refid": "the box assigns refid; it is not a YAML field",
    "serial": "the box assigns serial; it is not a YAML field",
}
_SECRET_PREFIX = "secret://"  # nosec B105  # URI scheme, not a password


class TrustValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``trust.cas`` and ``trust.certs`` resources at plan time."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ``ValidationReport`` to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Validate all trust resources.

        Args:
            context: Context whose ``resources`` hold the trust CAs and certificates.
        """
        resources = [r for r in context.resources if r.type in {"trust.cas", "trust.certs"}]
        if not resources:
            return
        for type_name in ("trust.cas", "trust.certs"):
            self._check_duplicates([r for r in resources if r.type == type_name], type_name)
        for resource in resources:
            self._validate_one(resource, context)

    def _fail(
        self, check: str, message: str, level: ValidationLevel = ValidationLevel.ERROR
    ) -> None:
        self.report.add_check(check_name=check, passed=False, message=message, level=level)

    def _check_duplicates(self, resources: list[ResourceConfig], type_name: str) -> None:
        seen: set[str] = set()
        dupes: set[str] = set()
        for r in resources:
            description = description_of(r.name, r.config)
            (dupes if description in seen else seen).add(description)
        if dupes:
            self._fail(
                f"{type_name}_unique_descriptions",
                f"{type_name} resources share descriptions: {sorted(dupes)!r}. "
                f"The description is the identity on the box; make each unique.",
            )

    def _validate_one(self, resource: ResourceConfig, context: OPNsenseValidationContext) -> None:
        name, config = resource.name, resource.config
        is_ca = resource.type == "trust.cas"
        label = "trust_ca" if is_ca else "trust_cert"
        allowed = _CA_KEYS if is_ca else _CERT_KEYS
        for key in sorted(set(config) - allowed):
            hint = _HINTS.get(key)
            self._fail(
                f"{label}_{name}_unknown_key_{key}",
                f"{label} '{name}' has unknown key '{key}'"
                + (f" ({hint})" if hint else f"; allowed: {sorted(allowed)}"),
            )
        crt = config.get("crt")
        if not isinstance(crt, str) or not crt.strip():
            self._fail(f"{label}_{name}_crt_required", f"{label} '{name}' requires 'crt'")
        for key in ("crt", "prv", "csr"):
            self._check_secret_field(label, name, config, key)
        if is_ca:
            description = description_of(name, config)
            if is_acme_issued_descr(description):
                self._fail(
                    f"{label}_{name}_acme_owned",
                    f"{label} '{name}' description looks issued by the AcmeClient plugin, "
                    f"which owns such CAs; pick another description",
                )
            return
        self._check_type(label, name, config)
        self._check_ca_ref(label, name, config, context)

    def _check_secret_field(self, label: str, name: str, config: dict[str, Any], key: str) -> None:
        value = config.get(key)
        if value is None or value == "":
            return
        if not isinstance(value, str):
            self._fail(f"{label}_{name}_{key}_type", f"{label} '{name}' {key} must be a string")
            return
        if value.startswith(_SECRET_PREFIX):
            return
        if not has_pem_markers(value):
            self._fail(
                f"{label}_{name}_{key}_pem",
                f"{label} '{name}' {key} is neither a secret:// URI nor PEM (no BEGIN/END markers)",
            )
        if key == "prv":
            self._fail(
                f"{label}_{name}_prv_literal",
                f"{label} '{name}' has a literal private key; use a secret:// URI",
            )
        elif key in {"crt", "csr"}:
            self._fail(
                f"{label}_{name}_{key}_literal",
                f"{label} '{name}' has a literal {key}; consider a secret:// URI",
                ValidationLevel.WARNING,
            )

    def _check_type(self, label: str, name: str, config: dict[str, Any]) -> None:
        cert_type = config.get("type")
        if cert_type in (None, ""):
            return
        if cert_type not in ALLOWED_CERT_TYPES:
            self._fail(
                f"{label}_{name}_type",
                f"{label} '{name}' type must be one of {list(ALLOWED_CERT_TYPES)}",
            )

    def _check_ca_ref(
        self, label: str, name: str, config: dict[str, Any], context: OPNsenseValidationContext
    ) -> None:
        ca_ref = config.get("ca_ref")
        if ca_ref in (None, ""):
            return
        if not isinstance(ca_ref, str):
            self._fail(f"{label}_{name}_ca_ref_type", f"{label} '{name}' ca_ref must be a string")
            return
        try:
            found = (
                resolve_xref(ca_ref, "trust.cas", context.index, current_plugin="trust")
                if context.index is not None
                else None
            )
        except ValueError:
            found = None
        if found is None:
            self._fail(
                f"{label}_{name}_ca_ref",
                f"{label} '{name}' ca_ref '{ca_ref}' does not match any trust.cas resource",
            )
