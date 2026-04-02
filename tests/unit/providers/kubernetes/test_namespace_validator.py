"""Unit tests for NamespaceValidator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator
from infrafoundry.providers.kubernetes.validators.namespace_validator import (
    NamespaceValidator,
)


@pytest.fixture
def validation_report():
    """Create a ValidationReport instance."""
    return ValidationReport()


@pytest.fixture
def api_validator(validation_report):
    """Create a BaseAPIValidator instance."""
    env_config = {
        "name": "test-env",
        "provider_settings": {"kubernetes": {}},
    }
    return BaseAPIValidator("kubernetes", env_config, validation_report)


@pytest.fixture
def validator(api_validator, validation_report):
    """Create a NamespaceValidator instance."""
    return NamespaceValidator(api_validator, validation_report)


def _namespace_api_response(names: list[str]) -> dict:
    """Build a mock Kubernetes namespace list response."""
    return {
        "items": [{"metadata": {"name": n}} for n in names],
    }


@pytest.mark.unit
class TestNamespaceValidator:
    """Tests for NamespaceValidator."""

    def test_existing_namespace(self, validator, validation_report, api_validator):
        """Test that existing namespaces produce INFO."""
        api_validator.fetch_json = MagicMock(
            return_value=_namespace_api_response(["default", "kube-system", "my-ns"])
        )
        validator.validate(
            server_url="https://k8s:6443",
            headers={"Authorization": "Bearer tok"},
            verify_ssl=False,
            referenced_namespaces={"my-ns"},
            config_namespaces=set(),
        )
        assert any(
            "exists in cluster" in r.message and r.check_name == "kubernetes_namespace_my-ns"
            for r in validation_report.results
        )

    def test_namespace_in_config(self, validator, validation_report, api_validator):
        """Test that namespaces in config produce 'will be created' INFO."""
        api_validator.fetch_json = MagicMock(return_value=_namespace_api_response(["default"]))
        validator.validate(
            server_url="https://k8s:6443",
            headers={"Authorization": "Bearer tok"},
            verify_ssl=False,
            referenced_namespaces={"new-ns"},
            config_namespaces={"new-ns"},
        )
        assert any("will be created" in r.message for r in validation_report.results)

    def test_namespace_missing_warning(self, validator, validation_report, api_validator):
        """Test that missing namespaces produce WARNING."""
        api_validator.fetch_json = MagicMock(return_value=_namespace_api_response(["default"]))
        validator.validate(
            server_url="https://k8s:6443",
            headers={"Authorization": "Bearer tok"},
            verify_ssl=False,
            referenced_namespaces={"unknown-ns"},
            config_namespaces=set(),
        )
        assert any(
            r.level == ValidationLevel.WARNING and "not found" in r.message
            for r in validation_report.results
        )

    def test_api_failure_graceful(self, validator, validation_report, api_validator):
        """Test graceful handling of API failure."""
        api_validator.fetch_json = MagicMock(return_value=None)
        validator.validate(
            server_url="https://k8s:6443",
            headers={"Authorization": "Bearer tok"},
            verify_ssl=False,
            referenced_namespaces={"my-ns"},
            config_namespaces=set(),
        )
        # Should not have namespace-specific checks since API failed
        ns_checks = [
            r for r in validation_report.results if r.check_name == "kubernetes_namespace_my-ns"
        ]
        assert len(ns_checks) == 0

    def test_empty_namespaces_skips(self, validator, validation_report, api_validator):
        """Test that empty namespaces set makes no API calls."""
        api_validator.fetch_json = MagicMock()
        validator.validate(
            server_url="https://k8s:6443",
            headers={"Authorization": "Bearer tok"},
            verify_ssl=False,
            referenced_namespaces=set(),
            config_namespaces=set(),
        )
        api_validator.fetch_json.assert_not_called()
