"""Configuration models for InfraFoundry."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from infrafoundry.core.config.backend_config import BackendConfig
from infrafoundry.core.hooks.models import HooksConfig


class IaCTool(StrEnum):
    """Supported Infrastructure as Code tools."""

    TERRAFORM = "terraform"
    OPENTOFU = "opentofu"


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


class NotificationChannelConfig(BaseModel):
    """Configuration for a single notification channel."""

    name: str
    type: str  # webhook, slack, email
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    events: list[str] | None = None  # None = all events
    levels: list[str] | None = None  # None = all levels


class NotificationsConfig(BaseModel):
    """Configuration for notifications in an environment."""

    channels: list[NotificationChannelConfig] = Field(default_factory=list)


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
    # Override provider execution order: ["opnsense", "proxmox", "oci", "kubernetes"]
    # Providers earlier in the list are applied first. Unlisted providers run last.
    # For destroy operations, the order is automatically reversed.
    provider_order: list[str] = Field(default_factory=list)
    # Terraform backend configuration for state management and locking
    backend: BackendConfig | None = None
    # Drift remediation configuration for automated drift detection and remediation
    drift_remediation: DriftRemediationConfig | None = None
    # Lifecycle hooks for environment-level script execution
    hooks: HooksConfig | None = None
    # Event handlers registered from settings.yaml (event_type -> handler configs)
    events: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    # Notification channels for this environment
    notifications: NotificationsConfig | None = None
    # Infrastructure as Code tool selection (terraform or opentofu)
    iac_tool: IaCTool = IaCTool.TERRAFORM
    # Decrypted secrets for this environment.
    #
    # NOTE: This field is NOT loaded from settings.yaml. It is populated by
    # ``SecretManager.populate_environment_config`` after sops decryption of
    # ``envs/{env}/secrets.yaml`` (or equivalent). It holds plaintext values
    # in memory only and must never be serialized back to disk.
    #
    # Consumers (e.g. provider mixins) flatten this dict to dotted keys and
    # resolve resource-level ``terraform_secrets:`` references against it to
    # build ``TF_VAR_*`` environment variables.
    secrets: dict[str, Any] | None = None

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


class PackageManifest(BaseModel):
    """Infrastructure package manifest (infrafoundry.yml).

    Defines a self-contained infrastructure package with variables,
    resource templates, and event handlers.
    """

    name: str
    description: str | None = None
    provider: str | None = None
    blueprint: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)
    resources: list[str] = Field(default_factory=list)
    events: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    inventory: dict[str, Any] | None = None
    # Raw YAML text of the manifest's ``inventory:`` block, extracted
    # before ``yaml.safe_load`` so the generator can render it through
    # Jinja2 with full control-flow support.  Framework-internal; not
    # serialised back to disk.
    inventory_raw: str | None = Field(default=None, exclude=True)
