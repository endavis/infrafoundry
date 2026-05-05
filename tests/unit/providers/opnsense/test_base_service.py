"""End-to-end tests for ``BaseService.from_environment`` credential resolution.

These tests exercise the integration between
``BaseService.from_environment`` and the
``infrafoundry.providers.opnsense.services._credentials`` helper. They
write a minimal ``envs/<env>/settings.yaml`` to ``tmp_path`` and run
``ConfigManager.load_environment`` end-to-end so we observe the same
construction the production code path uses.

``BaseService`` is abstract; ``VlanService`` is used as the concrete
subclass because it is the simplest direct-API service and the
construction logic lives entirely on the base class.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml

from infrafoundry.providers.opnsense.services._credentials import (
    API_KEY_ENV_VAR,
    API_SECRET_ENV_VAR,
    API_URL_ENV_VAR,
    GATE_ENV_VAR,
    VERIFY_SSL_ENV_VAR,
    reset_warning_state_for_tests,
)
from infrafoundry.providers.opnsense.services.vlan import VlanService

CREDENTIALS_LOGGER = "infrafoundry.providers.opnsense.services._credentials"


@pytest.fixture(autouse=True)
def _reset_warning_state() -> None:
    """Clear the credentials helper's warning state before every test."""
    reset_warning_state_for_tests()


@pytest.fixture(autouse=True)
def _scrub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure no test sees inherited OPNSENSE_* / gate state from the shell."""
    for var in (
        GATE_ENV_VAR,
        API_URL_ENV_VAR,
        API_KEY_ENV_VAR,
        API_SECRET_ENV_VAR,
        VERIFY_SSL_ENV_VAR,
    ):
        monkeypatch.delenv(var, raising=False)


def _write_settings(
    config_dir: Path,
    env_name: str,
    *,
    api_url: str = "https://settings.example",
    api_key: str = "settings-key",
    api_secret: str = "settings-secret",
    verify_ssl: bool = True,
) -> None:
    """Write a minimal ``envs/<env>/settings.yaml`` with OPNsense credentials.

    ``ConfigManager`` expects ``config_dir`` to be the parent of ``envs/``;
    callers should pass ``tmp_path`` directly.
    """
    env_dir = config_dir / "envs" / env_name
    env_dir.mkdir(parents=True, exist_ok=True)
    settings = {
        "name": env_name,
        "description": f"test env {env_name}",
        "providers": ["opnsense"],
        "provider_settings": {
            "opnsense": {
                "api_url": api_url,
                "api_key": api_key,
                "api_secret": api_secret,
                "verify_ssl": verify_ssl,
            }
        },
    }
    (env_dir / "settings.yaml").write_text(yaml.safe_dump(settings))


class TestFromEnvironmentNoOverride:
    def test_no_env_vars_uses_settings_yaml(self, tmp_path: Path) -> None:
        _write_settings(tmp_path, "prod", api_url="https://prod.example")
        service = VlanService.from_environment("prod", "opnsense", tmp_path / "envs")
        assert service.client.base_url == "https://prod.example"

    def test_gate_unset_ignores_env_vars(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _write_settings(tmp_path, "prod", api_url="https://prod.example")
        # Override env vars set, but no gate → settings.yaml wins.
        monkeypatch.setenv(API_URL_ENV_VAR, "https://mirror.example")
        monkeypatch.setenv(API_KEY_ENV_VAR, "env-key")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            service = VlanService.from_environment("prod", "opnsense", tmp_path / "envs")
        assert service.client.base_url == "https://prod.example"
        assert [r for r in caplog.records if r.name == CREDENTIALS_LOGGER] == []


class TestFromEnvironmentWithOverride:
    def test_url_override_targets_mirror(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _write_settings(tmp_path, "prod", api_url="https://prod.example")
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_URL_ENV_VAR, "https://prod-mirror.example")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            service = VlanService.from_environment("prod", "opnsense", tmp_path / "envs")
        # Constructed client targets the mirror, not the settings URL.
        assert service.client.base_url == "https://prod-mirror.example"
        # And the redirect WARNING fires once, naming the resolved URL.
        warnings = [r for r in caplog.records if r.name == CREDENTIALS_LOGGER]
        assert len(warnings) == 1
        assert warnings[0].getMessage().find("https://prod-mirror.example") != -1

    def test_no_provider_settings_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Settings file exists but has no opnsense provider_settings entry.
        env_dir = tmp_path / "envs" / "prod"
        env_dir.mkdir(parents=True)
        (env_dir / "settings.yaml").write_text(yaml.safe_dump({"name": "prod"}))
        # Even with the gate active, missing provider_settings still raises.
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_URL_ENV_VAR, "https://mirror.example")
        with pytest.raises(ValueError, match="No opnsense provider settings"):
            VlanService.from_environment("prod", "opnsense", tmp_path / "envs")
