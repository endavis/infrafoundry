"""System DNS service for OPNsense direct-API operations (#806).

Manages the OPNsense ``<system>`` block DNS resolver fields via the same
``system/general/*`` controller used by :mod:`system_hostname`. Identity
is the singleton ``settings`` — there is exactly one DNS configuration
per box.

Endpoint surface (XML-inferred per ``tmp/agents/claude/probe-806.md``;
operator should re-verify with a live probe after merge):

- ``GET system/general/get`` — shares the response with hostname.
- ``POST system/general/set`` — shares the write path with hostname.

Field schema (XML-derived):

- ``dns_servers`` — list of resolver IPs (XML repeats ``<dnsserver>``;
  the wire form is typically a comma-joined string ``"9.9.9.9,1.1.1.1"``).
- ``dns_allow_override`` — bool ("0"/"1") — accept DNS from DHCP.
- ``dns_allow_override_exclude`` — list of interface names that ignore
  override.
- ``dns_gateways`` — mapping ``{1: "WAN_GW", 2: "WAN_GW", ...}`` for
  the eight per-resolver gateway selectors (XML ``<dns1gw>``…``<dns8gw>``).

The hostname/domain/timezone/language sub-fields live in the same XML
block but are owned by :mod:`system_hostname`.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig

from ..api_client import OPNsenseClient, SystemClient
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService

# OPNsense exposes 8 per-resolver gateway selectors in the XML
# (``dns1gw``…``dns8gw``). Pulled out as a constant so ``extract`` and
# ``build_desired`` agree on the index range.
_DNS_GATEWAY_INDICES: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8)


class SystemDnsService(BaseService):
    """Service for OPNsense system-DNS operations via direct-API.

    Args:
        client: Configured ``OPNsenseClient`` instance.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize the DNS service with a SystemClient wrapper."""
        super().__init__(client)
        self.system_client = SystemClient(client)

    def get_settings(self) -> dict[str, Any]:
        """Fetch current general settings (DNS resolver block).

        Returns:
            Raw API response (envelope unwrapped at field-extract time).
        """
        return self.system_client.get_general_settings()

    def set_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Push DNS-block updates to OPNsense via the general/set endpoint.

        Args:
            payload: Settings payload (caller wraps in correct envelope).

        Returns:
            API response.
        """
        return self.system_client.set_general_settings(payload)

    def extract_dns_fields(self, api_response: dict[str, Any]) -> dict[str, Any]:
        """Extract DNS-relevant fields from a general/get API response.

        Args:
            api_response: Raw response from :meth:`get_settings`.

        Returns:
            Flat ``{field: value}`` mapping for DNS resolver/gateway fields.
        """
        body = _unwrap_general(api_response)
        servers_raw = body.get("dnsserver", "")
        servers = _coerce_list(servers_raw)
        excludes_raw = body.get("dnsallowoverride_exclude", "")
        excludes = _coerce_list(excludes_raw)
        return {
            "dns_servers": servers,
            "dns_allow_override": _str(body.get("dnsallowoverride")),
            "dns_allow_override_exclude": excludes,
            "dns_gateways": _extract_dns_gateways(body),
        }

    def build_desired_dns_fields(self, resource: ResourceConfig) -> dict[str, Any]:
        """Build the desired DNS field map from a YAML singleton.

        Args:
            resource: ``system.dns`` ``ResourceConfig``.

        Returns:
            Flat ``{field: value}`` mapping mirroring
            :meth:`extract_dns_fields`.
        """
        config = resource.config
        return {
            "dns_servers": _coerce_list(config.get("dns_servers", [])),
            "dns_allow_override": _str(config.get("dns_allow_override")),
            "dns_allow_override_exclude": _coerce_list(
                config.get("dns_allow_override_exclude", [])
            ),
            "dns_gateways": _coerce_gateway_map(config.get("dns_gateways", {})),
        }

    def export_to_yaml(self) -> str:
        """Export current DNS settings as nested YAML for ``infra migrate``.

        Returns:
            YAML string under the ``opnsense.system.dns`` namespace.
        """
        live = self.extract_dns_fields(self.get_settings())
        clean: dict[str, Any] = {}
        for key, value in live.items():
            # Drop empty containers and empty strings; keep non-empty
            # lists/dicts/strings so the migrated YAML is minimal.
            if isinstance(value, list | dict | str) and value:
                clean[key] = value
        return emit_nested_singleton_yaml("system.dns", clean)


def _unwrap_general(api_response: dict[str, Any]) -> dict[str, Any]:
    """Return the inner ``general`` dict regardless of envelope (see hostname)."""
    if isinstance(api_response.get("general"), dict):
        return api_response["general"]  # type: ignore[no-any-return]
    system = api_response.get("system")
    if isinstance(system, dict) and isinstance(system.get("general"), dict):
        return system["general"]  # type: ignore[no-any-return]
    return api_response


def _extract_dns_gateways(body: dict[str, Any]) -> dict[str, str]:
    """Return ``{<index>: <gateway_name>}`` for the 8 resolver gateway slots.

    Empty / ``"none"`` slots are dropped so the diff doesn't fire on
    every plan.
    """
    result: dict[str, str] = {}
    for idx in _DNS_GATEWAY_INDICES:
        raw = body.get(f"dns{idx}gw")
        text = _str(raw)
        if text and text != "none":
            result[str(idx)] = text
    return result


def _coerce_gateway_map(raw: Any) -> dict[str, str]:
    """Coerce a YAML gateway-map (dict or list) to ``{<index>: <gw>}``."""
    if isinstance(raw, dict):
        return {str(k): _str(v) for k, v in raw.items() if _str(v) and _str(v) != "none"}
    if isinstance(raw, list):
        return {str(i + 1): _str(v) for i, v in enumerate(raw) if _str(v) and _str(v) != "none"}
    return {}


def _coerce_list(raw: Any) -> list[str]:
    """Coerce a comma-joined string OR list-shape value to a normalized list."""
    if isinstance(raw, list):
        return [_str(v) for v in raw if _str(v)]
    if isinstance(raw, str):
        return [s.strip() for s in raw.split(",") if s.strip()]
    return []


def _str(value: Any) -> str:
    """Return a stripped string for any scalar."""
    if value is None:
        return ""
    return str(value).strip()
