"""Shared builders for the QNAP provider tests (documentation values only)."""

from __future__ import annotations

from typing import Any

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.qnap.components.firmware import FIRMWARE_TYPE
from infrafoundry.providers.qnap.settings import QnapSettings

from .qnap_fake import ServedQnap
from .qnap_fake import served_qnap as served_qnap  # re-exported fixture

SETTINGS = QnapSettings(
    api_url="https://192.0.2.10",
    username="admin-example",
    password="pw-example",
    fingerprint="a" * 64,
)

RAW_SETTINGS: dict[str, Any] = {
    "api_url": "https://192.0.2.10",
    "username": "secret://env_secrets/qnap/username",
    "password": "secret://env_secrets/qnap/password",
    "tls_fingerprint": "AB:" * 31 + "AB",
}


def firmware(name: str = "sw-fw", **config: Any) -> ResourceConfig:
    """Build a ``firmware.update`` resource."""
    return ResourceConfig(name=name, type=FIRMWARE_TYPE, provider="qnap", config=config)


def make_env(
    settings: dict[str, Any] | None = None, secrets: dict[str, Any] | None = None
) -> EnvironmentConfig:
    """Build an EnvironmentConfig with QNAP provider settings."""
    return EnvironmentConfig(
        name="test",
        provider_settings={"qnap": settings} if settings is not None else {},
        secrets=secrets or {},
    )


def settings_for(served: ServedQnap, **overrides: Any) -> QnapSettings:
    """Settings that point at a running fake, pinned to its certificate."""
    from .qnap_fake import PASSWORD, USER

    values: dict[str, Any] = {
        "api_url": served.api_url,
        "username": USER,
        "password": PASSWORD,
        "fingerprint": served.fingerprint,
        "timeout": 5,
    }
    values.update(overrides)
    return QnapSettings(**values)
