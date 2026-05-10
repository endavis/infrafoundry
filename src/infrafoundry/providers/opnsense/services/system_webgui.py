"""System WebGUI service for OPNsense direct-API operations (#806).

Manages the OPNsense ``<system><webgui>`` block via the
``system/settings/*`` controller. Identity is the singleton ``settings``
— there is exactly one webgui configuration per box.

Endpoint surface (XML-inferred; operator should re-verify with a live
probe after merge):

- ``GET system/settings/get`` — full system-settings dict (subkey
  ``webgui`` is the WebGUI-relevant slice).
- ``POST system/settings/set`` — writes the full block.

Field schema (XML-derived):

- ``protocol`` — ``"http"`` / ``"https"``
- ``port`` — int (empty defaults to 443)
- ``ssl_certref`` — cert UUID (matches XML's ``ssl-certref``; YAML uses
  underscore for consistency with rest of project conventions)
- ``ssl_ciphers`` — string
- ``interfaces`` — comma-joined interface list (empty = all)
- ``compression`` — string (httpd Gzip on/off)
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig

from ..api_client import OPNsenseClient, SystemClient
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService


class SystemWebguiService(BaseService):
    """Service for OPNsense system-WebGUI operations via direct-API.

    Args:
        client: Configured ``OPNsenseClient`` instance.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize the WebGUI service with a SystemClient wrapper."""
        super().__init__(client)
        self.system_client = SystemClient(client)

    def get_settings(self) -> dict[str, Any]:
        """Fetch current system settings (WebGUI subkey)."""
        return self.system_client.get_system_settings()

    def set_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Push WebGUI-block updates via system/settings/set.

        Args:
            payload: Settings payload (caller wraps in correct envelope).

        Returns:
            API response.
        """
        return self.system_client.set_system_settings(payload)

    def extract_webgui_fields(self, api_response: dict[str, Any]) -> dict[str, Any]:
        """Extract WebGUI-relevant fields from a system/settings/get response.

        Args:
            api_response: Raw response from :meth:`get_settings`.

        Returns:
            Flat ``{field: value}`` mapping for the webgui subkey.
        """
        body = _unwrap_webgui(api_response)
        return {
            "protocol": _str(body.get("protocol")),
            "port": _str(body.get("port")),
            "ssl_certref": _str(body.get("ssl-certref") or body.get("ssl_certref")),
            "ssl_ciphers": _str(body.get("ssl-ciphers") or body.get("ssl_ciphers")),
            "interfaces": _coerce_list(body.get("interfaces", "")),
            "compression": _str(body.get("compression")),
        }

    def build_desired_webgui_fields(self, resource: ResourceConfig) -> dict[str, Any]:
        """Build the desired WebGUI field map from a YAML singleton.

        Args:
            resource: ``system.webgui`` ``ResourceConfig``.

        Returns:
            Flat ``{field: value}`` mapping mirroring
            :meth:`extract_webgui_fields`.
        """
        config = resource.config
        return {
            "protocol": _str(config.get("protocol")),
            "port": _str(config.get("port")),
            "ssl_certref": _str(config.get("ssl_certref")),
            "ssl_ciphers": _str(config.get("ssl_ciphers")),
            "interfaces": _coerce_list(config.get("interfaces", [])),
            "compression": _str(config.get("compression")),
        }

    def export_to_yaml(self) -> str:
        """Export current WebGUI settings as nested YAML for ``infra migrate``.

        Returns:
            YAML string under the ``opnsense.system.webgui`` namespace.
        """
        live = self.extract_webgui_fields(self.get_settings())
        clean: dict[str, Any] = {}
        for key, value in live.items():
            if (isinstance(value, list) and value) or (isinstance(value, str) and value):
                clean[key] = value
        return emit_nested_singleton_yaml("system.webgui", clean)


def _unwrap_webgui(api_response: dict[str, Any]) -> dict[str, Any]:
    """Return the inner ``webgui`` dict regardless of envelope."""
    if isinstance(api_response.get("webgui"), dict):
        return api_response["webgui"]  # type: ignore[no-any-return]
    system = api_response.get("system")
    if isinstance(system, dict) and isinstance(system.get("webgui"), dict):
        return system["webgui"]  # type: ignore[no-any-return]
    return api_response


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
