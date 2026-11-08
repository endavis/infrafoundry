"""Trust CA component manager for OPNsense (ADR-0014, #807).

Manages ``trust.cas`` through :class:`~..services.trust.TrustService`. Deletes use
the managed-set scope (ADR-0018). A managed CA the box reports in use, or one whose
description looks AcmeClient-issued, is never deleted: it is kept, warned about and
reported as unresolved so it stays managed. ``crt``/``prv`` may be ``secret://`` URIs;
they are resolved here and never logged.
"""

from __future__ import annotations

from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.trust import (
    Diff,
    TrustCaConfig,
    TrustService,
    compute_diff,
    description_of,
    trust_ca_configs_from_resources,
)
from ._managed import managed_keys as derive_managed_keys
from ._secrets import resolve_resource_secrets
from .base import BaseComponentManager

_TYPE = "trust.cas"


class TrustCaManager(BaseComponentManager):
    """Manager for ``trust.cas`` operations."""

    #: Deletes are limited to the rows InfraFoundry applied before (ADR-0018).
    DELETE_SCOPE: ClassVar[str] = "managed_set"

    def _desired(self, env_name: str, resources: list[ResourceConfig]) -> list[TrustCaConfig]:
        resolved = resolve_resource_secrets(self.config_dir, env_name, resources, _TYPE)
        return trust_ca_configs_from_resources(resolved, require_pem=True)

    def _diff(
        self,
        service: TrustService,
        desired: list[TrustCaConfig],
        *,
        add_only: bool,
        managed_resources: list[ResourceConfig] | None,
        unresolved: set[str] | None = None,
    ) -> Diff[TrustCaConfig]:
        keys = derive_managed_keys(
            managed_resources,
            trust_ca_configs_from_resources,
            type_name=_TYPE,
            unresolved=unresolved,
        )
        return compute_diff(
            desired,
            service.search_cas(),
            kind="ca",
            add_only=add_only,
            managed_keys=keys,
        )

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
    ) -> Diff[TrustCaConfig]:
        """Compute the diff for the given CAs.

        Args:
            env_name: Active environment name.
            resources: ``trust.cas`` resources.
            add_only: If True, suppress deletes.
            managed_resources: Rows InfraFoundry applied before (ADR-0018).
            provider_name: Provider identifier.

        Returns:
            The diff apply would execute.

        Raises:
            SecretResolutionError: If a ``secret://`` URI cannot be resolved.
            ValueError: If a resolved value is not PEM.
        """
        service = TrustService.from_environment(env_name, provider_name, self.config_dir)
        desired = self._desired(env_name, resources)
        return self._diff(service, desired, add_only=add_only, managed_resources=managed_resources)

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
        """Apply the diff: add, update and delete CAs.

        Args:
            env_name: Active environment name.
            resources: ``trust.cas`` resources.
            auto_approve: Currently a no-op.
            add_only: If True, suppress deletes.
            managed_resources: Rows InfraFoundry applied before (ADR-0018).
            provider_name: Provider identifier.

        Returns:
            Counts, ``resource_outcomes``, ``warnings`` and ``unresolved_managed``.
        """
        del auto_approve
        service = TrustService.from_environment(env_name, provider_name, self.config_dir)
        desired = self._desired(env_name, resources)
        unresolved: set[str] = set()
        diff = self._diff(
            service,
            desired,
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
                address=f"opnsense_trust_ca.{c.name}", action="add", resource_name=c.name
            )
            for c in diff.adds
        ]
        outcomes += [
            ResourceOutcome(
                address=f"opnsense_trust_ca.{w.name}", action="update", resource_name=w.name
            )
            for _, w in diff.updates
        ]
        outcomes += [
            ResourceOutcome(
                address=f"opnsense_trust_ca.{d.description}",
                action="delete",
                resource_name=d.description,
            )
            for d in diff.deletes
        ]
        counts = service.apply_diff(diff, kind="ca")
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
        """Delete the live CAs named in ``resources``.

        Locked, in-use and ACME-looking CAs are skipped (warned, counted).

        Args:
            env_name: Active environment name.
            resources: ``trust.cas`` resources to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier.

        Returns:
            ``resources_destroyed``, ``locked_skipped`` and ``warnings``.
        """
        del auto_approve
        service = TrustService.from_environment(env_name, provider_name, self.config_dir)
        desired = self._desired(env_name, resources)
        live = service.search_cas()
        wanted = {c.diff_key for c in desired if not c.lock}
        diff = compute_diff([], [x for x in live if x.diff_key in wanted], kind="ca")
        counts = service.apply_diff(diff, kind="ca")
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
        """Return ``{resource_name: uuid}`` for live CAs matching ``resources``.

        Args:
            env_name: Active environment name.
            resources: ``trust.cas`` resources.
            provider_name: Provider identifier.
        """
        service = TrustService.from_environment(env_name, provider_name, self.config_dir)
        live = {x.description: x.uuid for x in service.search_cas()}
        return {
            r.name: live[description_of(r.name, r.config)]
            for r in resources
            if r.type == _TYPE and description_of(r.name, r.config) in live
        }
