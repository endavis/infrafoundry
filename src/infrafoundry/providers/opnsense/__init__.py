"""OPNsense provider for InfraFoundry."""

import base64
import logging
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar, override

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
)
from infrafoundry.core.validation import ValidationReport

from .validator import OPNsenseValidator

logger = logging.getLogger(__name__)


class _ExtractorAdapter:
    """Adapter that satisfies the :class:`Extractor` Protocol.

    Binds a component manager class to a ``config_dir`` and forwards
    ``extract(env_name, **kwargs)`` calls to ``manager.migrate(...)`` on a
    fresh manager instance. Implemented as a class rather than a closure so
    that ``repr()`` is informative and instances can be pickled by tests.

    Attributes:
        manager_class: Component manager class (must expose
            ``migrate(env_name, **kwargs) -> str``).
        config_dir: Configuration directory passed to the manager
            constructor.
    """

    def __init__(self, manager_class: type, config_dir: Path) -> None:
        """Initialize adapter for a manager class.

        Args:
            manager_class: Component manager class.
            config_dir: Configuration directory to pass through.
        """
        self.manager_class = manager_class
        self.config_dir = config_dir

    def extract(self, env_name: str, **kwargs: Any) -> str:
        """Instantiate the manager and call its ``migrate`` method.

        Args:
            env_name: Environment name.
            **kwargs: Per-component keyword arguments
                (e.g., ``interfaces`` for ISC-to-Kea).

        Returns:
            InfraFoundry YAML string.
        """
        manager = self.manager_class(self.config_dir)
        result: str = manager.migrate(env_name, **kwargs)
        return result

    def __repr__(self) -> str:
        """Return a debug-friendly representation."""
        return (
            f"_ExtractorAdapter(manager_class={self.manager_class.__name__}, "
            f"config_dir={self.config_dir!r})"
        )


class OPNsenseProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
):
    """OPNsense provider for managing firewall rules, VLANs, and routing."""

    _OPNSENSE_TFVARS_MAPPING: ClassVar[dict[str, str]] = {
        "api_url": "opnsense_api_url",
        "api_key": "opnsense_api_key",
        "api_secret": "opnsense_api_secret",  # nosec B105
    }

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize OPNsense provider."""
        super().__init__("opnsense", config_dir, output_dir)
        # Use TemplateRendererMixin to set up Jinja2 environment
        self._setup_template_environment()
        # Add base64 encoding filter for Ansible templates
        self.jinja_env.filters["b64encode"] = lambda s: base64.b64encode(s.encode()).decode()
        # Register migrate extractors for the CLI ``config migrate`` command.
        # Must run after ``self.config_dir`` is set by ProviderBase.__init__.
        self._register_extractors()

    def _register_extractors(self) -> None:
        """Register per-component extractors with the global registry.

        Each extractor is an :class:`_ExtractorAdapter` that binds a
        component manager class to ``self.config_dir`` and exposes the
        :class:`infrafoundry.core.extractors.Extractor` Protocol surface
        (``extract(env_name, **kwargs) -> str``). The CLI ``config migrate``
        command looks up extractors by ``(provider_name, resource_type)``
        and calls ``.extract(...)`` directly — no per-component if/elif
        chain on the CLI side, no per-component method on the provider.

        Re-registration silently overwrites prior entries (matches
        ``RunnerRegistry`` semantics), so re-instantiating the provider
        in tests doesn't error.
        """
        from infrafoundry.core.extractors import register_extractor

        from .components.alias import AliasManager
        from .components.firewall_rule import FirewallRuleManager
        from .components.gateway import GatewayManager
        from .components.interface_assignment import InterfaceAssignmentManager
        from .components.isc_to_kea_migration import ISCToKeaMigrationManager
        from .components.kea_dhcp import KeaDHCPManager
        from .components.nat_rule import NATRuleManager
        from .components.static_route import StaticRouteManager
        from .components.unbound_forward import UnboundForwardManager
        from .components.unbound_host_alias import UnboundHostAliasManager
        from .components.unbound_host_override import UnboundHostOverrideManager
        from .components.virtual_ip import VirtualIPManager
        from .components.vlan import VlanManager

        components: list[tuple[str, type]] = [
            ("vlans", VlanManager),
            ("interface_assignments", InterfaceAssignmentManager),
            ("aliases", AliasManager),
            ("nat_rules", NATRuleManager),
            ("firewall_rules", FirewallRuleManager),
            ("gateways", GatewayManager),
            ("static_routes", StaticRouteManager),
            ("virtual_ips", VirtualIPManager),
            ("unbound_host_override", UnboundHostOverrideManager),
            ("unbound_host_alias", UnboundHostAliasManager),
            ("unbound_forward", UnboundForwardManager),
            ("kea_dhcp", KeaDHCPManager),
            ("isc_to_kea", ISCToKeaMigrationManager),
        ]
        for resource_type, manager_class in components:
            register_extractor(
                "opnsense",
                resource_type,
                _ExtractorAdapter(manager_class, self.config_dir),
            )

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate OPNsense configuration."""
        required_fields = ["name"]
        return all(field in config for field in required_fields)

    @override
    def get_terraform_env_vars(self) -> dict[str, str]:
        """Return TF_VAR_* env vars for OPNsense provider."""
        return self.build_terraform_env_vars(
            provider_name="opnsense",
            mapping=self._OPNSENSE_TFVARS_MAPPING,
        )

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration for OPNsense resources.

        VLANs, firewall rules, and aliases are intentionally not generated
        here — all three are managed directly via ``OPNsenseDirectRunner``
        per ADR-0014 (and ADR-0015 for firewall rules). The runner is
        registered with ``priority = -10`` so the direct-API apply
        precedes terraform planning of dependents like
        ``dhcp_static_maps``.
        """
        resources_by_type = self.prepare_terraform_generation(resources)

        # Generate backend configuration if remote backend is configured
        self.render_backend()

        # Generate provider configuration
        self.render_provider_and_variables()

        # Generate resources by type
        if "dhcp_static_maps" in resources_by_type:
            self._generate_dhcp_static_maps_terraform(resources_by_type["dhcp_static_maps"])

        if "kea_subnet" in resources_by_type:
            self._generate_kea_subnet_terraform(resources_by_type["kea_subnet"])

        if "kea_reservation" in resources_by_type:
            self._generate_kea_reservation_terraform(resources_by_type["kea_reservation"])

        # ``unbound_host_override`` is managed by ``OPNsenseDirectRunner``
        # via ``UnboundHostOverrideManager`` (ADR-0014 per-component
        # decision, #776) — no terraform generation. Legacy template
        # ``unbound_host_override.tf.j2`` deleted in same PR.

        # DHCPv6 subnets / reservations are managed by ``OPNsenseDirectRunner``
        # via ``KeaDHCPv6SubnetManager`` / ``KeaDHCPv6ReservationManager``
        # (ADR-0014 per-component decision, #758) — no terraform generation.

        # Generate outputs
        self.render_outputs_terraform(resources_by_type)

    def generate_opnsense_direct(self, resources: list[ResourceConfig]) -> None:
        """No-op generator hook for the direct-API runner (ADR-0014).

        ``orchestrator_workflows.py`` requires ``generate_<tool_name>`` to
        exist on the provider in order to dispatch a runner; the direct-API
        runner reads YAML at runtime via the component manager, so this
        method just satisfies the dispatch contract.

        Args:
            resources: All provider resources for the env (passed through
                the orchestrator's regenerate-IaC-configs hook). Unused
                here — the runner re-reads them via ConfigManager.
        """
        del resources  # consumed by the runner directly via ConfigManager
        logger.debug("generate_opnsense_direct invoked; runner will read resources at apply time")

    def get_direct_api_resource_types(self) -> dict[str, type[Any]]:
        """Map InfraFoundry resource type names to their direct-API component manager.

        The ``OPNsenseDirectRunner`` iterates this dict to dispatch
        plan/apply/destroy/get_resource_ids across every component that
        opted into the direct-API path (ADR-0014). Adding a new entry
        here is the only provider-side change required to wire a new
        component into the runner.

        Returns:
            ``{resource_type_name: component_manager_class}`` mapping. The
            value type is annotated as ``type[Any]`` to avoid a hard import
            of ``BaseComponentManager`` at module-load time; the runner
            knows the duck-typed surface (``plan``, ``apply``, ``destroy``,
            ``get_resource_ids``) each manager must expose.
        """
        from .components.alias import AliasManager
        from .components.firewall_rule import FirewallRuleManager
        from .components.gateway import GatewayManager
        from .components.interface_assignment import InterfaceAssignmentManager
        from .components.kea_dhcp6_reservation import KeaDHCPv6ReservationManager
        from .components.kea_dhcp6_subnet import KeaDHCPv6SubnetManager
        from .components.nat_rule import NATRuleManager
        from .components.static_route import StaticRouteManager
        from .components.unbound_forward import UnboundForwardManager
        from .components.unbound_host_alias import UnboundHostAliasManager
        from .components.unbound_host_override import UnboundHostOverrideManager
        from .components.virtual_ip import VirtualIPManager
        from .components.vlan import VlanManager

        # Iteration order matches Python dict insertion order (preserved by
        # ``OPNsenseDirectRunner``). DHCPv6 subnets must be applied before
        # reservations because reservations resolve their subnet UUID via
        # ``search_dhcpv6_subnets`` at apply time — a brand-new subnet must
        # exist on the box before its reservations can reference it. Aliases
        # are applied before ``nat_rules`` and ``firewall_rules`` so the
        # alias names those rules reference exist on the box first (#775).
        # ``unbound_host_override`` is applied before ``unbound_host_alias``
        # so a brand-new override exists on the box before any aliases
        # reference it (#776).
        return {
            "vlans": VlanManager,
            "interface_assignments": InterfaceAssignmentManager,
            "aliases": AliasManager,
            "nat_rules": NATRuleManager,
            "firewall_rules": FirewallRuleManager,
            "gateways": GatewayManager,
            "static_routes": StaticRouteManager,
            "virtual_ips": VirtualIPManager,
            "unbound_host_override": UnboundHostOverrideManager,
            "unbound_host_alias": UnboundHostAliasManager,
            "unbound_forward": UnboundForwardManager,
            "kea_dhcp6_subnet": KeaDHCPv6SubnetManager,
            "kea_dhcp6_reservation": KeaDHCPv6ReservationManager,
        }

    def get_finalization_hooks(self) -> dict[str, Callable[[str], None]]:
        """Return end-of-apply hooks the direct-API runner fires per key (#758, #776).

        Each component manager opts in by declaring a ``FINALIZATION_HOOK``
        ClassVar; ``OPNsenseDirectRunner`` collects those keys for managers
        that mutated state during a given apply, dedupes them, and calls
        the matching callable here exactly once.

        Registered hooks:

        - ``kea_dhcp6_reconfigure`` — shared by :class:`KeaDHCPv6SubnetManager`
          and :class:`KeaDHCPv6ReservationManager` so a Kea reconfigure fires
          exactly once per apply when either component changed state.
        - ``unbound_reconfigure`` (#776) — shared by
          :class:`UnboundHostOverrideManager`, :class:`UnboundHostAliasManager`,
          and :class:`UnboundForwardManager` so a single
          ``unbound/service/reconfigure`` call fires per apply when any of
          the three unbound components changed state.

        The mechanism is generic — future components with shared post-apply
        work register their own key here.

        Returns:
            ``{hook_key: callable(env_name)}`` mapping; missing keys are a
            graceful no-op on the runner side.
        """
        return {
            "kea_dhcp6_reconfigure": self._reconfigure_kea_dhcp6,
            "unbound_reconfigure": self._reconfigure_unbound,
        }

    def _reconfigure_kea_dhcp6(self, env_name: str) -> None:
        """Reconfigure the Kea DHCP service after a DHCPv6 mutation (#758).

        Used by :meth:`get_finalization_hooks` so the OPNsense direct-API
        runner can fire a single Kea reconfigure after subnet and
        reservation managers have applied. Hook errors propagate, failing
        the apply (matches the legacy DHCPv6 path's behavior, which raised
        on a failed reconfigure response).

        Args:
            env_name: Active environment name (matches the runner's hook
                contract — ``hook(env_name) -> None``).
        """
        from .services.kea_dhcp import KeaDHCPService

        service = KeaDHCPService.from_environment(env_name, "opnsense", self.config_dir)
        service.reconfigure()

    def _reconfigure_unbound(self, env_name: str) -> None:
        """Reconfigure the Unbound service after any unbound mutation (#776).

        Used by :meth:`get_finalization_hooks` so the OPNsense direct-API
        runner can fire a single ``unbound/service/reconfigure`` call after
        the host_override, host_alias, and forward managers have applied.
        All three unbound services share the same reconfigure verb, so any
        of the three service instances works; this implementation uses
        :class:`UnboundHostOverrideService` arbitrarily. Hook errors
        propagate, failing the apply.

        Args:
            env_name: Active environment name (matches the runner's hook
                contract — ``hook(env_name) -> None``).
        """
        from .services.unbound_host_override import UnboundHostOverrideService

        service = UnboundHostOverrideService.from_environment(env_name, "opnsense", self.config_dir)
        service.reconfigure()

    def _generate_dhcp_static_maps_terraform(self, static_maps: list[ResourceConfig]) -> None:
        """Generate Terraform for OPNsense DHCP static mappings."""
        self.render_and_write_terraform(
            "opnsense/dhcp_static_maps.tf.j2",
            context={"static_maps": static_maps},
            output_name="dhcp_static_maps.tf",
        )

    def _generate_kea_subnet_terraform(self, subnets: list[ResourceConfig]) -> None:
        """Generate Terraform for Kea DHCP subnets."""
        self.render_and_write_terraform(
            "opnsense/kea_subnet.tf.j2",
            context={"subnets": subnets},
            output_name="kea_subnet.tf",
        )

    def _generate_kea_reservation_terraform(self, reservations: list[ResourceConfig]) -> None:
        """Generate Terraform for Kea DHCP reservations."""
        self.render_and_write_terraform(
            "opnsense/kea_reservation.tf.j2",
            context={"reservations": reservations},
            output_name="kea_reservation.tf",
        )

    # ``unbound_host_override`` terraform generation has been removed
    # (#776). The component now uses the direct-API path via
    # :class:`UnboundHostOverrideManager` registered in
    # :meth:`get_direct_api_resource_types`.

    # DHCPv6 subnet / reservation management lives on
    # ``OPNsenseDirectRunner`` via the ``KeaDHCPv6SubnetManager`` and
    # ``KeaDHCPv6ReservationManager`` component managers (#758,
    # ADR-0014 per-component decision). The ~200 lines of inline
    # mutation logic that previously lived here have been removed; the
    # change-detection helpers were relocated to ``services/kea_dhcp.py``.

    @override
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Generate Ansible playbooks for OPNsense configuration."""
        self.ensure_directories()

        # Generate main playbook
        content = self.render_template("opnsense/playbook.yml.j2", {"resources": resources})
        self._write_ansible_file("playbook.yml", content)

        # Generate inventory
        content = self.render_template("opnsense/inventory.yml.j2", {})
        self._write_ansible_file("inventory.yml", content)

    @override
    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return [
            "firewall_rules",
            "vlans",
            "interface_assignments",
            "aliases",
            "dhcp_static_maps",
            "kea_subnet",
            "kea_reservation",
            "kea_dhcp6_subnet",
            "kea_dhcp6_reservation",
            "unbound_host_override",
            "nat_rules",
            "gateways",
            "static_routes",
            "virtual_ips",
            "unbound_host_alias",
            "unbound_forward",
        ]

    @override
    def get_terraform_resource_types(self) -> dict[str, list[str]]:
        """Map InfraFoundry resource types to terraform resource types.

        ``vlans``, ``firewall_rules``, ``aliases``, and
        ``unbound_host_override`` are omitted here per ADR-0014 — they
        are managed by ``OPNsenseDirectRunner``, not terraform.
        """
        return {
            "kea_reservation": ["opnsense_kea_reservation"],
            "kea_subnet": ["opnsense_kea_subnet"],
            "dhcp_static_maps": ["opnsense_dhcpv4_static_map"],
        }

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies."""
        return {
            "firewall_rules": ["aliases", "vlans", "interface_assignments", "gateways"],
            "vlans": [],
            "interface_assignments": ["vlans"],
            "aliases": [],
            "dhcp_static_maps": ["vlans"],
            "kea_subnet": ["vlans"],
            "kea_reservation": ["kea_subnet"],
            "kea_dhcp6_subnet": ["vlans"],
            "kea_dhcp6_reservation": ["kea_dhcp6_subnet"],
            "unbound_host_override": [],
            "nat_rules": ["aliases", "interface_assignments"],
            "gateways": ["interface_assignments"],
            "static_routes": ["gateways"],
            "virtual_ips": ["interface_assignments"],
            "unbound_host_alias": ["unbound_host_override"],
            "unbound_forward": [],
        }

    @override
    def validate_connectivity(
        self, env_config: EnvironmentConfig, report: ValidationReport
    ) -> None:
        """Validate connectivity to OPNsense API."""
        validator = OPNsenseValidator(env_config, report)
        validator.validate_connectivity()

    @override
    def validate_references(
        self,
        resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Validate that referenced OPNsense resources exist."""
        validator = OPNsenseValidator(env_config, report)
        validator.validate_references(resources)

    def reset_kea_dhcpv4(self, env_name: str) -> None:
        """Reset (delete) all Kea DHCPv4 configuration.

        This removes all Kea DHCPv4 subnets and reservations from OPNsense,
        allowing a fresh configuration to be applied.

        Args:
            env_name: Environment name to reset
        """
        from .components.kea_dhcp import KeaDHCPManager

        manager = KeaDHCPManager(self.config_dir)
        manager.reset_dhcpv4(env_name, "opnsense")

    def reset_kea_dhcpv6(self, env_name: str) -> None:
        """Reset (delete) all Kea DHCPv6 configuration.

        This removes all Kea DHCPv6 subnets and reservations from OPNsense,
        allowing a fresh configuration to be applied.

        Args:
            env_name: Environment name to reset
        """
        from .components.kea_dhcp import KeaDHCPManager

        manager = KeaDHCPManager(self.config_dir)
        manager.reset_dhcpv6(env_name, "opnsense")

    def migrate_kea_dhcp(self, env_name: str) -> str:
        """Migrate current Kea DHCP configuration to InfraFoundry YAML.

        Reads the current Kea DHCPv4 and DHCPv6 configuration from OPNsense
        and generates InfraFoundry-compatible YAML configuration.

        .. deprecated::
            Use the :class:`infrafoundry.core.extractors.ExtractorRegistry`
            via ``get_extractor("opnsense", "kea_dhcp").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_kea_dhcp is deprecated; "
            'use get_extractor("opnsense", "kea_dhcp").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "kea_dhcp").extract(env_name)

    def migrate_vlan(self, env_name: str) -> str:
        """Migrate current VLAN configuration to InfraFoundry YAML.

        .. deprecated::
            Use ``get_extractor("opnsense", "vlans").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_vlan is deprecated; "
            'use get_extractor("opnsense", "vlans").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "vlans").extract(env_name)

    def migrate_interface_assignment(self, env_name: str) -> str:
        """Migrate current interface assignments to InfraFoundry YAML.

        .. deprecated::
            Use
            ``get_extractor("opnsense", "interface_assignments").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_interface_assignment is deprecated; "
            'use get_extractor("opnsense", "interface_assignments").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "interface_assignments").extract(env_name)

    def migrate_nat_rule(self, env_name: str) -> str:
        """Migrate current NAT rules (outbound + 1:1) to InfraFoundry YAML.

        .. deprecated::
            Use ``get_extractor("opnsense", "nat_rules").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_nat_rule is deprecated; "
            'use get_extractor("opnsense", "nat_rules").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "nat_rules").extract(env_name)

    def migrate_firewall_rule(self, env_name: str) -> str:
        """Migrate current firewall rules (MVC) to InfraFoundry YAML.

        .. deprecated::
            Use ``get_extractor("opnsense", "firewall_rules").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_firewall_rule is deprecated; "
            'use get_extractor("opnsense", "firewall_rules").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "firewall_rules").extract(env_name)

    def migrate_gateway(self, env_name: str) -> str:
        """Migrate current gateways to InfraFoundry YAML.

        .. deprecated::
            Use ``get_extractor("opnsense", "gateways").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_gateway is deprecated; "
            'use get_extractor("opnsense", "gateways").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "gateways").extract(env_name)

    def migrate_static_route(self, env_name: str) -> str:
        """Migrate current static routes to InfraFoundry YAML.

        .. deprecated::
            Use
            ``get_extractor("opnsense", "static_routes").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_static_route is deprecated; "
            'use get_extractor("opnsense", "static_routes").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "static_routes").extract(env_name)

    def migrate_virtual_ip(self, env_name: str) -> str:
        """Migrate current virtual IPs (CARP / ipalias / proxyarp) to InfraFoundry YAML.

        .. deprecated::
            Use
            ``get_extractor("opnsense", "virtual_ips").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_virtual_ip is deprecated; "
            'use get_extractor("opnsense", "virtual_ips").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "virtual_ips").extract(env_name)

    def migrate_unbound_host_alias(self, env_name: str) -> str:
        """Migrate current Unbound host aliases to InfraFoundry YAML.

        .. deprecated::
            Use
            ``get_extractor("opnsense", "unbound_host_alias").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_unbound_host_alias is deprecated; "
            'use get_extractor("opnsense", "unbound_host_alias").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "unbound_host_alias").extract(env_name)

    def migrate_unbound_forward(self, env_name: str) -> str:
        """Migrate current Unbound forwarders to InfraFoundry YAML.

        .. deprecated::
            Use
            ``get_extractor("opnsense", "unbound_forward").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_unbound_forward is deprecated; "
            'use get_extractor("opnsense", "unbound_forward").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "unbound_forward").extract(env_name)

    def migrate_isc_to_kea(self, env_name: str, interfaces: list[str] | None = None) -> str:
        """Migrate ISC DHCP configuration to Kea DHCP format.

        .. deprecated::
            Use
            ``get_extractor("opnsense", "isc_to_kea").extract(env_name, interfaces=...)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name
            interfaces: List of interfaces to migrate (None = all)

        Returns:
            YAML configuration as a string with Kea DHCP resources
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_isc_to_kea is deprecated; "
            'use get_extractor("opnsense", "isc_to_kea").extract'
            "(env_name, interfaces=...).",
            DeprecationWarning,
            stacklevel=2,
        )
        kwargs: dict[str, Any] = {}
        if interfaces is not None:
            kwargs["interfaces"] = interfaces
        return get_extractor("opnsense", "isc_to_kea").extract(env_name, **kwargs)
