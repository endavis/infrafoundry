"""Tailscale service for OPNsense direct-API operations (#787).

Manages three surfaces of the OPNsense ``os-tailscale`` plugin via the
``tailscale/settings`` and ``tailscale/authentication`` controllers:

1. **Settings** — the scalar settings fields (``enabled``, ``listenPort``,
   ``acceptDNS``, etc.) under the ``settings`` envelope.
2. **Subnets** — the ``settings.subnets.subnet4`` embedded list of CIDR
   strings. There is **no** per-subnet CRUD endpoint; subnets are a
   full-replace embedded list written via ``tailscale/settings/set``.
3. **Auth** — the ``loginServer`` / ``preAuthKey`` fields under the
   ``authentication`` envelope.

Endpoint surface (verified live against ``opnsense-a``, 2026-05-25):

- ``GET tailscale/settings/get`` — returns ``{"settings": {...}}``
  including ``subnets.subnet4`` array.
- ``POST tailscale/settings/set`` — writes the settings block.
- ``GET tailscale/authentication/get`` — returns
  ``{"authentication": {"loginServer": "...", "preAuthKey": "..."}}``.
- ``POST tailscale/authentication/set`` — writes auth.
- ``POST tailscale/service/reconfigure`` — apply pending changes.

Wire-to-operator field maps:

Settings (wire → operator):

- ``enabled`` → ``enable`` (``"0"``/``"1"`` ↔ bool)
- ``loginTimeout`` → ``login_timeout`` (string int ↔ int)
- ``listenPort`` → ``listen_port`` (string int ↔ int)
- ``acceptDNS`` → ``accept_dns`` (``"0"``/``"1"`` ↔ bool)
- ``advertiseExitNode`` → ``advertise_exit_node`` (``"0"``/``"1"`` ↔ bool)
- ``useExitNode`` → ``use_exit_node`` (select-dict ↔ string, empty = None)
- ``acceptSubnetRoutes`` → ``accept_subnet_routes`` (``"0"``/``"1"`` ↔ bool)
- ``enableSSH`` → ``enable_ssh`` (``"0"``/``"1"`` ↔ bool)
- ``disableSNAT`` → ``enable_snat`` (INVERTED: wire ``"0"`` = op ``True``)

Auth (wire → operator):

- ``loginServer`` → ``login_server`` (string)
- ``preAuthKey`` → ``pre_auth_key`` (string; may be a ``secret://`` URI)
"""

from __future__ import annotations

import logging
from typing import Any

from infrafoundry.core.provider import ResourceConfig

from ..api_client import OPNsenseClient, TailscaleClient
from ._nested_emit import emit_nested_list_yaml, emit_nested_singleton_yaml
from .base import BaseService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Wire ↔ operator field maps (settings)
# ---------------------------------------------------------------------------

#: Operator-facing snake_case → wire CamelCase/lowercase.
SETTINGS_WIRE_FIELD_MAP: dict[str, str] = {
    "enable": "enabled",
    "login_timeout": "loginTimeout",
    "listen_port": "listenPort",
    "accept_dns": "acceptDNS",
    "advertise_exit_node": "advertiseExitNode",
    "use_exit_node": "useExitNode",
    "accept_subnet_routes": "acceptSubnetRoutes",
    "enable_ssh": "enableSSH",
    # enable_snat is INVERTED to disableSNAT — handled explicitly below.
    "enable_snat": "disableSNAT",
}

#: Operator-facing snake_case → wire name for auth fields.
AUTH_WIRE_FIELD_MAP: dict[str, str] = {
    "login_server": "loginServer",
    "pre_auth_key": "preAuthKey",
}

#: Boolean-style operator fields (value is ``"0"`` / ``"1"`` on wire).
_BOOL_FIELDS: frozenset[str] = frozenset(
    {"enable", "accept_dns", "advertise_exit_node", "accept_subnet_routes", "enable_ssh"}
)

#: The ``enable_snat`` field inverts the wire ``disableSNAT`` polarity.
_INVERT_FIELDS: frozenset[str] = frozenset({"enable_snat"})


# ---------------------------------------------------------------------------
# TailscaleService
# ---------------------------------------------------------------------------


class TailscaleService(BaseService):
    """Service for OPNsense tailscale plugin operations via direct-API.

    Covers all three tailscale surfaces: settings, subnets, and auth.
    The settings and subnets surfaces share the same ``tailscale/settings/*``
    endpoints (subnets are embedded in the settings response).

    Args:
        client: Configured ``OPNsenseClient`` instance.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize the tailscale service with a TailscaleClient wrapper."""
        super().__init__(client)
        self.tailscale_client = TailscaleClient(client)

    # ------------------------------------------------------------------
    # API helpers — settings
    # ------------------------------------------------------------------

    def get_settings(self) -> dict[str, Any]:
        """Fetch the full tailscale settings block from the OPNsense API.

        Returns:
            Raw ``{"settings": {...}}`` API response, including embedded
            ``subnets.subnet4`` list.
        """
        return self.tailscale_client.get_settings()

    def set_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Push a tailscale settings update to OPNsense.

        Args:
            payload: Settings payload wrapped under ``"settings"``.

        Returns:
            API response (typically ``{"result": "saved"}``).
        """
        return self.tailscale_client.set_settings(payload)

    # ------------------------------------------------------------------
    # API helpers — auth
    # ------------------------------------------------------------------

    def get_authentication(self) -> dict[str, Any]:
        """Fetch the tailscale authentication block.

        Returns:
            Raw ``{"authentication": {...}}`` API response.
        """
        return self.tailscale_client.get_authentication()

    def set_authentication(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Push a tailscale authentication update to OPNsense.

        Args:
            payload: Auth payload wrapped under ``"authentication"``.

        Returns:
            API response (typically ``{"result": "saved"}``).
        """
        return self.tailscale_client.set_authentication(payload)

    def reconfigure(self) -> dict[str, Any]:
        """Reconfigure the tailscale daemon to apply pending changes.

        Returns:
            API response (typically ``{"status": "ok"}``).
        """
        return self.tailscale_client.reconfigure()

    def apply_settings_patch(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Safe read-modify-write for the tailscale settings endpoint.

        ``tailscale/settings/set`` is a full-replace endpoint — posting a
        partial payload clobbers unrelated fields (e.g. posting only subnets
        would erase the scalar settings).  This helper fetches the live
        settings, deep-merges *patch* into them, and posts the merged result.

        Args:
            patch: Partial ``{"settings": {...}}`` mapping to merge into the
                live settings.  Nested dicts are merged recursively; scalar
                values in *patch* overwrite their live counterparts.

        Returns:
            API response from :meth:`set_settings` (typically
            ``{"result": "saved"}``).
        """
        live = self.get_settings()
        merged = _deep_merge(live, patch)
        return self.set_settings(merged)

    # ------------------------------------------------------------------
    # Field extract / build — settings
    # ------------------------------------------------------------------

    def extract_settings_fields(self, api_response: dict[str, Any]) -> dict[str, Any]:
        """Extract settings fields from a ``tailscale/settings/get`` response.

        Translates wire names → operator names and normalises types.
        The ``enable_snat`` field inverts ``disableSNAT`` polarity.

        Args:
            api_response: Raw response from :meth:`get_settings`.

        Returns:
            Flat ``{op_field: value}`` mapping for the nine settings fields.
        """
        raw = api_response.get("settings", {})
        return {
            "enable": _wire_bool_to_str(raw.get("enabled", "0")),
            "login_timeout": _str_int(raw.get("loginTimeout", "10")),
            "listen_port": _str_int(raw.get("listenPort", "41641")),
            "accept_dns": _wire_bool_to_str(raw.get("acceptDNS", "0")),
            "advertise_exit_node": _wire_bool_to_str(raw.get("advertiseExitNode", "0")),
            "use_exit_node": _select_value(raw.get("useExitNode", "")),
            "accept_subnet_routes": _wire_bool_to_str(raw.get("acceptSubnetRoutes", "0")),
            "enable_ssh": _wire_bool_to_str(raw.get("enableSSH", "0")),
            # INVERTED: disableSNAT "0" → enable_snat "1", "1" → "0"
            "enable_snat": _invert_bool(raw.get("disableSNAT", "0")),
        }

    def build_desired_settings_fields(self, resource: ResourceConfig) -> dict[str, Any]:
        """Build the desired settings field map from a YAML singleton.

        Args:
            resource: ``tailscale.settings`` ``ResourceConfig`` with
                ``name="settings"`` and operator YAML in ``config``.

        Returns:
            Flat ``{op_field: value}`` mapping mirroring
            :meth:`extract_settings_fields`.
        """
        config = resource.config
        return {
            "enable": _coerce_bool(config.get("enable", False)),
            "login_timeout": _str_int(config.get("login_timeout", "10")),
            "listen_port": _str_int(config.get("listen_port", "41641")),
            "accept_dns": _coerce_bool(config.get("accept_dns", True)),
            "advertise_exit_node": _coerce_bool(config.get("advertise_exit_node", False)),
            "use_exit_node": str(config.get("use_exit_node", "") or "").strip(),
            "accept_subnet_routes": _coerce_bool(config.get("accept_subnet_routes", False)),
            "enable_ssh": _coerce_bool(config.get("enable_ssh", False)),
            "enable_snat": _coerce_bool(config.get("enable_snat", True)),
        }

    def build_settings_wire_payload(self, desired_fields: dict[str, Any]) -> dict[str, Any]:
        """Translate an operator settings field map into the wire payload.

        Args:
            desired_fields: Operator-facing field map from
                :meth:`build_desired_settings_fields`.

        Returns:
            ``{"settings": {...}}`` wire payload ready for
            :meth:`set_settings`.
        """
        wire: dict[str, Any] = {}
        for op_key, wire_key in SETTINGS_WIRE_FIELD_MAP.items():
            value = desired_fields.get(op_key)
            if op_key in _INVERT_FIELDS:
                # enable_snat "1" → disableSNAT "0", "0" → "1"
                wire[wire_key] = "0" if value == "1" else "1"
            elif op_key in _BOOL_FIELDS:
                wire[wire_key] = value if isinstance(value, str) else ("1" if value else "0")
            else:
                wire[wire_key] = str(value) if value is not None else ""
        return {"settings": wire}

    # ------------------------------------------------------------------
    # Field extract / build — auth
    # ------------------------------------------------------------------

    def extract_auth_fields(self, api_response: dict[str, Any]) -> dict[str, Any]:
        """Extract auth fields from a ``tailscale/authentication/get`` response.

        Args:
            api_response: Raw response from :meth:`get_authentication`.

        Returns:
            Flat ``{op_field: value}`` mapping for the two auth fields.
        """
        raw = api_response.get("authentication", {})
        return {
            "login_server": str(raw.get("loginServer", "") or "").strip(),
            "pre_auth_key": str(raw.get("preAuthKey", "") or "").strip(),
        }

    def build_desired_auth_fields(self, resource: ResourceConfig) -> dict[str, Any]:
        """Build the desired auth field map from a YAML singleton.

        The ``pre_auth_key`` field is redacted in plan output; the raw
        value (or secret URI) is retained in the returned map for diff
        comparison and apply-time writing.

        Args:
            resource: ``tailscale.auth`` ``ResourceConfig``.

        Returns:
            Flat ``{op_field: value}`` mapping.
        """
        config = resource.config
        return {
            "login_server": str(config.get("login_server", "") or "").strip(),
            "pre_auth_key": str(config.get("pre_auth_key", "") or "").strip(),
        }

    def build_auth_wire_payload(self, desired_fields: dict[str, Any]) -> dict[str, Any]:
        """Translate an operator auth field map into the wire payload.

        Args:
            desired_fields: Operator-facing field map from
                :meth:`build_desired_auth_fields`.

        Returns:
            ``{"authentication": {...}}`` wire payload ready for
            :meth:`set_authentication`.
        """
        wire: dict[str, Any] = {}
        for op_key, wire_key in AUTH_WIRE_FIELD_MAP.items():
            wire[wire_key] = desired_fields.get(op_key, "")
        return {"authentication": wire}

    # ------------------------------------------------------------------
    # Field extract / build — subnets
    # ------------------------------------------------------------------

    def extract_subnet_cidrs(self, api_response: dict[str, Any]) -> list[str]:
        """Extract the current subnet CIDR list from a settings response.

        Subnets live at ``settings.subnets.subnet4`` as a list of CIDR
        strings (IPv4 or IPv6 — both use the ``subnet4`` key per
        OPNsense's os-tailscale plugin quirk).

        Args:
            api_response: Raw response from :meth:`get_settings`.

        Returns:
            Sorted list of CIDR strings currently configured.
        """
        raw = api_response.get("settings", {})
        subnets_block = raw.get("subnets", {})
        if isinstance(subnets_block, dict):
            raw_list = subnets_block.get("subnet4", [])
        elif isinstance(subnets_block, list):
            raw_list = subnets_block
        else:
            raw_list = []
        if isinstance(raw_list, list):
            return sorted(str(c).strip() for c in raw_list if str(c).strip())
        return []

    def build_desired_subnet_cidrs(self, resources: list[ResourceConfig]) -> list[str]:
        """Build the desired subnet CIDR list from a list of YAML entries.

        Each ``tailscale.subnets`` ``ResourceConfig`` carries a ``cidr``
        field in ``config``. The ``name`` field is a slug-form identity
        key used only for state tracking; it is never sent on the wire.

        Args:
            resources: List of ``tailscale.subnets`` ``ResourceConfig``
                entries (one per subnet).

        Returns:
            Sorted list of CIDR strings to set on the wire.
        """
        cidrs: list[str] = []
        for resource in resources:
            cidr = str(resource.config.get("cidr", "") or "").strip()
            if cidr:
                cidrs.append(cidr)
        return sorted(cidrs)

    def build_subnets_wire_payload(self, cidrs: list[str]) -> dict[str, Any]:
        """Build the subnets full-replace wire payload.

        Writes only the ``subnets`` sub-key so other settings fields are
        not accidentally clobbered by a partial PUT.

        Args:
            cidrs: Desired CIDR list (from
                :meth:`build_desired_subnet_cidrs`).

        Returns:
            ``{"settings": {"subnets": {"subnet4": [...]}}}`` wire
            payload ready for :meth:`set_settings`.
        """
        return {"settings": {"subnets": {"subnet4": cidrs}}}

    # ------------------------------------------------------------------
    # migrate() helpers
    # ------------------------------------------------------------------

    def export_settings_to_yaml(self) -> str:
        """Export current tailscale settings as nested YAML.

        Returns:
            YAML string under the ``opnsense.tailscale.settings`` namespace.
        """
        live = self.extract_settings_fields(self.get_settings())
        # Emit only explicitly operator-facing names; skip defaults that
        # an empty installation would expose to reduce noise.
        clean: dict[str, Any] = {k: v for k, v in live.items() if v not in ("", None)}
        return emit_nested_singleton_yaml("tailscale.settings", clean)

    def export_auth_to_yaml(self) -> str:
        """Export current tailscale authentication as nested YAML.

        The ``pre_auth_key`` is redacted in exported YAML because the
        live API returns an empty string for it (the key is write-only
        on the OPNsense side).

        Returns:
            YAML string under the ``opnsense.tailscale.auth`` namespace.
        """
        live = self.extract_auth_fields(self.get_authentication())
        clean = {k: v for k, v in live.items() if k != "pre_auth_key" and v}
        return emit_nested_singleton_yaml("tailscale.auth", clean)

    def export_subnets_to_yaml(self) -> str:
        """Export current tailscale subnets as nested YAML.

        Returns:
            YAML string under the ``opnsense.tailscale.subnets`` namespace.
        """
        cidrs = self.extract_subnet_cidrs(self.get_settings())
        entries: list[dict[str, Any]] = [
            {"name": _cidr_to_name(cidr), "config": {"cidr": cidr}} for cidr in cidrs
        ]
        return emit_nested_list_yaml("tailscale.subnets", entries)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _wire_bool_to_str(value: Any) -> str:
    """Normalise a wire ``"0"``/``"1"`` field to a canonical string."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return "1" if value != 0 else "0"
    if isinstance(value, str):
        v = value.strip()
        if v in ("1", "true", "yes", "on"):
            return "1"
        return "0"
    return "0"


def _coerce_bool(value: Any) -> str:
    """Coerce an operator YAML bool/int/str to ``"0"``/``"1"``."""
    return _wire_bool_to_str(value)


def _invert_bool(value: Any) -> str:
    """Invert a wire bool string for the ``disableSNAT``↔``enable_snat`` mapping."""
    wire = _wire_bool_to_str(value)
    return "0" if wire == "1" else "1"


def _str_int(value: Any) -> str:
    """Coerce a value to a string-encoded integer for diff comparability."""
    if value is None:
        return ""
    try:
        return str(int(str(value).strip()))
    except (ValueError, TypeError):
        return str(value).strip()


def _select_value(value: Any) -> str:
    """Extract the selected value from an OPNsense single-select field.

    OPNsense returns select fields either as a flat string or as a dict
    keyed by option-id with a ``selected`` flag.
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key, info in value.items():
            if isinstance(info, dict) and info.get("selected"):
                selected_key = str(key).strip()
                # The empty-string key represents "None" / no exit-node.
                return selected_key
    return ""


def _cidr_to_name(cidr: str) -> str:
    """Synthesise a slug-form name from a CIDR for YAML identity tracking.

    Example: ``"192.168.110.0/24"`` → ``"subnet-192-168-110-0-24"``.
    """
    slug = cidr.replace(".", "-").replace(":", "-").replace("/", "-")
    return f"subnet-{slug}"


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *patch* into *base*, returning a new dict.

    Scalar values in *patch* overwrite their counterparts in *base*.
    Nested dicts are merged recursively so sibling keys not present in
    *patch* are preserved.

    Args:
        base: The base dictionary (e.g. live API response).
        patch: The dict of changes to apply.

    Returns:
        New merged dictionary (neither *base* nor *patch* is mutated).
    """
    result: dict[str, Any] = dict(base)
    for key, patch_val in patch.items():
        base_val = result.get(key)
        if isinstance(base_val, dict) and isinstance(patch_val, dict):
            result[key] = _deep_merge(base_val, patch_val)
        else:
            result[key] = patch_val
    return result
