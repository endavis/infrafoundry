"""ACME-client validator for OPNsense (#790).

Plan-time checks for ``acmeclient.settings``, ``.accounts``, ``.validations``,
``.actions`` and ``.certs`` (no live-box access). Messages name the resource and the
field, never a value: several fields are secrets.

- Unknown keys are ERRORs; keys the box assigns (``id``, ``key``, ``statusCode`` ...)
  carry a hint. ``UpdateCron`` is plugin-managed and not a key.
- Types, enums and ranges are checked with the services' own rules.
- A handle (the resource name) must not contain a ``.``: it would break references.
- Identities (wire name, or the CN for certs) are unique within a type.
- Accounts need ``email`` and ``ca``; ``ca: custom`` needs ``custom_ca``. A repeated
  ``(ca, email)`` is a WARNING.
- Certs need ``common_name``, ``account`` and ``validation``; each reference, and each
  ``restart_actions`` entry, must name a declared resource of the right type.
- A ``dns01`` validation needs ``dns_service``. A ``dns_<provider>_*`` field of another
  provider is an ERROR; a missing required field is an ERROR for providers in a curated
  map (``dns_cf``) and the other providers get a WARNING that it is not checked. A
  non-``dns01`` method that sets such fields gets a WARNING.
- Action pass-through fields must fit the action ``type``.
- A literal secret is a WARNING.
- ``acmeclient.settings`` with ``enabled: false`` while certs are declared: WARNING.
"""

from __future__ import annotations

import re
from typing import Any, override

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.services import acmeclient as svc
from infrafoundry.providers.opnsense.services import acmeclient_settings as settings_svc
from infrafoundry.providers.opnsense.validators._xref import resolve_xref
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

_SECRET_URI = re.compile(r"^secret://[^/]+/.+$")
_SETTINGS = "acmeclient.settings"
_PREFIX = "acmeclient_"


class AcmeClientValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``acmeclient.*`` resources at plan time."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ``ValidationReport`` to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Validate all ACME-client resources.

        Args:
            context: Context whose ``resources`` hold the ``acmeclient.*`` resources;
                ``index`` resolves references.
        """
        resources = [r for r in context.resources if r.type.startswith("acmeclient.")]
        if not resources:
            return
        for resource in resources:
            if resource.type == _SETTINGS:
                self._validate_settings(resource, resources)
        for spec in svc.SPECS.values():
            rows = [r for r in resources if r.type == spec.type_name]
            self._check_duplicates(spec, rows)
            if spec is svc.ACCOUNTS:
                self._check_duplicate_accounts(rows)
            for row in rows:
                self._validate_row(spec, row, context)

    # -- reporting -------------------------------------------------------------

    def _fail(
        self, check: str, message: str, level: ValidationLevel = ValidationLevel.ERROR
    ) -> None:
        self.report.add_check(check_name=check, passed=False, message=message, level=level)

    def _warn(self, check: str, message: str) -> None:
        self._fail(check, message, ValidationLevel.WARNING)

    # -- settings --------------------------------------------------------------

    def _validate_settings(self, resource: ResourceConfig, resources: list[ResourceConfig]) -> None:
        config = resource.config
        label = _SETTINGS
        prefix = f"{_PREFIX}settings"
        for key in sorted(set(config) - set(settings_svc.FIELD_MAP)):
            hint = " (the plugin manages it)" if key in {"update_cron", "UpdateCron"} else ""
            self._fail(
                f"{prefix}_unknown_key_{key}",
                f"{label} has unknown key '{key}'{hint}; allowed: {sorted(settings_svc.FIELD_MAP)}",
            )
        for key in settings_svc.FIELD_MAP:
            if key not in config:
                continue
            try:
                settings_svc.serialize_setting(key, config[key])
            except InvalidConfigurationError as exc:
                self._fail(f"{prefix}_{key}", str(exc))
        has_certs = any(r.type == svc.CERTS.type_name for r in resources)
        if has_certs and config.get("enabled") is False:
            self._warn(
                f"{prefix}_disabled_with_certs",
                f"{label} sets enabled: false while acmeclient.certs are declared; "
                f"the plugin will not issue them",
            )

    # -- list types ------------------------------------------------------------

    def _check_duplicates(self, spec: svc.ListSpec, rows: list[ResourceConfig]) -> None:
        seen: set[str] = set()
        dupes: set[str] = set()
        for r in rows:
            identity = svc.wire_name_of(spec, r.name, r.config)
            if not identity:
                continue
            (dupes if identity in seen else seen).add(identity)
        if dupes:
            self._fail(
                f"{_PREFIX}{spec.sub}_unique_identity",
                f"{spec.type_name} resources share names on the box: {sorted(dupes)!r}. "
                f"The wire name is the identity; make each unique.",
            )

    def _check_duplicate_accounts(self, rows: list[ResourceConfig]) -> None:
        seen: set[tuple[Any, Any]] = set()
        for r in rows:
            ca, email = r.config.get("ca"), r.config.get("email")
            if not (isinstance(ca, str) and isinstance(email, str)):
                continue
            if (ca, email) in seen:
                self._warn(
                    f"{_PREFIX}account_{r.name}_duplicate_registration",
                    f"acmeclient account '{r.name}' repeats a (ca, email) pair of another account",
                )
            seen.add((ca, email))

    def _validate_row(
        self, spec: svc.ListSpec, resource: ResourceConfig, context: OPNsenseValidationContext
    ) -> None:
        name, config = resource.name, resource.config
        label = f"acmeclient {spec.noun} '{name}'"
        prefix = f"{_PREFIX}{spec.noun}_{name}"
        if "." in name:
            self._fail(
                f"{prefix}_handle",
                f"{label}: the name must not contain '.', it is the reference handle",
            )
        self._check_keys(spec, prefix, label, config)
        self._check_fields(spec, prefix, label, config)
        self._check_secrets(spec, prefix, label, config)
        if "lock" in config and not isinstance(config["lock"], bool):
            self._fail(f"{prefix}_lock", f"{label} lock must be a boolean")
        identity_key = spec.identity_key or "display_name"
        if identity_key in config and not isinstance(config[identity_key], str):
            self._fail(f"{prefix}_{identity_key}", f"{label} {identity_key} must be a string")
        if spec is svc.ACCOUNTS:
            self._check_account(prefix, label, config)
        elif spec is svc.VALIDATIONS:
            self._check_validation(prefix, label, config)
        elif spec is svc.ACTIONS:
            self._check_action(prefix, label, config)
        else:
            self._check_cert(prefix, label, config, context)

    def _check_keys(
        self, spec: svc.ListSpec, prefix: str, label: str, config: dict[str, Any]
    ) -> None:
        for key in sorted(k for k in config if not spec.accepts(k)):
            if key in svc.SERVER_MANAGED:
                message = f"{label} must not set '{key}': the box assigns it"
            elif spec.identity_key and key == "display_name":
                message = f"{label} has no 'display_name'; use '{spec.identity_key}'"
            else:
                message = f"{label} has unknown key '{key}'; allowed: {sorted(spec.allowed_keys)}"
            self._fail(f"{prefix}_unknown_key_{key}", message)

    def _check_fields(
        self, spec: svc.ListSpec, prefix: str, label: str, config: dict[str, Any]
    ) -> None:
        for key, fspec in spec.fields.items():
            if key not in config:
                continue
            try:
                svc.serialize_value(label, key, fspec, config[key])
            except ValueError as exc:
                self._fail(f"{prefix}_{key}", str(exc))
        for key, value in config.items():
            if key in spec.fields or key in spec.meta_keys or not spec.accepts(key):
                continue
            try:
                svc._serialize_passthrough(label, key, value)
            except ValueError as exc:
                self._fail(f"{prefix}_{key}", str(exc))

    def _check_secrets(
        self, spec: svc.ListSpec, prefix: str, label: str, config: dict[str, Any]
    ) -> None:
        for key, value in config.items():
            if not spec.is_secret(key) or value in (None, ""):
                continue
            if not isinstance(value, str) or not _SECRET_URI.match(value):
                self._warn(
                    f"{prefix}_{key}_literal_secret",
                    f"{label} {key} should be a secret:// reference, not a literal value",
                )

    def _check_account(self, prefix: str, label: str, config: dict[str, Any]) -> None:
        if not config.get("email"):
            self._fail(f"{prefix}_email_required", f"{label} requires 'email'")
        if not config.get("ca"):
            self._fail(f"{prefix}_ca_required", f"{label} requires 'ca'")
        if config.get("ca") == "custom" and not config.get("custom_ca"):
            self._fail(
                f"{prefix}_custom_ca_required", f"{label} with ca 'custom' requires 'custom_ca'"
            )

    def _check_validation(self, prefix: str, label: str, config: dict[str, Any]) -> None:
        method = config.get("method")
        if not method:
            self._fail(f"{prefix}_method_required", f"{label} requires 'method'")
            return
        dns_keys = sorted(k for k in config if svc.VALIDATIONS.passthrough(k))
        if method != "dns01":
            if dns_keys:
                self._warn(
                    f"{prefix}_dns_fields_ignored",
                    f"{label} uses method '{method}', which ignores the dns_* credential "
                    f"fields: {', '.join(dns_keys)}",
                )
            return
        service = config.get("dns_service")
        if not isinstance(service, str) or not service:
            self._fail(
                f"{prefix}_dns_service_required",
                f"{label} with method dns01 requires 'dns_service'",
            )
            return
        foreign = [k for k in dns_keys if not k.startswith(f"{service}_")]
        if foreign:
            self._fail(
                f"{prefix}_dns_foreign_fields",
                f"{label} sets credential field(s) of another DNS provider than "
                f"'{service}': {', '.join(foreign)}",
            )
        required = svc.REQUIRED_DNS_FIELDS.get(service)
        if required is None:
            self._warn(
                f"{prefix}_dns_unchecked",
                f"{label}: required credential fields of '{service}' are not checked",
            )
            return
        for key in required:
            if not config.get(key):
                self._fail(f"{prefix}_{key}_required", f"{label} with '{service}' requires '{key}'")

    def _check_action(self, prefix: str, label: str, config: dict[str, Any]) -> None:
        action_type = config.get("type")
        if not action_type:
            self._fail(f"{prefix}_type_required", f"{label} requires 'type'")
            return
        allowed = svc.ACTION_TYPE_PREFIXES.get(str(action_type))
        if allowed is None:
            return  # the enum check already reported it
        for key in sorted(k for k in config if svc.ACTIONS.passthrough(k)):
            if not key.startswith(allowed):
                self._fail(
                    f"{prefix}_{key}_type",
                    f"{label}: field '{key}' does not belong to action type '{action_type}'",
                )

    def _check_cert(
        self, prefix: str, label: str, config: dict[str, Any], context: OPNsenseValidationContext
    ) -> None:
        if not config.get("common_name"):
            self._fail(f"{prefix}_common_name_required", f"{label} requires 'common_name'")
        for key in ("account", "validation"):
            if config.get(key) in (None, ""):
                self._fail(f"{prefix}_{key}_required", f"{label} requires '{key}'")
        for key, fspec in svc.CERTS.fields.items():
            if fspec.kind not in {svc.REF, svc.REFSET} or key not in config:
                continue
            value = config[key]
            entries = value if isinstance(value, list) else [value]
            for entry in entries:
                if isinstance(entry, str) and entry:
                    self._check_ref(prefix, label, key, entry, fspec.ref_sub, context)

    def _check_ref(
        self,
        prefix: str,
        label: str,
        key: str,
        value: str,
        sub: str,
        context: OPNsenseValidationContext,
    ) -> None:
        expected = f"acmeclient.{sub}"
        try:
            svc.ref_handle(value, sub)
            found = (
                resolve_xref(value, expected, context.index, current_plugin="acmeclient")
                if context.index is not None
                else None
            )
        except (ValueError, InvalidConfigurationError):
            found = None
        if found is None or found.type != expected:
            self._fail(
                f"{prefix}_{key}_ref",
                f"{label} {key} '{value}' does not match any {expected} resource",
            )
