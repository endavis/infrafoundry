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
            ("interfaces.vlans", VlanManager),
            ("interfaces.assignments", InterfaceAssignmentManager),
            ("firewall.aliases", AliasManager),
            ("firewall.nat", NATRuleManager),
            ("firewall.rules", FirewallRuleManager),
            ("routing.gateways", GatewayManager),
            ("routing.static", StaticRouteManager),
            ("interfaces.virtual_ips", VirtualIPManager),
            ("unbound.host_overrides", UnboundHostOverrideManager),
            ("unbound.host_aliases", UnboundHostAliasManager),
            ("unbound.forwards", UnboundForwardManager),
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

        After #782, every OPNsense resource type is managed via
        ``OPNsenseDirectRunner`` (per ADR-0014, ADR-0015) — no
        terraform write paths remain. This method now only emits the
        backend/provider/variables scaffold and the outputs block, both
        of which are still terraform-side concerns (state backend
        configuration, environment-variable mapping, output
        declarations) but produce no resource blocks.
        """
        resources_by_type = self.prepare_terraform_generation(resources)

        # Generate backend configuration if remote backend is configured
        self.render_backend()

        # Generate provider configuration
        self.render_provider_and_variables()

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
        from .components.kea_dhcp4_reservation import KeaDHCPv4ReservationManager
        from .components.kea_dhcp4_subnet import KeaDHCPv4SubnetManager
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
        # ``OPNsenseDirectRunner``). DHCPv4/DHCPv6 subnets must be applied
        # before reservations because reservations resolve their subnet UUID
        # via ``search_dhcpv4_subnets`` / ``search_dhcpv6_subnets`` at apply
        # time — a brand-new subnet must exist on the box before its
        # reservations can reference it. Aliases are applied before
        # ``nat_rules`` and ``firewall_rules`` so the alias names those
        # rules reference exist on the box first (#775).
        # ``unbound_host_override`` is applied before ``unbound_host_alias``
        # so a brand-new override exists on the box before any aliases
        # reference it (#776).
        return {
            "interfaces.vlans": VlanManager,
            "interfaces.assignments": InterfaceAssignmentManager,
            "firewall.aliases": AliasManager,
            "firewall.nat": NATRuleManager,
            "firewall.rules": FirewallRuleManager,
            "routing.gateways": GatewayManager,
            "routing.static": StaticRouteManager,
            "interfaces.virtual_ips": VirtualIPManager,
            "unbound.host_overrides": UnboundHostOverrideManager,
            "unbound.host_aliases": UnboundHostAliasManager,
            "unbound.forwards": UnboundForwardManager,
            "kea.dhcp4.subnets": KeaDHCPv4SubnetManager,
            "kea.dhcp4.reservations": KeaDHCPv4ReservationManager,
            "kea.dhcp6.subnets": KeaDHCPv6SubnetManager,
            "kea.dhcp6.reservations": KeaDHCPv6ReservationManager,
        }

    def get_finalization_hooks(self) -> dict[str, Callable[[str], None]]:
        """Return end-of-apply hooks the direct-API runner fires per key (#758, #776, #777).

        Each component manager opts in by declaring a ``FINALIZATION_HOOK``
        ClassVar; ``OPNsenseDirectRunner`` collects those keys for managers
        that mutated state during a given apply, dedupes them, and calls
        the matching callable here exactly once.

        Registered hooks:

        - ``kea_reconfigure`` — shared by :class:`KeaDHCPv4SubnetManager`,
          :class:`KeaDHCPv4ReservationManager`, :class:`KeaDHCPv6SubnetManager`,
          and :class:`KeaDHCPv6ReservationManager` so a single
          ``kea/service/reconfigure`` call fires per apply when any Kea
          component changed state. Renamed from the original
          ``kea_dhcp6_reconfigure`` (#758) to drop the v6-specific suffix
          when DHCPv4 was migrated to direct-API (#777, #778).
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
            "kea_reconfigure": self._reconfigure_kea,
            "unbound_reconfigure": self._reconfigure_unbound,
        }

    def _reconfigure_kea(self, env_name: str) -> None:
        """Reconfigure the Kea DHCP service after a DHCPv4 or DHCPv6 mutation.

        Used by :meth:`get_finalization_hooks` so the OPNsense direct-API
        runner can fire a single Kea reconfigure after any of the four
        Kea managers (DHCPv4 + DHCPv6, subnet + reservation) have
        applied. The OPNsense ``kea/service/reconfigure`` endpoint is
        shared between v4 and v6, so one call covers both. Hook errors
        propagate, failing the apply.

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

    # All OPNsense components are now managed by ``OPNsenseDirectRunner``
    # (ADR-0014). Per-component history:
    # - ``firewall_rules`` (#724, ADR-0015), ``aliases`` (#775, firewall_alias),
    #   ``unbound_host_override`` / ``unbound_host_alias`` / ``unbound_forward``
    #   (#776), ``kea_dhcp6_subnet`` / ``kea_dhcp6_reservation`` (#758),
    #   ``kea_subnet`` / ``kea_reservation`` DHCPv4 (#777, #778), and
    #   ``dhcp_static_maps`` (#782, deletion — superseded by
    #   ``kea_reservation`` direct-API; the legacy
    #   ``opnsense_dhcpv4_static_map`` terraform resource never existed
    #   in browningluke/opnsense).
    # The ``generate_terraform`` body retains only backend / provider /
    # outputs scaffolding so the orchestrator's terraform-runner
    # registration stays consistent with the other terraform-using
    # providers.

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
            "firewall.rules",
            "interfaces.vlans",
            "interfaces.assignments",
            "firewall.aliases",
            "kea.dhcp4.subnets",
            "kea.dhcp4.reservations",
            "kea.dhcp6.subnets",
            "kea.dhcp6.reservations",
            "unbound.host_overrides",
            "firewall.nat",
            "routing.gateways",
            "routing.static",
            "interfaces.virtual_ips",
            "unbound.host_aliases",
            "unbound.forwards",
        ]

    @override
    def get_terraform_resource_types(self) -> dict[str, list[str]]:
        """Map InfraFoundry resource types to terraform resource types.

        After #782, every OPNsense resource type is managed by
        ``OPNsenseDirectRunner`` per ADR-0014 / ADR-0015 — no terraform
        write paths remain. The mapping is empty; the method is kept
        on the provider so the ``ProviderBase`` contract is satisfied
        and any future terraform-managed component can be added without
        an interface change.
        """
        return {}

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies."""
        return {
            "firewall.rules": [
                "firewall.aliases",
                "interfaces.vlans",
                "interfaces.assignments",
                "routing.gateways",
            ],
            "interfaces.vlans": [],
            "interfaces.assignments": ["interfaces.vlans"],
            "firewall.aliases": [],
            "kea.dhcp4.subnets": ["interfaces.vlans"],
            "kea.dhcp4.reservations": ["kea.dhcp4.subnets"],
            "kea.dhcp6.subnets": ["interfaces.vlans"],
            "kea.dhcp6.reservations": ["kea.dhcp6.subnets"],
            "unbound.host_overrides": [],
            "firewall.nat": ["firewall.aliases", "interfaces.assignments"],
            "routing.gateways": ["interfaces.assignments"],
            "routing.static": ["routing.gateways"],
            "interfaces.virtual_ips": ["interfaces.assignments"],
            "unbound.host_aliases": ["unbound.host_overrides"],
            "unbound.forwards": [],
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
            Use ``get_extractor("opnsense", "interfaces.vlans").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_vlan is deprecated; "
            'use get_extractor("opnsense", "interfaces.vlans").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "interfaces.vlans").extract(env_name)

    def migrate_interface_assignment(self, env_name: str) -> str:
        """Migrate current interface assignments to InfraFoundry YAML.

        .. deprecated::
            Use
            ``get_extractor("opnsense", "interfaces.assignments").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_interface_assignment is deprecated; "
            'use get_extractor("opnsense", "interfaces.assignments").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "interfaces.assignments").extract(env_name)

    def migrate_nat_rule(self, env_name: str) -> str:
        """Migrate current NAT rules (outbound + 1:1) to InfraFoundry YAML.

        .. deprecated::
            Use ``get_extractor("opnsense", "firewall.nat").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_nat_rule is deprecated; "
            'use get_extractor("opnsense", "firewall.nat").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "firewall.nat").extract(env_name)

    def migrate_firewall_rule(self, env_name: str) -> str:
        """Migrate current firewall rules (MVC) to InfraFoundry YAML.

        .. deprecated::
            Use ``get_extractor("opnsense", "firewall.rules").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_firewall_rule is deprecated; "
            'use get_extractor("opnsense", "firewall.rules").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "firewall.rules").extract(env_name)

    def migrate_gateway(self, env_name: str) -> str:
        """Migrate current gateways to InfraFoundry YAML.

        .. deprecated::
            Use ``get_extractor("opnsense", "routing.gateways").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_gateway is deprecated; "
            'use get_extractor("opnsense", "routing.gateways").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "routing.gateways").extract(env_name)

    def migrate_static_route(self, env_name: str) -> str:
        """Migrate current static routes to InfraFoundry YAML.

        .. deprecated::
            Use
            ``get_extractor("opnsense", "routing.static").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_static_route is deprecated; "
            'use get_extractor("opnsense", "routing.static").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "routing.static").extract(env_name)

    def migrate_virtual_ip(self, env_name: str) -> str:
        """Migrate current virtual IPs (CARP / ipalias / proxyarp) to InfraFoundry YAML.

        .. deprecated::
            Use
            ``get_extractor("opnsense", "interfaces.virtual_ips").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_virtual_ip is deprecated; "
            'use get_extractor("opnsense", "interfaces.virtual_ips").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "interfaces.virtual_ips").extract(env_name)

    def migrate_unbound_host_alias(self, env_name: str) -> str:
        """Migrate current Unbound host aliases to InfraFoundry YAML.

        .. deprecated::
            Use
            ``get_extractor("opnsense", "unbound.host_aliases").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_unbound_host_alias is deprecated; "
            'use get_extractor("opnsense", "unbound.host_aliases").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "unbound.host_aliases").extract(env_name)

    def migrate_unbound_forward(self, env_name: str) -> str:
        """Migrate current Unbound forwarders to InfraFoundry YAML.

        .. deprecated::
            Use
            ``get_extractor("opnsense", "unbound.forwards").extract(env_name)``.
            This shim will be removed after one minor version.

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from infrafoundry.core.extractors import get_extractor

        warnings.warn(
            "OPNsenseProvider.migrate_unbound_forward is deprecated; "
            'use get_extractor("opnsense", "unbound.forwards").extract(env_name).',
            DeprecationWarning,
            stacklevel=2,
        )
        return get_extractor("opnsense", "unbound.forwards").extract(env_name)

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
