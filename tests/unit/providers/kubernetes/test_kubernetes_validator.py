"""Unit tests for KubernetesValidator (composition orchestrator)."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import (
    ProviderValidator,
    ValidationLevel,
    ValidationReport,
)
from infrafoundry.providers.kubernetes.validator import KubernetesValidator
from infrafoundry.providers.kubernetes.validators import (
    CRDValidator,
    HelmValidator,
    KubeconfigValidator,
    NamespaceValidator,
)
from infrafoundry.providers.kubernetes.validators.context import KubeconfigContext
from tests.helpers.env import make_env_config


@pytest.fixture
def mock_env_config() -> Any:
    """Create a mock environment config."""
    return make_env_config(
        name="test-env",
        provider_settings={
            "kubernetes": {
                "kubeconfig_path": "/path/to/kubeconfig",
            }
        },
    )


@pytest.fixture
def validation_report() -> ValidationReport:
    """Create a ValidationReport instance."""
    return ValidationReport()


@pytest.fixture
def validator(mock_env_config: Any, validation_report: ValidationReport) -> KubernetesValidator:
    """Create a KubernetesValidator instance."""
    return KubernetesValidator(mock_env_config, validation_report)


@pytest.mark.unit
class TestKubernetesValidatorProtocol:
    """Tests verifying KubernetesValidator implements ProviderValidator protocol."""

    def test_implements_provider_validator_protocol(self, validator: KubernetesValidator) -> None:
        """Test that KubernetesValidator implements ProviderValidator protocol."""
        assert isinstance(validator, ProviderValidator)
        assert hasattr(validator, "env_config")
        assert hasattr(validator, "report")
        assert hasattr(validator, "validate_connectivity")
        assert hasattr(validator, "validate_references")


@pytest.mark.unit
class TestKubernetesValidatorComposition:
    """Tests verifying composition of specialized validators."""

    def test_has_kubeconfig_validator(self, validator: KubernetesValidator) -> None:
        """Test that KubernetesValidator composes KubeconfigValidator."""
        assert isinstance(validator.kubeconfig_validator, KubeconfigValidator)

    def test_has_namespace_validator(self, validator: KubernetesValidator) -> None:
        """Test that KubernetesValidator composes NamespaceValidator."""
        assert isinstance(validator.namespace_validator, NamespaceValidator)

    def test_has_crd_validator(self, validator: KubernetesValidator) -> None:
        """Test that KubernetesValidator composes CRDValidator."""
        assert isinstance(validator.crd_validator, CRDValidator)

    def test_has_helm_validator(self, validator: KubernetesValidator) -> None:
        """Test that KubernetesValidator composes HelmValidator."""
        assert isinstance(validator.helm_validator, HelmValidator)


@pytest.mark.unit
class TestKubernetesValidatorConnectivity:
    """Tests for KubernetesValidator.validate_connectivity."""

    def test_validate_connectivity_with_existing_kubeconfig(
        self, mock_env_config: Any, validation_report: ValidationReport
    ) -> None:
        """Test validation when kubeconfig exists."""
        with patch.object(Path, "exists", return_value=True):
            validator = KubernetesValidator(mock_env_config, validation_report)
            validator.validate_connectivity()

        # Should have success result
        assert any(r.passed for r in validation_report.results)
        assert any("Kubeconfig found" in r.message for r in validation_report.results)

    def test_validate_connectivity_with_missing_kubeconfig(
        self, mock_env_config: Any, validation_report: ValidationReport
    ) -> None:
        """Test validation when kubeconfig doesn't exist."""
        with patch.object(Path, "exists", return_value=False):
            validator = KubernetesValidator(mock_env_config, validation_report)
            validator.validate_connectivity()

        # Should have error result
        assert any(not r.passed for r in validation_report.results)
        assert any("not found" in r.message for r in validation_report.results)

    def test_validate_connectivity_no_kubeconfig_path_with_default(
        self, validation_report: ValidationReport
    ) -> None:
        """Test validation when no kubeconfig path specified but default exists."""
        env_config = make_env_config(
            name="test-env",
            provider_settings={"kubernetes": {}},
        )

        with patch.object(Path, "exists", return_value=True):
            validator = KubernetesValidator(env_config, validation_report)
            validator.validate_connectivity()

        # Should have info result about using default
        assert any("default kubeconfig" in r.message for r in validation_report.results)

    def test_validate_connectivity_no_kubeconfig_path_no_default(
        self, validation_report: ValidationReport
    ) -> None:
        """Test validation when no kubeconfig path and no default."""
        env_config = make_env_config(
            name="test-env",
            provider_settings={"kubernetes": {}},
        )

        with patch.object(Path, "exists", return_value=False):
            validator = KubernetesValidator(env_config, validation_report)
            validator.validate_connectivity()

        # Should have warning result
        assert any(
            r.level == ValidationLevel.WARNING and not r.passed for r in validation_report.results
        )

    def test_validate_connectivity_delegates_to_kubeconfig_validator(
        self, mock_env_config: Any, validation_report: ValidationReport
    ) -> None:
        """Test that connectivity delegates to KubeconfigValidator."""
        validator = KubernetesValidator(mock_env_config, validation_report)
        validator.kubeconfig_validator.validate = MagicMock()  # type: ignore[method-assign]
        validator.validate_connectivity()
        validator.kubeconfig_validator.validate.assert_called_once_with(
            KubeconfigContext(kubeconfig_path="/path/to/kubeconfig", context_override=None)
        )

    def test_validate_connectivity_passes_context_override(
        self, validation_report: ValidationReport
    ) -> None:
        """Test that context override from settings is passed through."""
        env_config = make_env_config(
            name="test-env",
            provider_settings={
                "kubernetes": {
                    "kubeconfig_path": "/path/to/kubeconfig",
                    "context": "my-context",
                }
            },
        )
        validator = KubernetesValidator(env_config, validation_report)
        validator.kubeconfig_validator.validate = MagicMock()  # type: ignore[method-assign]
        validator.validate_connectivity()
        validator.kubeconfig_validator.validate.assert_called_once_with(
            KubeconfigContext(kubeconfig_path="/path/to/kubeconfig", context_override="my-context")
        )


@pytest.mark.unit
class TestKubernetesValidatorReferences:
    """Tests for KubernetesValidator.validate_references."""

    def test_validate_references_empty_resources(
        self, validator: KubernetesValidator, validation_report: ValidationReport
    ) -> None:
        """Test validation with no resources."""
        validator.validate_references([])

        # Should have no errors
        assert not validation_report.has_errors()

    def test_validate_references_valid_configmap_ref(
        self, validator: KubernetesValidator, validation_report: ValidationReport
    ) -> None:
        """Test validation with valid configmap reference."""
        resources = [
            ResourceConfig(
                provider="kubernetes",
                type="configmaps",
                name="my-config",
                config={"namespace": "default", "data": {"key": "value"}},
            ),
            ResourceConfig(
                provider="kubernetes",
                type="deployments",
                name="my-app",
                config={
                    "namespace": "default",
                    "env_from": [{"configmap": "my-config"}],
                },
            ),
        ]

        validator.validate_references(resources)

        # Should have no errors for configmap reference
        errors = [r for r in validation_report.results if not r.passed]
        configmap_errors = [e for e in errors if "configmap" in e.check_name]
        assert len(configmap_errors) == 0

    def test_validate_references_invalid_configmap_ref(
        self, validator: KubernetesValidator, validation_report: ValidationReport
    ) -> None:
        """Test validation with invalid configmap reference."""
        resources = [
            ResourceConfig(
                provider="kubernetes",
                type="deployments",
                name="my-app",
                config={
                    "namespace": "default",
                    "env_from": [{"configmap": "missing-config"}],
                },
            ),
        ]

        validator.validate_references(resources)

        # Should have error for missing configmap
        assert validation_report.has_errors()
        assert any("missing-config" in r.message for r in validation_report.results)

    def test_validate_references_invalid_secret_ref(
        self, validator: KubernetesValidator, validation_report: ValidationReport
    ) -> None:
        """Test validation with invalid secret reference."""
        resources = [
            ResourceConfig(
                provider="kubernetes",
                type="deployments",
                name="my-app",
                config={
                    "namespace": "default",
                    "env_from": [{"secret": "missing-secret"}],
                },
            ),
        ]

        validator.validate_references(resources)

        # Should have error for missing secret
        assert validation_report.has_errors()
        assert any("missing-secret" in r.message for r in validation_report.results)

    def test_secret_data_rejects_non_base64(
        self, validator: KubernetesValidator, validation_report: ValidationReport
    ) -> None:
        """A plain-text data value fails, naming the secret and key."""
        resources = [
            ResourceConfig(
                provider="kubernetes",
                type="secrets",
                name="db-creds",
                config={"data": {"password": "not base64!"}},
            ),
        ]

        validator.validate_references(resources)

        assert validation_report.has_errors()
        assert any(
            "db-creds" in r.message and "password" in r.message and "base64" in r.message
            for r in validation_report.results
        )

    def test_secret_data_accepts_base64_and_ignores_string_data(
        self, validator: KubernetesValidator, validation_report: ValidationReport
    ) -> None:
        """Valid base64 data passes; string_data may hold any plain text."""
        resources = [
            ResourceConfig(
                provider="kubernetes",
                type="secrets",
                name="db-creds",
                config={"data": {"password": "dmFsdWU="}, "string_data": {"u": "not base64!"}},
            ),
        ]

        validator.validate_references(resources)

        assert not validation_report.has_errors()

    def test_validate_references_reports_success(
        self, validator: KubernetesValidator, validation_report: ValidationReport
    ) -> None:
        """Test that validation reports overall success."""
        resources = [
            ResourceConfig(
                provider="kubernetes",
                type="namespaces",
                name="my-namespace",
                config={},
            ),
        ]

        validator.validate_references(resources)

        # Should report successful validation
        assert any("Validated references" in r.message for r in validation_report.results)

    def test_validate_references_runs_helm_always(
        self, validator: KubernetesValidator, validation_report: ValidationReport
    ) -> None:
        """Test that Helm validation runs regardless of connectivity."""
        validator.helm_validator.validate = MagicMock()  # type: ignore[method-assign]
        resources = [
            ResourceConfig(
                provider="kubernetes",
                type="helm_releases",
                name="nginx",
                config={"chart": "nginx", "repository": "https://charts.bitnami.com"},
            ),
        ]
        validator.validate_references(resources)
        validator.helm_validator.validate.assert_called_once()

    def test_validate_references_skips_api_when_disconnected(
        self, validator: KubernetesValidator, validation_report: ValidationReport
    ) -> None:
        """Test that API-based checks are skipped when not connected."""
        validator.namespace_validator.validate = MagicMock()  # type: ignore[method-assign]
        validator.crd_validator.validate = MagicMock()  # type: ignore[method-assign]
        resources = [
            ResourceConfig(
                provider="kubernetes",
                type="deployments",
                name="my-app",
                config={"namespace": "default"},
            ),
        ]
        # kubeconfig_validator.is_connected defaults to False
        validator.validate_references(resources)
        validator.namespace_validator.validate.assert_not_called()
        validator.crd_validator.validate.assert_not_called()

    def test_validate_references_runs_api_when_connected(
        self, validator: KubernetesValidator, validation_report: ValidationReport
    ) -> None:
        """Test that API-based checks run when connected."""
        from infrafoundry.providers.kubernetes.validators.kubeconfig_validator import (
            KubeConnectionInfo,
        )

        conn = KubeConnectionInfo(
            server_url="https://k8s.example.com:6443",
            headers={"Authorization": "Bearer token"},
            verify_ssl=True,
            connected=True,
        )
        validator.kubeconfig_validator._connection_info = conn
        validator.namespace_validator.validate = MagicMock()  # type: ignore[method-assign]
        validator.crd_validator.validate = MagicMock()  # type: ignore[method-assign]

        resources = [
            ResourceConfig(
                provider="kubernetes",
                type="deployments",
                name="my-app",
                config={"namespace": "my-ns"},
            ),
        ]
        validator.validate_references(resources)

        validator.namespace_validator.validate.assert_called_once()
        validator.crd_validator.validate.assert_called_once()

    def test_validate_references_service_account_not_in_config(
        self, validator: KubernetesValidator, validation_report: ValidationReport
    ) -> None:
        """Test service account reference not in config reports info."""
        resources = [
            ResourceConfig(
                provider="kubernetes",
                type="deployments",
                name="my-app",
                config={"namespace": "default", "service_account": "custom-sa"},
            ),
        ]
        validator.validate_references(resources)

        sa_results = [r for r in validation_report.results if "serviceaccount" in r.check_name]
        assert len(sa_results) == 1
        assert sa_results[0].level == ValidationLevel.INFO

    def test_validate_references_service_selector_no_match(
        self, validator: KubernetesValidator, validation_report: ValidationReport
    ) -> None:
        """Test service selector not matching any deployment reports info."""
        resources = [
            ResourceConfig(
                provider="kubernetes",
                type="services",
                name="my-svc",
                config={"namespace": "default", "selector": {"app": "nonexistent"}},
            ),
        ]
        validator.validate_references(resources)

        selector_results = [r for r in validation_report.results if "selector" in r.check_name]
        assert len(selector_results) == 1
        assert selector_results[0].level == ValidationLevel.INFO


@pytest.mark.unit
class TestKubernetesValidatorConfigName:
    """References resolve through config.name when it differs from the resource name."""

    @staticmethod
    def _namespace() -> ResourceConfig:
        return ResourceConfig(
            provider="kubernetes",
            type="namespaces",
            name="ns-key",
            config={"name": "real-ns"},
        )

    def test_namespace_reference_uses_config_name(
        self, validator: KubernetesValidator, validation_report: ValidationReport
    ) -> None:
        """A namespace referenced by config.name is not reported as missing."""
        resources = [
            self._namespace(),
            ResourceConfig(
                provider="kubernetes",
                type="deployments",
                name="my-app",
                config={"namespace": "real-ns"},
            ),
        ]
        validator.validate_references(resources)

        assert not [r for r in validation_report.results if "_namespace" in r.check_name]

    def test_configmap_reference_uses_config_name(
        self, validator: KubernetesValidator, validation_report: ValidationReport
    ) -> None:
        """A configmap referenced by config.name from env_from is not an error."""
        resources = [
            ResourceConfig(
                provider="kubernetes",
                type="configmaps",
                name="cm-key",
                config={"name": "real-cm", "namespace": "default"},
            ),
            ResourceConfig(
                provider="kubernetes",
                type="deployments",
                name="my-app",
                config={"namespace": "default", "env_from": [{"configmap": "real-cm"}]},
            ),
        ]
        validator.validate_references(resources)

        assert not validation_report.has_errors()

    def test_api_references_use_config_name_for_namespaces(
        self, validator: KubernetesValidator
    ) -> None:
        """The API path passes config.name values as config_namespaces."""
        from infrafoundry.providers.kubernetes.validators.kubeconfig_validator import (
            KubeConnectionInfo,
        )

        conn = KubeConnectionInfo(
            server_url="https://k8s.example.com:6443",
            headers={},
            verify_ssl=True,
            connected=True,
        )
        validator.namespace_validator.validate = MagicMock()  # type: ignore[method-assign]
        validator.crd_validator.validate = MagicMock()  # type: ignore[method-assign]

        validator._validate_api_references([self._namespace()], conn)

        ctx = validator.namespace_validator.validate.call_args.args[0]
        assert ctx.config_namespaces == {"real-ns"}
