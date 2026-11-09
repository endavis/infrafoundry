"""ACME-client list component managers for OPNsense (ADR-0014, #790).

Managers for ``acmeclient.accounts``, ``acmeclient.validations``,
``acmeclient.actions`` and ``acmeclient.certs``, all driven by the table-driven engine
in :mod:`..services.acmeclient`. Follows the OpenVPN instance pattern.

Certificates reference accounts, validations and actions by handle. The runner threads
those three types in as ``sibling_resources`` (and the managed ones as
``managed_sibling_resources``); the manager maps a handle to the sibling's wire name and
then to the live UUID. A reference that is not on the box yet is planned with a warning;
at apply an unresolved one raises :class:`ReferenceValidationError` before any write.

Deletes are limited to the managed set (ADR-0018). Certificates delete first
(``SPLIT_DELETE_PHASE``), before the accounts, validations and actions they use.
Reconfigure is deferred to the shared ``acmeclient_reconfigure`` finalization hook on
apply; destroy reconfigures directly. A 404 at plan means ``os-acme-client`` is not
installed yet: every desired row is an add, with a warning. Secrets are resolved here
and never logged.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, ClassVar

from infrafoundry.core.exceptions import APIError, InfraFoundryError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.acmeclient import (
    ACCOUNTS,
    ACTIONS,
    CERTS,
    LIST_SERVICES,
    REF_SERVICES,
    VALIDATIONS,
    AcmeAccountsService,
    AcmeActionsService,
    AcmeCertsService,
    AcmeItemConfig,
    AcmeListService,
    AcmeValidationsService,
    Diff,
    ListSpec,
    LiveAcmeItem,
    assign_migrate_handles,
    changed_fields,
    compute_diff,
    configs_from_resources,
    stale_provider_fields,
    wire_name_of,
)
from ._managed import managed_keys as derive_managed_keys
from ._migrate_names import env_provider_resources, reserved_names
from ._secrets import resolve_resource_secrets
from .acmeclient_settings import PLUGIN_MISSING_WARNING
from .base import BaseComponentManager

logger = logging.getLogger(__name__)

RefUuids = dict[tuple[str, str], str]


class _AcmeListManager(BaseComponentManager):
    """Shared behaviour of the four ACME list managers."""

    SPEC: ClassVar[ListSpec]
    SERVICE: ClassVar[type[AcmeListService]]

    #: Deletes are limited to the rows InfraFoundry applied before (ADR-0018).
    DELETE_SCOPE: ClassVar[str] = "managed_set"

    #: One ``acmeclient/service/reconfigure`` per apply that changed a row or a setting.
    FINALIZATION_HOOK: ClassVar[str] = "acmeclient_reconfigure"

    # -- hooks for subclasses ------------------------------------------------

    def _ref_uuids(
        self,
        service: AcmeListService,
        desired: list[AcmeItemConfig],
        sibling_resources: list[ResourceConfig] | None,
        managed_sibling_resources: list[ResourceConfig] | None,
    ) -> RefUuids:
        """Resolve references to live UUIDs; the list types without references have none."""
        del service, desired, sibling_resources, managed_sibling_resources
        return {}

    def _annotate(self, diff: Diff, service: AcmeListService) -> None:
        """Add type-specific plan warnings."""
        del diff, service

    # -- shared engine ---------------------------------------------------------

    def _parse(self, resources: Sequence[ResourceConfig]) -> list[AcmeItemConfig]:
        return configs_from_resources(self.SPEC, resources)

    def _desired(self, env_name: str, resources: list[ResourceConfig]) -> list[AcmeItemConfig]:
        resolved = resolve_resource_secrets(
            self.config_dir, env_name, resources, self.SPEC.type_name
        )
        return self._parse(resolved)

    @staticmethod
    def _check_passthrough(service: AcmeListService, desired: list[AcmeItemConfig]) -> None:
        wanted = {wire for c in desired for wire in c.extra_wires}
        if not wanted:
            return
        unknown = sorted(wanted - service.template_keys())
        if unknown:
            raise InvalidConfigurationError(
                f"acmeclient {service.SPEC.noun}: the plugin does not know field(s) "
                f"{', '.join(unknown)}"
            )

    def _diff(
        self,
        service: AcmeListService,
        desired: list[AcmeItemConfig],
        *,
        add_only: bool,
        managed_resources: list[ResourceConfig] | None,
        sibling_resources: list[ResourceConfig] | None,
        managed_sibling_resources: list[ResourceConfig] | None,
        tolerate_missing_plugin: bool,
        unresolved: set[str] | None = None,
    ) -> tuple[Diff, RefUuids]:
        spec = self.SPEC
        missing = False
        try:
            live = service.search()
        except APIError as exc:
            if not (tolerate_missing_plugin and exc.status_code == 404):
                raise
            live, missing = [], True
        ref_uuids: RefUuids = {}
        if not missing:
            self._check_passthrough(service, desired)
            ref_uuids = self._ref_uuids(
                service, desired, sibling_resources, managed_sibling_resources
            )
        keys = derive_managed_keys(
            managed_resources,
            self._parse,
            type_name=spec.type_name,
            unresolved=unresolved,
        )
        diff = compute_diff(
            spec,
            desired,
            live,
            add_only=add_only,
            managed_keys=keys,
            ref_uuids=ref_uuids,
        )
        if missing:
            diff.warnings.append(PLUGIN_MISSING_WARNING)
        for want in [*diff.adds, *(w for _, w in diff.updates)]:
            for sub, handle in want.pending_refs(ref_uuids):
                diff.warnings.append(
                    f"acmeclient {spec.noun} '{want.name}': {sub} '{handle}' is not on the "
                    f"box yet; it must be applied first"
                )
        if not missing:
            self._annotate(diff, service)
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
            The diff apply would execute; pending references and a missing plugin are
            warnings.
        """
        service = self.SERVICE.from_environment(env_name, provider_name, self.config_dir)
        diff, _ = self._diff(
            service,
            self._desired(env_name, resources),
            add_only=add_only,
            managed_resources=managed_resources,
            sibling_resources=sibling_resources,
            managed_sibling_resources=managed_sibling_resources,
            tolerate_missing_plugin=True,
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
            Counts, ``resource_outcomes``, ``warnings`` and ``unresolved_managed``.

        Raises:
            ReferenceValidationError: If an added or updated row references something
                not on the box.
        """
        del auto_approve
        service = self.SERVICE.from_environment(env_name, provider_name, self.config_dir)
        unresolved: set[str] = set()
        diff, ref_uuids = self._diff(
            service,
            self._desired(env_name, resources),
            add_only=add_only,
            managed_resources=managed_resources,
            sibling_resources=sibling_resources,
            managed_sibling_resources=managed_sibling_resources,
            tolerate_missing_plugin=False,
            unresolved=unresolved,
        )
        if deletes_only:
            diff.adds = []
            diff.updates = []
            diff.warnings = [w for w in diff.warnings if "is not on the box yet" not in w]

        prefix = f"opnsense_acmeclient_{self.SPEC.noun}"
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
        desired = self._desired(env_name, resources)
        wanted = {c.diff_key for c in desired if not c.lock}
        diff = Diff(deletes=[x for x in service.search() if x.diff_key in wanted])
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
        live = {x.diff_key: x.uuid for x in service.search()}
        spec = self.SPEC
        return {
            r.name: live[wire_name_of(spec, r.name, r.config)]
            for r in resources
            if r.type == spec.type_name and wire_name_of(spec, r.name, r.config) in live
        }

    def _migrate_handles(
        self, service: AcmeListService, env_name: str, provider_name: str
    ) -> tuple[dict[str, list[LiveAcmeItem]], dict[str, dict[str, str]]]:
        """Return every type's live rows and the handles the migrations assign.

        Every acmeclient migrate runs this on the same inputs, so each emits its own
        slice of one assignment that avoids every opnsense name in the environment.
        """
        live: dict[str, list[LiveAcmeItem]] = {}
        for sub, service_cls in LIST_SERVICES.items():
            live[sub] = (
                service.search() if sub == self.SPEC.sub else service_cls(service.client).search()
            )
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

        Handles come from one assignment over all four types that avoids every
        opnsense name already in the environment (#1337).
        """
        service = self.SERVICE.from_environment(env_name, provider_name, self.config_dir)
        live, handles = self._migrate_handles(service, env_name, provider_name)
        sub = self.SPEC.sub
        return service.export_to_yaml(items=live[sub], handles=handles[sub])


class AcmeClientAccountsManager(_AcmeListManager):
    """Manager for ``acmeclient.accounts``."""

    SPEC = ACCOUNTS
    SERVICE = AcmeAccountsService

    def _annotate(self, diff: Diff, service: AcmeListService) -> None:
        del service
        for have, want in diff.updates:
            if {"ca", "email"} & set(changed_fields(have, want)):
                diff.warnings.append(
                    f"acmeclient account '{want.name}': ca or email changes, but the stored "
                    f"account key belongs to the old registration"
                )


class AcmeClientValidationsManager(_AcmeListManager):
    """Manager for ``acmeclient.validations``."""

    SPEC = VALIDATIONS
    SERVICE = AcmeValidationsService

    def _annotate(self, diff: Diff, service: AcmeListService) -> None:
        defaults: dict[str, Any] | None = None
        for have, want in diff.matched:
            service_name = {w: v for w, v, _ in want.fields}.get("dns_service")
            if not service_name:
                continue
            if defaults is None:
                defaults = service.template_item()
            stale = stale_provider_fields(have.raw, service_name, defaults)
            if stale:
                diff.warnings.append(
                    f"acmeclient validation '{want.name}': the box still holds credential "
                    f"fields of another DNS provider: {', '.join(stale)}"
                )


class AcmeClientActionsManager(_AcmeListManager):
    """Manager for ``acmeclient.actions``."""

    SPEC = ACTIONS
    SERVICE = AcmeActionsService


class AcmeClientCertsManager(_AcmeListManager):
    """Manager for ``acmeclient.certs``."""

    SPEC = CERTS
    SERVICE = AcmeCertsService

    #: Types threaded in as ``sibling_resources`` to resolve references.
    SIBLING_RESOURCE_TYPE: ClassVar[tuple[str, ...]] = (
        "acmeclient.accounts",
        "acmeclient.validations",
        "acmeclient.actions",
    )

    #: Certificates are deleted before the accounts, validations and actions they use.
    SPLIT_DELETE_PHASE: ClassVar[bool] = True

    def _ref_uuids(
        self,
        service: AcmeListService,
        desired: list[AcmeItemConfig],
        sibling_resources: list[ResourceConfig] | None,
        managed_sibling_resources: list[ResourceConfig] | None,
    ) -> RefUuids:
        needed: dict[str, set[str]] = {}
        for config in desired:
            for _, ref_sub, ref_handles in config.refs:
                needed.setdefault(ref_sub, set()).update(ref_handles)
        resolved: RefUuids = {}
        for sub, wanted_handles in needed.items():
            ref_service = REF_SERVICES[sub](service.client)
            ref_spec = ref_service.SPEC
            wire_by_handle: dict[str, str] = {}
            for row in [*(managed_sibling_resources or []), *(sibling_resources or [])]:
                if row.type != ref_spec.type_name:
                    continue
                try:
                    parsed = configs_from_resources(ref_spec, [row])
                except (ValueError, InfraFoundryError):
                    continue
                wire_by_handle[row.name] = parsed[0].wire_name
            uuid_by_wire = {x.diff_key: x.uuid for x in ref_service.search()}
            for handle in wanted_handles:
                wire = wire_by_handle.get(handle)
                if wire is not None and wire in uuid_by_wire:
                    resolved[(sub, handle)] = uuid_by_wire[wire]
        return resolved

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the live certificates, with references as handles.

        The handles come from the same ``assign_migrate_handles`` call the accounts,
        validations and actions migrations make, so the emitted references match their
        output and avoid every opnsense name in the environment.
        """
        service = self.SERVICE.from_environment(env_name, provider_name, self.config_dir)
        live, handles = self._migrate_handles(service, env_name, provider_name)
        ref_handles = {sub: handles[sub] for sub in REF_SERVICES}
        return service.export_to_yaml(
            ref_handles, items=live[self.SPEC.sub], handles=handles[self.SPEC.sub]
        )
