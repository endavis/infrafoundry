"""Unit tests for KubernetesValidator."""

from pathlib import Path
from unittest.mock import patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import (
    ProviderValidator,
    ValidationLevel,
    ValidationReport,
)
from infrafoundry.providers.kubernetes.validator import KubernetesValidator


@pytest.fixture
def mock_env_config():
    """Create a mock environment config."""
    return {
        "name": "test-env",
        "provider_settings": {
            "kubernetes": {
                "kubeconfig_path": "/path/to/kubeconfig",
            }
        },
    }


@pytest.fixture
def validation_report():
    """Create a ValidationReport instance."""
    return ValidationReport()


@pytest.fixture
def validator(mock_env_config, validation_report):
    """Create a KubernetesValidator instance."""
    return KubernetesValidator(mock_env_config, validation_report)


@pytest.mark.unit
class TestKubernetesValidatorProtocol:
    """Tests verifying KubernetesValidator implements ProviderValidator protocol."""

    def test_implements_provider_validator_protocol(self, validator):
        """Test that KubernetesValidator implements ProviderValidator protocol."""
        assert isinstance(validator, ProviderValidator)
        assert hasattr(validator, "env_config")
        assert hasattr(validator, "report")
        assert hasattr(validator, "validate_connectivity")
        assert hasattr(validator, "validate_references")


@pytest.mark.unit
class TestKubernetesValidatorConnectivity:
    """Tests for KubernetesValidator.validate_connectivity."""

    def test_validate_connectivity_with_existing_kubeconfig(
        self, mock_env_config, validation_report
    ):
        """Test validation when kubeconfig exists."""
        with patch.object(Path, "exists", return_value=True):
            validator = KubernetesValidator(mock_env_config, validation_report)
            validator.validate_connectivity()

        # Should have success result
        assert any(r.passed for r in validation_report.results)
        assert any("Kubeconfig found" in r.message for r in validation_report.results)

    def test_validate_connectivity_with_missing_kubeconfig(
        self, mock_env_config, validation_report
    ):
        """Test validation when kubeconfig doesn't exist."""
        with patch.object(Path, "exists", return_value=False):
            validator = KubernetesValidator(mock_env_config, validation_report)
            validator.validate_connectivity()

        # Should have error result
        assert any(not r.passed for r in validation_report.results)
        assert any("not found" in r.message for r in validation_report.results)

    def test_validate_connectivity_no_kubeconfig_path_with_default(self, validation_report):
        """Test validation when no kubeconfig path specified but default exists."""
        env_config = {
            "name": "test-env",
            "provider_settings": {"kubernetes": {}},
        }

        with patch.object(Path, "exists", return_value=True):
            validator = KubernetesValidator(env_config, validation_report)
            validator.validate_connectivity()

        # Should have info result about using default
        assert any("default kubeconfig" in r.message for r in validation_report.results)

    def test_validate_connectivity_no_kubeconfig_path_no_default(self, validation_report):
        """Test validation when no kubeconfig path and no default."""
        env_config = {
            "name": "test-env",
            "provider_settings": {"kubernetes": {}},
        }

        with patch.object(Path, "exists", return_value=False):
            validator = KubernetesValidator(env_config, validation_report)
            validator.validate_connectivity()

        # Should have warning result
        assert any(
            r.level == ValidationLevel.WARNING and not r.passed for r in validation_report.results
        )


@pytest.mark.unit
class TestKubernetesValidatorReferences:
    """Tests for KubernetesValidator.validate_references."""

    def test_validate_references_empty_resources(self, validator, validation_report):
        """Test validation with no resources."""
        validator.validate_references([])

        # Should have no errors
        assert not validation_report.has_errors()

    def test_validate_references_valid_configmap_ref(self, validator, validation_report):
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

    def test_validate_references_invalid_configmap_ref(self, validator, validation_report):
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

    def test_validate_references_invalid_secret_ref(self, validator, validation_report):
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

    def test_validate_references_reports_success(self, validator, validation_report):
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
