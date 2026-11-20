"""Tailscale authentication service for OPNsense direct-API operations (#787).

Manages the ``authentication`` section of the ``os-tailscale`` plugin through
``GET tailscale/authentication/get`` and ``POST tailscale/authentication/set``.

YAML keys and their wire fields:

- ``login_server``         -> ``loginServer`` (an ``http(s)://`` URL)
- ``pre_auth_key``         -> ``preAuthKey`` (a ``secret://`` URI in YAML)
- ``update_pre_auth_key``  -> not a wire field; forces the key to be written
- ``mint``                 -> not a wire field; mints the key from an OAuth client at apply

Key material
------------

``pre_auth_key`` is a secret. The validator rejects a literal; the manager resolves the
URI before this module runs. The key is never logged, put in an exception message, shown
in a ``repr``, placed in a plan map (:func:`redacted` swaps it for ``[REDACTED]``) or
echoed back from the live document.

Write policy: when the live ``preAuthKey`` is non-empty it is compared (both sides
stripped) and written on a difference. When it is empty or masked the key is write-only:
it is sent only with ``update_pre_auth_key: true``. With ``update_pre_auth_key: true`` the
key is always sent and counts as a change. The write body echoes the live ``loginServer``
overwritten by the declared value but never the live ``preAuthKey``, because echoing an
empty or masked value would clear the stored key.

Minting (#1510)
---------------

``mint`` replaces ``pre_auth_key``: at apply, when ``tailscale/status/status`` does not
report ``BackendState: Running``, a single-use, tagged, short-lived key is created through
the Tailscale API from an OAuth client (``oauth_client_id``, ``oauth_client_secret``, both
``secret://``), written with ``authentication/set`` and never logged, shown, stored or
put in an exception. The OAuth client needs the ``auth_keys`` scope and must own the tags.

What is verified and what is not
--------------------------------

- Verified by a read-only probe (#787): the envelope is ``authentication`` with
  ``loginServer`` and ``preAuthKey``.
- Verified on a test firewall: ``set`` stores the key and ``get`` echoes it, so a
  changed key is detected without ``update_pre_auth_key``; the write-only path
  stays for a box that returns it empty or masked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import requests

from infrafoundry.core import tailscale as tailscale_core
from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService, raise_on_failed_write
from .openvpn_instances import flatten_option

logger = logging.getLogger(__name__)

#: YAML key -> wire key under ``authentication``.
FIELD_MAP: dict[str, str] = {
    "login_server": "loginServer",
    "pre_auth_key": "preAuthKey",
}
ALLOWED_KEYS: frozenset[str] = frozenset({*FIELD_MAP, "update_pre_auth_key", "mint"})
SECRET_FIELDS: tuple[str, ...] = ("pre_auth_key",)

#: What replaces the key in a plan map.
REDACTED = "[REDACTED]"

#: What the plan map shows for a key that apply will mint.
MINT_PLACEHOLDER = "[MINTED AT APPLY]"

#: Keys allowed in the ``mint`` block, and the bounds of ``expiry_seconds``.
MINT_KEYS: frozenset[str] = frozenset(
    {
        "oauth_client_id",
        "oauth_client_secret",
        "tags",
        "ephemeral",
        "preauthorized",
        "expiry_seconds",
    }
)
MIN_EXPIRY_SECONDS = 1
MAX_EXPIRY_SECONDS = 7776000  # 90 days, the Tailscale maximum
DEFAULT_EXPIRY_SECONDS = 3600

#: Description of minted keys in the Tailscale admin console.
MINT_DESCRIPTION = "infrafoundry opnsense tailscale auth"
MINT_TIMEOUT = 30.0

#: Placeholder written by migrate when the box holds a key.
KEY_PLACEHOLDER = "secret://env_secrets/opnsense/tailscale/auth/pre_auth_key"

_LOGIN_WIRE = FIELD_MAP["login_server"]
_KEY_WIRE = FIELD_MAP["pre_auth_key"]


@dataclass(frozen=True)
class MintSpec:
    """The ``mint`` block, parsed. The OAuth credentials are secrets: kept out of ``repr``."""

    oauth_client_id: str = field(repr=False)
    oauth_client_secret: str = field(repr=False)
    tags: tuple[str, ...]
    ephemeral: bool = False
    preauthorized: bool = True
    expiry_seconds: int = DEFAULT_EXPIRY_SECONDS


def _text(mint: dict[str, Any], key: str) -> str:
    value = mint.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidConfigurationError(f"tailscale.auth mint.{key} must be a non-empty string")
    return value


def _flag(mint: dict[str, Any], key: str, default: bool) -> bool:
    value = mint.get(key, default)
    if not isinstance(value, bool):
        raise InvalidConfigurationError(f"tailscale.auth mint.{key} must be a boolean")
    return value


def parse_mint(config: dict[str, Any]) -> MintSpec | None:
    """Parse the ``mint`` block of a ``tailscale.auth`` config.

    Args:
        config: The resource config. Credentials may still be ``secret://`` URIs.

    Returns:
        The spec, or ``None`` when ``mint`` is absent.

    Raises:
        InvalidConfigurationError: On a bad block or a conflict with ``pre_auth_key``;
            messages name fields, never values.
    """
    if "mint" not in config:
        return None
    for conflict in ("pre_auth_key", "update_pre_auth_key"):
        if conflict in config:
            raise InvalidConfigurationError(
                f"tailscale.auth mint and {conflict} are mutually exclusive"
            )
    mint = config["mint"]
    if not isinstance(mint, dict):
        raise InvalidConfigurationError("tailscale.auth mint must be a mapping")
    unknown = sorted(str(k) for k in set(mint) - MINT_KEYS)
    if unknown:
        raise InvalidConfigurationError(
            f"tailscale.auth mint has unknown key(s): {', '.join(unknown)}"
        )
    tags = mint.get("tags")
    if (
        not isinstance(tags, list)
        or not tags
        or not all(isinstance(t, str) and t.startswith("tag:") and len(t) > 4 for t in tags)
    ):
        raise InvalidConfigurationError(
            "tailscale.auth mint.tags must be a non-empty list of 'tag:' strings"
        )
    expiry = mint.get("expiry_seconds", DEFAULT_EXPIRY_SECONDS)
    if (
        isinstance(expiry, bool)
        or not isinstance(expiry, int)
        or not MIN_EXPIRY_SECONDS <= expiry <= MAX_EXPIRY_SECONDS
    ):
        raise InvalidConfigurationError(
            f"tailscale.auth mint.expiry_seconds must be an integer from "
            f"{MIN_EXPIRY_SECONDS} to {MAX_EXPIRY_SECONDS}"
        )
    return MintSpec(
        oauth_client_id=_text(mint, "oauth_client_id"),
        oauth_client_secret=_text(mint, "oauth_client_secret"),
        tags=tuple(tags),
        ephemeral=_flag(mint, "ephemeral", False),
        preauthorized=_flag(mint, "preauthorized", True),
        expiry_seconds=expiry,
    )


def _live_key(live: dict[str, Any]) -> str:
    """Return the readable live key, or ``""`` when unset or masked (only ``*``)."""
    text = flatten_option(live.get(_KEY_WIRE)).strip()
    return "" if set(text) <= {"*"} else text


def key_unreadable(live: dict[str, Any]) -> bool:
    """Return True when the live key is empty or masked, i.e. write-only."""
    return not _live_key(live)


def redacted(desired: dict[str, str]) -> dict[str, str]:
    """Return a copy of the desired map that is safe to show: the key is replaced."""
    return {k: (REDACTED if k in SECRET_FIELDS else v) for k, v in desired.items()}


def wants_key_update(resource: ResourceConfig) -> bool:
    """Return True when the resource sets ``update_pre_auth_key: true``."""
    return resource.config.get("update_pre_auth_key") is True


class TailscaleAuthService(BaseService):
    """Service for the Tailscale authentication singleton."""

    def get_auth(self) -> Any:
        """Fetch the Tailscale authentication document."""
        ep = endpoints.TAILSCALE_AUTH_GET
        return self.client.request(ep.method, ep.path())

    def set_auth(self, payload: dict[str, Any]) -> Any:
        """Write the Tailscale authentication document.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        ep = endpoints.TAILSCALE_AUTH_SET
        response = self.client.request(ep.method, ep.path(), data=payload)
        return raise_on_failed_write(response, "set tailscale authentication")

    def get_status(self) -> Any:
        """Fetch the Tailscale status document (read-only)."""
        ep = endpoints.TAILSCALE_STATUS
        return self.client.request(ep.method, ep.path())

    @staticmethod
    def backend_state(response: Any) -> str:
        """Return ``BackendState`` from a status response, ``""`` when absent."""
        if not isinstance(response, dict):
            return ""
        state = response.get("BackendState")
        if state is None and isinstance(response.get("status"), dict):
            state = response["status"].get("BackendState")
        return state if isinstance(state, str) else ""

    def is_running(self) -> bool:
        """Return True when the node is logged in (``BackendState`` is ``Running``)."""
        return self.backend_state(self.get_status()) == "Running"

    def service_enabled(self) -> bool:
        """Return True when the plugin's ``enabled`` setting is ``"1"``."""
        ep = endpoints.TAILSCALE_SETTINGS_GET
        response = self.client.request(ep.method, ep.path())
        settings = response.get("settings") if isinstance(response, dict) else None
        return isinstance(settings, dict) and flatten_option(settings.get("enabled")) == "1"

    def reconfigure(self) -> Any:
        """Apply the saved Tailscale configuration.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        ep = endpoints.TAILSCALE_RECONFIGURE
        response = self.client.request(ep.method, ep.path())
        return raise_on_failed_write(response, "reconfigure tailscale")

    def mint_key(
        self,
        spec: MintSpec,
        *,
        session: requests.Session | None = None,
        api_base: str = tailscale_core.TAILSCALE_API_BASE,
    ) -> str:
        """Create a single-use pre-auth key through the Tailscale API.

        Args:
            spec: The parsed ``mint`` block.
            session: HTTP session, injectable for tests.
            api_base: Tailscale API base URL.

        Returns:
            The key. The caller must never log or store it.

        Raises:
            APIError: On any failure; the message carries a status or an exception type,
                never a credential, token or key.
        """
        http = session or requests.Session()
        try:
            token = tailscale_core.request_oauth_token(
                http, api_base, spec.oauth_client_id, spec.oauth_client_secret, MINT_TIMEOUT
            )
            return tailscale_core.create_auth_key(
                http,
                api_base,
                token,
                tags=list(spec.tags),
                ephemeral=spec.ephemeral,
                preauthorized=spec.preauthorized,
                expiry_seconds=spec.expiry_seconds,
                description=MINT_DESCRIPTION,
                timeout=MINT_TIMEOUT,
            )
        except RuntimeError as exc:  # message carries the HTTP status and API message
            raise APIError(f"tailscale key mint failed: {exc}", provider="opnsense") from None
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            raise APIError(
                f"tailscale key mint failed: {type(exc).__name__}", provider="opnsense"
            ) from None

    def live_auth(self, response: Any) -> dict[str, Any]:
        """Return ``response["authentication"]``.

        Raises:
            APIError: If the envelope is missing; the message carries key names only.
        """
        auth = response.get("authentication") if isinstance(response, dict) else None
        if not isinstance(auth, dict):
            raise APIError(
                "OPNsense tailscale/authentication/get returned no authentication object",
                response=str(sorted(response)) if isinstance(response, dict) else "",
                provider="opnsense",
            )
        return auth

    def build_desired(self, resource: ResourceConfig) -> dict[str, str]:
        """Build the desired map for the declared keys (the key already resolved).

        Raises:
            InvalidConfigurationError: On unknown keys or wrongly typed values; no value
                is shown.
        """
        config = resource.config
        unknown = sorted(set(config) - ALLOWED_KEYS)
        if unknown:
            raise InvalidConfigurationError(
                f"tailscale.auth has unknown key(s): {', '.join(unknown)}"
            )
        if "update_pre_auth_key" in config and not isinstance(config["update_pre_auth_key"], bool):
            raise InvalidConfigurationError("tailscale.auth update_pre_auth_key must be a boolean")
        desired: dict[str, str] = {}
        for key in FIELD_MAP:
            if key not in config:
                continue
            value = config[key]
            if not isinstance(value, str):
                raise InvalidConfigurationError(f"tailscale.auth {key} must be a string")
            if key == "pre_auth_key" and not value.strip():
                raise InvalidConfigurationError("tailscale.auth pre_auth_key must not be empty")
            desired[key] = value
        return desired

    def changed_fields(
        self, live: dict[str, Any], desired: dict[str, str], update_key: bool
    ) -> list[str]:
        """Return the YAML field names that need a write; never values."""
        changed: list[str] = []
        if "login_server" in desired:
            have = flatten_option(live.get(_LOGIN_WIRE)).strip()
            if have != desired["login_server"].strip():
                changed.append("login_server")
        if "pre_auth_key" in desired:
            have_key = _live_key(live)
            if update_key or (have_key and have_key != desired["pre_auth_key"].strip()):
                changed.append("pre_auth_key")
        return changed

    def build_set_payload(
        self, live: dict[str, Any], desired: dict[str, str], send_key: bool
    ) -> dict[str, Any]:
        """Build the write body; the live ``preAuthKey`` is never echoed.

        Args:
            live: The live ``authentication`` object.
            desired: Desired map.
            send_key: Include the desired key.
        """
        body = {wire: flatten_option(value) for wire, value in live.items() if wire != _KEY_WIRE}
        if "login_server" in desired:
            body[_LOGIN_WIRE] = desired["login_server"]
        if send_key and "pre_auth_key" in desired:
            body[_KEY_WIRE] = desired["pre_auth_key"]
        return {"authentication": body}

    def export_to_yaml(self) -> str:
        """Export ``login_server`` and, when the box holds a key, only the placeholder."""
        live = self.live_auth(self.get_auth())
        clean: dict[str, Any] = {}
        if _LOGIN_WIRE in live:
            clean["login_server"] = flatten_option(live[_LOGIN_WIRE])
        if not key_unreadable(live):
            clean["pre_auth_key"] = KEY_PLACEHOLDER
        return emit_nested_singleton_yaml("tailscale.auth", clean)
