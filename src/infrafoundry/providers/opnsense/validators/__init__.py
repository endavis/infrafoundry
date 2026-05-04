"""Specialized validators for OPNsense resources."""

from infrafoundry.providers.opnsense.validators.dhcp_validator import DHCPValidator
from infrafoundry.providers.opnsense.validators.firewall_validator import FirewallValidator
from infrafoundry.providers.opnsense.validators.gateway_validator import GatewayValidator
from infrafoundry.providers.opnsense.validators.interface_assignment_validator import (
    InterfaceAssignmentValidator,
)
from infrafoundry.providers.opnsense.validators.nat_rule_validator import NATRuleValidator
from infrafoundry.providers.opnsense.validators.resource_name_validator import (
    ResourceNameValidator,
)
from infrafoundry.providers.opnsense.validators.static_route_validator import (
    StaticRouteValidator,
)
from infrafoundry.providers.opnsense.validators.unbound_forward_validator import (
    UnboundForwardValidator,
)
from infrafoundry.providers.opnsense.validators.unbound_host_alias_validator import (
    UnboundHostAliasValidator,
)
from infrafoundry.providers.opnsense.validators.unbound_validator import UnboundValidator
from infrafoundry.providers.opnsense.validators.vlan_validator import VLANValidator

__all__ = [
    "DHCPValidator",
    "FirewallValidator",
    "GatewayValidator",
    "InterfaceAssignmentValidator",
    "NATRuleValidator",
    "ResourceNameValidator",
    "StaticRouteValidator",
    "UnboundForwardValidator",
    "UnboundHostAliasValidator",
    "UnboundValidator",
    "VLANValidator",
]
