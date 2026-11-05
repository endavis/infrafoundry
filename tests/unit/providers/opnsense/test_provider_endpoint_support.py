"""Provider-level wiring of the OPNsense endpoint check (#1239)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.opnsense import OPNsenseProvider
from tests.helpers.env import make_env_config

_BASE = "infrafoundry.providers.opnsense.services.base.BaseService.client_from_environment"


def _provider(tmp_path: Path) -> OPNsenseProvider:
    return OPNsenseProvider(config_dir=tmp_path, output_dir=tmp_path)


def test_check_endpoint_support_returns_errors_and_warnings(tmp_path: Path) -> None:
    client = MagicMock()
    client.detect_version.return_value = "26.1.6_2"
    with patch(_BASE, return_value=client):
        result = _provider(tmp_path).check_endpoint_support("dev", ["system.hostname"])
    assert result["warnings"] == []
    assert any("system.hostname" in e for e in result["errors"])


def test_check_endpoint_support_clean(tmp_path: Path) -> None:
    client = MagicMock()
    client.detect_version.return_value = "26.1.6"
    with patch(_BASE, return_value=client):
        result = _provider(tmp_path).check_endpoint_support("dev", ["firewall.rules"])
    assert result == {"errors": [], "warnings": []}


def test_check_endpoint_support_missing_settings_is_a_warning(tmp_path: Path) -> None:
    with patch(_BASE, side_effect=ValueError("No opnsense provider settings")):
        result = _provider(tmp_path).check_endpoint_support("dev", ["firewall.rules"])
    assert result["errors"] == []
    assert len(result["warnings"]) == 1


def test_validate_references_runs_the_endpoint_check(tmp_path: Path) -> None:
    env_config = make_env_config(provider_settings={"opnsense": {}})
    report = ValidationReport()
    with patch("infrafoundry.providers.opnsense.OPNsenseValidator") as validator_cls:
        _provider(tmp_path).validate_references([], env_config, report)
        _provider(tmp_path).validate_references_in_context([], [], env_config, report)
    assert validator_cls.return_value.validate_endpoint_support.call_count == 2
