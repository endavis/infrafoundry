"""Provider-neutral env-var override of ``provider_settings`` (#783).

Generalizes the OPNsense direct-API pattern from #741
(``providers/opnsense/services/_credentials.py``) so any provider's
settings can be redirected for one invocation without editing the
SOPS-encrypted ``settings.yaml``.

The override is opt-in: env vars are consulted only when
``INFRAFOUNDRY_ALLOW_ENV_OVERRIDE`` is set to a value outside the falsy set
(``""``, ``"0"``, ``"false"``, ``"no"``, ``"off"``, case-insensitive), so a
forgotten ``direnv`` shell cannot silently retarget an apply. With the gate
active, a non-empty ``<PROVIDER>_<KEY>`` env var (for example
``PROXMOX_API_URL``) wins over ``provider_settings[<key>]``; an unset or
empty one falls back to the setting.

When the resolved ``api_url`` differs from the setting, a WARNING names the
new endpoint, once per process per provider and URL.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)

GATE_ENV_VAR = "INFRAFOUNDRY_ALLOW_ENV_OVERRIDE"

_FALSY = ("", "0", "false", "no", "off")

_warned_lock = threading.Lock()
_warned: set[tuple[str, str]] = set()


def gate_active() -> bool:
    """Return ``True`` if ``INFRAFOUNDRY_ALLOW_ENV_OVERRIDE`` is set to a truthy value."""
    return os.environ.get(GATE_ENV_VAR, "").strip().lower() not in _FALSY


def env_or_default(env_var: str, default: str) -> str:
    """Return the env var's value if non-empty, otherwise ``default``.

    Args:
        env_var: Name of the env var to consult.
        default: Fallback used when the env var is unset or empty.

    Returns:
        The non-empty env var value, or ``default``.
    """
    return os.environ.get(env_var, "") or default


def override_env_var(provider_name: str, key: str) -> str:
    """Return the env var that overrides ``provider_settings[key]``.

    Args:
        provider_name: Provider name, e.g. ``"proxmox"``.
        key: Settings key, e.g. ``"api_url"``.

    Returns:
        ``<PROVIDER>_<KEY>`` in upper case, e.g. ``"PROXMOX_API_URL"``.
    """
    return f"{provider_name}_{key}".upper()


def resolve_settings(
    provider_name: str,
    provider_settings: dict[str, Any],
    keys: Iterable[str],
) -> dict[str, Any]:
    """Apply gated env-var overrides to a provider's settings.

    Args:
        provider_name: Provider whose env vars to consult.
        provider_settings: The provider's entry from ``settings.yaml``.
        keys: Settings keys that may be overridden.

    Returns:
        A new dict: ``provider_settings`` with each non-empty
        ``<PROVIDER>_<KEY>`` env var applied when the gate is active, or an
        unchanged copy when it is not.
    """
    resolved = dict(provider_settings)
    if not gate_active():
        return resolved

    for key in keys:
        value = os.environ.get(override_env_var(provider_name, key), "")
        if value:
            resolved[key] = value

    url = resolved.get("api_url")
    if isinstance(url, str) and url and url != provider_settings.get("api_url"):
        _warn_once_about_redirect(provider_name, url)

    return resolved


def _warn_once_about_redirect(provider_name: str, resolved_url: str) -> None:
    """Warn that an env var redirected ``provider_name`` to ``resolved_url``, once each."""
    with _warned_lock:
        if (provider_name, resolved_url) in _warned:
            return
        _warned.add((provider_name, resolved_url))

    logger.warning(
        "%s endpoint overridden via %s=%s (gated by %s=1); terraform will target "
        "this endpoint instead of provider_settings.%s.api_url",
        provider_name,
        override_env_var(provider_name, "api_url"),
        resolved_url,
        GATE_ENV_VAR,
        provider_name,
    )


def reset_warning_state_for_tests() -> None:
    """Forget which redirects have been warned about. Test-only."""
    with _warned_lock:
        _warned.clear()
