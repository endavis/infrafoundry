"""Validation logic for Kubernetes provider."""

from __future__ import annotations

from typing import cast

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import KubernetesProviderSettings
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator
from infrafoundry.providers.kubernetes.validators import (
    CRDValidator,
    HelmValidator,
    KubeconfigValidator,
    NamespaceValidator,
)


class KubernetesValidator:
    """Validates Kubernetes configurations.

    Composes specialized validators for kubeconfig, namespaces,
    CRDs, and Helm releases. Local cross-reference checks always
    run; API-based checks only run when connectivity is established.
    """

    def __init__(self, env_config: EnvironmentConfig, report: ValidationReport) -> None:
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

        # Initialize specialized validators
        self.kubeconfig_validator = KubeconfigValidator(self.api_validator, report)
        self.namespace_validator = NamespaceValidator(self.api_validator, report)
        self.crd_validator = CRDValidator(self.api_validator, report)
        self.helm_validator = HelmValidator(report)

    def validate_connectivity(self) -> None:
        """Validate Kubernetes connectivity prerequisites.

        Delegates to KubeconfigValidator which parses the kubeconfig,
        extracts credentials, and tests API connectivity.
        """
        kubeconfig_path = self.provider_settings.get("kubeconfig_path")
        context_override = self.provider_settings.get("context")
        self.kubeconfig_validator.validate(kubeconfig_path, context_override)

    def validate_references(self, resources: list[ResourceConfig]) -> None:
        """Validate Kubernetes resource references.

        Always runs:
        - Local cross-reference checks (configmaps, secrets, service accounts, selectors)
        - Helm release validation

        When connected:
        - Namespace existence checks via API
        - CRD existence checks via API

        Args:
            resources: List of resources to validate
        """
        # Local cross-reference checks always run
        self._validate_local_references(resources)

        # Helm validation always runs (no API needed)
        helm_releases = [r for r in resources if r.type == "helm_releases"]
        self.helm_validator.validate(helm_releases)

        # API-based checks only when connected
        if self.kubeconfig_validator.is_connected:
            conn = self.kubeconfig_validator.connection_info
            self._validate_api_references(resources, conn)

        # Report success if we have resources
        if resources:
            self.report.add_check(
                check_name="kubernetes_references",
                passed=True,
                message=f"Validated references for {len(resources)} Kubernetes resources",
            )

    def _validate_api_references(
        self,
        resources: list[ResourceConfig],
        conn: object,
    ) -> None:
        """Run API-based validation checks.

        Args:
            resources: All resources to validate
            conn: KubeConnectionInfo with server_url, headers, verify_ssl
        """
        from infrafoundry.providers.kubernetes.validators.kubeconfig_validator import (
            KubeConnectionInfo,
        )

        info = cast(KubeConnectionInfo, conn)

        # Collect namespace references and config-defined namespaces
        config_namespaces = {r.name for r in resources if r.type == "namespaces"}
        referenced_namespaces: set[str] = set()
        for resource in resources:
            if resource.type == "namespaces":
                continue
            ns = resource.config.get("namespace")
            if ns:
                referenced_namespaces.add(ns)

        self.namespace_validator.validate(
            server_url=info.server_url,
            headers=info.headers,
            verify_ssl=info.verify_ssl,
            referenced_namespaces=referenced_namespaces,
            config_namespaces=config_namespaces,
        )

        # CRD validation for manifest resources
        manifests = [r for r in resources if r.type == "manifests"]
        self.crd_validator.validate(
            server_url=info.server_url,
            headers=info.headers,
            verify_ssl=info.verify_ssl,
            manifests=manifests,
        )

    def _validate_local_references(self, resources: list[ResourceConfig]) -> None:
        """Validate cross-resource references locally (no API calls).

        Checks:
        - Resources reference valid namespaces (within config)
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
                continue

            namespace = resource.config.get("namespace")
            if namespace and namespace not in namespaces:
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

            if selector:
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
