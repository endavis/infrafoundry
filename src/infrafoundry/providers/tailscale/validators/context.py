"""Validation contexts for the Tailscale sub-validators."""

from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.validation import ValidationContext


@dataclass(frozen=True, kw_only=True)
class TailscaleConfigContext(ValidationContext):
    """Context for the resource-config validators.

    Attributes:
        auth_mode: ``"oauth"``, ``"api_key"`` or ``"unset"``.
        acl_policy: The structured ``policy`` of the declared ``acl`` resource,
            or None when there is none (or it uses ``hujson``).
    """

    auth_mode: str = "unset"
    acl_policy: dict[str, Any] | None = None


@dataclass(frozen=True, kw_only=True)
class TailscaleCredentialsContext(ValidationContext):
    """Context for the credentials validator.

    Attributes:
        provider_settings: The ``provider_settings.tailscale`` mapping, with
            ``secret://`` URIs left unresolved.
        env_oauth: True when the OAuth fallback environment variables are set.
        env_api_key: True when ``TAILSCALE_API_KEY`` is set.
    """

    provider_settings: dict[str, Any] = field(default_factory=dict)
    env_oauth: bool = False
    env_api_key: bool = False
