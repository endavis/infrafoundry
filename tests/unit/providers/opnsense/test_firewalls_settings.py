"""Per-firewall settings, env override restriction and clients (#1450)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from infrafoundry.providers.opnsense.firewalls import (
    allows_env_override,
    firewall_label,
    firewall_settings,
    ha_backup_name,
    ha_primary_name,
    validate_firewalls_settings,
)
from infrafoundry.providers.opnsense.services._credentials import (
    API_URL_ENV_VAR,
    GATE_ENV_VAR,
    reset_warning_state_for_tests,
    resolve_credentials,
    resolve_ssh_settings,
)
from infrafoundry.providers.opnsense.services.hasync_status import run_ha_sync_after_apply
from infrafoundry.providers.opnsense.services.vlan import VlanService

CREDENTIALS_LOGGER = "infrafoundry.providers.opnsense.services._credentials"

FLAT: dict[str, Any] = {"api_url": "https://fw.example.com", "api_key": "k", "api_secret": "s"}
MULTI: dict[str, Any] = {
    "verify_ssl": False,
    "ssh_user": "admin",
    "primary": "fw-a",
    "firewalls": {
        "fw-a": {
            "api_url": "https://fw-a.example.com",
            "api_key": "ka",
            "api_secret": "sa",
            "ha_backup": "fw-b",
        },
        "fw-b": {
            "api_url": "https://fw-b.example.com",
            "api_key": "kb",
            "api_secret": "sb",
            "verify_ssl": True,
            "ha_sync_after_apply": False,
        },
    },
}


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_warning_state_for_tests()
    for var in (GATE_ENV_VAR, API_URL_ENV_VAR):
        monkeypatch.delenv(var, raising=False)


class TestFirewallSettings:
    def test_flat_settings_are_returned_unchanged(self) -> None:
        assert firewall_settings(FLAT, "opnsense") is FLAT

    def test_none_stays_none(self) -> None:
        assert firewall_settings(None, "opnsense") is None

    def test_primary_gets_defaults_merged_with_its_entry(self) -> None:
        settings = firewall_settings(MULTI, "opnsense")
        assert settings == {
            "verify_ssl": False,
            "ssh_user": "admin",
            "api_url": "https://fw-a.example.com",
            "api_key": "ka",
            "api_secret": "sa",
        }

    def test_entry_overrides_shared_defaults(self) -> None:
        settings = firewall_settings(MULTI, "opnsense@fw-b")
        assert settings is not None
        assert settings["verify_ssl"] is True
        assert settings["ssh_user"] == "admin"
        assert settings["ha_sync_after_apply"] is False
        assert "firewalls" not in settings and "primary" not in settings

    def test_unknown_firewall_resolves_to_empty(self) -> None:
        assert firewall_settings(MULTI, "opnsense@nope") == {}

    def test_ambiguous_primary_resolves_to_empty(self) -> None:
        ambiguous: dict[str, Any] = {"firewalls": {"a": {}, "b": {}}}
        assert firewall_settings(ambiguous, "opnsense") == {}

    def test_accepts_an_environment_config(self) -> None:
        env = MagicMock()
        env.get_provider_settings.return_value = MULTI
        settings = firewall_settings(env, "opnsense@fw-b")
        assert settings is not None and settings["api_key"] == "kb"
        env.get_provider_settings.assert_called_with("opnsense")

    def test_label_only_when_firewalls_declared(self) -> None:
        assert firewall_label(FLAT, "opnsense") is None
        assert firewall_label(MULTI, "opnsense") == "fw-a"
        assert firewall_label(MULTI, "opnsense@fw-b") == "fw-b"

    def test_ha_backup_name(self) -> None:
        assert ha_backup_name(MULTI, "opnsense") == "fw-b"
        assert ha_backup_name(MULTI, "opnsense@fw-b") is None
        assert ha_backup_name(FLAT, "opnsense") is None

    def test_ha_primary_name(self) -> None:
        assert ha_primary_name(MULTI, "opnsense@fw-b") == "fw-a"
        assert ha_primary_name(MULTI, "opnsense") is None
        assert ha_primary_name(FLAT, "opnsense") is None
        undeclared = {"firewalls": {"fw-a": {}, "fw-c": {}}, "primary": "fw-a"}
        assert ha_primary_name(undeclared, "opnsense@fw-c") is None

    def test_ha_primary_name_ignores_self_reference(self) -> None:
        selfref = {"firewalls": {"fw-a": {"ha_backup": "fw-a"}}}
        assert ha_primary_name(selfref, "opnsense") is None

    def test_env_override_only_for_the_primary(self) -> None:
        assert allows_env_override("opnsense") is True
        assert allows_env_override("opnsense@fw-b") is False


class TestValidateFirewallsSettings:
    def test_valid_and_flat_shapes_have_no_errors(self) -> None:
        assert validate_firewalls_settings(MULTI) == []
        assert validate_firewalls_settings(FLAT) == []
        assert validate_firewalls_settings(None) == []

    def test_single_firewall_needs_no_primary(self) -> None:
        assert validate_firewalls_settings({"firewalls": {"only": {}}}) == []

    def test_primary_required_with_two_firewalls(self) -> None:
        errors = validate_firewalls_settings({"firewalls": {"a": {}, "b": {}}})
        assert any("'primary' is required" in e for e in errors)

    def test_unknown_primary(self) -> None:
        errors = validate_firewalls_settings({"primary": "z", "firewalls": {"a": {}}})
        assert any("primary 'z' is not declared" in e for e in errors)

    def test_top_level_credentials_clash(self) -> None:
        errors = validate_firewalls_settings({**FLAT, "firewalls": {"a": {}}})
        assert any("api_url, api_key, api_secret" in e for e in errors)

    def test_invalid_names_and_entries(self) -> None:
        errors = validate_firewalls_settings({"primary": "A_1", "firewalls": {"A_1": {}, "b": 3}})
        assert any("firewall name 'A_1' is invalid" in e for e in errors)
        assert any("firewall 'b' must be a mapping" in e for e in errors)

    def test_empty_map(self) -> None:
        assert validate_firewalls_settings({"firewalls": {}})

    def test_ha_backup_unknown_or_self(self) -> None:
        settings = {
            "primary": "a",
            "firewalls": {"a": {"ha_backup": "z"}, "b": {"ha_backup": "b"}},
        }
        errors = validate_firewalls_settings(settings)
        assert any("ha_backup 'z' is not declared" in e for e in errors)
        assert any("cannot name the firewall itself" in e for e in errors)


class TestEnvOverrideRestriction:
    def test_primary_honours_the_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_URL_ENV_VAR, "https://override.example.com")
        assert resolve_credentials(FLAT)[0] == "https://override.example.com"

    def test_instance_ignores_the_override_and_warns_once(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_URL_ENV_VAR, "https://override.example.com")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            first = resolve_credentials(FLAT, allow_env_override=False)
            second = resolve_credentials(FLAT, allow_env_override=False)
        assert first == second
        assert first[0] == "https://fw.example.com"
        warnings = [r for r in caplog.records if "primary firewall" in r.getMessage()]
        assert len(warnings) == 1

    def test_instance_without_the_gate_does_not_warn(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            resolve_credentials(FLAT, allow_env_override=False)
        assert caplog.records == []

    def test_instance_ssh_settings_ignore_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv("OPNSENSE_SSH_HOST", "198.51.100.9")
        monkeypatch.setenv("OPNSENSE_SSH_USER", "intruder")
        ssh = resolve_ssh_settings(
            {**FLAT, "ssh_user": "admin", "ssh_port": 2222}, allow_env_override=False
        )
        assert (ssh.host, ssh.user, ssh.port) == ("fw.example.com", "admin", "2222")


def _write_settings(tmp_path: Path) -> Path:
    env = tmp_path / "envs" / "prod"
    env.mkdir(parents=True)
    (env / "settings.yaml").write_text(
        yaml.safe_dump({"name": "prod", "provider_settings": {"opnsense": MULTI}})
    )
    return tmp_path / "envs"


class TestClientFromEnvironment:
    def test_builds_one_client_per_firewall(self, tmp_path: Path) -> None:
        envs = _write_settings(tmp_path)
        primary = VlanService.client_from_environment("prod", "opnsense", envs)
        backup = VlanService.client_from_environment("prod", "opnsense@fw-b", envs)
        assert primary.base_url == "https://fw-a.example.com"
        assert backup.base_url == "https://fw-b.example.com"

    def test_instance_client_ignores_the_env_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        envs = _write_settings(tmp_path)
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_URL_ENV_VAR, "https://override.example.com")
        primary = VlanService.client_from_environment("prod", "opnsense", envs)
        backup = VlanService.client_from_environment("prod", "opnsense@fw-b", envs)
        assert primary.base_url == "https://override.example.com"
        assert backup.base_url == "https://fw-b.example.com"

    def test_undeclared_firewall_has_no_settings(self, tmp_path: Path) -> None:
        envs = _write_settings(tmp_path)
        with pytest.raises(ValueError, match="No opnsense@nope provider settings"):
            VlanService.client_from_environment("prod", "opnsense@nope", envs)


class TestHaSyncPerFirewall:
    @pytest.mark.parametrize(
        ("provider_name", "expected"),
        [
            ("opnsense@fw-b", "HA sync after apply disabled (ha_sync_after_apply: false)"),
            ("opnsense", "HA sync skipped: nothing changed"),
        ],
    )
    def test_each_firewall_uses_its_own_ha_sync_option(
        self, provider_name: str, expected: str
    ) -> None:
        env = MagicMock()
        env.get_provider_settings.return_value = MULTI
        with patch("infrafoundry.core.config.ConfigManager") as manager:
            manager.return_value.load_environment.return_value = env
            line = run_ha_sync_after_apply("prod", provider_name, Path("cfg"), False)
        assert line == expected
