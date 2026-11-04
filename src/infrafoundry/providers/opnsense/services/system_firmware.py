"""System firmware service for OPNsense direct-API operations (#806).

Manages the OPNsense ``<system><firmware>`` block via the
``firmware/info`` (read) + ``firmware/install/<name>`` (write) endpoints.
This is the **keystone** surface for #806 — without ``firmware.plugins``
automating the install of contrib plugins, the modern controllers for
follow-up issues (#790 AcmeClient, #808 OpenVPN-legacy) don't exist on
the cutover target and ``infra apply`` for those issues silently
no-ops with 404s.

Identity is the singleton ``settings`` — there is exactly one firmware
configuration per box.

**Apply semantics (per #806 user decision, 2026-05-10):**

- ``apply`` is **install-missing only**: any plugin in YAML but not on
  the box is installed; any plugin on the box but not in YAML is
  **logged at warning level only — never auto-removed**.
- ``destroy`` is a no-op (don't auto-uninstall).

This intentionally violates the usual "live state == YAML state" symmetry
for safety: an operator who forgot to declare ``os-tailscale`` in YAML
should not lose Tailscale on the next apply.

Endpoint surface (26.1; #1149):

- ``GET core/firmware/info`` — plugin/package list (verified live, 26.1.6_2).
- ``GET core/firmware/get`` — settings under ``{"firmware": {...}}``
  (verified live, 26.1.6_2).
- ``POST core/firmware/set`` — settings write; UNVERIFIED (MVC convention).
- ``POST core/firmware/install/<plugin_name>`` — install one plugin;
  UNVERIFIED. Asynchronous on OPNsense: returns a job acknowledgement.
- ``POST core/firmware/remove|lock/<plugin_name>`` — UNVERIFIED; the apply
  path NEVER calls them.

Field schema:

- ``plugins`` — list of plugin names that should be installed.
- ``mirror``, ``flavour``, ``type``, ``subscription``, ``reboot`` —
  settings fields. Only the keys present in YAML are compared or written,
  so an omitted ``mirror`` is never blanked.
"""

from __future__ import annotations

import logging
from typing import Any

from infrafoundry.core.provider import ResourceConfig

from ..api_client import OPNsenseClient, SystemClient
from ..components._singleton import diff_singleton
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService, raise_on_failed_write

logger = logging.getLogger(__name__)

_SETTINGS_FIELDS = ("mirror", "flavour", "type", "subscription", "reboot")


class SystemFirmwareService(BaseService):
    """Service for OPNsense system-firmware operations via direct-API.

    Args:
        client: Configured ``OPNsenseClient`` instance.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize the firmware service with a SystemClient wrapper."""
        super().__init__(client)
        self.system_client = SystemClient(client)

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

    def get_firmware_info(self) -> dict[str, Any]:
        """Fetch firmware/plugin info from OPNsense.

        Returns:
            Raw API response from ``core/firmware/info``.
        """
        return self.system_client.get_firmware_info()

    def get_firmware_settings(self) -> dict[str, Any]:
        """Fetch firmware settings from OPNsense.

        Returns:
            Raw API response from ``core/firmware/get``.
        """
        return self.system_client.get_firmware_settings()

    def set_firmware_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Write firmware settings.

        Args:
            payload: ``{"firmware": {<field>: <value>}}``.

        Returns:
            API response.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        response = self.system_client.set_firmware_settings(payload)
        raise_on_failed_write(response, "set firmware settings")
        return response

    def install_plugin(self, name: str) -> dict[str, Any]:
        """Install a single plugin.

        Args:
            name: Plugin name (e.g., ``os-acme-client``).

        Returns:
            API response.
        """
        response = self.system_client.install_plugin(name)
        raise_on_failed_write(response, f"install firmware plugin {name}")
        return response

    # ------------------------------------------------------------------
    # Field extract / build
    # ------------------------------------------------------------------

    def extract_installed_plugins(self, api_response: dict[str, Any]) -> list[str]:
        """Return the sorted list of plugin names currently installed.

        ``firmware/info`` returns ``plugin: [{name, installed, ...}, ...]``;
        a plugin is installed iff its ``installed`` field equals ``"1"``
        (string sentinel) or ``1`` (int) or any truthy value.

        Args:
            api_response: Raw response from :meth:`get_firmware_info`.

        Returns:
            Sorted list of installed plugin names. Empty list if the
            response shape is unexpected.
        """
        plugin_rows = api_response.get("plugin", [])
        if not isinstance(plugin_rows, list):
            return []
        installed: list[str] = []
        for row in plugin_rows:
            if not isinstance(row, dict):
                continue
            name = _str(row.get("name"))
            if not name:
                continue
            if _is_truthy(row.get("installed")):
                installed.append(name)
        return sorted(installed)

    def build_desired_plugin_list(self, resource: ResourceConfig) -> list[str]:
        """Build the desired plugin list from a YAML singleton.

        Args:
            resource: ``system.firmware`` ``ResourceConfig``.

        Returns:
            Sorted, de-duplicated list of plugin names from
            ``config["plugins"]``. Empty list when no ``plugins`` key.
        """
        config = resource.config
        raw = config.get("plugins", [])
        if isinstance(raw, str):
            names = [s.strip() for s in raw.split(",") if s.strip()]
        elif isinstance(raw, list):
            names = [_str(v) for v in raw if _str(v)]
        else:
            names = []
        return sorted(set(names))

    def extract_firmware_settings_fields(self, api_response: dict[str, Any]) -> dict[str, Any]:
        """Extract firmware settings from a ``core/firmware/get`` response.

        Args:
            api_response: Raw response from :meth:`get_firmware_settings`.

        Returns:
            ``{field: str}`` for every settings field; ``{}`` when the
            ``firmware`` envelope is missing or not a dict. ``plugins`` and
            ``aux`` are ignored.
        """
        envelope = api_response.get("firmware")
        if not isinstance(envelope, dict):
            return {}
        return {field: _str(envelope.get(field)) for field in _SETTINGS_FIELDS}

    def build_desired_firmware_settings_fields(self, resource: ResourceConfig) -> dict[str, Any]:
        """Build the desired settings map: only keys present in YAML.

        Args:
            resource: ``system.firmware`` ``ResourceConfig``.

        Returns:
            ``{field: str}`` for each settings field set in the YAML.
        """
        config = resource.config
        return {field: _str(config[field]) for field in _SETTINGS_FIELDS if field in config}

    def settings_drift(
        self, live: dict[str, Any], desired: dict[str, Any]
    ) -> dict[str, str] | None:
        """Compare only the keys named in YAML.

        Args:
            live: Output of :meth:`extract_firmware_settings_fields`.
            desired: Output of :meth:`build_desired_firmware_settings_fields`.

        Returns:
            The desired keys/values on any difference, else ``None``.
        """
        if not desired:
            return None
        scoped = {key: live.get(key, "") for key in desired}
        return diff_singleton(scoped, desired)

    # ------------------------------------------------------------------
    # Plugin reconciliation
    # ------------------------------------------------------------------

    def desired_vs_installed_plugins(
        self,
        desired: list[str],
        installed: list[str],
    ) -> tuple[list[str], list[str]]:
        """Return ``(install_missing, extras_to_warn)`` plugin name lists.

        - ``install_missing``: in ``desired`` but not in ``installed`` —
          the apply path will install each.
        - ``extras_to_warn``: in ``installed`` but not in ``desired`` —
          **never removed**; the manager logs each at WARNING level so
          the operator can react out-of-band.

        Args:
            desired: Plugin names from YAML.
            installed: Plugin names from the live ``firmware/info`` response.

        Returns:
            Tuple of (sorted install-missing list, sorted extras list).
        """
        desired_set = set(desired)
        installed_set = set(installed)
        return sorted(desired_set - installed_set), sorted(installed_set - desired_set)

    # ------------------------------------------------------------------
    # migrate()
    # ------------------------------------------------------------------

    def export_to_yaml(self) -> str:
        """Export current firmware settings as nested YAML for ``infra migrate``.

        Returns:
            YAML string under the ``opnsense.system.firmware`` namespace.
        """
        info = self.get_firmware_info()
        installed = self.extract_installed_plugins(info)
        settings = self.extract_firmware_settings_fields(self.get_firmware_settings())
        clean: dict[str, Any] = {}
        if installed:
            clean["plugins"] = installed
        for key, value in settings.items():
            if key == "subscription":
                continue
            if isinstance(value, str) and value:
                clean[key] = value
        return emit_nested_singleton_yaml("system.firmware", clean)


def _is_truthy(value: Any) -> bool:
    """OPNsense returns ``"1"`` / ``"0"`` / int / bool — accept any truthy form."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip() not in ("", "0", "false", "False", "no", "No", "off")
    return bool(value)


def _str(value: Any) -> str:
    """Return a stripped string for any scalar."""
    if value is None:
        return ""
    return str(value).strip()
