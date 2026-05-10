"""System hostname service for OPNsense direct-API operations (#806).

Manages the OPNsense ``<system>`` block hostname/domain/timezone/language
fields via the ``system/general/*`` controller. Identity is the singleton
``settings`` — there is exactly one hostname configuration per box.

Endpoint surface (XML-inferred per ``tmp/agents/claude/probe-806.md``;
operator should re-verify with a live probe after merge):

- ``GET system/general/get`` — returns the current general settings.
- ``POST system/general/set`` — writes the general settings.

Field schema (XML-derived):

- ``hostname`` — string (e.g., ``opnsense-a``)
- ``domain`` — string (e.g., ``endavis.net``)
- ``timezone`` — string (e.g., ``Etc/UTC``)
- ``language`` — string (e.g., ``en_US``)

The DNS sub-fields (``dnsserver``, ``dnsallowoverride``, ``dnsXgw``) live
in the same XML block but are owned by :mod:`system_dns` so the operator
can manage hostname and DNS independently.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig

from ..api_client import OPNsenseClient, SystemClient
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService


class SystemHostnameService(BaseService):
    """Service for OPNsense system-hostname operations via direct-API.

    Args:
        client: Configured ``OPNsenseClient`` instance.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize the hostname service with a SystemClient wrapper."""
        super().__init__(client)
        self.system_client = SystemClient(client)

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

    def get_settings(self) -> dict[str, Any]:
        """Fetch current general settings (hostname/domain/timezone/language).

        Returns:
            Raw API response (envelope unwrapped at field-extract time).
        """
        return self.system_client.get_general_settings()

    def set_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Push general settings updates to OPNsense.

        Args:
            payload: Settings payload (caller wraps in correct envelope).

        Returns:
            API response.
        """
        return self.system_client.set_general_settings(payload)

    # ------------------------------------------------------------------
    # Field extract / build
    # ------------------------------------------------------------------

    def extract_hostname_fields(self, api_response: dict[str, Any]) -> dict[str, Any]:
        """Extract hostname-relevant fields from a general/get API response.

        The API may wrap the general settings under ``general`` or at the
        top level; this helper accepts either shape so the change-detection
        comparison in the manager doesn't depend on a specific OPNsense
        version's envelope.

        Args:
            api_response: Raw response from :meth:`get_settings`.

        Returns:
            Flat ``{field: value}`` mapping for the four hostname fields.
        """
        body = _unwrap_general(api_response)
        return {
            "hostname": _str(body.get("hostname")),
            "domain": _str(body.get("domain")),
            "timezone": _str(body.get("timezone")),
            "language": _str(body.get("language")),
        }

    def build_desired_hostname_fields(self, resource: ResourceConfig) -> dict[str, Any]:
        """Build the desired hostname field map from a YAML singleton.

        Args:
            resource: ``system.hostname`` ``ResourceConfig`` with
                ``name="settings"`` and the operator's YAML mapping in
                ``config``.

        Returns:
            Flat ``{field: value}`` mapping mirroring
            :meth:`extract_hostname_fields`.
        """
        config = resource.config
        return {
            "hostname": _str(config.get("hostname")),
            "domain": _str(config.get("domain")),
            "timezone": _str(config.get("timezone")),
            "language": _str(config.get("language")),
        }

    # ------------------------------------------------------------------
    # migrate()
    # ------------------------------------------------------------------

    def export_to_yaml(self) -> str:
        """Export current hostname settings as nested YAML for ``infra migrate``.

        Returns:
            YAML string under the ``opnsense.system.hostname`` namespace.
        """
        live = self.extract_hostname_fields(self.get_settings())
        # Emit only non-empty fields so an operator who hasn't customised
        # the language / timezone gets a minimal YAML to start with.
        clean = {k: v for k, v in live.items() if v}
        return emit_nested_singleton_yaml("system.hostname", clean)


def _unwrap_general(api_response: dict[str, Any]) -> dict[str, Any]:
    """Return the inner ``general`` dict regardless of envelope.

    Tolerates three shapes:
    - ``{"general": {...}}`` (most common; modern MVC)
    - ``{"system": {"general": {...}}}``
    - flat fields directly at the top level (very old OPNsense)
    """
    if isinstance(api_response.get("general"), dict):
        return api_response["general"]  # type: ignore[no-any-return]
    system = api_response.get("system")
    if isinstance(system, dict) and isinstance(system.get("general"), dict):
        return system["general"]  # type: ignore[no-any-return]
    return api_response


def _str(value: Any) -> str:
    """Return a stripped string for any scalar (bytes/None/int/str)."""
    if value is None:
        return ""
    return str(value).strip()
