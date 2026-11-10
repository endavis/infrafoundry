"""OpenVPN static-key component manager for OPNsense (ADR-0014, #1319).

Manages ``openvpn.static_keys`` through
:class:`~..services.openvpn_static_keys.OpenVpnStaticKeyService`. Deletes use the
managed-set scope (ADR-0018). A managed key that a live instance of any role still
references through ``tls_key`` is never deleted: it is kept, warned about and
reported as unresolved so it stays managed (the ``trust.cas`` in-use pattern).

Static keys do not split the delete phase: they depend on no other table type. The
runner deletes instances first (they split), then runs this manager's forward pass.
Reconfigure is deferred to the shared ``openvpn_reconfigure`` finalization hook on
apply; destroy reconfigures directly. ``key`` is a ``secret://`` URI resolved here
and never logged.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.openvpn_instances import OpenVpnInstanceService, flatten_option
from ..services.openvpn_static_keys import (
    Diff,
    LiveStaticKey,
    OpenVpnStaticKeyConfig,
    OpenVpnStaticKeyService,
    compute_diff,
    description_of,
    static_key_configs_from_resources,
)
from ._managed import managed_keys as derive_managed_keys
from ._secrets import resolve_resource_secrets
from .base import BaseComponentManager

logger = logging.getLogger(__name__)

_TYPE = "openvpn.static_keys"


class OpenVpnStaticKeyManager(BaseComponentManager):
    """Manager for ``openvpn.static_keys`` operations."""

    #: Deletes are limited to the rows InfraFoundry applied before (ADR-0018).
    DELETE_SCOPE: ClassVar[str] = "managed_set"

    #: One ``openvpn/service/reconfigure`` per apply, shared with the instances.
    FINALIZATION_HOOK: ClassVar[str] = "openvpn_reconfigure"

    def _desired(
        self, env_name: str, resources: list[ResourceConfig]
    ) -> list[OpenVpnStaticKeyConfig]:
        resolved = resolve_resource_secrets(self.config_dir, env_name, resources, _TYPE)
        return static_key_configs_from_resources(resolved, require_key=True)

    @staticmethod
    def _in_use_uuids(service: OpenVpnStaticKeyService, uuids: set[str]) -> set[str]:
        """Return the subset of ``uuids`` a live instance (any role) references."""
        referenced = {
            flatten_option(instance.raw.get("tls_key"))
            for instance in OpenVpnInstanceService(service.client).search()
        }
        return uuids & referenced

    def _diff(
        self,
        service: OpenVpnStaticKeyService,
        desired: list[OpenVpnStaticKeyConfig],
        *,
        add_only: bool,
        managed_resources: list[ResourceConfig] | None,
        unresolved: set[str] | None = None,
    ) -> Diff:
        keys = derive_managed_keys(
            managed_resources,
            lambda rows: static_key_configs_from_resources(rows, require_key=False),
            type_name=_TYPE,
            unresolved=unresolved,
        )
        live = service.search()
        diff = compute_diff(desired, live, add_only=add_only, managed_keys=keys)
        if not diff.deletes:
            return diff
        # The in-use guard needs an instance search; run it only when deleting.
        in_use = self._in_use_uuids(service, {d.uuid for d in diff.deletes})
        if in_use:
            diff = compute_diff(
                desired, live, add_only=add_only, managed_keys=keys, in_use_uuids=in_use
            )
        return diff

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
    ) -> Diff:
        """Compute the diff for the given static keys.

        Args:
            env_name: Active environment name.
            resources: ``openvpn.static_keys`` resources.
            add_only: If True, suppress deletes.
            managed_resources: Rows InfraFoundry applied before (ADR-0018).
            provider_name: Provider identifier.

        Returns:
            The diff apply would execute; an in-use key is in ``blocked``.

        Raises:
            SecretResolutionError: If a ``secret://`` URI cannot be resolved.
            ValueError: If a resolved key is not PEM.
        """
        service = OpenVpnStaticKeyService.from_environment(env_name, provider_name, self.config_dir)
        return self._diff(
            service,
            self._desired(env_name, resources),
            add_only=add_only,
            managed_resources=managed_resources,
        )

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        managed_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Apply the diff: add, update and delete static keys.

        Args:
            env_name: Active environment name.
            resources: ``openvpn.static_keys`` resources.
            auto_approve: Currently a no-op.
            add_only: If True, suppress deletes.
            managed_resources: Rows InfraFoundry applied before (ADR-0018).
            provider_name: Provider identifier.

        Returns:
            Counts, ``resource_outcomes``, ``warnings`` and ``unresolved_managed``.
        """
        del auto_approve
        service = OpenVpnStaticKeyService.from_environment(env_name, provider_name, self.config_dir)
        unresolved: set[str] = set()
        diff = self._diff(
            service,
            self._desired(env_name, resources),
            add_only=add_only,
            managed_resources=managed_resources,
            unresolved=unresolved,
        )
        blocked = {live.description for live, _ in diff.blocked}
        for row in managed_resources or []:
            if description_of(row.name, row.config) in blocked:
                unresolved.add(row.name)

        outcomes = [
            ResourceOutcome(
                address=f"opnsense_openvpn_static_key.{c.name}",
                action="add",
                resource_name=c.name,
            )
            for c in diff.adds
        ]
        outcomes += [
            ResourceOutcome(
                address=f"opnsense_openvpn_static_key.{w.name}",
                action="update",
                resource_name=w.name,
            )
            for _, w in diff.updates
        ]
        outcomes += [
            ResourceOutcome(
                address=f"opnsense_openvpn_static_key.{d.description}",
                action="delete",
                resource_name=d.description,
            )
            for d in diff.deletes
        ]
        counts = service.apply_diff(diff)
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
    ) -> dict[str, Any]:
        """Delete the live static keys named in ``resources``.

        Locked and in-use keys are skipped (warned, counted). The finalization hook
        does not fire on destroy, so this reconfigures directly when something was
        deleted.

        Args:
            env_name: Active environment name.
            resources: ``openvpn.static_keys`` resources to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier.

        Returns:
            ``resources_destroyed``, ``locked_skipped`` and ``warnings``.
        """
        del auto_approve
        service = OpenVpnStaticKeyService.from_environment(env_name, provider_name, self.config_dir)
        desired = self._desired(env_name, resources)
        wanted = {c.diff_key for c in desired if not c.lock}
        live: list[LiveStaticKey] = [x for x in service.search() if x.diff_key in wanted]
        diff = compute_diff([], live)
        if diff.deletes:
            in_use = self._in_use_uuids(service, {d.uuid for d in diff.deletes})
            if in_use:
                diff = compute_diff([], live, in_use_uuids=in_use)
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
    ) -> dict[str, str]:
        """Return ``{resource_name: uuid}`` for live keys matching ``resources``.

        Args:
            env_name: Active environment name.
            resources: ``openvpn.static_keys`` resources.
            provider_name: Provider identifier.
        """
        service = OpenVpnStaticKeyService.from_environment(env_name, provider_name, self.config_dir)
        live = {x.description: x.uuid for x in service.search()}
        return {
            r.name: live[description_of(r.name, r.config)]
            for r in resources
            if r.type == _TYPE and description_of(r.name, r.config) in live
        }
