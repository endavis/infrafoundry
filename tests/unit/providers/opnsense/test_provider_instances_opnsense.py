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


class TestInstanceGeneration:
    """Non-primary firewalls generate files from the shared templates (#1462)."""

    def _gen(self, tmp_path: Path, firewall: str | None) -> OPNsenseProvider:
        provider = OPNsenseProvider(
            config_dir=tmp_path / "cfg", output_dir=tmp_path / "out", firewall=firewall
        )
        provider.set_environment("dev")
        return provider

    def test_terraform_is_generated_for_an_instance(self, tmp_path: Path) -> None:
        self._gen(tmp_path, "fw-b").generate_terraform([])
        out = tmp_path / "out" / "dev" / "terraform" / "opnsense@fw-b"
        assert "browningluke/opnsense" in (out / "provider.tf").read_text()
        assert (out / "variables.tf").exists()
        assert (out / "outputs.tf").exists()

    def test_ansible_is_generated_for_an_instance(self, tmp_path: Path) -> None:
        self._gen(tmp_path, "fw-b").generate_ansible([])
        out = tmp_path / "out" / "dev" / "ansible" / "opnsense@fw-b"
        assert (out / "playbook.yml").exists()
        assert (out / "inventory.yml").exists()

    def test_instances_do_not_touch_the_primarys_files_or_state(self, tmp_path: Path) -> None:
        self._gen(tmp_path, None).generate_terraform([])
        primary = tmp_path / "out" / "dev" / "terraform" / "opnsense"
        state_file = primary / "terraform.tfstate"
        state_file.write_text("{}")
        self._gen(tmp_path, "fw-b").generate_terraform([])
        assert (primary / "provider.tf").exists()
        assert state_file.read_text() == "{}"
        assert (tmp_path / "out" / "dev" / "terraform" / "opnsense@fw-b" / "provider.tf").exists()


class TestTerraformEnvVars:
    """Each firewall feeds Terraform its own endpoint (#1462)."""

    def _vars(
        self, tmp_path: Path, settings: dict[str, Any], firewall: str | None
    ) -> dict[str, str]:
        env = make_env_config(provider_settings={"opnsense": settings})
        with patch.object(OPNsenseProvider, "_load_environment_config", return_value=env):
            return _provider(tmp_path, firewall).get_terraform_env_vars()

    def test_primary_and_instance_get_their_own_url(self, tmp_path: Path) -> None:
        assert (
            self._vars(tmp_path, MULTI, None)["TF_VAR_opnsense_api_url"]
            == "https://fw-a.example.com"
        )
        assert (
            self._vars(tmp_path, MULTI, "fw-b")["TF_VAR_opnsense_api_url"]
            == "https://fw-b.example.com"
        )

    def test_env_override_reaches_only_the_primary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INFRAFOUNDRY_ALLOW_ENV_OVERRIDE", "1")
        monkeypatch.setenv("OPNSENSE_API_URL", "https://override.example.net")
        assert (
            self._vars(tmp_path, MULTI, None)["TF_VAR_opnsense_api_url"]
            == "https://override.example.net"
        )
        assert (
            self._vars(tmp_path, MULTI, "fw-b")["TF_VAR_opnsense_api_url"]
            == "https://fw-b.example.com"
        )

    def test_flat_settings_are_unchanged(self, tmp_path: Path) -> None:
        flat = {"api_url": "https://fw.example.com", "api_key": "k", "api_secret": "s"}
        assert self._vars(tmp_path, flat, None) == {
            "TF_VAR_opnsense_api_url": "https://fw.example.com",
            "TF_VAR_opnsense_api_key": "k",
            "TF_VAR_opnsense_api_secret": "s",
        }


class TestKeaReset:
    @pytest.mark.parametrize(
        ("firewall", "expected"), [(None, "opnsense"), ("fw-b", "opnsense@fw-b")]
    )
    def test_reset_targets_the_providers_own_name(
        self, tmp_path: Path, firewall: str | None, expected: str
    ) -> None:
        with patch("infrafoundry.providers.opnsense.components.kea_dhcp.KeaDHCPManager") as mgr:
            _provider(tmp_path, firewall).reset_kea_dhcpv4("dev")
            _provider(tmp_path, firewall).reset_kea_dhcpv6("dev")
        mgr.return_value.reset_dhcpv4.assert_called_once_with("dev", expected)
        mgr.return_value.reset_dhcpv6.assert_called_once_with("dev", expected)
