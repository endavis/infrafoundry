"""Tests for AWSProvider metadata, registration and the destroy hook."""

from pathlib import Path

import pytest

from infrafoundry.core.provider_registry import ProviderRegistry
from infrafoundry.providers import AWSProvider

from .conftest import make_env, res, volume


def test_registry_discovers_aws(tmp_path: Path) -> None:
    registry = ProviderRegistry(tmp_path, tmp_path / "out")
    registry.discover_and_register_all()
    assert isinstance(registry.get_provider("aws"), AWSProvider)


def test_metadata(provider: AWSProvider) -> None:
    assert provider.get_resource_types() == ["security_group", "instance", "ebs_volume"]
    assert provider.get_terraform_resource_types() == {
        "security_group": ["aws_security_group"],
        "instance": ["aws_instance"],
        "ebs_volume": ["aws_ebs_volume"],
    }
    assert provider.get_dependencies() == {
        "security_group": [],
        "instance": ["security_group"],
        "ebs_volume": ["instance"],
    }


def test_validate_config_needs_name(provider: AWSProvider) -> None:
    assert provider.validate_config({"name": "x"})
    assert not provider.validate_config({})


def test_generate_ansible_creates_directories_only(provider: AWSProvider) -> None:
    provider.generate_ansible([])
    assert provider.ansible_dir.exists()
    assert not list(provider.ansible_dir.glob("*"))


class TestKeptOnDestroy:
    def test_protected_by_default_and_when_true(self, provider: AWSProvider) -> None:
        resources = [volume("data-vol"), volume("other", prevent_destroy=True)]
        assert provider.get_state_addresses_kept_on_destroy(resources) == [
            "aws_ebs_volume.data_vol",
            "aws_ebs_volume.other",
        ]

    def test_unprotected_and_other_types_are_not_kept(self, provider: AWSProvider) -> None:
        resources = [volume("data", prevent_destroy=False), res("web", "security_group")]
        assert provider.get_state_addresses_kept_on_destroy(resources) == []


def test_connectivity_makes_no_network_call_and_warns_without_region(
    provider: AWSProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    from infrafoundry.core.validation import ValidationLevel, ValidationReport

    report = ValidationReport()
    provider.validate_connectivity(make_env({}), report)
    assert any(
        not r.passed
        and r.level == ValidationLevel.WARNING
        and r.check_name == "aws_settings_region"
        for r in report.results
    )
    assert not report.has_errors()


def test_validate_references_reports_tailscale_schema_and_config(provider: AWSProvider) -> None:
    from infrafoundry.core.validation import ValidationReport

    from .conftest import instance

    report = ValidationReport()
    bad = instance("app", tailscale={"hostname": "app"})
    provider.validate_references([bad, volume("data", availability_zone="")], make_env({}), report)
    names = {r.check_name for r in report.results if not r.passed}
    assert "aws_tailscale_schema_app" in names
    assert "aws_ebs_volume_data_availability_zone" in names
