"""Configuration models for InfraFoundry."""

from typing import Any

from pydantic import BaseModel, Field

from infrafoundry.core.config.backend_config import BackendConfig
from infrafoundry.core.hooks.models import HooksConfig


class DriftRemediationConfig(BaseModel):
    """Configuration for automated drift remediation."""

    enabled: bool = False
    check_interval_minutes: int = Field(default=60, ge=1)
    auto_apply_threshold: int = Field(
        default=5,
        ge=0,
        description="Maximum number of changes to auto-apply (0 = never auto-apply)",
    )
    max_to_add: int = Field(
        default=3,
        ge=0,
        description="Maximum resources to add automatically",
    )
    max_to_change: int = Field(
        default=3,
        ge=0,
        description="Maximum resources to change automatically",
    )
    max_to_destroy: int = Field(
        default=0,
        ge=0,
        description="Maximum resources to destroy automatically (0 = never destroy)",
    )
    notify_on_drift: bool = True
    notify_on_remediation: bool = True
    dry_run: bool = Field(
        default=False,
        description="Only detect drift, never auto-apply",
    )


class SSHConfig(BaseModel):
    """SSH configuration for provider operations."""

    user: str | None = None
    key_path: str | None = None
    port: int = 22


class EnvironmentConfig(BaseModel):
    """Environment-specific configuration."""

    name: str
    description: str | None = None
    providers: list[str] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    ssh: SSHConfig | None = None  # Global SSH config
    provider_ssh: dict[str, SSHConfig] = Field(default_factory=dict)  # Per-provider SSH
    # Provider-specific settings (credentials, api_url, etc.)
    provider_settings: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # Override runner execution order: { "pyinfra": 40, "ansible": 60 }
    runner_priorities: dict[str, int] = Field(default_factory=dict)
    # Terraform backend configuration for state management and locking
    backend: BackendConfig | None = None
    # Drift remediation configuration for automated drift detection and remediation
    drift_remediation: DriftRemediationConfig | None = None
    # Lifecycle hooks for environment-level script execution
    hooks: HooksConfig | None = None

    def get_ssh_config(self, provider_name: str) -> SSHConfig | None:
        """Get SSH config for a specific provider.

        Args:
            provider_name: Provider name (e.g., 'proxmox', 'opnsense')

        Returns:
            Provider-specific SSH config if exists, otherwise global SSH config
        """
        return self.provider_ssh.get(provider_name, self.ssh)

    def get_provider_settings(self, provider_name: str) -> dict[str, Any] | None:
        """Return provider-specific settings dict if present."""
        return self.provider_settings.get(provider_name)
