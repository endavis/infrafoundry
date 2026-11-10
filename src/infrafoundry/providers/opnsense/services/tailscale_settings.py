"""Tailscale settings service for OPNsense direct-API operations (#787).

Manages the ``settings`` section of the ``os-tailscale`` plugin through
``GET tailscale/settings/get``, ``POST tailscale/settings/set`` and
``POST tailscale/service/reconfigure``.

YAML keys (all optional; only declared keys are compared and written) and their wire
fields under ``settings``:

- ``enabled``              -> ``enabled`` (bool)
- ``login_timeout``        -> ``loginTimeout`` (non-negative int)
- ``listen_port``          -> ``listenPort`` (0-65535)
- ``accept_dns``           -> ``acceptDNS`` (bool)
- ``advertise_exit_node``  -> ``advertiseExitNode`` (bool)
- ``use_exit_node``        -> ``useExitNode`` (string, ``""`` = none)
- ``accept_subnet_routes`` -> ``acceptSubnetRoutes`` (bool)
- ``enable_ssh``           -> ``enableSSH`` (bool)
- ``enable_snat``          -> ``disableSNAT`` (bool, INVERTED: ``true`` is wire ``"0"``)

The probed ``get`` nests the subnet list inside the settings model as
``subnets: {subnet4: [...]}``. The write body never carries ``subnets``: OPNsense MVC
``set`` updates only the nodes posted, so omitting it leaves the list to the subnet CRUD
(``tailscale.subnets``).

``useExitNode`` is an option dict on ``get``; the live value is its selected key. The
offers depend on peers, so the manager checks the declared value against
:meth:`TailscaleSettingsService.exit_node_offers`.

What is verified and what is not
--------------------------------

- Verified on a test firewall (#787): the ``get`` shape described above, ``set``
  (``disableSNAT`` inversion, subnets untouched) and ``service/reconfigure``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService, raise_on_failed_write
from .openvpn_instances import flatten_option

logger = logging.getLogger(__name__)

#: YAML key -> wire key under ``settings``.
FIELD_MAP: dict[str, str] = {
    "enabled": "enabled",
    "login_timeout": "loginTimeout",
    "listen_port": "listenPort",
    "accept_dns": "acceptDNS",
    "advertise_exit_node": "advertiseExitNode",
    "use_exit_node": "useExitNode",
    "accept_subnet_routes": "acceptSubnetRoutes",
    "enable_ssh": "enableSSH",
    "enable_snat": "disableSNAT",
}

BOOL_FIELDS: frozenset[str] = frozenset(
    {
        "enabled",
        "accept_dns",
        "advertise_exit_node",
        "accept_subnet_routes",
        "enable_ssh",
        "enable_snat",
    }
)
#: Boolean YAML keys whose wire value is the opposite.
INVERTED_BOOL_FIELDS: frozenset[str] = frozenset({"enable_snat"})
PORT_FIELDS: frozenset[str] = frozenset({"listen_port"})
INT_FIELDS: frozenset[str] = frozenset({"login_timeout"})
STRING_FIELDS: frozenset[str] = frozenset({"use_exit_node"})

#: Keys that are refused, each with a hint.
REFUSED_KEY_HINTS: dict[str, str] = {
    "subnets": "use the tailscale.subnets type",
    "disable_snat": "use enable_snat, which is the inverse",
    "hostname": "not a plugin setting",
    "exit_node": "not a plugin setting; use use_exit_node or advertise_exit_node",
}

#: Wire keys of the settings model that are separate lists; never echoed on write.
NESTED_WIRE_KEYS: frozenset[str] = frozenset({"subnets"})


def serialize_setting(key: str, value: Any) -> str:
    """Serialize one settings value to its wire string.

    Raises:
        InvalidConfigurationError: On a wrong type or out-of-range value (no value shown).
    """
    label = f"tailscale.settings {key}"
    if key in BOOL_FIELDS:
        if not isinstance(value, bool):
            raise InvalidConfigurationError(f"{label} must be a boolean")
        on = value != (key in INVERTED_BOOL_FIELDS)
        return "1" if on else "0"
    if key in STRING_FIELDS:
        if not isinstance(value, str):
            raise InvalidConfigurationError(f"{label} must be a string")
        return value
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidConfigurationError(f"{label} must be an integer")
    if key in PORT_FIELDS:
        if not 0 <= value <= 65535:
            raise InvalidConfigurationError(f"{label} must be in range 0-65535")
    elif value < 0:
        raise InvalidConfigurationError(f"{label} must be a non-negative integer")
    return str(value)


class TailscaleSettingsService(BaseService):
    """Service for the Tailscale settings singleton."""

    def get_settings(self) -> Any:
        """Fetch the Tailscale settings document."""
        ep = endpoints.TAILSCALE_SETTINGS_GET
        return self.client.request(ep.method, ep.path())

    def set_settings(self, payload: dict[str, Any]) -> Any:
        """Write the Tailscale settings document.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        ep = endpoints.TAILSCALE_SETTINGS_SET
        response = self.client.request(ep.method, ep.path(), data=payload)
        return raise_on_failed_write(response, "set tailscale settings")

    def reconfigure(self) -> Any:
        """Apply the saved Tailscale configuration.

        Called by the provider's ``tailscale_reconfigure`` finalization hook (and by the
        subnet manager's destroy); the managers' ``apply`` must not call it.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        ep = endpoints.TAILSCALE_RECONFIGURE
        response = self.client.request(ep.method, ep.path())
        return raise_on_failed_write(response, "reconfigure tailscale")

    def live_settings(self, response: Any) -> dict[str, Any]:
        """Return ``response["settings"]``.

        Raises:
            APIError: If the envelope is missing, so a write is never built from nothing.
        """
        settings = response.get("settings") if isinstance(response, dict) else None
        if not isinstance(settings, dict):
            raise APIError(
                "OPNsense tailscale/settings/get returned no settings object",
                response=str(sorted(response)) if isinstance(response, dict) else "",
                provider="opnsense",
            )
        return settings

    def build_desired(self, resource: ResourceConfig) -> dict[str, str]:
        """Build the desired wire strings for the declared keys only.

        Raises:
            InvalidConfigurationError: On unknown or refused keys, or wrongly typed values.
        """
        config = resource.config
        unknown = sorted(set(config) - set(FIELD_MAP))
        if unknown:
            hints = "".join(
                f" ({k}: {REFUSED_KEY_HINTS[k]})" for k in unknown if k in REFUSED_KEY_HINTS
            )
            raise InvalidConfigurationError(
                f"tailscale.settings has unknown key(s): {', '.join(unknown)}{hints}"
            )
        desired: dict[str, str] = {}
        for key in FIELD_MAP:
            if key in config:
                desired[key] = serialize_setting(key, config[key])
        return desired

    def extract_live(self, settings: dict[str, Any], keys: Iterable[str]) -> dict[str, str]:
        """Extract the given YAML keys from the live object, as wire strings.

        Inverted keys keep their wire value. Raises ``APIError`` for an absent field.
        """
        live: dict[str, str] = {}
        for key in keys:
            wire = FIELD_MAP[key]
            if wire not in settings:
                raise APIError(
                    f"OPNsense tailscale/settings/get returned no '{wire}' field",
                    response=str(sorted(settings))[:200],
                    provider="opnsense",
                )
            live[key] = flatten_option(settings[wire])
        return live

    def drift(self, live: dict[str, str], desired: dict[str, str]) -> dict[str, str] | None:
        """Compare declared keys; return ``desired`` on any difference."""
        for key, value in desired.items():
            if live.get(key) != value:
                return desired
        return None

    @staticmethod
    def exit_node_offers(settings: dict[str, Any]) -> set[str]:
        """Return the exit-node values the box currently offers (``""`` included)."""
        value = settings.get(FIELD_MAP["use_exit_node"])
        if isinstance(value, dict):
            return {str(k) for k in value}
        return {""}

    def build_set_payload(
        self, settings: dict[str, Any], desired: dict[str, str]
    ) -> dict[str, Any]:
        """Build the write body: the flattened live section, declared fields set.

        Nested list nodes (``subnets``) are dropped, never echoed.
        """
        flat = {
            key: flatten_option(value)
            for key, value in settings.items()
            if key not in NESTED_WIRE_KEYS
        }
        for key, value in desired.items():
            flat[FIELD_MAP[key]] = value
        return {"settings": flat}

    def export_to_yaml(self) -> str:
        """Export every mapped field present on the box as nested YAML."""
        settings = self.live_settings(self.get_settings())
        present = [key for key, wire in FIELD_MAP.items() if wire in settings]
        live = self.extract_live(settings, present)
        clean: dict[str, Any] = {}
        for key in present:
            text = live[key]
            if key in BOOL_FIELDS:
                clean[key] = (text == "1") != (key in INVERTED_BOOL_FIELDS)
            elif key in STRING_FIELDS:
                clean[key] = text
            elif text.isascii() and text.isdigit():
                clean[key] = int(text)
            else:
                logger.warning("tailscale.settings: non-integer %s; omitted", key)
        return emit_nested_singleton_yaml("tailscale.settings", clean)
