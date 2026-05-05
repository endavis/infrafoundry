"""Shared runtime-credential resolution helper for the OPNsense direct-API path.

The two OPNsense direct-API construction sites — ``BaseService.from_environment``
(used by every direct-API service) and the Kea-DHCP path inside
``OPNsenseProvider`` — both build an ``OPNsenseClient`` from
``provider_settings.opnsense`` in the env's ``settings.yaml``. To target a
different OPNsense box for one ``foundry infra plan/apply`` invocation (e.g.,
a staging mirror, or a `direnv`-style ergonomic for box-to-box cutover), the
operator otherwise has to either edit the SOPS-encrypted ``settings.yaml`` in
place — high blast radius, easy to forget to revert — or duplicate the env
directory.

This helper lets the operator export ``OPNSENSE_API_URL`` /
``OPNSENSE_API_KEY`` / ``OPNSENSE_API_SECRET`` / ``OPNSENSE_VERIFY_SSL`` and
have the same env's plan/apply target the override box, without touching
``settings.yaml``. To prevent a forgotten direnv shell from silently
mass-applying to the wrong box, the override is **opt-in** via
``INFRAFOUNDRY_ALLOW_ENV_OVERRIDE=1``: without the gate, behavior is
unchanged from before.

Precedence (when the gate is active)
------------------------------------

1. A non-empty env var wins over the corresponding ``provider_settings`` key.
2. An unset or empty env var falls back to ``provider_settings``.
3. ``OPNSENSE_VERIFY_SSL`` is parsed via the project convention
   (``verify_raw not in ("0", "false", "no", "off")`` after
   ``.strip().lower()``), matching the live integration test at
   ``tests/integration/opnsense/test_vlan_live.py``.

Gate parsing matches the same falsy set: ``""``, ``"0"``, ``"false"``,
``"no"``, ``"off"`` (case-insensitive) all leave behavior unchanged. Any
other value enables override.

Warning behavior
----------------

When override is active and the resolved ``api_url`` differs from
``provider_settings.get("api_url")``, the helper emits a single WARNING-level
log record naming the resolved URL. The intent is to make endpoint redirects
loud at plan/apply time so an operator running against a mirror sees which
box is being targeted. The warning is **one-time per process per
resolved-URL**: a module-level set tracks which URLs have already been
warned about, so a single ``infra plan`` (which builds multiple services)
produces one warning, not one per service.

If override is active but the resolved ``api_url`` matches
``provider_settings`` (e.g., the gate is set with only ``OPNSENSE_API_KEY``
overridden and no URL change), no warning fires — there is no endpoint
redirect to flag.

Test affordance
---------------

``reset_warning_state_for_tests()`` clears the module-level warning-tracking
set. Test suites that exercise the helper (or services that delegate to it)
must call this from a ``setup_method`` / autouse fixture so each test
starts from a clean state — without it, the warning suppression from
earlier tests leaks into later ones.

References
----------

- Issue #741: feat — env-var override for OPNsense direct-API runtime
  credentials.
- ADR-0014 §"Secrets handling" → "Runtime credential resolution" subsection.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

# Name of the gate env var. Override is honored only when this env var is set
# to a value not in the falsy set below.
GATE_ENV_VAR = "INFRAFOUNDRY_ALLOW_ENV_OVERRIDE"

# Per-field env var names. Empty string and unset are treated identically
# (fall back to ``provider_settings``).
API_URL_ENV_VAR = "OPNSENSE_API_URL"
API_KEY_ENV_VAR = "OPNSENSE_API_KEY"
API_SECRET_ENV_VAR = "OPNSENSE_API_SECRET"
VERIFY_SSL_ENV_VAR = "OPNSENSE_VERIFY_SSL"

# The falsy set used for both the gate and ``OPNSENSE_VERIFY_SSL`` parsing.
# Matches the project convention from
# ``tests/integration/opnsense/test_vlan_live.py``.
_FALSY = ("", "0", "false", "no", "off")

# Module-level warning-tracking set, keyed by resolved ``api_url``. One entry
# per overridden URL per process.
_warned_urls_lock = threading.Lock()
_warned_urls: set[str] = set()


def _gate_active() -> bool:
    """Return ``True`` if the override gate is set to a truthy value."""
    raw = os.environ.get(GATE_ENV_VAR, "").strip().lower()
    return raw not in _FALSY


def _env_or_default(env_var: str, default: str) -> str:
    """Return the env var value if non-empty, otherwise ``default``.

    Empty strings are treated as unset — environment-variable convention
    favors absence-or-empty being equivalent for "operator hasn't set
    this".

    Args:
        env_var: Name of the env var to consult.
        default: Fallback value used when the env var is unset or empty.

    Returns:
        The non-empty env var value, or ``default``.
    """
    value = os.environ.get(env_var, "")
    if value:
        return value
    return default


def _parse_verify_ssl(env_value: str, default: bool) -> bool:
    """Parse ``OPNSENSE_VERIFY_SSL`` per the project convention.

    The convention (``verify_raw not in ("0", "false", "no", "off")`` after
    ``.strip().lower()``) is defined at
    ``tests/integration/opnsense/test_vlan_live.py:67-68``. Empty / unset
    falls back to ``default`` (the ``provider_settings`` value).

    Args:
        env_value: Raw value of ``OPNSENSE_VERIFY_SSL`` (may be empty).
        default: Fallback used when ``env_value`` is empty/unset.

    Returns:
        Parsed boolean.
    """
    if not env_value:
        return default
    normalized = env_value.strip().lower()
    return normalized not in ("0", "false", "no", "off")


def resolve_credentials(
    provider_settings: dict[str, Any],
) -> tuple[str, str, str, bool]:
    """Resolve OPNsense client credentials, honoring env-var overrides if gated.

    When ``INFRAFOUNDRY_ALLOW_ENV_OVERRIDE`` is set to a truthy value, each
    of the four credential fields is resolved env-FIRST: a non-empty
    ``OPNSENSE_*`` env var wins, otherwise the corresponding
    ``provider_settings`` key is used. When the gate is unset (or set to a
    falsy value), behavior is unchanged from before this helper existed:
    every field is read straight from ``provider_settings``.

    If override is active and the resolved ``api_url`` differs from
    ``provider_settings.get("api_url")``, a one-time-per-process warning
    fires naming the resolved URL.

    Args:
        provider_settings: The OPNsense entry of the env's
            ``provider_settings`` dict (i.e.,
            ``env_config.get_provider_settings("opnsense")``). Expected keys
            are ``api_url``, ``api_key``, ``api_secret``, ``verify_ssl``;
            missing keys default to empty string (``api_url``,
            ``api_key``, ``api_secret``) or ``True`` (``verify_ssl``).

    Returns:
        Tuple ``(api_url, api_key, api_secret, verify_ssl)`` ready to pass
        to ``OPNsenseClient(...)``.
    """
    settings_url = str(provider_settings.get("api_url", ""))
    settings_key = str(provider_settings.get("api_key", ""))
    settings_secret = str(provider_settings.get("api_secret", ""))
    settings_verify = bool(provider_settings.get("verify_ssl", True))

    if not _gate_active():
        return (settings_url, settings_key, settings_secret, settings_verify)

    api_url = _env_or_default(API_URL_ENV_VAR, settings_url)
    api_key = _env_or_default(API_KEY_ENV_VAR, settings_key)
    api_secret = _env_or_default(API_SECRET_ENV_VAR, settings_secret)
    verify_ssl = _parse_verify_ssl(
        os.environ.get(VERIFY_SSL_ENV_VAR, ""),
        settings_verify,
    )

    if api_url != settings_url:
        _warn_once_about_redirect(api_url)

    return (api_url, api_key, api_secret, verify_ssl)


def _warn_once_about_redirect(resolved_url: str) -> None:
    """Emit a WARNING about an env-var-driven endpoint redirect, once per URL.

    The set of already-warned URLs is process-local and module-level; a
    single ``infra plan`` invocation that constructs multiple services
    against the same overridden URL produces one warning, not one per
    service.

    Args:
        resolved_url: The ``api_url`` that the helper resolved to (i.e.,
            the value coming from ``OPNSENSE_API_URL``).
    """
    with _warned_urls_lock:
        if resolved_url in _warned_urls:
            return
        _warned_urls.add(resolved_url)

    logger.warning(
        "OPNsense endpoint overridden via %s=%s "
        "(gated by %s=1); plan/apply will target this endpoint instead of "
        "the value in provider_settings.opnsense.api_url",
        API_URL_ENV_VAR,
        resolved_url,
        GATE_ENV_VAR,
    )


def reset_warning_state_for_tests() -> None:
    """Clear the module-level warning-tracking set.

    Test-only affordance. Call from a ``setup_method`` or autouse fixture
    in test suites that exercise this helper (or services that delegate to
    it) so each test starts from a clean state.
    """
    with _warned_urls_lock:
        _warned_urls.clear()
