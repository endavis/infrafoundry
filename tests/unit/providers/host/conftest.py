"""Shared builders for the host provider tests (documentation values only)."""

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.host import HostProvider

AUTH_REF = "tailscale.oauth_client_secret"
SECRET_VALUE = "tskey-example-0123456789"


def host(name: str = "vps-01", **extra: Any) -> ResourceConfig:
    """A valid host resource."""
    config: dict[str, Any] = {"address": "vps-01.example.com"}
    config.update(extra)
    return ResourceConfig(name=name, type="host", provider="host", config=config)


def tailscale_block(**extra: Any) -> dict[str, Any]:
    """A valid OAuth ``tailscale:`` block."""
    block: dict[str, Any] = {
        "auth": {
            "oauth": {
                "client_id_secret": "tailscale.oauth_client_id",
                "client_secret_secret": AUTH_REF,
            }
        },
        "advertise_tags": ["tag:example"],
    }
    block.update(extra)
    return block


def make_env(secrets: dict[str, Any] | None = None) -> EnvironmentConfig:
    """Build an EnvironmentConfig holding the given secrets."""
    return EnvironmentConfig(name="test", secrets=secrets)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A config repo root with envs/ and a playbook."""
    (tmp_path / "envs").mkdir()
    (tmp_path / "playbooks").mkdir()
    (tmp_path / "playbooks" / "base.yml").write_text("---\n")
    return tmp_path


@pytest.fixture
def provider(repo: Path, tmp_path: Path) -> HostProvider:
    """A HostProvider writing under tmp_path for environment 'test'."""
    p = HostProvider(repo / "envs", tmp_path / "output")
    p.set_environment("test")
    return p
