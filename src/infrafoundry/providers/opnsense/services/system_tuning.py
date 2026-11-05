"""System tuning (sysctl) service for OPNsense direct-API operations (#806, #1149).

Manages OPNsense system tunables through the 26.1 ``core/tunables/*``
controller. Tunables are matched by tunable name; only tunables named in
YAML are ever added or updated, and tunables present only on the box (the
defaults) are never touched.

Endpoint surface:

- ``GET core/tunables/get`` — ``{"sysctl": {"item": {<uuid>: {tunable,
  value, descr, default_value, ...}}}}``. Verified live on 26.1.6_2.
- ``POST core/tunables/addItem`` / ``setItem/<uuid>`` / ``delItem/<uuid>``
  and ``POST core/tunables/reconfigure`` — verified live on 26.1.6_2
  (``delItem`` by hand). ``delItem`` is never called by apply.

Wire payload for a write: ``{"sysctl": {"tunable", "value", "descr"}}``.
"""

from __future__ import annotations

import logging
from typing import Any

from infrafoundry.core.provider import ResourceConfig

from ..api_client import OPNsenseClient, SystemClient
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService, raise_on_failed_write

logger = logging.getLogger(__name__)


class SystemTuningService(BaseService):
    """Service for OPNsense system-tuning (sysctl) operations via direct-API.

    Args:
        client: Configured ``OPNsenseClient`` instance.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize the tuning service with a SystemClient wrapper."""
        super().__init__(client)
        self.system_client = SystemClient(client)

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

    def get_tunables(self) -> dict[str, Any]:
        """Fetch all tunables (raw ``core/tunables/get`` response)."""
        return self.system_client.get_tunables()

    def add_tunable(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Add a tunable.

        Args:
            entry: ``{tunable, value, descr}``.

        Returns:
            API response.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        response = self.system_client.add_tunable({"sysctl": _wire(entry)})
        raise_on_failed_write(response, f"add tunable {entry.get('tunable')}")
        return response

    def set_tunable(self, uuid: str, entry: dict[str, Any]) -> dict[str, Any]:
        """Update a tunable by uuid.

        Args:
            uuid: Tunable uuid.
            entry: ``{tunable, value, descr}``.

        Returns:
            API response.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        response = self.system_client.set_tunable(uuid, {"sysctl": _wire(entry)})
        raise_on_failed_write(response, f"update tunable {entry.get('tunable')}")
        return response

    def reconfigure(self) -> dict[str, Any]:
        """Apply pending tunable changes.

        Called only by the provider's ``_reconfigure_tunables`` finalization
        hook; the manager must not call it directly.

        Returns:
            API response.
        """
        response = self.system_client.reconfigure_tunables()
        raise_on_failed_write(response, "reconfigure tunables")
        return response

    # ------------------------------------------------------------------
    # Extract / build / diff
    # ------------------------------------------------------------------

    def extract_live_tunables(self, api_response: dict[str, Any]) -> dict[str, dict[str, str]]:
        """Index live tunables by tunable name.

        Args:
            api_response: Raw response from :meth:`get_tunables`.

        Returns:
            ``{name: {uuid, value, descr, default_value}}``; ``{}`` on an
            unexpected shape. A duplicate live name keeps the first row and
            logs a warning.
        """
        sysctl = api_response.get("sysctl")
        if not isinstance(sysctl, dict):
            return {}
        items = sysctl.get("item")
        if not isinstance(items, dict):
            return {}
        live: dict[str, dict[str, str]] = {}
        for uuid, row in items.items():
            if not isinstance(row, dict):
                continue
            name = _str(row.get("tunable"))
            if not name:
                continue
            if name in live:
                logger.warning("system.tuning: duplicate live tunable %r; keeping the first", name)
                continue
            live[name] = {
                "uuid": str(uuid),
                "value": _str(row.get("value")),
                "descr": _str(row.get("descr")),
                "default_value": _str(row.get("default_value")),
            }
        return live

    def build_desired_tunables(self, resource: ResourceConfig) -> list[dict[str, Any]]:
        """Build desired entries ``{tunable, value, descr}`` from YAML.

        Args:
            resource: ``system.tuning`` ``ResourceConfig``.

        Returns:
            One entry per YAML item; ``descr`` is ``None`` when omitted.
        """
        raw = resource.config.get("items", [])
        if not isinstance(raw, list):
            return []
        desired: list[dict[str, Any]] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            descr = entry.get("descr")
            desired.append(
                {
                    "tunable": _str(entry.get("tunable")),
                    "value": _scalar(entry.get("value")),
                    "descr": None if descr is None else _str(descr),
                }
            )
        return desired

    def compute_changes(
        self,
        desired: list[dict[str, Any]],
        live: dict[str, dict[str, str]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Compute ``(adds, updates)``; live-only tunables never appear.

        Args:
            desired: Output of :meth:`build_desired_tunables`.
            live: Output of :meth:`extract_live_tunables`.

        Returns:
            Add entries ``{tunable, value, descr}`` and update entries that
            also carry the live ``uuid``. An update keeps the live ``descr``
            when YAML omits it.
        """
        adds: list[dict[str, Any]] = []
        updates: list[dict[str, Any]] = []
        for entry in desired:
            name = entry["tunable"]
            current = live.get(name)
            if current is None:
                adds.append({**entry, "descr": entry["descr"] or ""})
                continue
            yaml_descr = entry["descr"]
            value_differs = entry["value"] != current["value"]
            descr_differs = bool(yaml_descr) and yaml_descr != current["descr"]
            if not (value_differs or descr_differs):
                continue
            updates.append(
                {
                    "uuid": current["uuid"],
                    "tunable": name,
                    "value": entry["value"],
                    "descr": yaml_descr if yaml_descr else current["descr"],
                }
            )
        return adds, updates

    def export_to_yaml(self) -> str:
        """Export tunables whose value differs from the default as YAML.

        Returns:
            YAML string under the ``opnsense.system.tuning`` namespace.
        """
        live = self.extract_live_tunables(self.get_tunables())
        items: list[dict[str, str]] = []
        for name in sorted(live):
            row = live[name]
            if row["value"] == row["default_value"]:
                continue
            item = {"tunable": name, "value": row["value"]}
            if row["descr"]:
                item["descr"] = row["descr"]
            items.append(item)
        clean: dict[str, Any] = {}
        if items:
            clean["items"] = items
        return emit_nested_singleton_yaml("system.tuning", clean)


def _wire(entry: dict[str, Any]) -> dict[str, str]:
    """Return the ``{tunable, value, descr}`` wire body for an entry."""
    return {
        "tunable": str(entry["tunable"]),
        "value": str(entry["value"]),
        "descr": str(entry.get("descr") or ""),
    }


def _scalar(value: Any) -> str:
    """Stringify a YAML scalar; booleans become ``"1"``/``"0"``."""
    if isinstance(value, bool):
        return "1" if value else "0"
    return _str(value)


def _str(value: Any) -> str:
    """Return a stripped string for any scalar."""
    if value is None:
        return ""
    return str(value).strip()
