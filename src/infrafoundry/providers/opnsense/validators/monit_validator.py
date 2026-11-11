"""Monit validator for OPNsense (#791).

Plan-time checks for ``monit.settings``, ``monit.alerts``, ``monit.tests`` and
``monit.services`` (no live-box access). Messages name the resource and the field, never a
value: ``password``, ``httpd_password`` and ``mmonit_url`` are secrets.

- Unknown keys are ERRORs. Types, enums and ranges are checked with the services' own
  serializers (an alert event outside the 29 known ones is an ERROR).
- A handle (the resource name) must not contain a ``.``: it would break references.
- Identities (wire name, or the recipient for alerts) are unique within a type.
- Alerts need ``recipient``. Tests need ``condition``; ``action: exec`` without ``path`` is
  a WARNING.
- Services of type ``filesystem``, ``custom``, ``file``, ``fifo`` and ``directory`` need
  ``path`` (ERROR: monit cannot render them without one). ``process`` without ``pidfile`` or
  ``match``, ``host`` without ``address`` and ``network`` without ``address`` or
  ``interface`` get a WARNING; the rules are not probed. A test type is not checked against
  the service type.
- ``tests`` and ``depends`` entries must name a declared resource of the right type, in
  any of the three reference forms. A ``depends`` cycle or self-dependency is an ERROR.
- A literal non-empty secret is a WARNING.
"""

from __future__ import annotations

import re
from typing import Any, override

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.services import monit as svc
from infrafoundry.providers.opnsense.services import monit_settings as settings_svc
from infrafoundry.providers.opnsense.validators._xref import resolve_xref
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

_SECRET_URI = re.compile(r"^secret://[^/]+/.+$")
_SETTINGS = "monit.settings"
_PREFIX = "monit_"


class MonitValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``monit.*`` resources at plan time."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ``ValidationReport`` to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Validate all monit resources.

        Args:
            context: Context whose ``resources`` hold the ``monit.*`` resources; ``index``
                resolves references.
        """
        resources = [r for r in context.resources if r.type.startswith("monit.")]
        if not resources:
            return
        for resource in resources:
            if resource.type == _SETTINGS:
                self._validate_settings(resource)
        for spec in svc.SPECS.values():
            rows = [r for r in resources if r.type == spec.type_name]
            self._check_duplicates(spec, rows)
            for row in rows:
                self._validate_row(spec, row, context)
        self._check_dependency_cycles([r for r in resources if r.type == svc.SERVICES.type_name])

    # -- reporting -------------------------------------------------------------

    def _fail(
        self, check: str, message: str, level: ValidationLevel = ValidationLevel.ERROR
    ) -> None:
        self.report.add_check(check_name=check, passed=False, message=message, level=level)

    def _warn(self, check: str, message: str) -> None:
        self._fail(check, message, ValidationLevel.WARNING)

    # -- settings --------------------------------------------------------------

    def _validate_settings(self, resource: ResourceConfig) -> None:
        config = resource.config
        prefix = f"{_PREFIX}settings"
        for key in sorted(set(config) - set(settings_svc.FIELDS)):
            self._fail(
                f"{prefix}_unknown_key_{key}",
                f"{_SETTINGS} has unknown key '{key}'; allowed: {sorted(settings_svc.FIELDS)}",
            )
        for key in settings_svc.FIELDS:
            if key not in config:
                continue
            try:
                settings_svc.serialize_setting(key, config[key])
            except InvalidConfigurationError as exc:
                self._fail(f"{prefix}_{key}", str(exc))
        for key in settings_svc.SECRET_FIELDS:
            value = config.get(key)
            if value in (None, ""):
                continue
            if not isinstance(value, str) or not _SECRET_URI.match(value):
                self._warn(
                    f"{prefix}_{key}_literal_secret",
                    f"{_SETTINGS} {key} should be a secret:// reference, not a literal value",
                )

    # -- list types ------------------------------------------------------------

    def _check_duplicates(self, spec: svc.MonitListSpec, rows: list[ResourceConfig]) -> None:
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
                f"The wire identity is the key; make each unique.",
            )

    def _validate_row(
        self, spec: svc.MonitListSpec, resource: ResourceConfig, context: OPNsenseValidationContext
    ) -> None:
        name, config = resource.name, resource.config
        label = f"monit {spec.noun} '{name}'"
        prefix = f"{_PREFIX}{spec.noun}_{name}"
        if "." in name:
            self._fail(
                f"{prefix}_handle",
                f"{label}: the name must not contain '.', it is the reference handle",
            )
        for key in sorted(k for k in config if not spec.accepts(k)):
            self._fail(
                f"{prefix}_unknown_key_{key}",
                f"{label} has unknown key '{key}'; allowed: {sorted(spec.allowed_keys)}",
            )
        for key, fspec in spec.fields.items():
            if key not in config:
                continue
            try:
                svc.serialize_field(label, key, fspec, config[key])
            except ValueError as exc:
                self._fail(f"{prefix}_{key}", str(exc))
        if "lock" in config and not isinstance(config["lock"], bool):
            self._fail(f"{prefix}_lock", f"{label} lock must be a boolean")
        identity = config.get(spec.identity_key)
        if identity is not None and not isinstance(identity, str):
            self._fail(
                f"{prefix}_{spec.identity_key}", f"{label} {spec.identity_key} must be a string"
            )
        if spec is svc.ALERTS:
            if not config.get("recipient"):
                self._fail(f"{prefix}_recipient_required", f"{label} requires 'recipient'")
        elif spec is svc.TESTS:
            self._check_test(prefix, label, config)
        else:
            self._check_service(prefix, label, config, context)

    def _check_test(self, prefix: str, label: str, config: dict[str, Any]) -> None:
        if not config.get("condition"):
            self._fail(f"{prefix}_condition_required", f"{label} requires 'condition'")
        if config.get("action") == "exec" and not config.get("path"):
            self._warn(f"{prefix}_exec_path", f"{label} uses action 'exec' without a 'path'")

    def _check_service(
        self, prefix: str, label: str, config: dict[str, Any], context: OPNsenseValidationContext
    ) -> None:
        kind = config.get("type")
        if kind in svc.PATH_REQUIRED_TYPES and not config.get("path"):
            self._fail(f"{prefix}_path_required", f"{label} with type '{kind}' requires 'path'")
        elif kind == "process" and not (config.get("pidfile") or config.get("match")):
            self._warn(
                f"{prefix}_process_target",
                f"{label} with type 'process' sets neither 'pidfile' nor 'match'",
            )
        elif kind == "host" and not config.get("address"):
            self._warn(f"{prefix}_host_address", f"{label} with type 'host' sets no 'address'")
        elif kind == "network" and not (config.get("address") or config.get("interface")):
            self._warn(
                f"{prefix}_network_target",
                f"{label} with type 'network' sets neither 'address' nor 'interface'",
            )
        for key, fspec in svc.SERVICES.fields.items():
            if fspec.kind != svc.REFSET or key not in config:
                continue
            entries = config[key]
            if not isinstance(entries, list):
                continue
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
        expected = f"monit.{sub}"
        try:
            svc.ref_handle(value, sub)
            found = (
                resolve_xref(value, expected, context.index, current_plugin="monit")
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

    def _check_dependency_cycles(self, rows: list[ResourceConfig]) -> None:
        graph: dict[str, list[str]] = {}
        for row in rows:
            handles: list[str] = []
            depends = row.config.get("depends")
            for entry in depends if isinstance(depends, list) else []:
                if not isinstance(entry, str) or not entry:
                    continue
                try:
                    handles.append(svc.ref_handle(entry, "services"))
                except InvalidConfigurationError:
                    continue
            graph[row.name] = handles
        for name, handles in sorted(graph.items()):
            if name in handles:
                self._fail(
                    f"{_PREFIX}service_{name}_depends_self",
                    f"monit service '{name}' depends on itself",
                )
        reported: set[str] = set()
        for start in sorted(graph):
            if start in reported:
                continue
            cycle = self._find_cycle(graph, start)
            if cycle:
                reported.update(cycle)
                self._fail(
                    f"{_PREFIX}service_{start}_depends_cycle",
                    f"monit services form a depends cycle: {' -> '.join(cycle)}",
                )

    @staticmethod
    def _find_cycle(graph: dict[str, list[str]], start: str) -> list[str]:
        """Return a cycle (length >= 2) reachable from ``start``, or ``[]``."""
        path: list[str] = []
        done: set[str] = set()

        def visit(node: str) -> list[str]:
            if node in path:
                return [*path[path.index(node) :], node]
            if node in done or node not in graph:
                return []
            path.append(node)
            for nxt in graph[node]:
                if nxt == node:
                    continue
                found = visit(nxt)
                if found:
                    return found
            path.pop()
            done.add(node)
            return []

        return visit(start)
