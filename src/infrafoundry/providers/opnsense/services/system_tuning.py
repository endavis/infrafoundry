"""System tuning (sysctl) service for OPNsense direct-API operations (#806).

Manages OPNsense system tunables (sysctl items) via the
``diagnostics/system/sysctl/*`` controller. Identity is the singleton
``settings`` — tunables are global to the box.

Endpoint surface (XML-inferred per ``tmp/agents/claude/probe-806.md``;
operator should re-verify with a live probe after merge — this is the
"optional 7th" surface from #806):

- ``GET diagnostics/system/sysctl/get`` — returns the configured items.
- ``POST diagnostics/system/sysctl/set`` — write the items collection.

Field schema (XML-derived):

- ``items`` — list of ``{tunable, value, descr}`` dicts. Empty on both
  source and target boxes today; included for forward compatibility.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig

from ..api_client import OPNsenseClient, SystemClient
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService


class SystemTuningService(BaseService):
    """Service for OPNsense system-tuning (sysctl) operations via direct-API.

    Args:
        client: Configured ``OPNsenseClient`` instance.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize the tuning service with a SystemClient wrapper."""
        super().__init__(client)
        self.system_client = SystemClient(client)

    def get_settings(self) -> dict[str, Any]:
        """Fetch current sysctl-tuning settings."""
        return self.system_client.get_tuning_settings()

    def set_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Push sysctl-tuning updates to OPNsense.

        Args:
            payload: Settings payload (caller wraps in correct envelope).

        Returns:
            API response.
        """
        return self.system_client.set_tuning_settings(payload)

    def extract_tuning_fields(self, api_response: dict[str, Any]) -> dict[str, Any]:
        """Extract tuning-relevant fields from a sysctl/get response.

        Args:
            api_response: Raw response from :meth:`get_settings`.

        Returns:
            Flat ``{field: value}`` mapping. The ``items`` key holds a
            sorted list of tunable dicts so equality is order-independent.
        """
        body = _unwrap_sysctl(api_response)
        items_raw = body.get("item") or body.get("items") or []
        items = _coerce_items(items_raw)
        return {"items": items}

    def build_desired_tuning_fields(self, resource: ResourceConfig) -> dict[str, Any]:
        """Build the desired tuning field map from a YAML singleton.

        Args:
            resource: ``system.tuning`` ``ResourceConfig``.

        Returns:
            Flat ``{field: value}`` mapping mirroring
            :meth:`extract_tuning_fields`.
        """
        config = resource.config
        items = _coerce_items(config.get("items", []))
        return {"items": items}

    def export_to_yaml(self) -> str:
        """Export current sysctl-tuning settings as nested YAML.

        Returns:
            YAML string under the ``opnsense.system.tuning`` namespace.
        """
        live = self.extract_tuning_fields(self.get_settings())
        clean: dict[str, Any] = {}
        items = live.get("items", [])
        if items:
            clean["items"] = items
        return emit_nested_singleton_yaml("system.tuning", clean)


def _unwrap_sysctl(api_response: dict[str, Any]) -> dict[str, Any]:
    """Return the inner sysctl dict regardless of envelope."""
    if isinstance(api_response.get("sysctl"), dict):
        return api_response["sysctl"]  # type: ignore[no-any-return]
    return api_response


def _coerce_items(raw: Any) -> list[dict[str, str]]:
    """Coerce a sysctl-items collection (list or dict-of-dicts) to a sorted list.

    OPNsense's MVC controllers return the items either as a list of dicts
    or as a dict keyed by UUID; both shapes normalize to a sorted list of
    ``{tunable, value, descr}`` dicts so equality is stable across calls.
    """
    if isinstance(raw, dict):
        items = list(raw.values())
    elif isinstance(raw, list):
        items = list(raw)
    else:
        return []
    out: list[dict[str, str]] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        out.append(
            {
                "tunable": _str(entry.get("tunable")),
                "value": _str(entry.get("value")),
                "descr": _str(entry.get("descr")),
            }
        )
    out.sort(key=lambda e: (e["tunable"], e["value"]))
    return out


def _str(value: Any) -> str:
    """Return a stripped string for any scalar."""
    if value is None:
        return ""
    return str(value).strip()
