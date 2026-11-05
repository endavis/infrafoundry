"""Unbound advanced-settings service for OPNsense direct-API operations (#1254).

Manages the ``advanced`` section of the Unbound settings document, which holds
the private-domain, insecure-domain and private-address lists, through
``GET unbound/settings/get`` and ``POST unbound/settings/set``.

Wire fields (comma-separated lists under ``unbound.advanced``):

- ``private_domains``   -> ``privatedomain``
- ``insecure_domains``  -> ``insecuredomain``
- ``private_addresses`` -> ``privateaddress``

The GET response renders these as option dicts (``{"a.example": {"selected": 1}}``),
with ``{"": {"selected": 1}}`` meaning "no selection"; the normaliser also accepts a
plain comma string.

Write envelope (decision, unverified live): the apply posts
``{"unbound": {"advanced": <whole live advanced section, flattened, declared fields
overwritten>}}``. The key ``unbound`` is the GET envelope key. The bundled
``opnsense-openapi`` spec instead names the request body key ``settings`` for
``unbound/settings/set``; that looks like a generator default (it says the same for
``radvd/settings/set``), so it is not treated as evidence. In-tree precedent
(``set_firmware_settings``, ``set_dhcp4_general``) writes with the GET envelope key.
Nothing outside ``advanced`` is sent. Sending the whole section keeps undeclared
advanced settings unchanged whether ``set`` treats the section as partial or whole.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from .base import BaseService, raise_on_failed_write

#: YAML key -> wire key under ``unbound.advanced``.
FIELD_MAP: dict[str, str] = {
    "private_domains": "privatedomain",
    "insecure_domains": "insecuredomain",
    "private_addresses": "privateaddress",
}


def _split_entries(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _selected_entries(value: Any) -> list[str]:
    """Return the non-empty selected entries of an option dict or comma string."""
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
    """Flatten a live field into its wire string."""
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


class UnboundAdvancedService(BaseService):
    """Service for the Unbound ``advanced`` settings section."""

    def get_settings(self) -> Any:
        """Fetch the Unbound settings document."""
        return self.client.request(
            endpoints.UNBOUND_SETTINGS_GET.method, endpoints.UNBOUND_SETTINGS_GET.path()
        )

    def set_settings(self, payload: dict[str, Any]) -> Any:
        """Write the settings document.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        response = self.client.request(
            endpoints.UNBOUND_SETTINGS_SET.method,
            endpoints.UNBOUND_SETTINGS_SET.path(),
            data=payload,
        )
        return raise_on_failed_write(response, "set unbound advanced settings")

    def live_advanced(self, response: Any) -> dict[str, Any]:
        """Return ``response["unbound"]["advanced"]``.

        Raises:
            APIError: If the section is missing, so a write is never built from nothing.
        """
        unbound = response.get("unbound") if isinstance(response, dict) else None
        advanced = unbound.get("advanced") if isinstance(unbound, dict) else None
        if not isinstance(advanced, dict):
            raise APIError(
                "OPNsense unbound/settings/get returned no unbound.advanced section",
                response=str(response)[:200],
                provider="opnsense",
            )
        return advanced

    def build_desired(self, resource: ResourceConfig) -> dict[str, list[str]]:
        """Build the desired lists for the declared keys only.

        Raises:
            InvalidConfigurationError: On unknown keys or non-list-of-string values.
        """
        config = resource.config
        unknown = sorted(set(config) - set(FIELD_MAP))
        if unknown:
            raise InvalidConfigurationError(
                f"unbound.advanced has unknown key(s): {', '.join(unknown)}"
            )
        desired: dict[str, list[str]] = {}
        for key in FIELD_MAP:
            if key not in config:
                continue
            value = config[key]
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise InvalidConfigurationError(f"unbound.advanced {key} must be a list of strings")
            entries: list[str] = []
            for item in value:
                stripped = item.strip()
                if stripped and stripped not in entries:
                    entries.append(stripped)
            desired[key] = entries
        return desired

    def extract_live(self, advanced: dict[str, Any]) -> dict[str, frozenset[str]]:
        """Extract the three managed fields from the live section, as sets."""
        return {
            key: frozenset(_selected_entries(advanced.get(wire))) for key, wire in FIELD_MAP.items()
        }

    def drift(
        self, live: dict[str, frozenset[str]], desired: dict[str, list[str]]
    ) -> dict[str, list[str]] | None:
        """Compare declared keys as sets; return ``desired`` on any difference."""
        for key, values in desired.items():
            if frozenset(values) != live.get(key, frozenset()):
                return desired
        return None

    def build_set_payload(
        self, advanced: dict[str, Any], desired: dict[str, list[str]]
    ) -> dict[str, Any]:
        """Build the write body: the whole flattened live section with declared fields set."""
        flat = {key: _flatten(value) for key, value in advanced.items()}
        for key, values in desired.items():
            flat[FIELD_MAP[key]] = ",".join(values)
        return {"unbound": {"advanced": flat}}
