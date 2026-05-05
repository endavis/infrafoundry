"""OPNsense provider for InfraFoundry."""

import base64
import logging
import warnings
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


def _normalize_field_value(value: str) -> str:
    """Normalize a field value for comparison.

    Strips leading/trailing whitespace and sorts newline-separated lines
    (e.g., pool ranges) so ordering differences don't cause false positives.

    Args:
        value: Raw string field value

    Returns:
        Normalized string value
    """
    stripped = value.strip()
    if "\n" in stripped:
        lines = [line.strip() for line in stripped.split("\n") if line.strip()]
        return "\n".join(sorted(lines))
    return stripped


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

        VLANs and firewall rules are intentionally not generated here —
        both are managed directly via ``OPNsenseDirectRunner`` per ADR-0014
        and ADR-0015. The runner is registered with ``priority = -10`` so
        the direct-API apply precedes terraform planning of dependents like
        ``dhcp_static_maps``.
        """
        resources_by_type = self.prepare_terraform_generation(resources)

        # Generate backend configuration if remote backend is configured
        self.render_backend()

        # Generate provider configuration
        self.render_provider_and_variables()

        # Generate resources by type
        if "aliases" in resources_by_type:
            self._generate_aliases_terraform(resources_by_type["aliases"])

        if "dhcp_static_maps" in resources_by_type:
            self._generate_dhcp_static_maps_terraform(resources_by_type["dhcp_static_maps"])

        if "kea_subnet" in resources_by_type:
            self._generate_kea_subnet_terraform(resources_by_type["kea_subnet"])

        if "kea_reservation" in resources_by_type:
            self._generate_kea_reservation_terraform(resources_by_type["kea_reservation"])

        if "unbound_host_override" in resources_by_type:
            self._generate_unbound_host_override_terraform(
                resources_by_type["unbound_host_override"]
            )

        # Batch DHCPv6 subnets and reservations together for optimal performance
        kea_dhcp6_subnets = resources_by_type.get("kea_dhcp6_subnet", [])
        kea_dhcp6_reservations = resources_by_type.get("kea_dhcp6_reservation", [])
        if kea_dhcp6_subnets or kea_dhcp6_reservations:
            self._generate_kea_dhcp6_resources(kea_dhcp6_subnets, kea_dhcp6_reservations)

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
        from .components.firewall_rule import FirewallRuleManager
        from .components.gateway import GatewayManager
        from .components.interface_assignment import InterfaceAssignmentManager
        from .components.nat_rule import NATRuleManager
        from .components.static_route import StaticRouteManager
        from .components.unbound_forward import UnboundForwardManager
        from .components.unbound_host_alias import UnboundHostAliasManager
        from .components.virtual_ip import VirtualIPManager
        from .components.vlan import VlanManager

        return {
            "vlans": VlanManager,
            "interface_assignments": InterfaceAssignmentManager,
            "nat_rules": NATRuleManager,
            "firewall_rules": FirewallRuleManager,
            "gateways": GatewayManager,
            "static_routes": StaticRouteManager,
            "virtual_ips": VirtualIPManager,
            "unbound_host_alias": UnboundHostAliasManager,
            "unbound_forward": UnboundForwardManager,
        }

    def _generate_aliases_terraform(self, aliases: list[ResourceConfig]) -> None:
        """Generate Terraform for OPNsense aliases."""
        self.render_and_write_terraform(
            "opnsense/aliases.tf.j2",
            context={"aliases": aliases},
            output_name="aliases.tf",
        )

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

    def _generate_unbound_host_override_terraform(self, overrides: list[ResourceConfig]) -> None:
        """Generate Terraform for Unbound DNS host overrides."""
        self.render_and_write_terraform(
            "opnsense/unbound_host_override.tf.j2",
            context={"overrides": overrides},
            output_name="unbound_host_override.tf",
        )

    @staticmethod
    def _extract_subnet_fields(api_response: dict[str, Any]) -> dict[str, str]:
        """Extract and normalize subnet fields from an OPNsense GET response.

        The OPNsense API returns GET responses wrapped under a resource key
        (e.g., ``{"subnet6": {"subnet": "...", "interface": {...}, ...}}``).
        Select fields like ``interface`` may be returned as dicts with
        ``selected`` indicators rather than plain strings.  This method
        normalizes those values so they can be compared with the flat
        strings we send in update requests.

        Args:
            api_response: Raw response from ``get_dhcp6_subnet(uuid)``

        Returns:
            Flat dictionary of normalized field values (all strings)
        """
        data = api_response.get("subnet6", {})
        result: dict[str, str] = {}

        # Simple string fields — normalize whitespace and sort multi-line values
        for field in ("subnet", "pools", "valid_lifetime", "description"):
            result[field] = _normalize_field_value(str(data.get(field, "") or ""))

        # Interface may be a dict with selected keys or a plain string
        iface_raw = data.get("interface", "")
        if isinstance(iface_raw, dict):
            # Find selected interface(s)
            selected = [
                name
                for name, info in iface_raw.items()
                if isinstance(info, dict) and info.get("selected", 0)
            ]
            result["interface"] = ",".join(sorted(selected))
        else:
            result["interface"] = _normalize_field_value(str(iface_raw or ""))

        # option_data sub-fields
        option_data = data.get("option_data", {})
        if isinstance(option_data, dict):
            result["option_data.dns_servers"] = _normalize_field_value(
                str(option_data.get("dns_servers", "") or "")
            )
            result["option_data.domain_search"] = _normalize_field_value(
                str(option_data.get("domain_search", "") or "")
            )
        else:
            result["option_data.dns_servers"] = ""
            result["option_data.domain_search"] = ""

        return result

    @staticmethod
    def _extract_reservation_fields(api_response: dict[str, Any]) -> dict[str, str]:
        """Extract and normalize reservation fields from an OPNsense GET response.

        The OPNsense API returns GET responses wrapped under a resource key
        (e.g., ``{"reservation": {"ip_address": "...", ...}}``).
        The ``subnet`` field may be returned as a dict with ``selected``
        indicators.  This method normalizes values for comparison.

        Args:
            api_response: Raw response from ``get_dhcp6_reservation(uuid)``

        Returns:
            Flat dictionary of normalized field values (all strings)
        """
        data = api_response.get("reservation", {})
        result: dict[str, str] = {}

        # Simple string fields
        for field in ("ip_address", "duid", "hostname", "description"):
            result[field] = str(data.get(field, "") or "")

        # Subnet may be a dict with selected UUID or a plain string
        subnet_raw = data.get("subnet", "")
        if isinstance(subnet_raw, dict):
            selected = [
                uuid
                for uuid, info in subnet_raw.items()
                if isinstance(info, dict) and info.get("selected", 0)
            ]
            result["subnet"] = selected[0] if selected else ""
        else:
            result["subnet"] = str(subnet_raw or "")

        return result

    @staticmethod
    def _build_desired_subnet_fields(subnet_data: dict[str, Any]) -> dict[str, str]:
        """Build a normalized field dict from the desired subnet data we send to the API.

        Args:
            subnet_data: Subnet configuration dict prepared for the update call

        Returns:
            Flat dictionary of normalized field values matching the format
            returned by ``_extract_subnet_fields``
        """
        result: dict[str, str] = {}
        for field in ("subnet", "pools", "valid_lifetime", "description"):
            result[field] = _normalize_field_value(str(subnet_data.get(field, "") or ""))
        result["interface"] = _normalize_field_value(str(subnet_data.get("interface", "") or ""))

        option_data = subnet_data.get("option_data", {})
        if isinstance(option_data, dict):
            result["option_data.dns_servers"] = _normalize_field_value(
                str(option_data.get("dns_servers", "") or "")
            )
            result["option_data.domain_search"] = _normalize_field_value(
                str(option_data.get("domain_search", "") or "")
            )
        else:
            result["option_data.dns_servers"] = ""
            result["option_data.domain_search"] = ""

        return result

    @staticmethod
    def _build_desired_reservation_fields(
        reservation_data: dict[str, Any],
    ) -> dict[str, str]:
        """Build a normalized field dict from the desired reservation data.

        Args:
            reservation_data: Reservation configuration dict prepared for the update call

        Returns:
            Flat dictionary of normalized field values matching the format
            returned by ``_extract_reservation_fields``
        """
        result: dict[str, str] = {}
        for field in ("subnet", "ip_address", "duid", "hostname", "description"):
            result[field] = str(reservation_data.get(field, "") or "")
        return result

    @staticmethod
    def _log_field_diff(
        resource_name: str,
        current_fields: dict[str, str],
        desired_fields: dict[str, str],
    ) -> None:
        """Log field-by-field differences between current and desired state.

        Only logs when DEBUG level is enabled to avoid noise in normal operation.

        Args:
            resource_name: Human-readable name of the resource for log messages
            current_fields: Normalized fields extracted from the API response
            desired_fields: Normalized fields built from the desired configuration
        """
        if not logger.isEnabledFor(logging.DEBUG):
            return

        all_keys = sorted(set(current_fields) | set(desired_fields))
        for key in all_keys:
            current_val = current_fields.get(key, "<missing>")
            desired_val = desired_fields.get(key, "<missing>")
            if current_val != desired_val:
                logger.debug(
                    "%s field %r differs: current=%r desired=%r",
                    resource_name,
                    key,
                    current_val,
                    desired_val,
                )

    def _generate_kea_dhcp6_resources(
        self, subnets: list[ResourceConfig], reservations: list[ResourceConfig]
    ) -> None:
        """Generate DHCPv6 subnet and reservation configuration using OPNsense API.

        This method batches all DHCPv6 operations (subnets + reservations) to minimize
        API calls. It creates a single API client, searches existing resources once,
        processes all resources, and reconfigures the service only when changes are
        detected.

        Since the Terraform provider doesn't support Kea DHCPv6 resources,
        this method uses the OPNsense API directly to manage DHCPv6 configuration.

        Args:
            subnets: List of DHCPv6 subnet resources to configure
            reservations: List of DHCPv6 reservation resources to configure
        """
        from infrafoundry.core.config import ConfigManager

        # Early return if no resources to process
        if not subnets and not reservations:
            return

        if not self._current_environment:
            return

        env_name = self._current_environment
        config_manager = ConfigManager(self.config_dir)
        env_config = config_manager.load_environment(env_name)
        provider_settings = env_config.get_provider_settings("opnsense")

        if not provider_settings:
            raise ValueError(f"No OPNsense provider settings found for environment {env_name}")

        # Initialize API client ONCE
        from .api_client import KeaClient, OPNsenseClient

        client = OPNsenseClient(
            api_key=provider_settings.get("api_key", ""),
            api_secret=provider_settings.get("api_secret", ""),
            base_url=provider_settings.get("api_url", ""),
            verify_ssl=provider_settings.get("verify_ssl", True),
        )
        kea = KeaClient(client)

        # Ensure DHCPv6 service is enabled with required interfaces
        required_interfaces: list[str] = sorted(
            {s.config["interface"] for s in subnets if s.config.get("interface")}
        )
        if required_interfaces:
            kea.ensure_dhcp6_enabled(required_interfaces)

        # Search existing resources ONCE
        existing_subnets = kea.search_dhcp6_subnets() if subnets else []
        existing_reservations = kea.search_dhcp6_reservations() if reservations else []

        # Create lookup maps for efficient searching
        existing_subnets_map = {s.get("subnet"): s.get("uuid") for s in existing_subnets}
        existing_reservations_map = {
            (r.get("duid"), r.get("subnet")): r.get("uuid") for r in existing_reservations
        }

        # Track whether any changes were made
        changes_made = False

        # Process all subnets
        for subnet_resource in subnets:
            config = subnet_resource.config
            subnet_name = subnet_resource.name
            subnet_address = config.get("subnet")

            # Look up existing subnet
            existing_uuid = existing_subnets_map.get(subnet_address)

            # Prepare subnet data — field names match OPNsense Kea DHCPv6 API
            subnet_data: dict[str, Any] = {
                "subnet": subnet_address,
                "interface": config.get("interface"),
            }

            # Pools is a newline-separated string of ranges
            if "pools" in config:
                pool_strings = [pool["range"] for pool in config["pools"]]
                subnet_data["pools"] = "\n".join(pool_strings)

            # Optional fields
            if "valid_lifetime" in config:
                subnet_data["valid_lifetime"] = str(config["valid_lifetime"])
            if "description" in config:
                subnet_data["description"] = config["description"]

            # DNS settings go under option_data
            option_data: dict[str, str] = {}
            if "dns_servers" in config:
                option_data["dns_servers"] = ",".join(config["dns_servers"])
            if "dns_search_list" in config:
                option_data["domain_search"] = ",".join(config["dns_search_list"])
            if option_data:
                subnet_data["option_data"] = option_data

            # Create or update subnet
            if existing_uuid:
                # Fetch current config and compare before updating
                current = kea.get_dhcp6_subnet(existing_uuid)
                current_fields = self._extract_subnet_fields(current)
                desired_fields = self._build_desired_subnet_fields(subnet_data)

                if current_fields != desired_fields:
                    self._log_field_diff(
                        f"DHCPv6 subnet {subnet_name}", current_fields, desired_fields
                    )
                    print(f"Updating DHCPv6 subnet {subnet_name} (UUID: {existing_uuid})")
                    kea.update_dhcp6_subnet(existing_uuid, subnet_data)
                    changes_made = True
                else:
                    print(f"DHCPv6 subnet {subnet_name} unchanged, skipping update")
            else:
                print(f"Creating DHCPv6 subnet {subnet_name}")
                result = kea.add_dhcp6_subnet(subnet_data)
                if result.get("result") == "failed":
                    raise ValueError(f"Failed to create DHCPv6 subnet {subnet_name}: {result}")
                # The add response doesn't include the UUID, so search for the
                # newly created subnet to retrieve it
                created_uuid = None
                for s in kea.search_dhcp6_subnets():
                    if s.get("subnet") == subnet_address:
                        created_uuid = s.get("uuid")
                        break
                print(f"Created with UUID: {created_uuid}")
                # Update map for use in reservations
                existing_subnets_map[subnet_address] = created_uuid
                changes_made = True

        # Process all reservations
        for reservation_resource in reservations:
            config = reservation_resource.config
            reservation_name = reservation_resource.name

            # Resolve subnet_id from updated subnet map
            subnet_ref = config.get("subnet")
            subnet_id = existing_subnets_map.get(subnet_ref)
            if not subnet_id:
                print(
                    f"Warning: Subnet {subnet_ref} not found, "
                    f"skipping reservation {reservation_name}"
                )
                continue

            # Look up existing reservation by DUID and subnet_id
            duid = config.get("duid")
            existing_uuid = existing_reservations_map.get((duid, subnet_id))

            # Prepare reservation data — field names match OPNsense Kea DHCPv6 API
            reservation_data = {
                "subnet": subnet_id,
                "ip_address": config.get("ip_address"),
                "duid": duid,
                "hostname": config.get("hostname", ""),
                "description": config.get("description", ""),
            }

            # Create or update reservation
            if existing_uuid:
                # Fetch current config and compare before updating
                current = kea.get_dhcp6_reservation(existing_uuid)
                current_fields = self._extract_reservation_fields(current)
                desired_fields = self._build_desired_reservation_fields(reservation_data)

                if current_fields != desired_fields:
                    self._log_field_diff(
                        f"DHCPv6 reservation {reservation_name}",
                        current_fields,
                        desired_fields,
                    )
                    print(f"Updating DHCPv6 reservation {reservation_name} (UUID: {existing_uuid})")
                    kea.update_dhcp6_reservation(existing_uuid, reservation_data)
                    changes_made = True
                else:
                    print(f"DHCPv6 reservation {reservation_name} unchanged, skipping update")
            else:
                print(f"Creating DHCPv6 reservation {reservation_name}")
                result = kea.add_dhcp6_reservation(reservation_data)
                if result.get("result") == "failed":
                    validations = result.get("validations", {})
                    raise ValueError(
                        f"Failed to create DHCPv6 reservation {reservation_name}: {validations}"
                    )
                print(f"Created reservation {reservation_name}")
                changes_made = True

        # Reconfigure service ONCE — only if changes were made
        if changes_made:
            print("Reconfiguring Kea service...")
            kea.reconfigure_service()
            print("DHCPv6 configuration applied")
        else:
            print("No DHCPv6 changes detected, skipping Kea reconfigure")

    def _generate_kea_dhcp6_subnet_terraform(self, subnets: list[ResourceConfig]) -> None:
        """Generate DHCPv6 subnet configuration using OPNsense API.

        This method is deprecated in favor of _generate_kea_dhcp6_resources which
        batches subnets and reservations together for better performance.

        Since the Terraform provider doesn't support Kea DHCPv6 resources,
        this method uses the OPNsense API directly to manage DHCPv6 subnets.
        """
        # Delegate to the batched method with empty reservations
        self._generate_kea_dhcp6_resources(subnets, [])

    def _generate_kea_dhcp6_reservation_terraform(self, reservations: list[ResourceConfig]) -> None:
        """Generate DHCPv6 reservation configuration using OPNsense API.

        This method is deprecated in favor of _generate_kea_dhcp6_resources which
        batches subnets and reservations together for better performance.

        Since the Terraform provider doesn't support Kea DHCPv6 resources,
        this method uses the OPNsense API directly to manage DHCPv6 reservations.
        """
        # Delegate to the batched method with empty subnets
        self._generate_kea_dhcp6_resources([], reservations)

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

        ``vlans`` is omitted here per ADR-0014 — VLANs are managed by
        ``OPNsenseDirectRunner``, not terraform.
        """
        return {
            "kea_reservation": ["opnsense_kea_reservation"],
            "kea_subnet": ["opnsense_kea_subnet"],
            "aliases": ["opnsense_firewall_alias"],
            "dhcp_static_maps": ["opnsense_dhcpv4_static_map"],
            "unbound_host_override": ["opnsense_unbound_host_override"],
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
