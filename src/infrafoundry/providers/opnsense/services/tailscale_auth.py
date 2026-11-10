"""Tailscale authentication service for OPNsense direct-API operations (#787).

Manages the ``authentication`` section of the ``os-tailscale`` plugin through
``GET tailscale/authentication/get`` and ``POST tailscale/authentication/set``.

YAML keys and their wire fields:

- ``login_server``         -> ``loginServer`` (an ``http(s)://`` URL)
- ``pre_auth_key``         -> ``preAuthKey`` (a ``secret://`` URI in YAML)
- ``update_pre_auth_key``  -> not a wire field; forces the key to be written

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
from typing import Any

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
ALLOWED_KEYS: frozenset[str] = frozenset({*FIELD_MAP, "update_pre_auth_key"})
SECRET_FIELDS: tuple[str, ...] = ("pre_auth_key",)

#: What replaces the key in a plan map.
REDACTED = "[REDACTED]"

#: Placeholder written by migrate when the box holds a key.
KEY_PLACEHOLDER = "secret://env_secrets/opnsense/tailscale/auth/pre_auth_key"

_LOGIN_WIRE = FIELD_MAP["login_server"]
_KEY_WIRE = FIELD_MAP["pre_auth_key"]


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
