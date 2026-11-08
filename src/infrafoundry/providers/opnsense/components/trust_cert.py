"""Trust certificate component manager for OPNsense (ADR-0014, #807).

Manages ``trust.certs``. Follows the kea reservation sibling pattern: the runner
threads the ``trust.cas`` resources in as ``sibling_resources`` (and the managed
ones as ``managed_sibling_resources``), and ``ca_ref`` is resolved to the live CA
``refid`` through :func:`~..services.trust.ca_refids_by_name`. A ``ca_ref`` whose CA
is not on the box yet is planned with a warning; at apply, after the CA manager ran,
an unresolved ``ca_ref`` raises :class:`ReferenceValidationError`.

Deletes run in the runner's delete phase (``SPLIT_DELETE_PHASE``), before CAs are
touched. Secrets are resolved here and never logged.
"""

from __future__ import annotations

from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.trust import (
    Diff,
    TrustCertConfig,
    TrustService,
    ca_refids_by_name,
    compute_diff,
    description_of,
    trust_cert_configs_from_resources,
)
from ._managed import managed_keys as derive_managed_keys
from ._secrets import resolve_resource_secrets
from .base import BaseComponentManager

_TYPE = "trust.certs"


class TrustCertManager(BaseComponentManager):
    """Manager for ``trust.certs`` operations."""

    #: Resource type threaded in as ``sibling_resources`` to resolve ``ca_ref``.
    SIBLING_RESOURCE_TYPE: ClassVar[str | None] = "trust.cas"

    #: Deletes are limited to the rows InfraFoundry applied before (ADR-0018).
    DELETE_SCOPE: ClassVar[str] = "managed_set"

    #: Certificates are deleted before their CAs.
    SPLIT_DELETE_PHASE: ClassVar[bool] = True

    def _desired(self, env_name: str, resources: list[ResourceConfig]) -> list[TrustCertConfig]:
        resolved = resolve_resource_secrets(self.config_dir, env_name, resources, _TYPE)
        return trust_cert_configs_from_resources(resolved, require_pem=True)

    def _diff(
        self,
        service: TrustService,
        desired: list[TrustCertConfig],
        *,
        add_only: bool,
        managed_resources: list[ResourceConfig] | None,
        sibling_resources: list[ResourceConfig] | None,
        managed_sibling_resources: list[ResourceConfig] | None,
        unresolved: set[str] | None = None,
    ) -> tuple[Diff[TrustCertConfig], dict[str, str]]:
        ca_refids = ca_refids_by_name(
            [*(managed_sibling_resources or []), *(sibling_resources or [])],
            service.search_cas(),
        )
        keys = derive_managed_keys(
            managed_resources,
            trust_cert_configs_from_resources,
            type_name=_TYPE,
            unresolved=unresolved,
        )
        diff = compute_diff(
            desired,
            service.search_certs(),
            kind="cert",
            add_only=add_only,
            managed_keys=keys,
            ca_refids=ca_refids,
        )
        for want in [*diff.adds, *(w for _, w in diff.updates)]:
            if want.ca_ref and want.ca_ref not in ca_refids:
                diff.warnings.append(
                    f"trust cert '{want.name}': CA '{want.ca_ref}' is not on the box yet; "
                    f"it must be applied first"
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
    ) -> Diff[TrustCertConfig]:
        """Compute the diff for the given certificates.

        Args:
            env_name: Active environment name.
            resources: ``trust.certs`` resources.
            add_only: If True, suppress deletes.
            managed_resources: Rows InfraFoundry applied before (ADR-0018).
            managed_sibling_resources: Managed ``trust.cas`` rows.
            provider_name: Provider identifier.
            sibling_resources: ``trust.cas`` resources from YAML.

        Returns:
            The diff apply would execute; a pending CA is a warning.
        """
        service = TrustService.from_environment(env_name, provider_name, self.config_dir)
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
        """Apply the diff: add, update and delete certificates.

        Args:
            env_name: Active environment name.
            resources: ``trust.certs`` resources.
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
            ReferenceValidationError: If an added or updated certificate's ``ca_ref``
                matches no live CA.
        """
        del auto_approve
        service = TrustService.from_environment(env_name, provider_name, self.config_dir)
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
        blocked = {live.description for live, _ in diff.blocked}
        for row in managed_resources or []:
            if description_of(row.name, row.config) in blocked:
                unresolved.add(row.name)

        outcomes = [
            ResourceOutcome(
                address=f"opnsense_trust_cert.{c.name}", action="add", resource_name=c.name
            )
            for c in diff.adds
        ]
        outcomes += [
            ResourceOutcome(
                address=f"opnsense_trust_cert.{w.name}", action="update", resource_name=w.name
            )
            for _, w in diff.updates
        ]
        outcomes += [
            ResourceOutcome(
                address=f"opnsense_trust_cert.{d.description}",
                action="delete",
                resource_name=d.description,
            )
            for d in diff.deletes
        ]
        counts = service.apply_diff(diff, kind="cert", ca_refids=ca_refids)
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
        """Delete the live certificates named in ``resources``.

        Locked and in-use certificates are skipped (warned, counted).

        Args:
            env_name: Active environment name.
            resources: ``trust.certs`` resources to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier.
            sibling_resources: Accepted for the runner; unused.

        Returns:
            ``resources_destroyed``, ``locked_skipped`` and ``warnings``.
        """
        del auto_approve, sibling_resources
        service = TrustService.from_environment(env_name, provider_name, self.config_dir)
        desired = self._desired(env_name, resources)
        wanted = {c.diff_key for c in desired if not c.lock}
        live = [x for x in service.search_certs() if x.diff_key in wanted]
        diff = compute_diff([], live, kind="cert")
        counts = service.apply_diff(diff, kind="cert")
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
        """Return ``{resource_name: uuid}`` for live certificates matching ``resources``.

        Args:
            env_name: Active environment name.
            resources: ``trust.certs`` resources.
            provider_name: Provider identifier.
            sibling_resources: Accepted for the runner; unused.
        """
        del sibling_resources
        service = TrustService.from_environment(env_name, provider_name, self.config_dir)
        live = {x.description: x.uuid for x in service.search_certs()}
        return {
            r.name: live[description_of(r.name, r.config)]
            for r in resources
            if r.type == _TYPE and description_of(r.name, r.config) in live
        }
