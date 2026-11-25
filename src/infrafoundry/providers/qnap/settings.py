"""Connection settings for the QNAP provider, read from ``provider_settings.qnap`` (ADR-0038).

.. code-block:: yaml

    provider_settings:
      qnap:
        api_url: https://192.0.2.10
        username: secret://env_secrets/qnap/username
        password: secret://env_secrets/qnap/password
        tls_fingerprint: "AB:CD:..."   # SHA-256 of the switch's certificate

One switch per environment. ``username`` and ``password`` must be ``secret://``
references. Messages name keys, never values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.tls_pin import FINGERPRINT_HEX_LENGTH, normalize_fingerprint
from infrafoundry.secrets.environment import resolved_provider_settings
from infrafoundry.secrets.resolver import is_secret_uri

PROVIDER_NAME = "qnap"
DEFAULT_TIMEOUT = 10
MIN_TIMEOUT = 1
MAX_TIMEOUT = 120
DEFAULT_CHECK_TIMEOUT = 90
MIN_CHECK_TIMEOUT = 10
MAX_CHECK_TIMEOUT = 600
DEFAULT_UPGRADE_TIMEOUT = 1200
MIN_UPGRADE_TIMEOUT = 300
MAX_UPGRADE_TIMEOUT = 3600
_REQUIRED = ("api_url", "username", "password")
_TIMEOUTS = (
    ("timeout", MIN_TIMEOUT, MAX_TIMEOUT),
    ("check_timeout", MIN_CHECK_TIMEOUT, MAX_CHECK_TIMEOUT),
    ("upgrade_timeout", MIN_UPGRADE_TIMEOUT, MAX_UPGRADE_TIMEOUT),
)


class QnapSettingsError(InfraFoundryError):
    """The QNAP provider settings are missing or invalid. Never carries a secret."""


@dataclass(frozen=True)
class QnapSettings:
    """How to reach one QNAP switch's web API. Credentials are hidden from ``repr``."""

    api_url: str
    username: str = field(repr=False)
    password: str = field(repr=False)
    fingerprint: str | None = None
    verify_ssl: bool = True
    timeout: int = DEFAULT_TIMEOUT
    check_timeout: int = DEFAULT_CHECK_TIMEOUT
    upgrade_timeout: int = DEFAULT_UPGRADE_TIMEOUT

    @property
    def host(self) -> str:
        """Host part of ``api_url``."""
        return urlparse(self.api_url).hostname or ""

    @property
    def port(self) -> int:
        """Port of ``api_url``, 443 by default."""
        return urlparse(self.api_url).port or 443


def raw_settings_problems(
    raw: dict[str, Any],
    *,
    require_secret_refs: bool = True,
    where: str = "provider_settings.qnap",
) -> list[str]:
    """Return what is wrong with the raw ``provider_settings.qnap`` mapping (empty when valid).

    The check is offline and looks at the unresolved mapping. Messages name keys only.

    Args:
        raw: The ``provider_settings.qnap`` mapping.
        require_secret_refs: Require ``username`` and ``password`` to be ``secret://``
            references (False for a mapping whose secrets are already resolved).
        where: Prefix of every message, naming the mapping that is checked.
    """
    problems: list[str] = []
    missing = [key for key in _REQUIRED if not raw.get(key)]
    if missing:
        problems.append(f"{where} is missing: " + ", ".join(missing))
    api_url = raw.get("api_url")
    if api_url:
        parsed = urlparse(str(api_url))
        if parsed.scheme != "https":
            problems.append(f"{where}.api_url must start with https://")
        elif not parsed.hostname:
            problems.append(f"{where}.api_url has no host")
    for key in ("username", "password"):
        value = raw.get(key)
        if require_secret_refs and value and not (isinstance(value, str) and is_secret_uri(value)):
            problems.append(f"{where}.{key} must be a secret:// reference")
    verify = raw.get("verify_ssl", True)
    if not isinstance(verify, bool):
        problems.append(f"{where}.verify_ssl must be true or false")
    pin = raw.get("tls_fingerprint")
    if pin not in (None, ""):
        if normalize_fingerprint(pin) is None:
            problems.append(
                f"{where}.tls_fingerprint must be a SHA-256 fingerprint "
                f"({FINGERPRINT_HEX_LENGTH} hex characters, ':' separators allowed)"
            )
    elif verify is not False:
        problems.append(
            f"{where} needs tls_fingerprint (the switch's SHA-256 certificate pin) "
            "or, unsafely, verify_ssl: false"
        )
    for key, low, high in _TIMEOUTS:
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(value, bool) or not isinstance(value, int):
            problems.append(f"{where}.{key} must be an integer number of seconds")
        elif not low <= value <= high:
            problems.append(f"{where}.{key} must be within {low}-{high} seconds")
    return problems


def settings_from_mapping(
    resolved: dict[str, Any], *, where: str = "provider_settings.qnap"
) -> QnapSettings:
    """Build settings from an already secret-resolved mapping.

    Args:
        resolved: The ``provider_settings.qnap`` mapping with secrets resolved.
        where: Prefix of every error message, naming the mapping that is checked.

    Raises:
        QnapSettingsError: On a missing key or an invalid value. Names keys, never values.
    """
    problems = raw_settings_problems(resolved, require_secret_refs=False, where=where)
    if problems:
        raise QnapSettingsError("; ".join(problems))
    return QnapSettings(
        api_url=str(resolved["api_url"]).rstrip("/"),
        username=str(resolved["username"]),
        password=str(resolved["password"]),
        fingerprint=normalize_fingerprint(resolved.get("tls_fingerprint")),
        verify_ssl=resolved.get("verify_ssl", True) is not False,
        timeout=int(resolved.get("timeout", DEFAULT_TIMEOUT)),
        check_timeout=int(resolved.get("check_timeout", DEFAULT_CHECK_TIMEOUT)),
        upgrade_timeout=int(resolved.get("upgrade_timeout", DEFAULT_UPGRADE_TIMEOUT)),
    )


def load_settings(config_dir: Path, env_name: str) -> QnapSettings:
    """Load and secret-resolve ``provider_settings.qnap`` for an environment.

    Args:
        config_dir: Configuration directory.
        env_name: Environment name.

    Raises:
        QnapSettingsError: If the settings are absent or invalid.
        SecretResolutionError: If a ``secret://`` reference cannot be resolved.
    """
    env_config = ConfigManager(config_dir).load_environment(env_name)
    raw = env_config.provider_settings.get(PROVIDER_NAME) if env_config else None
    if not raw or env_config is None:
        raise QnapSettingsError(f"No provider_settings.qnap found for environment '{env_name}'")
    problems = raw_settings_problems(raw)
    if problems:
        raise QnapSettingsError("; ".join(problems))
    resolved = resolved_provider_settings(env_config, PROVIDER_NAME) or {}
    return settings_from_mapping(resolved)
