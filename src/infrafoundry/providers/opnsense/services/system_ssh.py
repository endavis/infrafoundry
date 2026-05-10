"""System SSH service for OPNsense direct-API operations (#806).

Manages the OPNsense ``<system><ssh>`` block via the
``system/settings/*`` controller. Identity is the singleton ``settings``
— there is exactly one SSH daemon configuration per box.

Endpoint surface (XML-inferred per ``tmp/agents/claude/probe-806.md``;
operator should re-verify with a live probe after merge):

- ``GET system/settings/get`` — returns the full system-settings dict
  (subkey ``ssh`` is the SSH-relevant slice).
- ``POST system/settings/set`` — writes the full block; this service
  passes only the SSH subkey, OPNsense merges with the rest.

Field schema (XML-derived):

- ``enabled`` — string sentinel (``"enabled"`` / ``""``)
- ``group`` — admin group name (e.g., ``admins``)
- ``noauto`` — bool ("0"/"1") — disable auto-start
- ``interfaces`` — comma-joined interface list
- ``kex``, ``ciphers``, ``macs``, ``keys``, ``keysig``, ``rekeylimit``
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig

from ..api_client import OPNsenseClient, SystemClient
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService


class SystemSshService(BaseService):
    """Service for OPNsense system-SSH operations via direct-API.

    Args:
        client: Configured ``OPNsenseClient`` instance.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize the SSH service with a SystemClient wrapper."""
        super().__init__(client)
        self.system_client = SystemClient(client)

    def get_settings(self) -> dict[str, Any]:
        """Fetch current system settings (SSH subkey)."""
        return self.system_client.get_system_settings()

    def set_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Push SSH-block updates via system/settings/set.

        Args:
            payload: Settings payload (caller wraps in correct envelope).

        Returns:
            API response.
        """
        return self.system_client.set_system_settings(payload)

    def extract_ssh_fields(self, api_response: dict[str, Any]) -> dict[str, Any]:
        """Extract SSH-relevant fields from a system/settings/get response.

        Args:
            api_response: Raw response from :meth:`get_settings`.

        Returns:
            Flat ``{field: value}`` mapping for the ssh subkey.
        """
        body = _unwrap_ssh(api_response)
        interfaces_raw = body.get("interfaces", "")
        return {
            "enabled": _str(body.get("enabled")),
            "group": _str(body.get("group")),
            "noauto": _str(body.get("noauto")),
            "interfaces": _coerce_list(interfaces_raw),
            "kex": _str(body.get("kex")),
            "ciphers": _str(body.get("ciphers")),
            "macs": _str(body.get("macs")),
            "keys": _str(body.get("keys")),
            "keysig": _str(body.get("keysig")),
            "rekeylimit": _str(body.get("rekeylimit")),
        }

    def build_desired_ssh_fields(self, resource: ResourceConfig) -> dict[str, Any]:
        """Build the desired SSH field map from a YAML singleton.

        Args:
            resource: ``system.ssh`` ``ResourceConfig``.

        Returns:
            Flat ``{field: value}`` mapping mirroring
            :meth:`extract_ssh_fields`.
        """
        config = resource.config
        return {
            "enabled": _str(config.get("enabled")),
            "group": _str(config.get("group")),
            "noauto": _str(config.get("noauto")),
            "interfaces": _coerce_list(config.get("interfaces", [])),
            "kex": _str(config.get("kex")),
            "ciphers": _str(config.get("ciphers")),
            "macs": _str(config.get("macs")),
            "keys": _str(config.get("keys")),
            "keysig": _str(config.get("keysig")),
            "rekeylimit": _str(config.get("rekeylimit")),
        }

    def export_to_yaml(self) -> str:
        """Export current SSH settings as nested YAML for ``infra migrate``.

        Returns:
            YAML string under the ``opnsense.system.ssh`` namespace.
        """
        live = self.extract_ssh_fields(self.get_settings())
        clean: dict[str, Any] = {}
        for key, value in live.items():
            if (isinstance(value, list) and value) or (isinstance(value, str) and value):
                clean[key] = value
        return emit_nested_singleton_yaml("system.ssh", clean)


def _unwrap_ssh(api_response: dict[str, Any]) -> dict[str, Any]:
    """Return the inner ``ssh`` dict regardless of envelope.

    Tolerates ``{"ssh": {...}}`` (most common), ``{"system": {"ssh": {...}}}``,
    and a flat layout where ssh fields sit at the top level.
    """
    if isinstance(api_response.get("ssh"), dict):
        return api_response["ssh"]  # type: ignore[no-any-return]
    system = api_response.get("system")
    if isinstance(system, dict) and isinstance(system.get("ssh"), dict):
        return system["ssh"]  # type: ignore[no-any-return]
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
