"""Monit list component managers for OPNsense (ADR-0014, #791).

Managers for ``monit.alerts``, ``monit.tests`` and ``monit.services``, all driven by the
table-driven engine in :mod:`..services.monit`. Follows the ACME-client pattern.

Live state is one call per manager call: ``settings/get`` returns every row. Services
reference tests (``tests``) and other services (``depends``) by handle. The runner threads
``monit.tests`` in as ``sibling_resources`` (and the managed ones as
``managed_sibling_resources``); a handle maps to the sibling's wire name and then to the
live UUID. A reference that is not on the box yet is planned with a warning; at apply an
unresolved one raises :class:`ReferenceValidationError` before any write, except a
``depends`` target that the same apply adds (services are added dependencies first).

Deletes are limited to the managed set (ADR-0018). Services delete first
(``SPLIT_DELETE_PHASE``), before the tests they use, dependents before the services they
depend on. A delete that a surviving live row still references (a test used by a service,
a service another service depends on) is *blocked*: the row is kept with a warning, its
name stays managed and the next apply removes it once the reference is gone.

Reconfigure is deferred to the shared ``monit_reconfigure`` finalization hook on apply;
destroy reconfigures directly.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, ClassVar

from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.monit import (
    ALERTS,
    LIST_SERVICES,
    SERVICES,
    TESTS,
    Diff,
    LiveMonitItem,
    MonitAlertsService,
    MonitItemConfig,
    MonitListService,
    MonitListSpec,
    MonitServicesService,
    MonitTestsService,
    assign_migrate_handles,
    compute_diff,
    configs_from_resources,
    live_items,
    references_to,
    wire_name_of,
)
from ._managed import managed_keys as derive_managed_keys
from ._migrate_names import env_provider_resources, reserved_names
from .base import BaseComponentManager

logger = logging.getLogger(__name__)

RefUuids = dict[tuple[str, str], str]

_PENDING = "is not on the box yet"


class _MonitListManager(BaseComponentManager):
    """Shared behaviour of the three monit list managers."""

    SPEC: ClassVar[MonitListSpec]
    SERVICE: ClassVar[type[MonitListService]]

    #: Deletes are limited to the rows InfraFoundry applied before (ADR-0018).
    DELETE_SCOPE: ClassVar[str] = "managed_set"

    #: One ``monit/service/reconfigure`` per apply that changed a row or a setting.
    FINALIZATION_HOOK: ClassVar[str] = "monit_reconfigure"

    # -- hooks for subclasses ------------------------------------------------

    def _ref_uuids(
        self,
        model: dict[str, Any],
        desired: list[MonitItemConfig],
        managed_resources: list[ResourceConfig] | None,
        sibling_resources: list[ResourceConfig] | None,
        managed_sibling_resources: list[ResourceConfig] | None,
    ) -> RefUuids:
        """Resolve references to live UUIDs; the list types without references have none."""
        del model, desired, managed_resources, sibling_resources, managed_sibling_resources
        return {}

    def _block_deletes(self, diff: Diff, model: dict[str, Any], ref_uuids: RefUuids) -> None:
        """Move deletes that a surviving row still references to ``diff.blocked``."""
        del diff, model, ref_uuids

    # -- shared engine ---------------------------------------------------------

    def _parse(self, resources: Sequence[ResourceConfig]) -> list[MonitItemConfig]:
        return configs_from_resources(self.SPEC, resources)

    def _desired(self, resources: list[ResourceConfig]) -> list[MonitItemConfig]:
        return self._parse(resources)

    def _block(self, diff: Diff, live: LiveMonitItem, reason: str) -> None:
        diff.deletes.remove(live)
        diff.blocked.append((live, reason))
        diff.warnings.append(f"monit {self.SPEC.noun} '{live.name}' is kept: {reason}")

    def _diff(
        self,
        service: MonitListService,
        desired: list[MonitItemConfig],
        *,
        add_only: bool,
        managed_resources: list[ResourceConfig] | None,
        sibling_resources: list[ResourceConfig] | None,
        managed_sibling_resources: list[ResourceConfig] | None,
        unresolved: set[str] | None = None,
    ) -> tuple[Diff, RefUuids]:
        spec = self.SPEC
        model = service.get_model()
        live = live_items(model, spec)
        ref_uuids = self._ref_uuids(
            model, desired, managed_resources, sibling_resources, managed_sibling_resources
        )
        keys = derive_managed_keys(
            managed_resources, self._parse, type_name=spec.type_name, unresolved=unresolved
        )
        diff = compute_diff(
            spec, desired, live, add_only=add_only, managed_keys=keys, ref_uuids=ref_uuids
        )
        in_apply = {c.name for c in diff.adds}
        for want in [*diff.adds, *(w for _, w in diff.updates)]:
            for sub, handle in want.pending_refs(ref_uuids):
                if sub == spec.sub and handle in in_apply:
                    continue
                diff.warnings.append(
                    f"monit {spec.noun} '{want.name}': {sub} '{handle}' {_PENDING}; "
                    f"it must be applied first"
                )
        self._block_deletes(diff, model, ref_uuids)
        return diff, ref_uuids

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: list[ResourceConfig] | None = None,
        managed_sibling_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
        sibling_resources: list[ResourceConfig] | None = None,
    ) -> Diff:
        """Compute the diff for the given rows.

        Args:
            env_name: Active environment name.
            resources: Resources of this manager's type.
            add_only: If True, suppress deletes.
            managed_resources: Rows InfraFoundry applied before (ADR-0018).
            managed_sibling_resources: Managed rows of the sibling types.
            provider_name: Provider identifier.
            sibling_resources: Sibling resources from YAML.

        Returns:
            The diff apply would execute; pending references and kept rows are warnings.
        """
        service = self.SERVICE.from_environment(env_name, provider_name, self.config_dir)
        diff, _ = self._diff(
            service,
            self._desired(resources),
            add_only=add_only,
            managed_resources=managed_resources,
            sibling_resources=sibling_resources,
            managed_sibling_resources=managed_sibling_resources,
        )
        return diff

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        deletes_only: bool = False,
        managed_resources: list[ResourceConfig] | None = None,
        managed_sibling_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
        sibling_resources: list[ResourceConfig] | None = None,
    ) -> dict[str, Any]:
        """Apply the diff: add, update and delete rows.

        Args:
            env_name: Active environment name.
            resources: Resources of this manager's type.
            auto_approve: Currently a no-op.
            add_only: If True, suppress deletes.
            deletes_only: If True, only delete (the runner's delete phase).
            managed_resources: Rows InfraFoundry applied before (ADR-0018).
            managed_sibling_resources: Managed rows of the sibling types.
            provider_name: Provider identifier.
            sibling_resources: Sibling resources from YAML.

        Returns:
            Counts, ``resource_outcomes``, ``warnings`` and ``unresolved_managed`` (which
            includes the managed rows whose delete was blocked).

        Raises:
            ReferenceValidationError: If an added or updated row references something
                not on the box.
        """
        del auto_approve
        service = self.SERVICE.from_environment(env_name, provider_name, self.config_dir)
        unresolved: set[str] = set()
        diff, ref_uuids = self._diff(
            service,
            self._desired(resources),
            add_only=add_only,
            managed_resources=managed_resources,
            sibling_resources=sibling_resources,
            managed_sibling_resources=managed_sibling_resources,
            unresolved=unresolved,
        )
        if deletes_only:
            diff.adds = []
            diff.updates = []
            diff.warnings = [w for w in diff.warnings if _PENDING not in w]
        blocked = {live.name for live, _ in diff.blocked}
        for row in managed_resources or []:
            if wire_name_of(self.SPEC, row.name, row.config) in blocked:
                unresolved.add(row.name)

        prefix = f"opnsense_monit_{self.SPEC.noun}"
        outcomes = [
            ResourceOutcome(address=f"{prefix}.{c.name}", action="add", resource_name=c.name)
            for c in diff.adds
        ]
        outcomes += [
            ResourceOutcome(address=f"{prefix}.{w.name}", action="update", resource_name=w.name)
            for _, w in diff.updates
        ]
        outcomes += [
            ResourceOutcome(address=f"{prefix}.{d.name}", action="delete", resource_name=d.name)
            for d in diff.deletes
        ]
        counts = service.apply_diff(diff, ref_uuids)
        return {
            "success": True,
            "resources_created": counts["created"],
            "resources_updated": counts["updated"],
            "resources_deleted": counts["deleted"],
            "resource_outcomes": outcomes,
            "unresolved_managed": sorted(unresolved),
            "warnings": list(diff.warnings),
        }

    def destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        provider_name: str = "opnsense",
        sibling_resources: list[ResourceConfig] | None = None,
    ) -> dict[str, Any]:
        """Delete the live rows named in ``resources``.

        Locked entries are skipped and counted. The finalization hook does not fire on
        destroy, so this reconfigures directly when something was deleted.

        Args:
            env_name: Active environment name.
            resources: Resources to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier.
            sibling_resources: Accepted for the runner; unused.

        Returns:
            ``resources_destroyed``, ``locked_skipped`` and ``warnings``.
        """
        del auto_approve, sibling_resources
        service = self.SERVICE.from_environment(env_name, provider_name, self.config_dir)
        desired = self._desired(resources)
        wanted = {c.diff_key for c in desired if not c.lock}
        diff = Diff(deletes=[x for x in service.live() if x.diff_key in wanted])
        counts = service.apply_diff(diff)
        if counts["deleted"]:
            service.reconfigure()
        return {
            "success": True,
            "resources_destroyed": counts["deleted"],
            "locked_skipped": sum(1 for c in desired if c.lock),
            "warnings": list(diff.warnings),
        }

    def get_resource_ids(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        provider_name: str = "opnsense",
        sibling_resources: list[ResourceConfig] | None = None,
    ) -> dict[str, str]:
        """Return ``{resource_name: uuid}`` for live rows matching ``resources``.

        Args:
            env_name: Active environment name.
            resources: Resources of this manager's type.
            provider_name: Provider identifier.
            sibling_resources: Accepted for the runner; unused.
        """
        del sibling_resources
        service = self.SERVICE.from_environment(env_name, provider_name, self.config_dir)
        live = {x.diff_key: x.uuid for x in service.live()}
        spec = self.SPEC
        return {
            r.name: live[wire_name_of(spec, r.name, r.config)]
            for r in resources
            if r.type == spec.type_name and wire_name_of(spec, r.name, r.config) in live
        }

    def _migrate_handles(
        self, service: MonitListService, env_name: str, provider_name: str
    ) -> tuple[dict[str, list[LiveMonitItem]], dict[str, dict[str, str]]]:
        """Return every type's live rows and the handles the migrations assign.

        Every monit migrate runs this on the same inputs, so each emits its own slice of
        one assignment that avoids every opnsense name in the environment.
        """
        model = service.get_model()
        live = {sub: live_items(model, cls.SPEC) for sub, cls in LIST_SERVICES.items()}
        resources = env_provider_resources(self.config_dir, env_name, provider_name)
        existing: dict[str, dict[str, str]] = {sub: {} for sub in LIST_SERVICES}
        for sub, service_cls in LIST_SERVICES.items():
            spec = service_cls.SPEC
            for r in resources:
                wire = wire_name_of(spec, r.name, r.config) if r.type == spec.type_name else ""
                if wire:
                    existing[sub].setdefault(wire, r.name)
        handles = assign_migrate_handles(
            live, existing, reserved_names(resources, exclude_types=())
        )
        return live, handles

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the live rows to InfraFoundry YAML.

        Handles come from one assignment over all three types that avoids every opnsense
        name already in the environment.
        """
        service = self.SERVICE.from_environment(env_name, provider_name, self.config_dir)
        live, handles = self._migrate_handles(service, env_name, provider_name)
        sub = self.SPEC.sub
        return service.export_to_yaml(
            {s: handles[s] for s in ("tests", "services")}, items=live[sub], handles=handles[sub]
        )


class MonitAlertsManager(_MonitListManager):
    """Manager for ``monit.alerts``."""

    SPEC = ALERTS
    SERVICE = MonitAlertsService


class MonitTestsManager(_MonitListManager):
    """Manager for ``monit.tests``."""

    SPEC = TESTS
    SERVICE = MonitTestsService

    def _block_deletes(self, diff: Diff, model: dict[str, Any], ref_uuids: RefUuids) -> None:
        del ref_uuids
        users = references_to(model, "tests")
        for live in list(diff.deletes):
            names = sorted(s.name for s in users.get(live.uuid, []))
            if names:
                self._block(diff, live, f"still used by service(s) {', '.join(names)}")


class MonitServicesManager(_MonitListManager):
    """Manager for ``monit.services``."""

    SPEC = SERVICES
    SERVICE = MonitServicesService

    #: Types threaded in as ``sibling_resources`` to resolve ``tests`` references.
    SIBLING_RESOURCE_TYPE: ClassVar[tuple[str, ...]] = ("monit.tests",)

    #: Services are deleted before the tests they use.
    SPLIT_DELETE_PHASE: ClassVar[bool] = True

    @staticmethod
    def _wire_by_handle(spec: MonitListSpec, rows: Sequence[ResourceConfig]) -> dict[str, str]:
        wires: dict[str, str] = {}
        for row in rows:
            if row.type != spec.type_name:
                continue
            try:
                parsed = configs_from_resources(spec, [row])
            except (ValueError, InfraFoundryError):
                continue
            wires[row.name] = parsed[0].wire_name
        return wires

    def _ref_uuids(
        self,
        model: dict[str, Any],
        desired: list[MonitItemConfig],
        managed_resources: list[ResourceConfig] | None,
        sibling_resources: list[ResourceConfig] | None,
        managed_sibling_resources: list[ResourceConfig] | None,
    ) -> RefUuids:
        needed: dict[str, set[str]] = {}
        for config in desired:
            for _, ref_sub, ref_handles in config.refs:
                needed.setdefault(ref_sub, set()).update(ref_handles)
        resolved: RefUuids = {}
        if "tests" in needed:
            wires = self._wire_by_handle(
                TESTS, [*(managed_sibling_resources or []), *(sibling_resources or [])]
            )
            uuids = {x.diff_key: x.uuid for x in live_items(model, TESTS)}
            for handle in needed["tests"]:
                if wires.get(handle) in uuids:
                    resolved[("tests", handle)] = uuids[wires[handle]]
        if "services" in needed:
            wires = {c.name: c.wire_name for c in desired}
            for handle, wire in self._wire_by_handle(SERVICES, managed_resources or []).items():
                wires.setdefault(handle, wire)
            uuids = {x.diff_key: x.uuid for x in live_items(model, SERVICES)}
            for handle in needed["services"]:
                if wires.get(handle) in uuids:
                    resolved[("services", handle)] = uuids[wires[handle]]
        return resolved

    def _block_deletes(self, diff: Diff, model: dict[str, Any], ref_uuids: RefUuids) -> None:
        deleting = {d.uuid for d in diff.deletes}
        dependents = references_to(model, "depends")
        # A declared service that depends on a row about to be deleted keeps it too.
        declared = [*diff.adds, *(w for _, w in diff.matched)]
        wanted: dict[str, list[str]] = {}
        for config in declared:
            for _, sub, handles in config.refs:
                for handle in handles:
                    if sub == "services" and ("services", handle) in ref_uuids:
                        wanted.setdefault(ref_uuids[("services", handle)], []).append(config.name)
        for live in list(diff.deletes):
            names = sorted(
                {s.name for s in dependents.get(live.uuid, []) if s.uuid not in deleting}
                | set(wanted.get(live.uuid, []))
            )
            if names:
                self._block(diff, live, f"still a dependency of service(s) {', '.join(names)}")
