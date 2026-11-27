"""Connection settings for the ONTAP provider, read from ``provider_settings.ontap`` (ADR-0042).

.. code-block:: yaml

    provider_settings:
      ontap:
        host: cluster1.example.com            # the cluster management LIF
        username: secret://env_secrets/ontap/username
        password: secret://env_secrets/ontap/password
        tls_fingerprint: "AB:CD:..."           # SHA-256 of the cluster's certificate
        ca_bundle: certs/ca.pem                # or validate the chain against a CA bundle
        verify_ssl: true                       # or against the system store
        timeout: 30                            # optional, seconds
        api_spec_dir: ~/.infrafoundry/netapp/apis   # optional, holds ontap/all.json

One cluster per environment. ``username`` and ``password`` must be ``secret://`` references.
Exactly one way to trust the cluster: ``tls_fingerprint``, ``ca_bundle``, ``verify_ssl: true``,
or the unsafe opt-out ``verify_ssl: false`` with no pin. Messages name keys, never values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.tls_pin import FINGERPRINT_HEX_LENGTH, normalize_fingerprint
from infrafoundry.providers._netapp.ontap import ConnectionParams
from infrafoundry.secrets.environment import resolved_provider_settings
from infrafoundry.secrets.resolver import is_secret_uri

PROVIDER_NAME = "ontap"
DEFAULT_TIMEOUT = 30
MIN_TIMEOUT = 1
MAX_TIMEOUT = 600
DEFAULT_SPEC_DIR = "~/.infrafoundry/netapp/apis"
SPEC_API = "ontap"
SPEC_FILE = "all.json"
_REQUIRED = ("host", "username", "password")
_KNOWN = (
    *_REQUIRED,
    "tls_fingerprint",
    "ca_bundle",
    "verify_ssl",
    "timeout",
    "api_spec_dir",
)


class OntapSettingsError(InfraFoundryError):
    """The ONTAP provider settings are missing or invalid. Never carries a secret."""


@dataclass(frozen=True)
class OntapSettings:
    """How to reach one ONTAP cluster's REST API. Credentials are hidden from ``repr``."""

    host: str
    username: str = field(repr=False)
    password: str = field(repr=False)
    fingerprint: str | None = None
    ca_bundle: Path | None = None
    verify_ssl: bool | None = None
    timeout: int = DEFAULT_TIMEOUT
    api_spec_dir: Path = field(default_factory=lambda: Path(DEFAULT_SPEC_DIR).expanduser())

    @property
    def unverified(self) -> bool:
        """True for the unsafe opt-out: no pin, no CA bundle and no chain validation."""
        return self.fingerprint is None and self.ca_bundle is None and self.verify_ssl is not True

    @property
    def spec_file(self) -> Path:
        """Where the OpenAPI spec of the ONTAP REST API is read from."""
        return self.api_spec_dir / SPEC_API / SPEC_FILE

    def connection_params(self) -> ConnectionParams:
        """Return what the shared service layer needs to connect."""
        return ConnectionParams(
            host=self.host,
            username=self.username,
            password=self.password,
            fingerprint=self.fingerprint,
            ca_bundle=self.ca_bundle,
            verify_ssl=self.verify_ssl,
            timeout=self.timeout,
            spec_file=self.spec_file,
        )


def _resolve_path(value: str, config_dir: Path | None) -> Path:
    """Expand ``~`` and anchor a relative path at the configuration directory."""
    path = Path(value).expanduser()
    if not path.is_absolute() and config_dir is not None:
        path = config_dir / path
    return path


def spec_file_for(raw: dict[str, Any], config_dir: Path | None) -> Path:
    """Return the spec path a raw settings mapping points at (default ``~/.infrafoundry``)."""
    configured = raw.get("api_spec_dir")
    directory = _resolve_path(
        str(configured) if configured else DEFAULT_SPEC_DIR,
        config_dir,
    )
    return directory / SPEC_API / SPEC_FILE


def settings_problems(
    raw: dict[str, Any],
    *,
    require_secret_refs: bool = True,
    where: str = "provider_settings.ontap",
) -> list[str]:
    """Return what is wrong with the raw ``provider_settings.ontap`` mapping (empty when valid).

    The check is offline and looks at the unresolved mapping. Messages name keys only.

    Args:
        raw: The ``provider_settings.ontap`` mapping.
        require_secret_refs: Require ``username`` and ``password`` to be ``secret://``
            references (False for a mapping whose secrets are already resolved).
        where: Prefix of every message.
    """
    problems: list[str] = []
    missing = [key for key in _REQUIRED if not raw.get(key)]
    if missing:
        problems.append(f"{where} is missing: " + ", ".join(missing))
    unknown = sorted(set(raw) - set(_KNOWN))
    if unknown:
        problems.append(f"{where} has unknown key(s): " + ", ".join(unknown))
    host = raw.get("host")
    if host and (not isinstance(host, str) or "/" in host or " " in host.strip()):
        problems.append(f"{where}.host must be a host name or address, without a scheme or path")
    for key in ("username", "password"):
        value = raw.get(key)
        if require_secret_refs and value and not (isinstance(value, str) and is_secret_uri(value)):
            problems.append(f"{where}.{key} must be a secret:// reference")
    problems.extend(_tls_problems(raw, where))
    if "timeout" in raw:
        value = raw["timeout"]
        if isinstance(value, bool) or not isinstance(value, int):
            problems.append(f"{where}.timeout must be an integer number of seconds")
        elif not MIN_TIMEOUT <= value <= MAX_TIMEOUT:
            problems.append(f"{where}.timeout must be within {MIN_TIMEOUT}-{MAX_TIMEOUT} seconds")
    spec_dir = raw.get("api_spec_dir")
    if spec_dir is not None and (not isinstance(spec_dir, str) or not spec_dir.strip()):
        problems.append(f"{where}.api_spec_dir must be a non-empty path")
    return problems


def _tls_problems(raw: dict[str, Any], where: str) -> list[str]:
    """Check the trust keys: one way to trust the cluster, and no contradictions."""
    problems: list[str] = []
    verify = raw.get("verify_ssl")
    if verify is not None and not isinstance(verify, bool):
        problems.append(f"{where}.verify_ssl must be true or false")
    bundle = raw.get("ca_bundle")
    if bundle is not None and (not isinstance(bundle, str) or not bundle.strip()):
        problems.append(f"{where}.ca_bundle must be a non-empty path")
        bundle = None
    pin = raw.get("tls_fingerprint")
    has_pin = pin not in (None, "")
    if has_pin and normalize_fingerprint(pin) is None:
        problems.append(
            f"{where}.tls_fingerprint must be a SHA-256 fingerprint "
            f"({FINGERPRINT_HEX_LENGTH} hex characters, ':' separators allowed)"
        )
    if bundle and verify is False:
        problems.append(f"{where}.ca_bundle cannot be combined with verify_ssl: false")
    if has_pin and (bundle or verify is True):
        problems.append(
            f"{where}.tls_fingerprint cannot be combined with ca_bundle or verify_ssl: true; "
            "choose the pin or chain validation"
        )
    if not has_pin and not bundle and verify is None:
        problems.append(
            f"{where} needs tls_fingerprint (the cluster's SHA-256 certificate pin), ca_bundle "
            "or verify_ssl: true, or, unsafely, verify_ssl: false"
        )
    return problems


def settings_from_mapping(
    resolved: dict[str, Any],
    *,
    config_dir: Path | None = None,
    where: str = "provider_settings.ontap",
) -> OntapSettings:
    """Build settings from an already secret-resolved mapping.

    Args:
        resolved: The ``provider_settings.ontap`` mapping with secrets resolved.
        config_dir: Anchor of relative ``ca_bundle`` and ``api_spec_dir`` paths.
        where: Prefix of every error message.

    Raises:
        OntapSettingsError: On a missing key or an invalid value. Names keys, never values.
    """
    problems = settings_problems(resolved, require_secret_refs=False, where=where)
    if problems:
        raise OntapSettingsError("; ".join(problems))
    bundle = resolved.get("ca_bundle")
    return OntapSettings(
        host=str(resolved["host"]).strip(),
        username=str(resolved["username"]),
        password=str(resolved["password"]),
        fingerprint=normalize_fingerprint(resolved.get("tls_fingerprint")),
        ca_bundle=_resolve_path(str(bundle), config_dir) if bundle else None,
        verify_ssl=resolved.get("verify_ssl"),
        timeout=int(resolved.get("timeout", DEFAULT_TIMEOUT)),
        api_spec_dir=_resolve_path(
            str(resolved.get("api_spec_dir") or DEFAULT_SPEC_DIR), config_dir
        ),
    )


def load_settings(config_dir: Path, env_name: str) -> OntapSettings:
    """Load and secret-resolve ``provider_settings.ontap`` for an environment.

    Args:
        config_dir: Configuration directory.
        env_name: Environment name.

    Raises:
        OntapSettingsError: If the settings are absent or invalid.
        SecretResolutionError: If a ``secret://`` reference cannot be resolved.
    """
    env_config = ConfigManager(config_dir).load_environment(env_name)
    raw = env_config.provider_settings.get(PROVIDER_NAME) if env_config else None
    if not raw or env_config is None:
        raise OntapSettingsError(f"No provider_settings.ontap found for environment '{env_name}'")
    problems = settings_problems(raw)
    if problems:
        raise OntapSettingsError("; ".join(problems))
    resolved = resolved_provider_settings(env_config, PROVIDER_NAME) or {}
    return settings_from_mapping(resolved, config_dir=config_dir)
