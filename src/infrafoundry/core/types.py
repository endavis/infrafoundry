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


__all__ = [
    "ProxmoxEnvironmentConfig",
    "ProxmoxProviderSettings",
    "OPNsenseEnvironmentConfig",
    "OPNsenseProviderSettings",
]
