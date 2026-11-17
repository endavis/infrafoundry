"""The OPNsense provider as a per-firewall instance (#1450)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.opnsense import OPNsenseProvider
from tests.helpers.env import make_env_config

MULTI: dict[str, Any] = {
    "primary": "fw-a",
    "firewalls": {
        "fw-a": {"api_url": "https://fw-a.example.com", "api_key": "k", "api_secret": "s"},
        "fw-b": {"api_url": "https://fw-b.example.com", "api_key": "k", "api_secret": "s"},
    },
}


def _provider(tmp_path: Path, firewall: str | None = None) -> OPNsenseProvider:
    return OPNsenseProvider(config_dir=tmp_path, output_dir=tmp_path, firewall=firewall)


def test_default_provider_keeps_the_plain_name(tmp_path: Path) -> None:
    assert _provider(tmp_path).name == "opnsense"


def test_spawn_instance_is_named_after_the_firewall(tmp_path: Path) -> None:
    base = _provider(tmp_path)
    instance = base.spawn_instance("fw-b")
    assert instance.name == "opnsense@fw-b"
    assert instance.config_dir == base.config_dir
    assert instance.terraform_dir == tmp_path / "terraform" / "opnsense@fw-b"


def test_spawn_instance_inherits_the_current_environment(tmp_path: Path) -> None:
    base = _provider(tmp_path)
    base.set_environment("prod")
    instance = base.spawn_instance("fw-b")
    assert instance._current_environment == "prod"


def test_instances_do_not_reregister_extractors(tmp_path: Path) -> None:
    base = _provider(tmp_path)
    with patch.object(OPNsenseProvider, "_register_extractors") as register:
        base.spawn_instance("fw-b")
    register.assert_not_called()


def test_reconfigure_hooks_use_the_instance_name(tmp_path: Path) -> None:
    instance = _provider(tmp_path, "fw-b")
    with patch("infrafoundry.providers.opnsense.services.kea_dhcp.KeaDHCPService") as service:
        instance._reconfigure_kea("prod")
    service.from_environment.assert_called_once_with("prod", "opnsense@fw-b", tmp_path)


def test_post_apply_hook_syncs_for_the_instance(tmp_path: Path) -> None:
    instance = _provider(tmp_path, "fw-b")
    with patch(
        "infrafoundry.providers.opnsense.services.hasync_status.run_ha_sync_after_apply",
        return_value="line",
    ) as sync:
        assert instance.post_apply_hook("prod", True) == "line"
    sync.assert_called_once_with("prod", "opnsense@fw-b", tmp_path, True)


class TestFirewallLabel:
    def _with_settings(self, tmp_path: Path, settings: dict[str, Any]) -> Any:
        env = make_env_config(provider_settings={"opnsense": settings})
        return patch(
            "infrafoundry.core.config.ConfigManager",
            return_value=MagicMock(load_environment=MagicMock(return_value=env)),
        )

    def test_label_for_primary_and_instance(self, tmp_path: Path) -> None:
        with self._with_settings(tmp_path, MULTI):
            assert _provider(tmp_path).firewall_label("prod") == "fw-a"
            assert _provider(tmp_path, "fw-b").firewall_label("prod") == "fw-b"

    def test_no_label_for_a_flat_config(self, tmp_path: Path) -> None:
        with self._with_settings(tmp_path, {"api_url": "https://fw.example.com"}):
            assert _provider(tmp_path).firewall_label("prod") is None

    def test_no_label_without_settings(self, tmp_path: Path) -> None:
        with patch("infrafoundry.core.config.ConfigManager") as manager:
            manager.return_value.load_environment.side_effect = FileNotFoundError
            assert _provider(tmp_path).firewall_label("prod") is None

    def test_label_is_cached_per_environment(self, tmp_path: Path) -> None:
        provider = _provider(tmp_path)
        with self._with_settings(tmp_path, MULTI) as manager:
            provider.firewall_label("prod")
            provider.firewall_label("prod")
        assert manager.call_count == 1


class TestValidationLabels:
    def _env(self) -> Any:
        return make_env_config(provider_settings={"opnsense": MULTI})

    def test_results_get_a_firewall_prefix_when_firewalls_are_declared(
        self, tmp_path: Path
    ) -> None:
        report = ValidationReport()

        def fake_connectivity(self: Any) -> None:
            self.report.add_check("c", True, "connected")

        with patch(
            "infrafoundry.providers.opnsense.OPNsenseValidator.validate_connectivity",
            fake_connectivity,
        ):
            _provider(tmp_path, "fw-b").validate_connectivity(self._env(), report)
            _provider(tmp_path).validate_connectivity(self._env(), report)
        assert [r.message for r in report.results] == ["[fw-b] connected", "[fw-a] connected"]

    def test_flat_config_results_are_not_prefixed(self, tmp_path: Path) -> None:
        report = ValidationReport()
        env = make_env_config(provider_settings={"opnsense": {"api_url": "x"}})

        def fake_connectivity(self: Any) -> None:
            self.report.add_check("c", True, "connected")

        with patch(
            "infrafoundry.providers.opnsense.OPNsenseValidator.validate_connectivity",
            fake_connectivity,
        ):
            _provider(tmp_path).validate_connectivity(env, report)
        assert [r.message for r in report.results] == ["connected"]

    def test_validator_is_built_for_the_instance(self, tmp_path: Path) -> None:
        with patch("infrafoundry.providers.opnsense.OPNsenseValidator") as validator_cls:
            _provider(tmp_path, "fw-b").validate_references([], self._env(), ValidationReport())
        assert validator_cls.call_args.kwargs["provider_name"] == "opnsense@fw-b"

    def test_offline_reports_firewalls_shape_errors_once(self, tmp_path: Path) -> None:
        bad = make_env_config(provider_settings={"opnsense": {"firewalls": {"a": {}, "b": {}}}})
        primary_report = ValidationReport()
        instance_report = ValidationReport()
        _provider(tmp_path).validate_offline([], [], bad, primary_report)
        _provider(tmp_path, "b").validate_offline([], [], bad, instance_report)
        names = [r.check_name for r in primary_report.results]
        assert "opnsense_firewalls_settings" in names
        assert "opnsense_firewalls_settings" not in [r.check_name for r in instance_report.results]

    def test_each_firewall_validates_only_its_own_resources(self, tmp_path: Path) -> None:
        def vip(provider: str) -> ResourceConfig:
            return ResourceConfig(
                name="carp",
                type="interfaces.virtual_ips",
                provider=provider,
                config={"mode": "carp", "vhid": 1, "interface": "lan", "subnet": "192.0.2.1"},
            )

        env = self._env()
        for provider_name, firewall in (("opnsense", None), ("opnsense@fw-b", "fw-b")):
            report = ValidationReport()
            _provider(tmp_path, firewall).validate_offline(
                [vip(provider_name)], [vip(provider_name)], env, report
            )
            assert not any("vhid" in r.message.lower() and not r.passed for r in report.results)


@pytest.mark.parametrize("firewall", [None, "fw-b"])
def test_check_endpoint_support_resolves_the_instance(tmp_path: Path, firewall: str | None) -> None:
    client = MagicMock()
    client.detect_version.return_value = "26.1.6"
    with patch(
        "infrafoundry.providers.opnsense.services.base.BaseService.client_from_environment",
        return_value=client,
    ) as factory:
        _provider(tmp_path, firewall).check_endpoint_support("dev", ["firewall.rules"])
    expected = "opnsense" if firewall is None else f"opnsense@{firewall}"
    assert factory.call_args.args[1] == expected
