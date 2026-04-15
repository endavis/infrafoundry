"""Unit tests for KubeconfigValidator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator
from infrafoundry.providers.kubernetes.validators.kubeconfig_validator import (
    KubeconfigValidator,
)
from tests.helpers.env import make_env_config


@pytest.fixture
def validation_report():
    """Create a ValidationReport instance."""
    return ValidationReport()


@pytest.fixture
def api_validator(validation_report):
    """Create a BaseAPIValidator instance."""
    env_config = make_env_config(
        name="test-env",
        provider_settings={"kubernetes": {"kubeconfig_path": "/path/to/kubeconfig"}},
    )
    return BaseAPIValidator("kubernetes", env_config, validation_report)


@pytest.fixture
def validator(api_validator, validation_report):
    """Create a KubeconfigValidator instance."""
    return KubeconfigValidator(api_validator, validation_report)


def _make_kubeconfig(
    *,
    server: str = "https://k8s.example.com:6443",
    context_name: str = "test-context",
    cluster_name: str = "test-cluster",
    user_name: str = "test-user",
    token: str | None = "test-token",
    token_file: str | None = None,
    exec_auth: bool = False,
    ca_data: str | None = None,
    insecure: bool = False,
) -> dict:
    """Build a minimal kubeconfig dict for testing."""
    cluster_info: dict = {"server": server}
    if ca_data:
        cluster_info["certificate-authority-data"] = ca_data
    if insecure:
        cluster_info["insecure-skip-tls-verify"] = True

    user_info: dict = {}
    if token:
        user_info["token"] = token
    if token_file:
        user_info["tokenFile"] = token_file
    if exec_auth:
        user_info["exec"] = {"command": "aws", "args": ["eks", "get-token"]}

    return {
        "apiVersion": "v1",
        "kind": "Config",
        "current-context": context_name,
        "contexts": [
            {
                "name": context_name,
                "context": {"cluster": cluster_name, "user": user_name},
            }
        ],
        "clusters": [{"name": cluster_name, "cluster": cluster_info}],
        "users": [{"name": user_name, "user": user_info}],
    }


@pytest.mark.unit
class TestKubeconfigValidatorResolve:
    """Tests for kubeconfig path resolution."""

    def test_existing_kubeconfig(self, validator, validation_report, tmp_path):
        """Test with an existing kubeconfig file."""
        kubeconfig = tmp_path / "config"
        kubeconfig.write_text("apiVersion: v1\nkind: Config\ncurrent-context: x\n")
        # Will fail on context parsing but path check should pass
        validator.validate(str(kubeconfig))
        assert any(r.passed and "Kubeconfig found" in r.message for r in validation_report.results)

    def test_missing_kubeconfig(self, validator, validation_report):
        """Test with a missing kubeconfig file."""
        validator.validate("/nonexistent/kubeconfig")
        assert any(not r.passed and "not found" in r.message for r in validation_report.results)

    def test_no_path_default_exists(self, validator, validation_report):
        """Test fallback to default kubeconfig when it exists."""
        with patch.object(Path, "exists", return_value=True):
            validator.validate(None)
        assert any("default kubeconfig" in r.message for r in validation_report.results)

    def test_no_path_no_default(self, validator, validation_report):
        """Test warning when no kubeconfig path and no default."""
        with patch.object(Path, "exists", return_value=False):
            validator.validate(None)
        assert any(
            r.level == ValidationLevel.WARNING and not r.passed for r in validation_report.results
        )


@pytest.mark.unit
class TestKubeconfigValidatorParsing:
    """Tests for kubeconfig parsing."""

    def test_invalid_yaml(self, validator, validation_report, tmp_path):
        """Test error on invalid YAML."""
        kubeconfig = tmp_path / "config"
        kubeconfig.write_text("{{invalid yaml")
        validator.validate(str(kubeconfig))
        assert any(not r.passed and "parse" in r.message.lower() for r in validation_report.results)

    def test_missing_current_context(self, validator, validation_report, tmp_path):
        """Test error when current-context is missing."""
        kubeconfig = tmp_path / "config"
        kubeconfig.write_text("apiVersion: v1\nkind: Config\n")
        validator.validate(str(kubeconfig))
        assert any(
            not r.passed and "current-context" in r.message for r in validation_report.results
        )

    def test_context_not_found(self, validator, validation_report, tmp_path):
        """Test error when named context doesn't exist."""
        kubeconfig = tmp_path / "config"
        data = _make_kubeconfig(context_name="real-context")
        import yaml

        kubeconfig.write_text(yaml.dump(data))
        validator.validate(str(kubeconfig), context_override="nonexistent")
        assert any(not r.passed and "nonexistent" in r.message for r in validation_report.results)

    def test_explicit_context_override(self, validator, validation_report, tmp_path):
        """Test that context override takes precedence."""
        kubeconfig = tmp_path / "config"
        data = _make_kubeconfig(context_name="override-ctx")
        import yaml

        kubeconfig.write_text(yaml.dump(data))
        # Mock connectivity to avoid real API calls
        validator.api_validator.check_api_connectivity = MagicMock(return_value=False)
        validator.validate(str(kubeconfig), context_override="override-ctx")
        # Should not fail on context lookup
        context_errors = [
            r for r in validation_report.results if not r.passed and "context" in r.check_name
        ]
        assert len(context_errors) == 0


@pytest.mark.unit
class TestKubeconfigValidatorAuth:
    """Tests for authentication extraction."""

    def test_bearer_token(self, validator, validation_report, tmp_path):
        """Test bearer token extraction."""
        kubeconfig = tmp_path / "config"
        data = _make_kubeconfig(token="my-secret-token")
        import yaml

        kubeconfig.write_text(yaml.dump(data))
        validator.api_validator.check_api_connectivity = MagicMock(return_value=False)
        validator.validate(str(kubeconfig))
        assert validator.connection_info.headers.get("Authorization") == "Bearer my-secret-token"

    def test_token_file(self, validator, validation_report, tmp_path):
        """Test tokenFile extraction."""
        token_file = tmp_path / "token"
        token_file.write_text("file-based-token\n")

        kubeconfig = tmp_path / "config"
        data = _make_kubeconfig(token=None, token_file=str(token_file))
        import yaml

        kubeconfig.write_text(yaml.dump(data))
        validator.api_validator.check_api_connectivity = MagicMock(return_value=False)
        validator.validate(str(kubeconfig))
        assert validator.connection_info.headers.get("Authorization") == "Bearer file-based-token"

    def test_exec_auth_warning(self, validator, validation_report, tmp_path):
        """Test that exec-based auth produces a warning."""
        kubeconfig = tmp_path / "config"
        data = _make_kubeconfig(token=None, exec_auth=True)
        import yaml

        kubeconfig.write_text(yaml.dump(data))
        validator.api_validator.check_api_connectivity = MagicMock(return_value=False)
        validator.validate(str(kubeconfig))
        assert any(
            "exec-based auth" in r.message and r.level == ValidationLevel.WARNING
            for r in validation_report.results
        )


@pytest.mark.unit
class TestKubeconfigValidatorConnectivity:
    """Tests for API connectivity."""

    def test_connectivity_success(self, validator, validation_report, tmp_path):
        """Test successful connectivity."""
        kubeconfig = tmp_path / "config"
        data = _make_kubeconfig(insecure=True)
        import yaml

        kubeconfig.write_text(yaml.dump(data))

        validator.api_validator.check_api_connectivity = MagicMock(return_value=True)
        validator.api_validator.fetch_json = MagicMock(return_value={"gitVersion": "v1.28.0"})
        validator.validate(str(kubeconfig))
        assert validator.is_connected

    def test_connectivity_failure(self, validator, validation_report, tmp_path):
        """Test connectivity failure produces warning."""
        kubeconfig = tmp_path / "config"
        data = _make_kubeconfig(insecure=True)
        import yaml

        kubeconfig.write_text(yaml.dump(data))

        validator.api_validator.check_api_connectivity = MagicMock(return_value=False)
        validator.validate(str(kubeconfig))
        assert not validator.is_connected
        assert any(
            "skipped" in r.message.lower() and r.level == ValidationLevel.WARNING
            for r in validation_report.results
        )

    def test_no_auth_skips_connectivity(self, validator, validation_report, tmp_path):
        """Test that missing auth skips connectivity test."""
        kubeconfig = tmp_path / "config"
        data = _make_kubeconfig(token=None, insecure=True)
        import yaml

        kubeconfig.write_text(yaml.dump(data))
        validator.validate(str(kubeconfig))
        assert not validator.is_connected
        assert any("No auth" in r.message for r in validation_report.results)
