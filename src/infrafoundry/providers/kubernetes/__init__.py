"""Kubernetes provider for InfraFoundry."""

from pathlib import Path
from typing import Any, ClassVar, override

import yaml

from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
)


class KubernetesProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
):
    """Kubernetes provider for managing deployments, services, secrets, RBAC, and Helm releases."""

    # Mapping from settings.yaml keys to terraform variable names
    _KUBERNETES_TFVARS_MAPPING: ClassVar[dict[str, str]] = {
        "kubeconfig_path": "kubeconfig_path",
    }

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize Kubernetes provider."""
        super().__init__("kubernetes", config_dir, output_dir)
        # Use TemplateRendererMixin to set up Jinja2 environment
        self._setup_template_environment()
        # Add custom filter for YAML serialization
        self.jinja_env.filters["toyaml"] = lambda x: yaml.dump(x, default_flow_style=False).rstrip()

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate Kubernetes configuration."""
        required_fields = ["name"]
        return all(field in config for field in required_fields)

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration for Kubernetes resources."""
        resources_by_type = self.prepare_terraform_generation(resources)

        # Generate backend configuration if remote backend is configured
        self.render_backend()

        # Check if we have helm releases to conditionally include helm provider
        has_helm_releases = "helm_releases" in resources_by_type

        # Generate provider configuration with helm flag
        self._render_provider_with_helm(has_helm_releases)

        # Generate variables configuration
        self.render_and_write_terraform(
            "kubernetes/variables.tf.j2",
            context={},
            output_name="variables.tf",
        )

        # Generate terraform.tfvars from settings.yaml
        self.generate_provider_tfvars(
            provider_name="kubernetes",
            mapping=self._KUBERNETES_TFVARS_MAPPING,
        )

        # Generate resources by type - Core resources
        if "namespaces" in resources_by_type:
            self._generate_namespaces_terraform(resources_by_type["namespaces"])

        if "configmaps" in resources_by_type:
            self._generate_configmaps_terraform(resources_by_type["configmaps"])

        if "secrets" in resources_by_type:
            self._generate_secrets_terraform(resources_by_type["secrets"])

        if "persistentvolumeclaims" in resources_by_type:
            self._generate_pvcs_terraform(resources_by_type["persistentvolumeclaims"])

        # RBAC resources
        self._generate_rbac_terraform(resources_by_type)

        # Workload resources
        if "deployments" in resources_by_type:
            self._generate_deployments_terraform(resources_by_type["deployments"])

        if "services" in resources_by_type:
            self._generate_services_terraform(resources_by_type["services"])

        if "ingresses" in resources_by_type:
            self._generate_ingresses_terraform(resources_by_type["ingresses"])

        if "jobs" in resources_by_type:
            self._generate_jobs_terraform(resources_by_type["jobs"])

        if "cronjobs" in resources_by_type:
            self._generate_cronjobs_terraform(resources_by_type["cronjobs"])

        # Helm releases
        if "helm_releases" in resources_by_type:
            self._generate_helm_releases_terraform(resources_by_type["helm_releases"])

        # Custom manifests (CRDs, etc.)
        if "manifests" in resources_by_type:
            self._generate_manifests_terraform(resources_by_type["manifests"])

        # Generate outputs
        self.render_outputs_terraform(resources_by_type)

    def _render_provider_with_helm(self, has_helm_releases: bool) -> None:
        """Render provider.tf with conditional Helm provider."""
        self.render_and_write_terraform(
            "kubernetes/provider.tf.j2",
            context={"has_helm_releases": has_helm_releases},
            output_name="provider.tf",
        )

    def _generate_namespaces_terraform(self, namespaces: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes namespaces."""
        self.render_and_write_terraform(
            "kubernetes/namespaces.tf.j2",
            context={"namespaces": namespaces},
            output_name="namespaces.tf",
        )

    def _generate_configmaps_terraform(self, configmaps: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes configmaps."""
        self.render_and_write_terraform(
            "kubernetes/configmaps.tf.j2",
            context={"configmaps": configmaps},
            output_name="configmaps.tf",
        )

    def _generate_secrets_terraform(self, secrets: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes secrets."""
        self.render_and_write_terraform(
            "kubernetes/secrets.tf.j2",
            context={"secrets": secrets},
            output_name="secrets.tf",
        )

    def _generate_pvcs_terraform(self, pvcs: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes persistent volume claims."""
        self.render_and_write_terraform(
            "kubernetes/pvc.tf.j2",
            context={"pvcs": pvcs},
            output_name="pvc.tf",
        )

    def _generate_rbac_terraform(self, resources_by_type: dict[str, list[ResourceConfig]]) -> None:
        """Generate Terraform for RBAC resources."""
        # Collect all RBAC resource types
        serviceaccounts = resources_by_type.get("serviceaccounts", [])
        roles = resources_by_type.get("roles", [])
        rolebindings = resources_by_type.get("rolebindings", [])
        clusterroles = resources_by_type.get("clusterroles", [])
        clusterrolebindings = resources_by_type.get("clusterrolebindings", [])

        # Only generate if we have any RBAC resources
        if any([serviceaccounts, roles, rolebindings, clusterroles, clusterrolebindings]):
            self.render_and_write_terraform(
                "kubernetes/rbac.tf.j2",
                context={
                    "serviceaccounts": serviceaccounts,
                    "roles": roles,
                    "rolebindings": rolebindings,
                    "clusterroles": clusterroles,
                    "clusterrolebindings": clusterrolebindings,
                },
                output_name="rbac.tf",
            )

    def _generate_deployments_terraform(self, deployments: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes deployments."""
        self.render_and_write_terraform(
            "kubernetes/deployments.tf.j2",
            context={"deployments": deployments},
            output_name="deployments.tf",
        )

    def _generate_services_terraform(self, services: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes services."""
        self.render_and_write_terraform(
            "kubernetes/services.tf.j2",
            context={"services": services},
            output_name="services.tf",
        )

    def _generate_ingresses_terraform(self, ingresses: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes ingresses."""
        self.render_and_write_terraform(
            "kubernetes/ingress.tf.j2",
            context={"ingresses": ingresses},
            output_name="ingress.tf",
        )

    def _generate_jobs_terraform(self, jobs: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes jobs."""
        self.render_and_write_terraform(
            "kubernetes/jobs.tf.j2",
            context={"jobs": jobs},
            output_name="jobs.tf",
        )

    def _generate_cronjobs_terraform(self, cronjobs: list[ResourceConfig]) -> None:
        """Generate Terraform for Kubernetes cron jobs."""
        self.render_and_write_terraform(
            "kubernetes/cronjobs.tf.j2",
            context={"cronjobs": cronjobs},
            output_name="cronjobs.tf",
        )

    def _generate_helm_releases_terraform(self, helm_releases: list[ResourceConfig]) -> None:
        """Generate Terraform for Helm releases."""
        self.render_and_write_terraform(
            "kubernetes/helm_releases.tf.j2",
            context={"helm_releases": helm_releases},
            output_name="helm_releases.tf",
        )

    def _generate_manifests_terraform(self, manifests: list[ResourceConfig]) -> None:
        """Generate Terraform for custom Kubernetes manifests (CRDs, etc.)."""
        self.render_and_write_terraform(
            "kubernetes/manifests.tf.j2",
            context={"manifests": manifests},
            output_name="manifests.tf",
        )

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
        return [
            # Core resources
            "namespaces",
            "configmaps",
            "secrets",
            "persistentvolumeclaims",
            # RBAC resources
            "serviceaccounts",
            "roles",
            "rolebindings",
            "clusterroles",
            "clusterrolebindings",
            # Workload resources
            "deployments",
            "services",
            "ingresses",
            "jobs",
            "cronjobs",
            # Helm
            "helm_releases",
            # Custom manifests (CRDs, etc.)
            "manifests",
        ]

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies for proper ordering."""
        return {
            # Core resources - namespace is base
            "namespaces": [],
            "configmaps": ["namespaces"],
            "secrets": ["namespaces"],
            "persistentvolumeclaims": ["namespaces"],
            # RBAC - service accounts first, then roles, then bindings
            "serviceaccounts": ["namespaces"],
            "roles": ["namespaces"],
            "rolebindings": ["namespaces", "roles", "serviceaccounts"],
            "clusterroles": [],
            "clusterrolebindings": ["clusterroles", "serviceaccounts"],
            # Workloads depend on config/secrets/RBAC
            "deployments": [
                "namespaces",
                "configmaps",
                "secrets",
                "serviceaccounts",
                "persistentvolumeclaims",
            ],
            "services": ["namespaces", "deployments"],
            "ingresses": ["namespaces", "services"],
            "jobs": [
                "namespaces",
                "configmaps",
                "secrets",
                "serviceaccounts",
            ],
            "cronjobs": [
                "namespaces",
                "configmaps",
                "secrets",
                "serviceaccounts",
            ],
            # Helm can create its own namespace
            "helm_releases": ["namespaces"],
            # Custom manifests depend on namespaces and potentially helm (for CRDs)
            "manifests": ["namespaces", "helm_releases"],
        }
