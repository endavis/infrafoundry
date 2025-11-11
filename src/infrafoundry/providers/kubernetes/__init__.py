"""Kubernetes provider for InfraFoundry."""

from pathlib import Path
from typing import Any, override

from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import ResourceGrouperMixin, TemplateRendererMixin


class KubernetesProvider(ProviderBase, TemplateRendererMixin, ResourceGrouperMixin):
    """Kubernetes provider for managing deployments, services, and configs."""

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize Kubernetes provider."""
        super().__init__("kubernetes", config_dir, output_dir)
        # Use TemplateRendererMixin to set up Jinja2 environment
        self._setup_template_environment()

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate Kubernetes configuration."""
        required_fields = ["name"]
        return all(field in config for field in required_fields)

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration for Kubernetes resources."""
        self.ensure_directories()

        # Use ResourceGrouperMixin to group resources by type
        resources_by_type = self.group_resources_by_type(resources)

        # Generate provider configuration
        content = self.render_template("kubernetes/provider.tf.j2", {})
        self._write_terraform_file("provider.tf", content)

        # Generate variables file
        content = self.render_template("kubernetes/variables.tf.j2", {})
        self._write_terraform_file("variables.tf", content)

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
        content = self.render_template(
            "kubernetes/outputs.tf.j2",
            {"resources_by_type": resources_by_type},
        )
        self._write_terraform_file("outputs.tf", content)

    def _generate_deployments_terraform(self, deployments: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes deployments."""
        content = self.render_template("kubernetes/deployments.tf.j2", {"deployments": deployments})
        self._write_terraform_file("deployments.tf", content)

    def _generate_services_terraform(self, services: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes services."""
        content = self.render_template("kubernetes/services.tf.j2", {"services": services})
        self._write_terraform_file("services.tf", content)

    def _generate_configmaps_terraform(self, configmaps: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes configmaps."""
        content = self.render_template("kubernetes/configmaps.tf.j2", {"configmaps": configmaps})
        self._write_terraform_file("configmaps.tf", content)

    def _generate_namespaces_terraform(self, namespaces: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes namespaces."""
        content = self.render_template("kubernetes/namespaces.tf.j2", {"namespaces": namespaces})
        self._write_terraform_file("namespaces.tf", content)

    @override
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Generate Ansible playbooks for Kubernetes post-configuration."""
        self.ensure_directories()

        # Generate main playbook
        content = self.render_template("kubernetes/playbook.yml.j2", {"resources": resources})
        self._write_ansible_file("playbook.yml", content)

        # Generate inventory (localhost for kubectl operations)
        content = self.render_template("kubernetes/inventory.yml.j2", {})
        self._write_ansible_file("inventory.yml", content)

    @override
    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return ["deployments", "services", "configmaps", "namespaces"]

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies."""
        return {
            "deployments": ["namespaces", "configmaps"],
            "services": ["namespaces", "deployments"],
            "configmaps": ["namespaces"],
            "namespaces": [],
        }
