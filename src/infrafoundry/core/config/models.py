"""Configuration models for InfraFoundry."""

from typing import Any

from pydantic import BaseModel, Field


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
