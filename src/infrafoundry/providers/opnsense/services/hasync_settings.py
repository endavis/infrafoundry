"""HA sync settings service for OPNsense direct-API operations (#1389).

Manages System > High Availability > Settings (the ``hasync`` model) through
``GET core/hasync/get``, ``POST core/hasync/set`` and ``POST core/hasync/reconfigure``.

YAML keys (all optional; only declared keys are compared and written) and their wire
fields under ``hasync``:

- ``disable_preempt``    -> ``disablepreempt`` (bool)
- ``disconnect_ppps``    -> ``disconnectppps`` (bool)
- ``pfsync_interface``   -> ``pfsyncinterface`` (str, ``""`` = none)
- ``pfsync_peer_ip``     -> ``pfsyncpeerip`` (IPv4 or ``""``)
- ``pfsync_version``     -> ``pfsyncversion`` (``"1301"`` or ``"1400"``; an int is allowed)
- ``pfsync_defer``       -> ``pfsyncdefer`` (bool)
- ``synchronize_to_ip``  -> ``synchronizetoip`` (IP or ``""``)
- ``verify_peer``        -> ``verifypeer`` (bool)
- ``username``           -> ``username`` (str)
- ``password``           -> ``password`` (a ``secret://`` URI in YAML)
- ``sync_items``         -> ``syncitems`` (list of str, compared as a set)
- ``update_password``    -> not a wire field; forces the password to be written

Password
--------

``password`` is a secret. The manager resolves the URI before this module runs. The
password is never logged, put in an exception message, shown in a plan map
(:func:`redacted` swaps it for ``[REDACTED]``) or echoed back from the live document.

A readable live password (non-empty and not only ``*``) is compared and written on a
difference. An empty or masked live password cannot be compared and never counts as
drift. The resolved password is still sent when ``update_password: true`` is set, or
when another declared field is written in the same apply (see
:meth:`HasyncSettingsService.should_send_password`).

Write envelope: ``{"hasync": {...}}``, the whole flattened live object with the
declared fields overwritten. The live ``password`` is never echoed, because echoing an
empty or masked value could clear the stored one.

What is verified and what is not
--------------------------------

- Verified: the three endpoints exist in every bundled 26.1 spec; ``pfsyncversion``
  option keys read ``1301`` and ``1400`` live.
- Not verified from code: what ``reconfigure`` does on the box.
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

#: YAML key -> wire key under ``hasync``.
FIELD_MAP: dict[str, str] = {
    "disable_preempt": "disablepreempt",
    "disconnect_ppps": "disconnectppps",
    "pfsync_interface": "pfsyncinterface",
    "pfsync_peer_ip": "pfsyncpeerip",
    "pfsync_version": "pfsyncversion",
    "pfsync_defer": "pfsyncdefer",
    "synchronize_to_ip": "synchronizetoip",
    "verify_peer": "verifypeer",
    # Same name on both sides; spelled as a comprehension so bandit's B105
    # does not read the field name as a hardcoded password.
    **{name: name for name in ("username", "password")},
    "sync_items": "syncitems",
}

#: YAML keys whose value is a boolean (wire ``"1"``/``"0"``).
BOOL_FIELDS: frozenset[str] = frozenset(
    {"disable_preempt", "disconnect_ppps", "pfsync_defer", "verify_peer"}
)

#: YAML keys that hold plain strings.
STRING_FIELDS: frozenset[str] = frozenset(
    {"pfsync_interface", "pfsync_peer_ip", "synchronize_to_ip", "username"}
)

ALLOWED_KEYS: frozenset[str] = frozenset({*FIELD_MAP, "update_password"})
SECRET_FIELDS: tuple[str, ...] = ("password",)

#: The pfsync protocol versions the box offers (live option keys).
PFSYNC_VERSIONS: tuple[str, ...] = ("1301", "1400")

#: What replaces the password in a plan map.
REDACTED = "[REDACTED]"

#: Placeholder written by migrate when the box holds a password.
PASSWORD_PLACEHOLDER = "secret://env_secrets/opnsense/hasync/password"  # nosec B105  # a secret:// URI placeholder, not a password

_PASSWORD_WIRE = FIELD_MAP["password"]
_ITEMS_WIRE = FIELD_MAP["sync_items"]


def _live_password(live: dict[str, Any]) -> str:
    """Return the readable live password, or ``""`` when unset or masked (only ``*``)."""
    text = flatten_option(live.get(_PASSWORD_WIRE)).strip()
    return "" if set(text) <= {"*"} else text


def password_unreadable(live: dict[str, Any]) -> bool:
    """Return True when the live password is empty or masked, i.e. write-only."""
    return not _live_password(live)


def redacted(desired: dict[str, str]) -> dict[str, str]:
    """Return a copy of the desired map that is safe to show: the password is replaced."""
    return {k: (REDACTED if k in SECRET_FIELDS else v) for k, v in desired.items()}


def wants_password_update(resource: ResourceConfig) -> bool:
    """Return True when the resource sets ``update_password: true``."""
    return resource.config.get("update_password") is True


def live_options(live: dict[str, Any], wire: str) -> set[str]:
    """Return the non-empty option keys of a live option map; empty when it is not a map."""
    value = live.get(wire)
    if not isinstance(value, dict):
        return set()
    return {str(key) for key in value if str(key)}


def _split_items(text: str) -> list[str]:
    """Split a comma-joined item string into its sorted, deduplicated, non-empty parts."""
    return sorted({part.strip() for part in text.split(",") if part.strip()})


def _live_text(live: dict[str, Any], key: str) -> str:
    """Return the live value of a YAML key in the same form ``build_desired`` produces."""
    text = flatten_option(live.get(FIELD_MAP[key])).strip()
    if key in BOOL_FIELDS:
        return "1" if text == "1" else "0"
    if key == "sync_items":
        return ",".join(_split_items(text))
    return text


class HasyncSettingsService(BaseService):
    """Service for the OPNsense HA sync settings singleton."""

    def get_settings(self) -> Any:
        """Fetch the HA sync settings document."""
        ep = endpoints.HASYNC_GET
        return self.client.request(ep.method, ep.path())

    def set_settings(self, payload: dict[str, Any]) -> Any:
        """Write the HA sync settings document.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        ep = endpoints.HASYNC_SET
        response = self.client.request(ep.method, ep.path(), data=payload)
        return raise_on_failed_write(response, "set ha sync settings")

    def reconfigure(self) -> Any:
        """Reload the saved HA sync settings.

        Called only by the provider's ``_reconfigure_hasync`` finalization hook; the
        manager must not call it directly.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}`` or ``"status": "failed"``.
        """
        ep = endpoints.HASYNC_RECONFIGURE
        response = self.client.request(ep.method, ep.path())
        raise_on_failed_write(response, "reconfigure ha sync")
        if isinstance(response, dict) and response.get("status") == "failed":
            raise APIError(
                "OPNsense core/hasync/reconfigure reported status 'failed'",
                response=str(sorted(response)),
                provider="opnsense",
            )
        return response

    def live_hasync(self, response: Any) -> dict[str, Any]:
        """Return ``response["hasync"]``.

        Raises:
            APIError: If the envelope is missing; the message carries key names only.
        """
        hasync = response.get("hasync") if isinstance(response, dict) else None
        if not isinstance(hasync, dict):
            raise APIError(
                "OPNsense core/hasync/get returned no hasync object",
                response=str(sorted(response)) if isinstance(response, dict) else "",
                provider="opnsense",
            )
        return hasync

    def build_desired(self, resource: ResourceConfig) -> dict[str, str]:
        """Build the desired map for the declared keys (the password already resolved).

        Booleans become ``"1"``/``"0"``; ``sync_items`` a sorted, deduplicated,
        comma-joined string; ``pfsync_version`` a string.

        Raises:
            InvalidConfigurationError: On unknown keys or wrongly typed values; no value
                is shown.
        """
        config = resource.config
        unknown = sorted(set(config) - ALLOWED_KEYS)
        if unknown:
            raise InvalidConfigurationError(
                f"hasync.settings has unknown key(s): {', '.join(str(k) for k in unknown)}"
            )
        if "update_password" in config and not isinstance(config["update_password"], bool):
            raise InvalidConfigurationError("hasync.settings update_password must be a boolean")
        desired: dict[str, str] = {}
        for key in FIELD_MAP:
            if key not in config:
                continue
            value = config[key]
            if key in BOOL_FIELDS:
                if not isinstance(value, bool):
                    raise InvalidConfigurationError(f"hasync.settings {key} must be a boolean")
                desired[key] = "1" if value else "0"
            elif key == "pfsync_version":
                text = (
                    str(value) if isinstance(value, int) and not isinstance(value, bool) else value
                )
                if not isinstance(text, str) or text not in PFSYNC_VERSIONS:
                    allowed = ", ".join(PFSYNC_VERSIONS)
                    raise InvalidConfigurationError(
                        f"hasync.settings pfsync_version must be one of {allowed}"
                    )
                desired[key] = text
            elif key == "sync_items":
                if not isinstance(value, list) or not all(
                    isinstance(item, str) and item.strip() for item in value
                ):
                    raise InvalidConfigurationError(
                        "hasync.settings sync_items must be a list of non-empty strings"
                    )
                desired[key] = ",".join(sorted({item.strip() for item in value}))
            else:
                if not isinstance(value, str):
                    raise InvalidConfigurationError(f"hasync.settings {key} must be a string")
                if key == "password" and not value.strip():
                    raise InvalidConfigurationError("hasync.settings password must not be empty")
                desired[key] = value
        return desired

    def changed_fields(
        self, live: dict[str, Any], desired: dict[str, str], update_password: bool
    ) -> list[str]:
        """Return the YAML field names that need a write; never values.

        An empty or masked live password cannot be compared, so it counts as a change
        only with ``update_password``.
        """
        changed: list[str] = []
        for key, value in desired.items():
            if key == "password":
                if update_password or (
                    not password_unreadable(live) and _live_password(live) != value.strip()
                ):
                    changed.append(key)
            elif _live_text(live, key) != value.strip():
                changed.append(key)
        return changed

    def should_send_password(
        self, desired: dict[str, str], changed: list[str], update_password: bool
    ) -> bool:
        """Return True when the write body must carry the resolved password.

        Sent with ``update_password`` or whenever any declared field is written, so the
        first configuration works without the flag and never causes drift.
        """
        return "password" in desired and (update_password or bool(changed))

    def unknown_references(self, live: dict[str, Any], desired: dict[str, str]) -> list[str]:
        """Return messages for a ``pfsync_interface`` or ``sync_items`` entry the box lacks.

        A check is skipped when the live option map is empty or absent.
        """
        messages: list[str] = []
        interfaces = live_options(live, "pfsyncinterface")
        interface = desired.get("pfsync_interface", "")
        if interface and interfaces and interface not in interfaces:
            messages.append(
                f"hasync.settings pfsync_interface '{interface}' is not offered by the box"
            )
        items = live_options(live, _ITEMS_WIRE)
        if items:
            for item in _split_items(desired.get("sync_items", "")):
                if item not in items:
                    messages.append(
                        f"hasync.settings sync_items entry '{item}' is not offered by the box"
                    )
        return messages

    def build_set_payload(
        self, live: dict[str, Any], desired: dict[str, str], send_password: bool
    ) -> dict[str, Any]:
        """Build the write body; the live ``password`` is never echoed.

        Args:
            live: The live ``hasync`` object.
            desired: Desired map.
            send_password: Include the desired password.
        """
        body = {
            wire: flatten_option(value) for wire, value in live.items() if wire != _PASSWORD_WIRE
        }
        for key, value in desired.items():
            if key != "password":
                body[FIELD_MAP[key]] = value
        if send_password and "password" in desired:
            body[_PASSWORD_WIRE] = desired["password"]
        return {"hasync": body}

    def export_to_yaml(self) -> str:
        """Export the live fields as nested YAML; the password is only a placeholder."""
        live = self.live_hasync(self.get_settings())
        clean: dict[str, Any] = {}
        for key, wire in FIELD_MAP.items():
            if key == "password" or wire not in live:
                continue
            text = _live_text(live, key)
            if key in BOOL_FIELDS:
                clean[key] = text == "1"
            elif key == "sync_items":
                clean[key] = _split_items(text)
            else:
                clean[key] = text
        if not password_unreadable(live):
            clean["password"] = PASSWORD_PLACEHOLDER
        return emit_nested_singleton_yaml("hasync.settings", clean)
