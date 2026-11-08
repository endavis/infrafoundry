"""Host-discovery service for OPNsense direct-API operations (#792).

Manages the ``OPNsense\\Hostdiscovery`` model (the passive host-discovery
service) through ``GET hostdiscovery/settings/get``,
``POST hostdiscovery/settings/set`` and ``POST hostdiscovery/service/reconfigure``.
The YAML key is ``hostdiscovery`` (not the plugin's old name ``hostwatch``) so it
matches the wire API.

YAML keys (all optional; only declared keys are compared and written) and their
wire fields under ``hostdiscovery.general``:

- ``enabled``          -> ``enabled`` (bool)
- ``promisc``          -> ``promisc`` (bool)
- ``verbose``          -> ``verbose`` (bool)
- ``skip_nets``        -> ``skip_nets`` (list of CIDRs, comma-joined on the wire)
- ``interface``        -> ``interface`` (list of interface keys, comma-joined on the wire)
- ``expire4_interval`` -> ``expire4_interval`` (non-negative int)
- ``expire6_interval`` -> ``expire6_interval`` (non-negative int)

List fields compare as sets. Write envelope: both GET and SET use
``{"hostdiscovery": {"general": {...}}}``; the apply posts the whole flattened live
``general`` section with the declared fields overwritten, so undeclared settings
stay unchanged.

Unverified live: the ``set`` and ``reconfigure`` calls have not been run against a
box, and the wire field names above follow the YAML names by assumption.
"""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Iterable
from typing import Any

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService, raise_on_failed_write

logger = logging.getLogger(__name__)

#: YAML key -> wire key under ``hostdiscovery.general``. Single allowed-key source.
FIELD_MAP: dict[str, str] = {
    "enabled": "enabled",
    "promisc": "promisc",
    "verbose": "verbose",
    "skip_nets": "skip_nets",
    "interface": "interface",
    "expire4_interval": "expire4_interval",
    "expire6_interval": "expire6_interval",
}

#: YAML keys whose value is a boolean (wire ``"1"``/``"0"``).
BOOL_FIELDS: frozenset[str] = frozenset({"enabled", "promisc", "verbose"})

#: YAML keys whose value is a list (wire comma-joined string).
LIST_FIELDS: frozenset[str] = frozenset({"skip_nets", "interface"})

#: YAML keys whose value is a non-negative integer.
INT_FIELDS: frozenset[str] = frozenset({"expire4_interval", "expire6_interval"})


def _split_entries(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _selected_entries(value: Any) -> list[str]:
    """Return the non-empty selected entries of an option dict, option list or comma string."""
    if isinstance(value, list):
        return [
            str(index)
            for index, entry in enumerate(value)
            if isinstance(entry, dict) and entry.get("selected")
        ]
    if isinstance(value, dict):
        return [
            str(key)
            for key, meta in value.items()
            if str(key) and isinstance(meta, dict) and meta.get("selected")
        ]
    if isinstance(value, str):
        return _split_entries(value)
    return []


def _flatten(value: Any) -> str:
    """Flatten a live field into its wire string (selected keys comma-joined)."""
    if isinstance(value, list | dict):
        return ",".join(_selected_entries(value))
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


class HostDiscoveryService(BaseService):
    """Service for the OPNsense host-discovery singleton."""

    def get_settings(self) -> Any:
        """Fetch the host-discovery document."""
        return self.client.request(
            endpoints.HOSTDISCOVERY_SETTINGS_GET.method,
            endpoints.HOSTDISCOVERY_SETTINGS_GET.path(),
        )

    def set_settings(self, payload: dict[str, Any]) -> Any:
        """Write the host-discovery document.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        response = self.client.request(
            endpoints.HOSTDISCOVERY_SETTINGS_SET.method,
            endpoints.HOSTDISCOVERY_SETTINGS_SET.path(),
            data=payload,
        )
        return raise_on_failed_write(response, "set host discovery settings")

    def reconfigure(self) -> Any:
        """Apply the saved host-discovery settings.

        Called only by the provider's ``_reconfigure_hostdiscovery`` finalization
        hook; the manager must not call it directly.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}`` or
                ``{"status": "failed"}``.
        """
        response = self.client.request(
            endpoints.HOSTDISCOVERY_RECONFIGURE.method,
            endpoints.HOSTDISCOVERY_RECONFIGURE.path(),
        )
        raise_on_failed_write(response, "reconfigure host discovery")
        if isinstance(response, dict) and response.get("status") == "failed":
            raise APIError(
                "OPNsense rejected reconfigure host discovery: status failed",
                response=str(response),
                provider="opnsense",
            )
        return response

    def live_general(self, response: Any) -> dict[str, Any]:
        """Return ``response["hostdiscovery"]["general"]``.

        Raises:
            APIError: If the envelope is missing, so a write is never built from nothing.
        """
        root = response.get("hostdiscovery") if isinstance(response, dict) else None
        general = root.get("general") if isinstance(root, dict) else None
        if not isinstance(general, dict):
            raise APIError(
                "OPNsense hostdiscovery/settings/get returned no hostdiscovery.general object",
                response=str(response)[:200],
                provider="opnsense",
            )
        return general

    def build_desired(self, resource: ResourceConfig) -> dict[str, Any]:
        """Build the desired values for the declared keys only.

        Booleans and integers become wire strings; list fields stay lists of strings.

        Raises:
            InvalidConfigurationError: On unknown keys or wrongly typed values.
        """
        config = resource.config
        unknown = sorted(set(config) - set(FIELD_MAP))
        if unknown:
            raise InvalidConfigurationError(
                f"hostdiscovery has unknown key(s): {', '.join(unknown)}"
            )
        desired: dict[str, Any] = {}
        for key in FIELD_MAP:
            if key not in config:
                continue
            value = config[key]
            if key in BOOL_FIELDS:
                if not isinstance(value, bool):
                    raise InvalidConfigurationError(f"hostdiscovery {key} must be a boolean")
                desired[key] = "1" if value else "0"
            elif key in LIST_FIELDS:
                desired[key] = self._build_list(key, value)
            else:
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise InvalidConfigurationError(
                        f"hostdiscovery {key} must be a non-negative integer"
                    )
                desired[key] = str(value)
        return desired

    @staticmethod
    def _build_list(key: str, value: Any) -> list[str]:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise InvalidConfigurationError(f"hostdiscovery {key} must be a list of strings")
        entries = [item.strip() for item in value]
        for entry in entries:
            if not entry or "," in entry:
                raise InvalidConfigurationError(
                    f"hostdiscovery {key} entries must be non-empty and contain no comma"
                )
            if key == "skip_nets":
                try:
                    ipaddress.ip_network(entry, strict=False)
                except ValueError as exc:
                    raise InvalidConfigurationError(
                        f"hostdiscovery skip_nets entry {entry!r} is not a valid CIDR"
                    ) from exc
        return entries

    def extract_live(self, general: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
        """Extract the given YAML keys from the live section.

        Booleans and integers come back as wire strings, list fields as frozensets.

        Raises:
            APIError: If a requested field is absent from the live section.
        """
        live: dict[str, Any] = {}
        for key in keys:
            wire = FIELD_MAP[key]
            if wire not in general:
                raise APIError(
                    f"OPNsense hostdiscovery/settings/get returned no '{wire}' field",
                    response=str(sorted(general))[:200],
                    provider="opnsense",
                )
            if key in LIST_FIELDS:
                live[key] = frozenset(_selected_entries(general[wire]))
            else:
                live[key] = _flatten(general[wire])
        return live

    def drift(self, live: dict[str, Any], desired: dict[str, Any]) -> dict[str, Any] | None:
        """Compare declared keys (lists as sets); return ``desired`` on any difference."""
        for key, value in desired.items():
            if key in LIST_FIELDS:
                if frozenset(value) != live.get(key, frozenset()):
                    return desired
            elif live.get(key) != value:
                return desired
        return None

    def build_set_payload(self, general: dict[str, Any], desired: dict[str, Any]) -> dict[str, Any]:
        """Build the write body: the whole flattened live section with declared fields set."""
        flat = {key: _flatten(value) for key, value in general.items()}
        for key, value in desired.items():
            flat[FIELD_MAP[key]] = ",".join(value) if key in LIST_FIELDS else value
        return {"hostdiscovery": {"general": flat}}

    def export_to_yaml(self) -> str:
        """Export every live field present as nested YAML."""
        general = self.live_general(self.get_settings())
        present = [key for key, wire in FIELD_MAP.items() if wire in general]
        live = self.extract_live(general, present)
        clean: dict[str, Any] = {}
        for key in present:
            value = self._to_yaml_value(key, live[key])
            if value is not None:
                clean[key] = value
        return emit_nested_singleton_yaml("hostdiscovery", clean)

    @staticmethod
    def _to_yaml_value(key: str, live: Any) -> Any:
        """Convert a live value to its YAML value, or ``None`` when unrecognised."""
        if key in BOOL_FIELDS:
            return live == "1"
        if key in LIST_FIELDS:
            return sorted(live)
        try:
            return int(live)
        except ValueError:
            logger.warning("hostdiscovery: non-integer %s %r; omitted", key, live)
            return None
