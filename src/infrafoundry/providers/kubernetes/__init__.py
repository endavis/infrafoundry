"""Kubernetes provider for InfraFoundry."""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from infrafoundry.core.provider import ProviderBase, ResourceConfig


class KubernetesProvider(ProviderBase):
    """Kubernetes provider for managing deployments, services, and configs."""

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize Kubernetes provider."""
        super().__init__("kubernetes", config_dir, output_dir)
        self.template_dir = Path(__file__).parent / "templates"
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate Kubernetes configuration."""
        required_fields = ["name"]
        return all(field in config for field in required_fields)

    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration for Kubernetes resources."""
        self.ensure_directories()

        # Group resources by type
        resources_by_type: dict[str, list[ResourceConfig]] = {}
        for resource in resources:
            if resource.type not in resources_by_type:
                resources_by_type[resource.type] = []
            resources_by_type[resource.type].append(resource)

        # Generate provider configuration
        provider_template = self.jinja_env.get_template("kubernetes/provider.tf.j2")
        provider_content = provider_template.render()
        (self.terraform_dir / "provider.tf").write_text(provider_content)

        # Generate variables file
        variables_template = self.jinja_env.get_template("kubernetes/variables.tf.j2")
        variables_content = variables_template.render()
        (self.terraform_dir / "variables.tf").write_text(variables_content)

        # Generate resources by type
        if "deployments" in resources_by_type:
            self._generate_deployments_terraform(resources_by_type["deployments"])

        if "services" in resources_by_type:
            self._generate_services_terraform(resources_by_type["services"])

        if "configmaps" in resources_by_type:
            self._generate_configmaps_terraform(resources_by_type["configmaps"])

        if "namespaces" in resources_by_type:
            self._generate_namespaces_terraform(resources_by_type["namespaces"])

        # Generate outputs
        outputs_template = self.jinja_env.get_template("kubernetes/outputs.tf.j2")
        outputs_content = outputs_template.render(
            resources_by_type=resources_by_type,
        )
        (self.terraform_dir / "outputs.tf").write_text(outputs_content)

    def _generate_deployments_terraform(self, deployments: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes deployments."""
        template = self.jinja_env.get_template("kubernetes/deployments.tf.j2")
        content = template.render(deployments=deployments)
        (self.terraform_dir / "deployments.tf").write_text(content)

    def _generate_services_terraform(self, services: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes services."""
        template = self.jinja_env.get_template("kubernetes/services.tf.j2")
        content = template.render(services=services)
        (self.terraform_dir / "services.tf").write_text(content)

    def _generate_configmaps_terraform(self, configmaps: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes configmaps."""
        template = self.jinja_env.get_template("kubernetes/configmaps.tf.j2")
        content = template.render(configmaps=configmaps)
        (self.terraform_dir / "configmaps.tf").write_text(content)

    def _generate_namespaces_terraform(self, namespaces: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes namespaces."""
        template = self.jinja_env.get_template("kubernetes/namespaces.tf.j2")
        content = template.render(namespaces=namespaces)
        (self.terraform_dir / "namespaces.tf").write_text(content)

    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Generate Ansible playbooks for Kubernetes post-configuration."""
        self.ensure_directories()

        # Generate main playbook
        playbook_template = self.jinja_env.get_template("kubernetes/playbook.yml.j2")
        playbook_content = playbook_template.render(resources=resources)
        (self.ansible_dir / "playbook.yml").write_text(playbook_content)

        # Generate inventory (localhost for kubectl operations)
        inventory_template = self.jinja_env.get_template("kubernetes/inventory.yml.j2")
        inventory_content = inventory_template.render()
        (self.ansible_dir / "inventory.yml").write_text(inventory_content)

    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return ["deployments", "services", "configmaps", "namespaces"]

    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies."""
        return {
            "deployments": ["namespaces", "configmaps"],
            "services": ["namespaces", "deployments"],
            "configmaps": ["namespaces"],
            "namespaces": [],
        }
