"""Validation logic for Kubernetes provider."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import EnvironmentData, KubernetesProviderSettings
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator


class KubernetesValidator:
    """Validates Kubernetes configurations.

    Performs pre-flight validation including:
    - Kubeconfig file existence and accessibility
    - Cross-resource reference validation (namespaces, secrets, configmaps)
    """

    def __init__(self, env_config: EnvironmentData, report: ValidationReport) -> None:
        """Initialize Kubernetes validator.

        Args:
            env_config: Environment configuration including provider_settings
            report: ValidationReport to add results to
        """
        self.env_config = env_config
        self.report = report
        self.api_validator = BaseAPIValidator("kubernetes", env_config, report)
        self.provider_settings = cast(
            KubernetesProviderSettings, self.api_validator.provider_settings
        )

    def validate_connectivity(self) -> None:
        """Validate Kubernetes connectivity prerequisites.

        Checks:
        - Kubeconfig file exists and is readable
        """
        kubeconfig_path = self.provider_settings.get("kubeconfig_path")

        if not kubeconfig_path:
            # Check default location
            default_path = Path.home() / ".kube" / "config"
            if default_path.exists():
                self.report.add_check(
                    check_name="kubernetes_kubeconfig",
                    passed=True,
                    message=f"Using default kubeconfig at {default_path}",
                    level=ValidationLevel.INFO,
                )
            else:
                self.report.add_check(
                    check_name="kubernetes_kubeconfig",
                    passed=False,
                    message=("No kubeconfig_path specified and default ~/.kube/config not found"),
                    level=ValidationLevel.WARNING,
                )
            return

        kubeconfig = Path(kubeconfig_path).expanduser()
        if kubeconfig.exists():
            self.report.add_check(
                check_name="kubernetes_kubeconfig",
                passed=True,
                message=f"Kubeconfig found at {kubeconfig}",
            )
        else:
            self.report.add_check(
                check_name="kubernetes_kubeconfig",
                passed=False,
                message=f"Kubeconfig not found at {kubeconfig}",
                level=ValidationLevel.ERROR,
            )

    def validate_references(self, resources: list[ResourceConfig]) -> None:
        """Validate Kubernetes resource references.

        Checks:
        - Resources reference valid namespaces
        - ConfigMap/Secret references exist in config
        - Service selectors match deployments

        Args:
            resources: List of resources to validate
        """
        # Collect resources by type
        namespaces = {r.name for r in resources if r.type == "namespaces"}
        configmaps = {r.name for r in resources if r.type == "configmaps"}
        secrets = {r.name for r in resources if r.type == "secrets"}
        deployments = {r.name for r in resources if r.type == "deployments"}
        serviceaccounts = {r.name for r in resources if r.type == "serviceaccounts"}

        # Validate namespace references
        for resource in resources:
            if resource.type in ("namespaces",):
                continue  # Namespaces don't reference other namespaces

            namespace = resource.config.get("namespace")
            if namespace and namespace not in namespaces:
                # It might be an existing namespace not in config - just warn
                self.report.add_check(
                    check_name=f"kubernetes_ref_{resource.name}_namespace",
                    passed=True,
                    message=(
                        f"Resource '{resource.name}' references namespace '{namespace}' "
                        f"(not in config - assuming it exists)"
                    ),
                    level=ValidationLevel.INFO,
                )

        # Validate deployment references to configmaps/secrets
        for resource in resources:
            if resource.type != "deployments":
                continue

            config = resource.config or {}

            # Check configmap references in env_from
            env_from = config.get("env_from", [])
            for ref in env_from:
                cm_ref = ref.get("configmap")
                if cm_ref and cm_ref not in configmaps:
                    self.report.add_check(
                        check_name=f"kubernetes_ref_{resource.name}_configmap_{cm_ref}",
                        passed=False,
                        message=(
                            f"Deployment '{resource.name}' references configmap '{cm_ref}' "
                            f"which is not defined in configuration"
                        ),
                        level=ValidationLevel.ERROR,
                    )
                secret_ref = ref.get("secret")
                if secret_ref and secret_ref not in secrets:
                    self.report.add_check(
                        check_name=f"kubernetes_ref_{resource.name}_secret_{secret_ref}",
                        passed=False,
                        message=(
                            f"Deployment '{resource.name}' references secret '{secret_ref}' "
                            f"which is not defined in configuration"
                        ),
                        level=ValidationLevel.ERROR,
                    )

            # Check service account references
            sa_ref = config.get("service_account")
            if sa_ref and sa_ref not in serviceaccounts:
                self.report.add_check(
                    check_name=f"kubernetes_ref_{resource.name}_serviceaccount",
                    passed=True,
                    message=(
                        f"Deployment '{resource.name}' references service account '{sa_ref}' "
                        f"(not in config - assuming it exists)"
                    ),
                    level=ValidationLevel.INFO,
                )

        # Validate service references to deployments
        for resource in resources:
            if resource.type != "services":
                continue

            config = resource.config or {}
            selector = config.get("selector", {})

            # Check if selector matches any deployment
            if selector:
                # Simple check - see if app label matches a deployment name
                app_label = selector.get("app") or selector.get("app.kubernetes.io/name")
                if app_label and app_label not in deployments:
                    self.report.add_check(
                        check_name=f"kubernetes_ref_{resource.name}_selector",
                        passed=True,
                        message=(
                            f"Service '{resource.name}' selector may not match any deployment "
                            f"in configuration (selector.app={app_label})"
                        ),
                        level=ValidationLevel.INFO,
                    )

        # Report success if we have resources
        if resources:
            self.report.add_check(
                check_name="kubernetes_references",
                passed=True,
                message=f"Validated references for {len(resources)} Kubernetes resources",
            )
