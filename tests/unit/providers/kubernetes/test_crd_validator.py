"""Unit tests for CRDValidator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator
from infrafoundry.providers.kubernetes.validators.crd_validator import CRDValidator


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
    """Create a CRDValidator instance."""
    return CRDValidator(api_validator, validation_report)


def _crd_api_response(groups: list[str]) -> dict:
    """Build a mock CRD list response."""
    return {
        "items": [{"spec": {"group": g}} for g in groups],
    }


@pytest.mark.unit
class TestCRDValidator:
    """Tests for CRDValidator."""

    def test_existing_crd(self, validator, validation_report, api_validator):
        """Test that existing CRDs produce success."""
        api_validator.fetch_json = MagicMock(
            return_value=_crd_api_response(["cert-manager.io", "traefik.io"])
        )
        manifests = [
            ResourceConfig(
                provider="kubernetes",
                type="manifests",
                name="my-cert",
                config={"apiVersion": "cert-manager.io/v1", "kind": "Certificate"},
            ),
        ]
        validator.validate(
            server_url="https://k8s:6443",
            headers={"Authorization": "Bearer tok"},
            verify_ssl=False,
            manifests=manifests,
        )
        assert any(r.passed and "cert-manager.io" in r.message for r in validation_report.results)

    def test_missing_crd_error(self, validator, validation_report, api_validator):
        """Test that missing CRDs produce ERROR."""
        api_validator.fetch_json = MagicMock(return_value=_crd_api_response(["some-other.io"]))
        manifests = [
            ResourceConfig(
                provider="kubernetes",
                type="manifests",
                name="my-cert",
                config={"apiVersion": "cert-manager.io/v1", "kind": "Certificate"},
            ),
        ]
        validator.validate(
            server_url="https://k8s:6443",
            headers={"Authorization": "Bearer tok"},
            verify_ssl=False,
            manifests=manifests,
        )
        assert any(
            not r.passed and r.level == ValidationLevel.ERROR and "cert-manager.io" in r.message
            for r in validation_report.results
        )

    def test_standard_api_groups_skipped(self, validator, validation_report, api_validator):
        """Test that standard K8s API groups are not checked."""
        api_validator.fetch_json = MagicMock(return_value=_crd_api_response([]))
        manifests = [
            ResourceConfig(
                provider="kubernetes",
                type="manifests",
                name="my-deploy",
                config={"apiVersion": "apps/v1", "kind": "Deployment"},
            ),
        ]
        validator.validate(
            server_url="https://k8s:6443",
            headers={"Authorization": "Bearer tok"},
            verify_ssl=False,
            manifests=manifests,
        )
        # No CRD checks should be emitted for standard groups
        api_validator.fetch_json.assert_not_called()

    def test_no_manifests_skips(self, validator, validation_report, api_validator):
        """Test that empty manifests list makes no API calls."""
        api_validator.fetch_json = MagicMock()
        validator.validate(
            server_url="https://k8s:6443",
            headers={"Authorization": "Bearer tok"},
            verify_ssl=False,
            manifests=[],
        )
        api_validator.fetch_json.assert_not_called()

    def test_api_failure_graceful(self, validator, validation_report, api_validator):
        """Test graceful handling when CRD API call fails."""
        api_validator.fetch_json = MagicMock(return_value=None)
        manifests = [
            ResourceConfig(
                provider="kubernetes",
                type="manifests",
                name="my-cert",
                config={"apiVersion": "cert-manager.io/v1", "kind": "Certificate"},
            ),
        ]
        validator.validate(
            server_url="https://k8s:6443",
            headers={"Authorization": "Bearer tok"},
            verify_ssl=False,
            manifests=manifests,
        )
        # No CRD-specific error/success checks since API failed
        crd_checks = [
            r for r in validation_report.results if "kubernetes_crd_cert-manager" in r.check_name
        ]
        assert len(crd_checks) == 0
