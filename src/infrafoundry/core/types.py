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


class OCIProviderSettings(TypedDict, total=False):
    """Provider settings expected by the OCI provider."""

    tenancy_ocid: str
    user_ocid: str
    fingerprint: str
    private_key_path: str
    region: str
    compartment_ocid: str


class OPNsenseProviderSettings(TypedDict, total=False):
    """Provider settings expected by the OPNsense provider."""

    api_url: str
    api_key: str
    api_secret: str


class EsxiHostSettings(TypedDict, total=False):
    """Settings for a single ESXi host."""

    hostname: str
    username: str
    password: str


class EsxiProviderSettings(TypedDict, total=False):
    """Provider settings expected by the ESXi provider."""

    hosts: dict[str, EsxiHostSettings]
    timeout: int


class KubernetesProviderSettings(TypedDict, total=False):
    """Provider settings expected by the Kubernetes provider."""

    kubeconfig_path: str


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


class PlanDeploymentMetadata(TypedDict, total=False):
    """Metadata recorded for plan deployments."""

    resource_filter: list[str] | None


class ApplyDeploymentMetadata(PlanDeploymentMetadata, total=False):
    """Metadata recorded for apply deployments."""

    auto_approve: bool


class DestroyDeploymentMetadata(PlanDeploymentMetadata, total=False):
    """Metadata recorded for destroy deployments."""

    auto_approve: bool


class RollbackDeploymentMetadata(TypedDict, total=False):
    """Metadata recorded when performing a rollback deployment."""

    rollback_from: int
    rollback: bool


DeploymentMetadata = (
    PlanDeploymentMetadata
    | ApplyDeploymentMetadata
    | DestroyDeploymentMetadata
    | RollbackDeploymentMetadata
)


class ResourceTrackingMetadata(TypedDict, total=False):
    """Metadata stored with tracked resources."""

    depends_on: list[str]
    custom_tags: dict[str, str]


class ResourceEventData(TypedDict, total=False):
    """Event payload for resource lifecycle events."""

    resource_id: int | None
    provider: str
    name: str
    terraform_id: str | None


class DeploymentEventData(TypedDict, total=False):
    """Event payload for deployment-level events."""

    deployment_id: int
    results: dict[str, Any] | None
    error: str | None


class RunnerEventData(TypedDict, total=False):
    """Event payload for runner lifecycle events."""

    provider: str
    runner: str
    phase: str
    success: bool
    error: str | None


class RollbackResourceSnapshot(TypedDict):
    """Snapshot of a single resource for rollback purposes."""

    provider: str
    type: str
    name: str
    config: dict[str, Any]


class RollbackData(TypedDict):
    """Snapshot data stored for deployment rollback."""

    environment: str
    timestamp: str  # ISO format datetime string
    resources: list[RollbackResourceSnapshot]


__all__ = [
    "ApplyDeploymentMetadata",
    "DeploymentEventData",
    "DeploymentMetadata",
    "DestroyDeploymentMetadata",
    "EnvironmentData",
    "EsxiHostSettings",
    "EsxiProviderSettings",
    "KubernetesProviderSettings",
    "OCIProviderSettings",
    "OPNsenseEnvironmentConfig",
    "OPNsenseProviderSettings",
    "PlanDeploymentMetadata",
    "ProxmoxEnvironmentConfig",
    "ProxmoxProviderSettings",
    "ResourceEventData",
    "ResourceTrackingMetadata",
    "RollbackData",
    "RollbackDeploymentMetadata",
    "RollbackResourceSnapshot",
    "RunnerEventData",
    "SSHConfigData",
]
