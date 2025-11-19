"""Shared typing utilities for InfraFoundry."""

from __future__ import annotations

from typing import Any, TypedDict


class ProxmoxProviderSettings(TypedDict, total=False):
    """Provider settings expected by the Proxmox validator."""

    api_url: str
    api_token: str
    api_token_id: str
    api_token_secret: str
    node: str


class ProxmoxEnvironmentConfig(TypedDict, total=False):
    """Subset of the environment configuration consumed by Proxmox."""

    provider_settings: dict[str, ProxmoxProviderSettings | dict[str, Any]]


class OPNsenseProviderSettings(TypedDict, total=False):
    """Provider settings expected by the OPNsense provider."""

    api_url: str
    api_key: str
    api_secret: str


class OPNsenseEnvironmentConfig(TypedDict, total=False):
    """Subset of the environment configuration consumed by OPNsense."""

    provider_settings: dict[str, OPNsenseProviderSettings | dict[str, Any]]


class SSHConfigData(TypedDict, total=False):
    """Raw SSH config data stored in environment configs."""

    user: str
    key_path: str
    port: int


class EnvironmentData(TypedDict, total=False):
    """Structured representation of EnvironmentConfig.model_dump()."""

    name: str
    description: str | None
    providers: list[str]
    variables: dict[str, Any]
    ssh: SSHConfigData | None
    provider_ssh: dict[str, SSHConfigData]
    provider_settings: dict[str, dict[str, Any]]


__all__ = [
    "EnvironmentData",
    "ProxmoxEnvironmentConfig",
    "ProxmoxProviderSettings",
    "OPNsenseEnvironmentConfig",
    "OPNsenseProviderSettings",
    "SSHConfigData",
]
