"""Service layer package for OPNsense operations."""

from .base import BaseService
from .interface_assignment import (
    InterfaceAssignmentConfig,
    InterfaceAssignmentService,
    LiveInterfaceAssignment,
    interface_assignment_configs_from_resources,
)
from .isc_dhcp import ISCDHCPService
from .kea_dhcp import KeaDHCPService
from .vlan import Diff, LiveVlan, VlanConfig, VlanService, compute_diff

__all__ = [
    "BaseService",
    "Diff",
    "ISCDHCPService",
    "InterfaceAssignmentConfig",
    "InterfaceAssignmentService",
    "KeaDHCPService",
    "LiveInterfaceAssignment",
    "LiveVlan",
    "VlanConfig",
    "VlanService",
    "compute_diff",
    "interface_assignment_configs_from_resources",
]
