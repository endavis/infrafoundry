"""Validation contexts for the Proxmox sub-validators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypedDict

from infrafoundry.core.validation import ValidationContext

if TYPE_CHECKING:
    from infrafoundry.core.provider import ResourceConfig
    from infrafoundry.providers.proxmox.api_client import ProxmoxClient


class ClusterVM(TypedDict, total=False):
    """Typed representation of a VM entry in the Proxmox cluster listing."""

    vmid: int
    name: str
    template: int
    type: str


@dataclass(frozen=True, kw_only=True)
class ProxmoxConfigContext(ValidationContext):
    """Context for the config validators, which check resources by type.

    Attributes:
        storage: ``storage`` resources.
        vms: ``vm`` resources.
        containers: ``container`` resources.
        templates: ``template`` resources.
        sdn_zones: ``sdn_zone`` resources.
        sdn_vnets: ``sdn_vnet`` resources.
    """

    storage: list[ResourceConfig] = field(default_factory=list)
    vms: list[ResourceConfig] = field(default_factory=list)
    containers: list[ResourceConfig] = field(default_factory=list)
    templates: list[ResourceConfig] = field(default_factory=list)
    sdn_zones: list[ResourceConfig] = field(default_factory=list)
    sdn_vnets: list[ResourceConfig] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class ProxmoxLiveContext(ValidationContext):
    """Context for validators that query the Proxmox API.

    Attributes:
        client: Proxmox API client.
        nodes: Node names to validate.
        storage_pools: ``(node, storage)`` tuples to validate.
        bridges: ``(node, bridge)`` tuples to validate.
        declared_vnets: IDs of ``sdn_vnet`` resources in the validated set. A bridge
            that is one of these but not applied yet is a warning, not an error,
            since the same apply creates it.
    """

    client: ProxmoxClient
    nodes: set[str] = field(default_factory=set)
    storage_pools: set[tuple[str, str]] = field(default_factory=set)
    bridges: set[tuple[str, str]] = field(default_factory=set)
    declared_vnets: frozenset[str] = frozenset()


@dataclass(frozen=True, kw_only=True)
class ProxmoxClusterContext(ValidationContext):
    """Context for validators that check against the cluster VM listing.

    Attributes:
        cluster_vms: Cluster VM data, or None if the fetch failed.
        template_refs: ``{vmid_or_name: [resource_names]}``.
        vmids: ``{vmid: resource_name}``.
    """

    cluster_vms: list[ClusterVM] | None = None
    template_refs: dict[str, list[str]] = field(default_factory=dict)
    vmids: dict[int, str] = field(default_factory=dict)
