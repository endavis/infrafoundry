"""Shared fixtures and builders for the Tailscale provider tests."""

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.tailscale import TailscaleProvider

# Fake credentials; deliberately not PEM-shaped.
SECRET_ID = "sentinel-oauth-id-870"  # pragma: allowlist secret
SECRET_VALUE = "sentinel-oauth-secret-870"  # pragma: allowlist secret
API_KEY_VALUE = "sentinel-api-key-870"  # pragma: allowlist secret
OAUTH_URIS: dict[str, Any] = {
    "oauth_client_id": "secret://env_secrets/tailscale/oauth_client_id",
    "oauth_client_secret": "secret://env_secrets/tailscale/oauth_client_secret",
    "tailnet": "-",
}
OAUTH_SECRETS: dict[str, Any] = {
    "tailscale": {"oauth_client_id": SECRET_ID, "oauth_client_secret": SECRET_VALUE}
}


def make_env(
    settings: dict[str, Any] | None = None, secrets: dict[str, Any] | None = None
) -> EnvironmentConfig:
    """Build an EnvironmentConfig with ``provider_settings.tailscale``."""
    return EnvironmentConfig(
        name="test",
        provider_settings={"tailscale": settings} if settings is not None else {},
        secrets=secrets,
    )


def res(name: str, rtype: str, **config: Any) -> ResourceConfig:
    """Build a tailscale ResourceConfig."""
    import_id = config.pop("import_id", None)
    return ResourceConfig(
        name=name, type=rtype, provider="tailscale", config=config, import_id=import_id
    )


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the host's TAILSCALE_* and override-gate variables out of every test."""
    for var in (
        "TAILSCALE_API_KEY",
        "TAILSCALE_OAUTH_CLIENT_ID",
        "TAILSCALE_OAUTH_CLIENT_SECRET",
        "TAILSCALE_TAILNET",
        "INFRAFOUNDRY_ALLOW_ENV_OVERRIDE",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def provider(tmp_path: Path) -> TailscaleProvider:
    """A TailscaleProvider writing under tmp_path for environment 'test'."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    p = TailscaleProvider(config_dir, tmp_path / "output")
    p.set_environment("test")
    return p
