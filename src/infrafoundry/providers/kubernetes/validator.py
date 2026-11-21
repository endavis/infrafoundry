"""Validation logic for Kubernetes provider."""

from __future__ import annotations

import base64
import binascii
from typing import Any, cast

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.package_secret_refs import (
    is_package_ref,
    package_ref_problem,
    resolve_package_secret,
)
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.secrets.secret_manager import SecretManager
from infrafoundry.core.types import KubernetesProviderSettings
from infrafoundry.core.validation import ValidationLevel, ValidationReport, run_validators
from infrafoundry.core.validation_helpers import BaseAPIValidator
from infrafoundry.core.validation_helpers.terraform_secrets_validator import (
    validate_terraform_secrets_references,
)
from infrafoundry.providers.kubernetes.clusters import (
    cluster_settings,
    kubeconfig_env_override,
    validate_clusters_settings,
)
from infrafoundry.providers.kubernetes.names import kubernetes_object_name
from infrafoundry.providers.kubernetes.secret_refs import shape_errors, with_terraform_secrets
from infrafoundry.providers.kubernetes.validators import (
    CRDValidator,
    HelmValidator,
    KubeconfigValidator,
    NamespaceValidator,
)
from infrafoundry.providers.kubernetes.validators.context import (
    KubeconfigContext,
    KubernetesApiContext,
    KubernetesHelmContext,
)
from infrafoundry.providers.kubernetes.validators.kubeconfig_validator import (
    KubeConnectionInfo,
)


class KubernetesValidator:
    """Validates Kubernetes configurations.

    Composes specialized validators for kubeconfig, namespaces,
    CRDs, and Helm releases. Local cross-reference checks always
    run; API-based checks only run when connectivity is established.
    """

    def __init__(
        self,
        env_config: EnvironmentConfig,
        report: ValidationReport,
        provider_name: str = "kubernetes",
    ) -> None:
        """Initialize Kubernetes validator.

        Args:
            env_config: Environment configuration including provider_settings
            report: ValidationReport to add results to
            provider_name: ``kubernetes`` (the primary) or ``kubernetes@<cluster>`` (#1539);
                selects which cluster's settings the checks use.
        """
        self.env_config = env_config
        self.report = report
        self.provider_name = provider_name
        self.api_validator = self._cluster_api_validator(report)
        self.provider_settings = cast(
            KubernetesProviderSettings, self.api_validator.provider_settings
        )

        # Initialize specialized validators
        self.kubeconfig_validator = KubeconfigValidator(self.api_validator, report)
        self.namespace_validator = NamespaceValidator(self.api_validator, report)
        self.crd_validator = CRDValidator(self.api_validator, report)
        self.helm_validator = HelmValidator(report)

    def _cluster_api_validator(self, report: ValidationReport) -> BaseAPIValidator:
        """Return an API validator whose settings are this cluster's own."""
        validator = BaseAPIValidator("kubernetes", self.env_config, report)
        validator.provider_settings = (
            cluster_settings(validator.provider_settings, self.provider_name) or {}
        )
        return validator

    def _kubeconfig_context(self) -> KubeconfigContext:
        """Build the kubeconfig context in the order Terraform uses.

        Order: first non-empty ``KUBECONFIG`` entry (a flat configuration only, ADR-0030),
        then ``kubeconfig_path``, then the default ``~/.kube/config`` (signalled by ``None``).

        Returns:
            The context to validate.
        """
        env_path = kubeconfig_env_override(self.env_config)
        kubeconfig_path = env_path or self.provider_settings.get("kubeconfig_path")
        return KubeconfigContext(
            kubeconfig_path=kubeconfig_path,
            context_override=self.provider_settings.get("context"),
        )

    def validate_connectivity(self) -> None:
        """Validate Kubernetes connectivity prerequisites.

        Delegates to KubeconfigValidator which parses the kubeconfig,
        extracts credentials, and tests API connectivity. Temporary credential
        files are removed before returning.
        """
        try:
            self.kubeconfig_validator.validate(self._kubeconfig_context())
        finally:
            self.kubeconfig_validator.cleanup()

    def validate_offline(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig] | None = None,
    ) -> None:
        """Run the checks that need no kubeconfig, network or subprocess.

        Covers local cross-references, secret ``data`` encoding, ``terraform_secrets``
        references (unresolved refs, base64 of ``data_secrets`` values), Helm releases and
        the ``kubernetes_references`` summary.

        Args:
            resources: Resources to validate.
            reference_resources: Resources names are resolved against; defaults to
                ``resources``.
        """
        if self.provider_name == "kubernetes":
            for message in validate_clusters_settings(
                self.env_config.get_provider_settings("kubernetes")
            ):
                self.api_validator.add_error(
                    check_name="kubernetes_clusters_settings", message=message
                )
        self._validate_local_references(resources, reference_resources)
        self._validate_secret_refs(resources)

        helm_releases = [r for r in resources if r.type == "helm_releases"]
        self.helm_validator.validate(KubernetesHelmContext(helm_releases=helm_releases))

        if resources:
            self.report.add_check(
                check_name="kubernetes_references",
                passed=True,
                message=f"Validated references for {len(resources)} Kubernetes resources",
            )

    def validate_references(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig] | None = None,
    ) -> None:
        """Validate Kubernetes resource references.

        Always runs the offline checks. When a kubeconfig connects, also checks
        namespaces and CRD groups against the cluster.

        Args:
            resources: List of resources to validate
            reference_resources: Resources names are resolved against; defaults to
                ``resources``.
        """
        self.validate_offline(resources, reference_resources)

        probe: KubeconfigValidator | None = None
        try:
            conn, probe = self._ensure_connection()
            if conn is not None:
                self._validate_api_references(resources, conn, reference_resources)
        finally:
            if probe is not None:
                probe.cleanup()

    def _ensure_connection(self) -> tuple[KubeConnectionInfo | None, KubeconfigValidator | None]:
        """Return connection info, probing the cluster when none is established yet.

        The probe uses a scratch report: ``validate_connectivity`` already reported
        these results into the real one.

        Returns:
            The connection info (None when not connected) and the probe validator to
            clean up (None when an existing connection was reused).
        """
        if self.kubeconfig_validator.is_connected:
            return self.kubeconfig_validator.connection_info, None
        scratch = ValidationReport()
        probe = KubeconfigValidator(self._cluster_api_validator(scratch), scratch)
        probe.validate(self._kubeconfig_context())
        if probe.is_connected:
            return probe.connection_info, probe
        return None, probe

    def _validate_api_references(
        self,
        resources: list[ResourceConfig],
        conn: object,
        reference_resources: list[ResourceConfig] | None = None,
    ) -> None:
        """Run API-based validation checks.

        Args:
            resources: All resources to validate
            conn: KubeConnectionInfo with server_url, headers, verify_ssl
            reference_resources: Resources whose namespaces count as defined in config
        """
        info = cast(KubeConnectionInfo, conn)
        known = reference_resources if reference_resources is not None else resources

        # Namespaces created by the configuration, directly or by a Helm release
        config_namespaces = {kubernetes_object_name(r) for r in known if r.type == "namespaces"}
        helm_in_config = False
        for r in known:
            if r.type != "helm_releases":
                continue
            helm_in_config = True
            config = r.config or {}
            if config.get("create_namespace") and config.get("namespace"):
                config_namespaces.add(str(config["namespace"]))
        referenced_namespaces: set[str] = set()
        for resource in resources:
            if resource.type == "namespaces":
                continue
            ns = resource.config.get("namespace")
            if ns:
                referenced_namespaces.add(ns)

        # Namespace checks run before CRD checks (manifests only feed the CRD check)
        manifests = [r for r in resources if r.type == "manifests"]
        run_validators(
            (self.namespace_validator, self.crd_validator),
            KubernetesApiContext(
                server_url=info.server_url,
                headers=info.headers,
                verify_ssl=info.verify_ssl,
                referenced_namespaces=referenced_namespaces,
                config_namespaces=config_namespaces,
                manifests=manifests,
                helm_releases_in_config=helm_in_config,
                client_cert=info.client_cert,
                ca_bundle=info.ca_bundle,
            ),
        )

    def _validate_secret_data_encoding(self, resources: list[ResourceConfig]) -> None:
        """Check that every ``data`` value of a secret is valid base64.

        ``data`` takes base64 text, as in a Kubernetes Secret manifest. Plain values
        belong in ``string_data``.

        Args:
            resources: List of resources to validate
        """
        for resource in resources:
            if resource.type != "secrets":
                continue
            data = (resource.config or {}).get("data") or {}
            for key, value in data.items():
                try:
                    base64.b64decode(str(value), validate=True)
                except (binascii.Error, ValueError):
                    self.report.add_check(
                        check_name=f"kubernetes_secret_{resource.name}_data_{key}_base64",
                        passed=False,
                        message=(
                            f"Secret '{resource.name}' key '{key}' in 'data' is not valid "
                            f"base64; 'data' takes base64-encoded values, use 'string_data' "
                            f"for plain values"
                        ),
                        level=ValidationLevel.ERROR,
                    )

    def _validate_secret_refs(self, resources: list[ResourceConfig]) -> None:
        """Check ``*_secrets`` maps, ``value_secret`` and ``terraform_secrets`` references.

        Reports malformed fields, refs missing from the env's secrets, and ``data_secrets``
        values that are not base64. Messages name keys and refs, never secret values.

        Args:
            resources: List of resources to validate
        """
        well_formed: list[ResourceConfig] = []
        for resource in resources:
            errors = shape_errors(resource)
            for message in errors:
                self.report.add_check(
                    check_name=f"kubernetes_secret_refs_{resource.name}",
                    passed=False,
                    message=message,
                    level=ValidationLevel.ERROR,
                )
            if errors:
                continue
            try:
                well_formed.append(with_terraform_secrets(resource))
            except TypeError as exc:
                self.report.add_check(
                    check_name=f"kubernetes_secret_refs_{resource.name}",
                    passed=False,
                    message=str(exc),
                    level=ValidationLevel.ERROR,
                )
        validate_terraform_secrets_references(
            self.provider_name, well_formed, self.env_config, self.report, allow_output_refs=True
        )

        flat = SecretManager.flatten_dict(getattr(self.env_config, "secrets", None))
        for resource in resources:
            if resource.type != "secrets" or shape_errors(resource):
                continue
            data_secrets = (resource.config or {}).get("data_secrets") or {}
            for key, ref in data_secrets.items():
                if is_package_ref(ref):
                    if package_ref_problem(resource, ref) is not None:
                        continue  # reported by validate_terraform_secrets_references
                    value = resolve_package_secret(resource, ref)
                elif ref in flat:
                    value = flat[ref]
                else:
                    continue
                try:
                    base64.b64decode(value, validate=True)
                except (binascii.Error, ValueError):
                    self.report.add_check(
                        check_name=f"kubernetes_secret_{resource.name}_data_secrets_{key}_base64",
                        passed=False,
                        message=(
                            f"Secret '{resource.name}' key '{key}' in 'data_secrets' "
                            f"(ref '{ref}') is not valid base64; 'data_secrets' values must "
                            f"be base64-encoded, use 'string_data_secrets' for plain values"
                        ),
                        level=ValidationLevel.ERROR,
                    )

    def _validate_deployment_pod_spec(self, resources: list[ResourceConfig]) -> None:
        """Check deployment volume mounts, env sources and rollout strategy offline.

        Scoped to ``deployments``; jobs and cronjobs are not checked.

        Args:
            resources: Resources to validate
        """
        for resource in resources:
            if resource.type != "deployments":
                continue
            config = resource.config or {}
            name = resource.name

            volumes = config.get("volumes")
            declared = (
                {v.get("name") for v in volumes if isinstance(v, dict)}
                if isinstance(volumes, list)
                else set()
            )

            containers = config.get("containers")
            for container in containers if isinstance(containers, list) else []:
                if not isinstance(container, dict):
                    continue
                cname = container.get("name", "?")
                mounts = container.get("volume_mounts")
                for mount in mounts if isinstance(mounts, list) else []:
                    if not isinstance(mount, dict):
                        continue
                    vol = mount.get("name")
                    if vol not in declared:
                        self.report.add_check(
                            check_name=f"kubernetes_volume_mount_{name}_{cname}_{vol}",
                            passed=False,
                            message=(
                                f"Deployment '{name}' container '{cname}' mounts volume "
                                f"'{vol}' which is not declared in volumes"
                            ),
                            level=ValidationLevel.ERROR,
                        )
                envs = container.get("env")
                for env in envs if isinstance(envs, list) else []:
                    if not isinstance(env, dict):
                        continue
                    has_value = "value" in env
                    has_from = "value_from" in env
                    if has_value == has_from:
                        problem = "both" if has_value else "neither"
                        self.report.add_check(
                            check_name=f"kubernetes_env_source_{name}_{cname}_{env.get('name')}",
                            passed=False,
                            message=(
                                f"Deployment '{name}' container '{cname}' env "
                                f"'{env.get('name')}' sets {problem} of 'value' and "
                                f"'value_from'; set exactly one"
                            ),
                            level=ValidationLevel.ERROR,
                        )

            strategy = config.get("strategy")
            if strategy is not None:
                stype = strategy.get("type") if isinstance(strategy, dict) else None
                if stype not in ("RollingUpdate", "Recreate"):
                    self.report.add_check(
                        check_name=f"kubernetes_strategy_{name}",
                        passed=False,
                        message=(
                            f"Deployment '{name}' strategy.type must be 'RollingUpdate' or "
                            f"'Recreate', got {stype!r}"
                        ),
                        level=ValidationLevel.ERROR,
                    )

    def _validate_local_references(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig] | None = None,
    ) -> None:
        """Validate cross-resource references locally (no API calls).

        Checks:
        - Resources reference valid namespaces (within config)
        - ConfigMap/Secret references exist in config
        - Service selectors match deployments

        Args:
            resources: List of resources to validate
            reference_resources: Resources names are resolved against; defaults to
                ``resources``
        """
        # Collect resources by type
        known = reference_resources if reference_resources is not None else resources
        namespaces = {kubernetes_object_name(r) for r in known if r.type == "namespaces"}
        configmaps = {kubernetes_object_name(r) for r in known if r.type == "configmaps"}
        secrets = {kubernetes_object_name(r) for r in known if r.type == "secrets"}
        deployments = {kubernetes_object_name(r) for r in known if r.type == "deployments"}
        serviceaccounts = {kubernetes_object_name(r) for r in known if r.type == "serviceaccounts"}

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

        self._validate_secret_data_encoding(resources)
        self._validate_deployment_pod_spec(resources)

        # Validate deployment references to configmaps/secrets
        for resource in resources:
            if resource.type != "deployments":
                continue

            config = resource.config or {}

            env_from = config.get("env_from") or []
            for ref in env_from:
                if not isinstance(ref, dict):
                    continue
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
            selector: Any = config.get("selector")

            if selector:
                if isinstance(selector, dict):
                    app_label = selector.get("app") or selector.get("app.kubernetes.io/name")
                else:
                    app_label = str(selector)
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
