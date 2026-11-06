"""Interface-settings service for OPNsense direct-API operations (#1092).

Manages the ``OPNsense\\Interfaces\\Settings`` model (hardware offloading, VLAN
hardware filtering, IPv6 and the DHCPv6 client) through
``GET interfaces/settings/get``, ``POST interfaces/settings/set`` and
``POST interfaces/settings/reconfigure``.

YAML keys (all optional; only declared keys are compared and written) and their
wire fields under ``settings``:

- ``disable_checksum_offloading``      -> ``disablechecksumoffloading`` (bool)
- ``disable_segmentation_offloading``  -> ``disablesegmentationoffloading`` (bool)
- ``disable_large_receive_offloading`` -> ``disablelargereceiveoffloading`` (bool)
- ``vlan_hardware_filtering``          -> ``disablevlanhwfilter``
  (``enable`` = ``"0"``, ``disable`` = ``"1"``, ``default`` = ``"2"``)
- ``disable_ipv6``                     -> ``disableipv6`` (bool)
- ``dhcp6_no_release``                 -> ``dhcp6_norelease`` (bool)
- ``dhcp6_debug``                      -> ``dhcp6_debug`` (bool)
- ``dhcp6_duid``                       -> ``dhcp6_duid`` (str)
- ``dhcp6_ra_timeout``                 -> ``dhcp6_ratimeout`` (int)

Write envelope: both GET and SET use the key ``settings``
(``{"settings": {...}}``); the bundled 26.1 spec agrees. The apply posts the whole
flattened live ``settings`` object with the declared fields overwritten, so
undeclared settings stay unchanged.

Unverified live: the ``set`` and ``reconfigure`` calls have not been run against a
box. The GET shape and the defaults were probed on 26.1.6_2.
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

logger = logging.getLogger(__name__)

#: YAML key -> wire key under ``settings``.
FIELD_MAP: dict[str, str] = {
    "disable_checksum_offloading": "disablechecksumoffloading",
    "disable_segmentation_offloading": "disablesegmentationoffloading",
    "disable_large_receive_offloading": "disablelargereceiveoffloading",
    "vlan_hardware_filtering": "disablevlanhwfilter",
    "disable_ipv6": "disableipv6",
    "dhcp6_no_release": "dhcp6_norelease",
    "dhcp6_debug": "dhcp6_debug",
    "dhcp6_duid": "dhcp6_duid",
    "dhcp6_ra_timeout": "dhcp6_ratimeout",
}

#: YAML keys whose value is a boolean (wire ``"1"``/``"0"``).
BOOL_FIELDS: frozenset[str] = frozenset(
    {
        "disable_checksum_offloading",
        "disable_segmentation_offloading",
        "disable_large_receive_offloading",
        "disable_ipv6",
        "dhcp6_no_release",
        "dhcp6_debug",
    }
)

#: ``vlan_hardware_filtering`` value -> wire value.
VLAN_FILTER_VALUES: dict[str, str] = {"enable": "0", "disable": "1", "default": "2"}

#: Model defaults in YAML terms (OPNsense 26.1.6 ``Settings.xml``); ``export_to_yaml``
#: emits only fields that differ from these.
DEFAULTS: dict[str, Any] = {
    "disable_checksum_offloading": True,
    "disable_segmentation_offloading": True,
    "disable_large_receive_offloading": True,
    "vlan_hardware_filtering": "default",
    "disable_ipv6": False,
    "dhcp6_no_release": False,
    "dhcp6_debug": False,
    "dhcp6_duid": "",
    "dhcp6_ra_timeout": 10,
}


def _flatten(value: Any) -> str:
    """Flatten a live field into its wire string.

    An option dict (``{"1": {"value": "Disable", "selected": 1}, ...}``) flattens to
    the comma-joined selected keys. An option list
    (``[{"value": "Disable", "selected": 1}, ...]``) flattens to the comma-joined
    positional indexes of the selected entries. ``None`` and ``[]`` flatten to ``""``.
    """
    if isinstance(value, list):
        return ",".join(
            str(index)
            for index, entry in enumerate(value)
            if isinstance(entry, dict) and entry.get("selected")
        )
    if isinstance(value, dict):
        return ",".join(
            str(key)
            for key, meta in value.items()
            if str(key) and isinstance(meta, dict) and meta.get("selected")
        )
    if value is None or value == []:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


class InterfacesSettingsService(BaseService):
    """Service for the OPNsense interface-settings singleton."""

    def get_settings(self) -> Any:
        """Fetch the interface-settings document."""
        return self.client.request(
            endpoints.INTERFACES_SETTINGS_GET.method, endpoints.INTERFACES_SETTINGS_GET.path()
        )

    def set_settings(self, payload: dict[str, Any]) -> Any:
        """Write the interface-settings document.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        response = self.client.request(
            endpoints.INTERFACES_SETTINGS_SET.method,
            endpoints.INTERFACES_SETTINGS_SET.path(),
            data=payload,
        )
        return raise_on_failed_write(response, "set interface settings")

    def reconfigure(self) -> Any:
        """Apply the saved interface settings.

        Called only by the provider's ``_reconfigure_interfaces_settings``
        finalization hook; the manager must not call it directly.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        response = self.client.request(
            endpoints.INTERFACES_SETTINGS_RECONFIGURE.method,
            endpoints.INTERFACES_SETTINGS_RECONFIGURE.path(),
        )
        return raise_on_failed_write(response, "reconfigure interface settings")

    def live_settings(self, response: Any) -> dict[str, Any]:
        """Return ``response["settings"]``.

        Raises:
            APIError: If the envelope is missing, so a write is never built from nothing.
        """
        settings = response.get("settings") if isinstance(response, dict) else None
        if not isinstance(settings, dict):
            raise APIError(
                "OPNsense interfaces/settings/get returned no settings object",
                response=str(response)[:200],
                provider="opnsense",
            )
        return settings

    def build_desired(self, resource: ResourceConfig) -> dict[str, str]:
        """Build the desired wire strings for the declared keys only.

        Raises:
            InvalidConfigurationError: On unknown keys or wrongly typed values.
        """
        config = resource.config
        unknown = sorted(set(config) - set(FIELD_MAP))
        if unknown:
            raise InvalidConfigurationError(
                f"interfaces.settings has unknown key(s): {', '.join(unknown)}"
            )
        desired: dict[str, str] = {}
        for key in FIELD_MAP:
            if key not in config:
                continue
            value = config[key]
            if key in BOOL_FIELDS:
                if not isinstance(value, bool):
                    raise InvalidConfigurationError(f"interfaces.settings {key} must be a boolean")
                desired[key] = "1" if value else "0"
            elif key == "vlan_hardware_filtering":
                if not isinstance(value, str) or value not in VLAN_FILTER_VALUES:
                    raise InvalidConfigurationError(
                        "interfaces.settings vlan_hardware_filtering must be one of: "
                        + ", ".join(VLAN_FILTER_VALUES)
                    )
                desired[key] = VLAN_FILTER_VALUES[value]
            elif key == "dhcp6_duid":
                if not isinstance(value, str):
                    raise InvalidConfigurationError(
                        "interfaces.settings dhcp6_duid must be a string"
                    )
                desired[key] = value.strip()
            else:
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise InvalidConfigurationError(
                        f"interfaces.settings {key} must be a non-negative integer"
                    )
                desired[key] = str(value)
        return desired

    def extract_live(self, settings: dict[str, Any], keys: Iterable[str]) -> dict[str, str]:
        """Extract the given YAML keys from the live object, as wire strings.

        Raises:
            APIError: If a requested field is absent from the live object.
        """
        live: dict[str, str] = {}
        for key in keys:
            wire = FIELD_MAP[key]
            if wire not in settings:
                raise APIError(
                    f"OPNsense interfaces/settings/get returned no '{wire}' field",
                    response=str(sorted(settings))[:200],
                    provider="opnsense",
                )
            live[key] = _flatten(settings[wire])
        return live

    def drift(self, live: dict[str, str], desired: dict[str, str]) -> dict[str, str] | None:
        """Compare declared keys; return ``desired`` on any difference."""
        for key, value in desired.items():
            if live.get(key) != value:
                return desired
        return None

    def build_set_payload(
        self, settings: dict[str, Any], desired: dict[str, str]
    ) -> dict[str, Any]:
        """Build the write body: the whole flattened live object with declared fields set."""
        flat = {key: _flatten(value) for key, value in settings.items()}
        for key, value in desired.items():
            flat[FIELD_MAP[key]] = value
        return {"settings": flat}

    def export_to_yaml(self) -> str:
        """Export the settings that differ from the model defaults as nested YAML.

        An unrecognised ``disablevlanhwfilter`` value is logged and omitted.
        """
        settings = self.live_settings(self.get_settings())
        present = [key for key, wire in FIELD_MAP.items() if wire in settings]
        live = self.extract_live(settings, present)
        clean: dict[str, Any] = {}
        for key in present:
            value = self._to_yaml_value(key, live[key])
            if value is None or value == DEFAULTS[key]:
                continue
            clean[key] = value
        return emit_nested_singleton_yaml("interfaces.settings", clean)

    @staticmethod
    def _to_yaml_value(key: str, wire: str) -> Any:
        """Convert a live wire string to its YAML value, or ``None`` when unrecognised."""
        if key in BOOL_FIELDS:
            return wire == "1"
        if key == "vlan_hardware_filtering":
            for name, value in VLAN_FILTER_VALUES.items():
                if value == wire:
                    return name
            logger.warning("interfaces.settings: unknown disablevlanhwfilter %r; omitted", wire)
            return None
        if key == "dhcp6_duid":
            return wire
        try:
            return int(wire)
        except ValueError:
            logger.warning("interfaces.settings: non-integer %s %r; omitted", key, wire)
            return None
