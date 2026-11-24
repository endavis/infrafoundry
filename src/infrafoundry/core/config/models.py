"""Configuration models for InfraFoundry."""

import os
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

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


class CollectorDeviceConfig(BaseModel):
    """One unmanaged device whose configuration is collected read-only."""

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    type: str
    address: str
    username: str | None = None
    password: str | None = None
    port: int | None = None
    ssh_key_file: str | None = None
    verify_ssl: bool = True
    timeout: int = Field(default=30, ge=1)
    options: dict[str, Any] = Field(default_factory=dict)


class CollectorsConfig(BaseModel):
    """The ``collectors:`` section of ``settings.yaml``."""

    output_dir: str | None = None
    devices: list[CollectorDeviceConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_names(self) -> "CollectorsConfig":
        names = [d.name for d in self.devices]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"duplicate collector device name(s): {', '.join(dupes)}")
        return self


_CREDENTIAL_URI_PREFIXES = ("secret://env/", "secret://env_secrets/")


class BitwardenBackendConfig(BaseModel):
    """The ``secret_backends.bitwarden`` block of ``settings.yaml``.

    ``client_id``, ``client_secret`` and ``master_password`` are ``secret://`` URIs naming
    where the bootstrap credentials come from. Only the ``env`` and ``env_secrets`` backends
    are accepted, so a credential can never point back into the vault. ``device_id_file``
    optionally overrides where the ``bw`` device id (app id) is persisted between runs.
    """

    server: str
    organization: str | None = None
    collection: str | None = None
    client_id: str = "secret://env/bw_clientid"
    client_secret: str = "secret://env/bw_clientsecret"
    master_password: str = "secret://env/bw_password"
    device_id_file: str | None = None

    @field_validator("device_id_file")
    @classmethod
    def _absolute_device_id_file(cls, value: str | None) -> str | None:
        if value is None:
            return None
        expanded = os.path.expanduser(value)
        if not value or not os.path.isabs(expanded):
            raise ValueError("device_id_file must be an absolute path (a leading ~ is expanded)")
        return expanded

    @field_validator("server")
    @classmethod
    def _https_only(cls, value: str) -> str:
        if not value.startswith("https://") or len(value) <= len("https://"):
            raise ValueError("server must be an https:// URL")
        return value

    @field_validator("client_id", "client_secret", "master_password")
    @classmethod
    def _credential_uri(cls, value: str) -> str:
        if not value.startswith(_CREDENTIAL_URI_PREFIXES) or value.endswith("/"):
            raise ValueError(
                "must be a secret://env/<key> or secret://env_secrets/<path> URI "
                "(a credential cannot be read from the vault itself)"
            )
        return value


class SecretBackendsConfig(BaseModel):
    """The ``secret_backends:`` section of ``settings.yaml``."""

    bitwarden: BitwardenBackendConfig | None = None


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
    # Read-only collectors for unmanaged network devices (``infra collect``)
    collectors: CollectorsConfig | None = None
    # Extra ``secret://`` backends (e.g. ``bitwarden``) for this environment
    secret_backends: SecretBackendsConfig | None = None
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
    # Default firewall (provider instance) for the package's resources (#1450).
    firewall: str | None = None
    # Default kubernetes cluster (provider instance) for the package's resources (#1539).
    cluster: str | None = None
    # Default openwrt device (provider instance) for the package's resources (#1656).
    device: str | None = None
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
