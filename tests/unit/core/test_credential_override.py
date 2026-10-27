"""Gated env-var override of provider settings on the terraform path (#783)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.credential_override import (
    GATE_ENV_VAR,
    reset_warning_state_for_tests,
    resolve_settings,
)
from infrafoundry.providers.oci import OCIProvider
from infrafoundry.providers.proxmox import ProxmoxProvider

LOGGER = "infrafoundry.core.credential_override"

PROXMOX_SETTINGS = {
    "api_url": "https://pve-a.example:8006/api2/json",
    "api_token_id": "root@pam!a",
    "api_token_secret": "secret-a",
    "node": "pve1",
}
OCI_SETTINGS = {"tenancy_ocid": "ocid1.tenancy.a", "region": "us-ashburn-1"}


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Start every test with the gate and override env vars unset."""
    for var in (GATE_ENV_VAR, "PROXMOX_API_URL", "PROXMOX_API_TOKEN_SECRET", "OCI_REGION"):
        monkeypatch.delenv(var, raising=False)
    reset_warning_state_for_tests()
    yield
    reset_warning_state_for_tests()


class TestResolveSettings:
    def test_gate_unset_ignores_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROXMOX_API_URL", "https://pve-b.example")

        assert resolve_settings("proxmox", PROXMOX_SETTINGS, ["api_url"]) == PROXMOX_SETTINGS

    @pytest.mark.parametrize("gate", ["", "0", "false", "No", " OFF "])
    def test_falsy_gate_ignores_env(self, monkeypatch: pytest.MonkeyPatch, gate: str) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, gate)
        monkeypatch.setenv("PROXMOX_API_URL", "https://pve-b.example")

        assert resolve_settings("proxmox", PROXMOX_SETTINGS, ["api_url"]) == PROXMOX_SETTINGS

    def test_gate_on_env_wins_and_empty_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv("PROXMOX_API_URL", "https://pve-b.example")
        monkeypatch.setenv("PROXMOX_API_TOKEN_SECRET", "")

        resolved = resolve_settings("proxmox", PROXMOX_SETTINGS, ["api_url", "api_token_secret"])

        assert resolved["api_url"] == "https://pve-b.example"
        assert resolved["api_token_secret"] == "secret-a"

    def test_only_requested_keys_are_consulted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv("PROXMOX_API_URL", "https://pve-b.example")

        assert resolve_settings("proxmox", PROXMOX_SETTINGS, ["node"]) == PROXMOX_SETTINGS

    def test_settings_are_not_mutated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv("PROXMOX_API_URL", "https://pve-b.example")
        settings = dict(PROXMOX_SETTINGS)

        resolve_settings("proxmox", settings, ["api_url"])

        assert settings == PROXMOX_SETTINGS


class TestRedirectWarning:
    def test_warns_once_per_url(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv("PROXMOX_API_URL", "https://pve-b.example")

        with caplog.at_level(logging.WARNING, logger=LOGGER):
            resolve_settings("proxmox", PROXMOX_SETTINGS, ["api_url"])
            resolve_settings("proxmox", PROXMOX_SETTINGS, ["api_url"])

        warnings = [r for r in caplog.records if r.name == LOGGER]
        assert len(warnings) == 1
        assert "PROXMOX_API_URL=https://pve-b.example" in warnings[0].getMessage()

    def test_no_warning_when_url_unchanged(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv("PROXMOX_API_TOKEN_SECRET", "secret-b")

        with caplog.at_level(logging.WARNING, logger=LOGGER):
            resolve_settings("proxmox", PROXMOX_SETTINGS, ["api_url", "api_token_secret"])

        assert not [r for r in caplog.records if r.name == LOGGER]


def _env(provider_settings: dict[str, dict[str, str]]) -> EnvironmentConfig:
    return EnvironmentConfig(name="test", provider_settings=provider_settings)


class TestTerraformEnvVars:
    """``get_terraform_env_vars`` is what the terraform runner merges into its environment."""

    def _proxmox(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProxmoxProvider:
        provider = ProxmoxProvider(tmp_path, tmp_path)
        env = _env({"proxmox": PROXMOX_SETTINGS})
        monkeypatch.setattr(provider, "_load_environment_config", lambda: env)
        return provider

    def test_proxmox_apply_is_redirected_when_gated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv("PROXMOX_API_URL", "https://pve-b.example:8006/api2/json")
        monkeypatch.setenv("PROXMOX_API_TOKEN_SECRET", "secret-b")

        env_vars = self._proxmox(tmp_path, monkeypatch).get_terraform_env_vars()

        assert env_vars["TF_VAR_proxmox_api_url"] == "https://pve-b.example:8006/api2/json"
        assert env_vars["TF_VAR_proxmox_api_token_secret"] == "secret-b"
        assert env_vars["TF_VAR_proxmox_api_token_id"] == "root@pam!a"

    def test_proxmox_apply_uses_settings_without_the_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROXMOX_API_URL", "https://pve-b.example:8006/api2/json")

        env_vars = self._proxmox(tmp_path, monkeypatch).get_terraform_env_vars()

        assert env_vars["TF_VAR_proxmox_api_url"] == PROXMOX_SETTINGS["api_url"]

    def test_oci_region_is_overridden_when_gated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv("OCI_REGION", "eu-frankfurt-1")
        provider = OCIProvider(tmp_path, tmp_path)
        env = _env({"oci": OCI_SETTINGS})
        monkeypatch.setattr(provider, "_load_environment_config", lambda: env)

        env_vars = provider.get_terraform_env_vars()

        assert env_vars["TF_VAR_oci_region"] == "eu-frankfurt-1"
        assert env_vars["TF_VAR_oci_tenancy_ocid"] == "ocid1.tenancy.a"
