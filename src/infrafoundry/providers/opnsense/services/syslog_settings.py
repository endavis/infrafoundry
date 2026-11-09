"""Syslog-settings service for OPNsense direct-API operations (#804).

Manages the ``general`` section of the ``OPNsense\\Syslog`` model (local logging
switch and log rotation) through ``GET syslog/settings/get``,
``POST syslog/settings/set`` and ``POST syslog/service/reconfigure``.

YAML keys (all optional; only declared keys are compared and written) and their
wire fields under ``syslog.general``:

- ``enabled``       -> ``enabled`` (bool)
- ``log_local``     -> ``loglocal`` (bool)
- ``max_preserve``  -> ``maxpreserve`` (non-negative int)
- ``max_file_size`` -> ``maxfilesize`` (non-negative int)

The ``destinations`` list under the same model is out of scope.

Write envelope: ``{"syslog": {"general": {...}}}``, the same shape the GET returns.
The apply posts the whole flattened live ``general`` object with the declared fields
overwritten, so undeclared settings stay unchanged.

Unverified live: the ``set`` and ``reconfigure`` calls have not been run against a
box. The GET shape was probed on 26.1.
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

#: YAML key -> wire key under ``syslog.general``.
FIELD_MAP: dict[str, str] = {
    "enabled": "enabled",
    "log_local": "loglocal",
    "max_preserve": "maxpreserve",
    "max_file_size": "maxfilesize",
}

#: YAML keys whose value is a boolean (wire ``"1"``/``"0"``).
BOOL_FIELDS: frozenset[str] = frozenset({"enabled", "log_local"})

#: YAML keys whose value is a non-negative integer.
INT_FIELDS: frozenset[str] = frozenset({"max_preserve", "max_file_size"})


def _flatten(value: Any) -> str:
    """Flatten a live field into its wire string.

    An option dict flattens to the comma-joined selected keys. ``None`` and ``[]``
    flatten to ``""``.
    """
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


class SyslogSettingsService(BaseService):
    """Service for the OPNsense syslog-settings singleton."""

    def get_settings(self) -> Any:
        """Fetch the syslog-settings document."""
        return self.client.request(
            endpoints.SYSLOG_SETTINGS_GET.method, endpoints.SYSLOG_SETTINGS_GET.path()
        )

    def set_settings(self, payload: dict[str, Any]) -> Any:
        """Write the syslog-settings document.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        response = self.client.request(
            endpoints.SYSLOG_SETTINGS_SET.method,
            endpoints.SYSLOG_SETTINGS_SET.path(),
            data=payload,
        )
        return raise_on_failed_write(response, "set syslog settings")

    def reconfigure(self) -> Any:
        """Apply the saved syslog settings.

        Called only by the provider's ``_reconfigure_syslog`` finalization hook; the
        manager must not call it directly.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        response = self.client.request(
            endpoints.SYSLOG_RECONFIGURE.method, endpoints.SYSLOG_RECONFIGURE.path()
        )
        return raise_on_failed_write(response, "reconfigure syslog")

    def live_general(self, response: Any) -> dict[str, Any]:
        """Return ``response["syslog"]["general"]``.

        Raises:
            APIError: If the envelope is missing, so a write is never built from nothing.
        """
        syslog = response.get("syslog") if isinstance(response, dict) else None
        general = syslog.get("general") if isinstance(syslog, dict) else None
        if not isinstance(general, dict):
            raise APIError(
                "OPNsense syslog/settings/get returned no syslog.general object",
                response=str(response)[:200],
                provider="opnsense",
            )
        return general

    def build_desired(self, resource: ResourceConfig) -> dict[str, str]:
        """Build the desired wire strings for the declared keys only.

        Raises:
            InvalidConfigurationError: On unknown keys or wrongly typed values.
        """
        config = resource.config
        unknown = sorted(set(config) - set(FIELD_MAP))
        if unknown:
            raise InvalidConfigurationError(
                f"syslog.settings has unknown key(s): {', '.join(unknown)}"
            )
        desired: dict[str, str] = {}
        for key in FIELD_MAP:
            if key not in config:
                continue
            value = config[key]
            if key in BOOL_FIELDS:
                if not isinstance(value, bool):
                    raise InvalidConfigurationError(f"syslog.settings {key} must be a boolean")
                desired[key] = "1" if value else "0"
            else:
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise InvalidConfigurationError(
                        f"syslog.settings {key} must be a non-negative integer"
                    )
                desired[key] = str(value)
        return desired

    def extract_live(self, general: dict[str, Any], keys: Iterable[str]) -> dict[str, str]:
        """Extract the given YAML keys from the live object, as wire strings.

        Raises:
            APIError: If a requested field is absent from the live object.
        """
        live: dict[str, str] = {}
        for key in keys:
            wire = FIELD_MAP[key]
            if wire not in general:
                raise APIError(
                    f"OPNsense syslog/settings/get returned no '{wire}' field",
                    response=str(sorted(general))[:200],
                    provider="opnsense",
                )
            live[key] = _flatten(general[wire])
        return live

    def drift(self, live: dict[str, str], desired: dict[str, str]) -> dict[str, str] | None:
        """Compare declared keys; return ``desired`` on any difference."""
        for key, value in desired.items():
            if live.get(key) != value:
                return desired
        return None

    def build_set_payload(self, general: dict[str, Any], desired: dict[str, str]) -> dict[str, Any]:
        """Build the write body: the whole flattened live ``general`` with declared fields set.

        ``destinations`` is never sent.
        """
        flat = {key: _flatten(value) for key, value in general.items() if key != "destinations"}
        for key, value in desired.items():
            flat[FIELD_MAP[key]] = value
        return {"syslog": {"general": flat}}

    def export_to_yaml(self) -> str:
        """Export every ``general`` field present on the box as nested YAML.

        A live integer that is not a non-negative digit string is logged and omitted.
        """
        general = self.live_general(self.get_settings())
        present = [key for key, wire in FIELD_MAP.items() if wire in general]
        live = self.extract_live(general, present)
        clean: dict[str, Any] = {}
        for key in present:
            text = live[key]
            if key in BOOL_FIELDS:
                clean[key] = text == "1"
            elif text.isascii() and text.isdigit():
                clean[key] = int(text)
            else:
                logger.warning("syslog.settings: non-integer %s %r; omitted", key, text)
        return emit_nested_singleton_yaml("syslog.settings", clean)
