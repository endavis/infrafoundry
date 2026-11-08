"""OpenVPN client-instance component manager for OPNsense (ADR-0014, #808).

Manages ``openvpn.instances`` (modern MVC client instances). Follows the trust
certificate pattern: the runner threads the ``trust.cas`` resources in as
``sibling_resources`` (and the managed ones as ``managed_sibling_resources``), and
``ca_ref`` is resolved to the live CA ``refid``. A ``ca_ref`` whose CA is not on the
box yet is planned with a warning; at apply an unresolved ``ca_ref`` raises
:class:`ReferenceValidationError` before any write.

Deletes run in the runner's delete phase (``SPLIT_DELETE_PHASE``), before CAs are
touched. Reconfigure is deferred to the ``openvpn_reconfigure`` finalization hook on
apply; destroy reconfigures directly. Secrets are resolved here and never logged.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.openvpn_instances import (
    Diff,
    OpenVpnInstanceConfig,
    OpenVpnInstanceService,
    compute_diff,
    description_of,
    openvpn_instance_configs_from_resources,
)
from ..services.trust import TrustService, ca_refids_by_name
from ._managed import managed_keys as derive_managed_keys
from ._secrets import resolve_resource_secrets
from .base import BaseComponentManager

logger = logging.getLogger(__name__)

_TYPE = "openvpn.instances"


class OpenVpnInstanceManager(BaseComponentManager):
    """Manager for ``openvpn.instances`` operations."""

    #: Resource type threaded in as ``sibling_resources`` to resolve ``ca_ref``.
    SIBLING_RESOURCE_TYPE: ClassVar[str | None] = "trust.cas"

    #: Deletes are limited to the rows InfraFoundry applied before (ADR-0018).
    DELETE_SCOPE: ClassVar[str] = "managed_set"

    #: Instances are deleted before their CAs.
    SPLIT_DELETE_PHASE: ClassVar[bool] = True

    #: One ``openvpn/service/reconfigure`` per apply that changed an instance.
    FINALIZATION_HOOK: ClassVar[str] = "openvpn_reconfigure"

    def _desired(
        self, env_name: str, resources: list[ResourceConfig]
    ) -> list[OpenVpnInstanceConfig]:
        resolved = resolve_resource_secrets(self.config_dir, env_name, resources, _TYPE)
        return openvpn_instance_configs_from_resources(resolved)

    def _diff(
        self,
        service: OpenVpnInstanceService,
        desired: list[OpenVpnInstanceConfig],
        *,
        add_only: bool,
        managed_resources: list[ResourceConfig] | None,
        sibling_resources: list[ResourceConfig] | None,
        managed_sibling_resources: list[ResourceConfig] | None,
        unresolved: set[str] | None = None,
    ) -> tuple[Diff, dict[str, str]]:
        trust = TrustService(service.client)
        ca_refids = ca_refids_by_name(
            [*(managed_sibling_resources or []), *(sibling_resources or [])],
            trust.search_cas(),
        )
        keys = derive_managed_keys(
            managed_resources,
            openvpn_instance_configs_from_resources,
            type_name=_TYPE,
            unresolved=unresolved,
        )
        diff = compute_diff(
            desired,
            service.search(),
            add_only=add_only,
            managed_keys=keys,
            ca_refids=ca_refids,
        )
        for want in [*diff.adds, *(w for _, w in diff.updates)]:
            if want.ca_ref not in ca_refids:
                diff.warnings.append(
                    f"openvpn instance '{want.name}': CA '{want.ca_ref}' is not on the box "
                    f"yet; it must be applied first"
                )
        return diff, ca_refids

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
        """Compute the diff for the given client instances.

        Args:
            env_name: Active environment name.
            resources: ``openvpn.instances`` resources.
            add_only: If True, suppress deletes.
            managed_resources: Rows InfraFoundry applied before (ADR-0018).
            managed_sibling_resources: Managed ``trust.cas`` rows.
            provider_name: Provider identifier.
            sibling_resources: ``trust.cas`` resources from YAML.

        Returns:
            The diff apply would execute; a pending CA is a warning.
        """
        service = OpenVpnInstanceService.from_environment(env_name, provider_name, self.config_dir)
        diff, _ = self._diff(
            service,
            self._desired(env_name, resources),
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
        """Apply the diff: add, update and delete client instances.

        Args:
            env_name: Active environment name.
            resources: ``openvpn.instances`` resources.
            auto_approve: Currently a no-op.
            add_only: If True, suppress deletes.
            deletes_only: If True, only delete (the runner's delete phase).
            managed_resources: Rows InfraFoundry applied before (ADR-0018).
            managed_sibling_resources: Managed ``trust.cas`` rows.
            provider_name: Provider identifier.
            sibling_resources: ``trust.cas`` resources from YAML.

        Returns:
            Counts, ``resource_outcomes``, ``warnings`` and ``unresolved_managed``.

        Raises:
            ReferenceValidationError: If an added or updated instance's ``ca_ref``
                matches no live CA.
        """
        del auto_approve
        service = OpenVpnInstanceService.from_environment(env_name, provider_name, self.config_dir)
        unresolved: set[str] = set()
        diff, ca_refids = self._diff(
            service,
            self._desired(env_name, resources),
            add_only=add_only,
            managed_resources=managed_resources,
            sibling_resources=sibling_resources,
            managed_sibling_resources=managed_sibling_resources,
            unresolved=unresolved,
        )
        if deletes_only:
            diff.adds = []
            diff.updates = []
            diff.warnings = [w for w in diff.warnings if "is not on the box yet" not in w]

        outcomes = [
            ResourceOutcome(
                address=f"opnsense_openvpn_instance.{c.name}", action="add", resource_name=c.name
            )
            for c in diff.adds
        ]
        outcomes += [
            ResourceOutcome(
                address=f"opnsense_openvpn_instance.{w.name}",
                action="update",
                resource_name=w.name,
            )
            for _, w in diff.updates
        ]
        outcomes += [
            ResourceOutcome(
                address=f"opnsense_openvpn_instance.{d.description}",
                action="delete",
                resource_name=d.description,
            )
            for d in diff.deletes
        ]
        counts = service.apply_diff(diff, ca_refids)
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
        """Delete the live client instances named in ``resources``.

        Locked entries are skipped and counted. The finalization hook does not fire
        on destroy, so this reconfigures directly when something was deleted.

        Args:
            env_name: Active environment name.
            resources: ``openvpn.instances`` resources to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier.
            sibling_resources: Accepted for the runner; unused.

        Returns:
            ``resources_destroyed``, ``locked_skipped`` and ``warnings``.
        """
        del auto_approve, sibling_resources
        service = OpenVpnInstanceService.from_environment(env_name, provider_name, self.config_dir)
        desired = self._desired(env_name, resources)
        wanted = {c.diff_key for c in desired if not c.lock}
        live = [x for x in service.search() if x.is_client and x.diff_key in wanted]
        diff = compute_diff([], live)
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
        """Return ``{resource_name: uuid}`` for live clients matching ``resources``.

        Args:
            env_name: Active environment name.
            resources: ``openvpn.instances`` resources.
            provider_name: Provider identifier.
            sibling_resources: Accepted for the runner; unused.
        """
        del sibling_resources
        service = OpenVpnInstanceService.from_environment(env_name, provider_name, self.config_dir)
        live = {x.description: x.uuid for x in service.search() if x.is_client}
        return {
            r.name: live[description_of(r.name, r.config)]
            for r in resources
            if r.type == _TYPE and description_of(r.name, r.config) in live
        }
