"""OPNsense provider for InfraFoundry."""

import base64
from pathlib import Path
from typing import Any, override

from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
)
from infrafoundry.core.validation import ValidationReport

from .validator import OPNsenseValidator


class OPNsenseProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
):
    """OPNsense provider for managing firewall rules, VLANs, and routing."""

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize OPNsense provider."""
        super().__init__("opnsense", config_dir, output_dir)
        # Use TemplateRendererMixin to set up Jinja2 environment
        self._setup_template_environment()
        # Add base64 encoding filter for Ansible templates
        self.jinja_env.filters["b64encode"] = lambda s: base64.b64encode(s.encode()).decode()

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate OPNsense configuration."""
        required_fields = ["name"]
        return all(field in config for field in required_fields)

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration for OPNsense resources."""
        self.ensure_directories()

        # Use ResourceGrouperMixin to group resources by type
        resources_by_type = self.group_resources_by_type(resources)

        # Generate provider configuration
        content = self.render_template("opnsense/provider.tf.j2", {})
        self._write_terraform_file("provider.tf", content)

        # Generate variables file
        content = self.render_template("opnsense/variables.tf.j2", {})
        self._write_terraform_file("variables.tf", content)

        # Generate terraform.tfvars from settings.yaml
        self.generate_provider_tfvars(
            provider_name="opnsense",
            mapping=self._OPNSENSE_TFVARS_MAPPING,
        )

        # Generate resources by type
        if "firewall_rules" in resources_by_type:
            self._generate_firewall_rules_terraform(resources_by_type["firewall_rules"])

        if "vlans" in resources_by_type:
            self._generate_vlans_terraform(resources_by_type["vlans"])

        if "aliases" in resources_by_type:
            self._generate_aliases_terraform(resources_by_type["aliases"])

        if "dhcp_static_maps" in resources_by_type:
            self._generate_dhcp_static_maps_terraform(resources_by_type["dhcp_static_maps"])

        if "kea_subnet" in resources_by_type:
            self._generate_kea_subnet_terraform(resources_by_type["kea_subnet"])

        if "kea_reservation" in resources_by_type:
            self._generate_kea_reservation_terraform(resources_by_type["kea_reservation"])

        # Batch DHCPv6 subnets and reservations together for optimal performance
        kea_dhcp6_subnets = resources_by_type.get("kea_dhcp6_subnet", [])
        kea_dhcp6_reservations = resources_by_type.get("kea_dhcp6_reservation", [])
        if kea_dhcp6_subnets or kea_dhcp6_reservations:
            self._generate_kea_dhcp6_resources(kea_dhcp6_subnets, kea_dhcp6_reservations)

        # Generate outputs
        content = self.render_template(
            "opnsense/outputs.tf.j2",
            {"resources_by_type": resources_by_type},
        )
        self._write_terraform_file("outputs.tf", content)

    def _generate_firewall_rules_terraform(self, rules: list[ResourceConfig]) -> None:
        """Generate Terraform for OPNsense firewall rules."""
        content = self.render_template("opnsense/firewall_rules.tf.j2", {"rules": rules})
        self._write_terraform_file("firewall_rules.tf", content)

    def _generate_vlans_terraform(self, vlans: list[ResourceConfig]) -> None:
        """Generate Terraform for OPNsense VLANs."""
        content = self.render_template("opnsense/vlans.tf.j2", {"vlans": vlans})
        self._write_terraform_file("vlans.tf", content)

    def _generate_aliases_terraform(self, aliases: list[ResourceConfig]) -> None:
        """Generate Terraform for OPNsense aliases."""
        content = self.render_template("opnsense/aliases.tf.j2", {"aliases": aliases})
        self._write_terraform_file("aliases.tf", content)

    def _generate_dhcp_static_maps_terraform(self, static_maps: list[ResourceConfig]) -> None:
        """Generate Terraform for OPNsense DHCP static mappings."""
        content = self.render_template(
            "opnsense/dhcp_static_maps.tf.j2", {"static_maps": static_maps}
        )
        self._write_terraform_file("dhcp_static_maps.tf", content)

    def _generate_kea_subnet_terraform(self, subnets: list[ResourceConfig]) -> None:
        """Generate Terraform for Kea DHCP subnets."""
        content = self.render_template("opnsense/kea_subnet.tf.j2", {"subnets": subnets})
        self._write_terraform_file("kea_subnet.tf", content)

    def _generate_kea_reservation_terraform(self, reservations: list[ResourceConfig]) -> None:
        """Generate Terraform for Kea DHCP reservations."""
        content = self.render_template(
            "opnsense/kea_reservation.tf.j2", {"reservations": reservations}
        )
        self._write_terraform_file("kea_reservation.tf", content)

    def _generate_kea_dhcp6_resources(
        self, subnets: list[ResourceConfig], reservations: list[ResourceConfig]
    ) -> None:
        """Generate DHCPv6 subnet and reservation configuration using OPNsense API.

        This method batches all DHCPv6 operations (subnets + reservations) to minimize
        API calls. It creates a single API client, searches existing resources once,
        processes all resources, and reconfigures the service once at the end.

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

        # Search existing resources ONCE
        existing_subnets = kea.search_dhcp6_subnets() if subnets else []
        existing_reservations = kea.search_dhcp6_reservations() if reservations else []

        # Create lookup maps for efficient searching
        existing_subnets_map = {s.get("subnet"): s.get("uuid") for s in existing_subnets}
        existing_reservations_map = {
            (r.get("duid"), r.get("subnet_id")): r.get("uuid") for r in existing_reservations
        }

        # Process all subnets
        for subnet_resource in subnets:
            config = subnet_resource.config
            subnet_name = subnet_resource.name
            subnet_address = config.get("subnet")

            # Look up existing subnet
            existing_uuid = existing_subnets_map.get(subnet_address)

            # Prepare subnet data
            subnet_data = {
                "subnet": subnet_address,
                "interface": config.get("interface"),
                "option_data_autocollect": str(int(config.get("auto_collect", True))),
            }

            # Add pools
            if "pools" in config:
                subnet_data["pools"] = []
                for pool in config["pools"]:
                    subnet_data["pools"].append({"pool": pool["range"]})

            # Add optional fields
            if "valid_lifetime" in config:
                subnet_data["valid_lifetime"] = str(config["valid_lifetime"])
            if "dns_servers" in config:
                subnet_data["dns_servers"] = ",".join(config["dns_servers"])
            if "dns_search_list" in config:
                subnet_data["dns_search_list"] = ",".join(config["dns_search_list"])
            if "description" in config:
                subnet_data["description"] = config["description"]

            # Create or update subnet
            if existing_uuid:
                print(f"Updating DHCPv6 subnet {subnet_name} (UUID: {existing_uuid})")
                kea.update_dhcp6_subnet(existing_uuid, subnet_data)
            else:
                print(f"Creating DHCPv6 subnet {subnet_name}")
                response = kea.add_dhcp6_subnet(subnet_data)
                created_uuid = response.get("uuid")
                print(f"Created with UUID: {created_uuid}")
                # Update map for use in reservations
                existing_subnets_map[subnet_address] = created_uuid

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

            # Prepare reservation data
            reservation_data = {
                "subnet_id": subnet_id,
                "duid": duid,
                "ip_addresses": config.get("ip_address"),
                "hostname": config.get("hostname", ""),
                "description": config.get("description", ""),
            }

            # Create or update reservation
            if existing_uuid:
                print(f"Updating DHCPv6 reservation {reservation_name} (UUID: {existing_uuid})")
                kea.update_dhcp6_reservation(existing_uuid, reservation_data)
            else:
                print(f"Creating DHCPv6 reservation {reservation_name}")
                response = kea.add_dhcp6_reservation(reservation_data)
                print(f"Created with UUID: {response.get('uuid')}")

        # Reconfigure service ONCE to apply all changes
        print("Reconfiguring Kea service...")
        kea.reconfigure_service()
        print("DHCPv6 configuration applied")

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
            "aliases",
            "dhcp_static_maps",
            "kea_subnet",
            "kea_reservation",
            "kea_dhcp6_subnet",
            "kea_dhcp6_reservation",
        ]

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies."""
        return {
            "firewall_rules": ["aliases", "vlans"],
            "vlans": [],
            "aliases": [],
            "dhcp_static_maps": ["vlans"],
            "kea_subnet": ["vlans"],
            "kea_reservation": ["kea_subnet"],
            "kea_dhcp6_subnet": ["vlans"],
            "kea_dhcp6_reservation": ["kea_dhcp6_subnet"],
        }

    @override
    def validate_connectivity(self, env_config: dict[str, Any], report: ValidationReport) -> None:
        """Validate connectivity to OPNsense API."""
        validator = OPNsenseValidator(env_config, report)
        validator.validate_connectivity()

    @override
    def validate_references(
        self, resources: list[ResourceConfig], env_config: dict[str, Any], report: ValidationReport
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

        Args:
            env_name: Environment name

        Returns:
            YAML configuration as a string
        """
        from .components.kea_dhcp import KeaDHCPManager

        manager = KeaDHCPManager(self.config_dir)
        return manager.migrate(env_name, "opnsense")

    def migrate_isc_to_kea(self, env_name: str, interfaces: list[str] | None = None) -> str:
        """Migrate ISC DHCP configuration to Kea DHCP format.

        Reads the legacy ISC DHCP configuration and generates InfraFoundry YAML
        with Kea DHCP resources (both DHCPv4 and DHCPv6).

        Args:
            env_name: Environment name
            interfaces: List of interfaces to migrate (None = all)

        Returns:
            YAML configuration as a string with Kea DHCP resources
        """
        from .components.isc_to_kea_migration import ISCToKeaMigrationManager

        manager = ISCToKeaMigrationManager(self.config_dir)
        return manager.export_to_yaml(env_name, "opnsense", interfaces)
