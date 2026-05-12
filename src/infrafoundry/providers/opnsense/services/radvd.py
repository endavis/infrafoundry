"""Radvd service for OPNsense direct-API operations (#788).

Manages the OPNsense ``radvd`` (IPv6 Router Advertisement) modern MVC
controller via the ``radvd/settings/*Entry`` endpoints. The ``radvd``
controller is OPNsense 26.x's modern replacement for the legacy
``<dhcpdv6>/<optN>/<ra*>`` per-interface fields in ``config.xml`` —
each interface that should emit Router Advertisements gets its own
record on the box.

Identity is per-interface — the wire ``interface`` field (e.g. ``opt1``,
``lan``) is the natural key. YAML, however, is a **dict-shape singleton**
under the nested namespace (``opnsense.radvd.interfaces``); the operator
authors a single ``radvd`` resource whose ``interfaces`` mapping carries
one inner mapping per interface. The hybrid YAML-singleton/wire-list
pattern mirrors :class:`SystemFirmwareService` (#806) where bulk read
and per-item write coexist.

**Apply semantics (per the #788 user decision, 2026-05-10):**

- **Full reconcile.** Interfaces in live state but absent from YAML are
  DELETED. Safe — deleting a radvd record stops RA emission for that
  interface; no data loss.
- **Per-item writes.** Each add/update/delete maps to a single
  ``addEntry`` / ``setEntry/<uuid>`` / ``delEntry/<uuid>`` POST.
- **Reconfigure deferred** to the runner's finalization-hook plumbing —
  the manager declares ``FINALIZATION_HOOK = "radvd_reconfigure"``.

Endpoint surface (verified live against ``opnsense-a`` 2026-05-10):

- ``GET radvd/settings/get`` — bulk read; returns ``{"radvd": {"entries": [...]}}``.
- ``POST radvd/settings/searchEntry`` — paginated list of per-interface records.
- ``GET radvd/settings/getEntry`` — empty/template form (introspection).
- ``GET radvd/settings/getEntry/<uuid>`` — single record.
- ``POST radvd/settings/addEntry`` — create.
- ``POST radvd/settings/setEntry/<uuid>`` — update.
- ``POST radvd/settings/delEntry/<uuid>`` — delete.
- ``POST radvd/settings/toggleEntry/<uuid>`` — flip enabled (apply path doesn't use).
- ``POST radvd/service/reconfigure`` — apply pending changes.
- ``GET radvd/service/status`` — daemon health.

Wire schema (per-entry, names verified live):

- ``enabled`` — string ``"0"`` / ``"1"``.
- ``interface`` — single-select; the per-interface natural key.
- ``Base6Interface`` — optional reference for prefix delegation.
- ``mode`` — single-select: ``router`` / ``unmanaged`` / ``managed`` /
  ``assist`` / ``stateless`` (NOT ``disabled`` — use ``enabled=0``).
- ``DeprecatePrefix`` / ``RemoveAdvOnExit`` / ``RemoveRoute`` —
  single-select: ``""`` (auto) / ``on`` / ``off``.
- ``routes`` — multi-select free-text list (advertised routes).
- ``RDNSS`` — multi-select free-text list (DNS server addresses).
- ``DNSSL`` — multi-select free-text list (DNS search-list domains).
- ``dns`` — string ``"0"`` / ``"1"``.
- ``MinRtrAdvInterval`` / ``MaxRtrAdvInterval`` — string-encoded ints.
- ``Adv*Lifetime`` / ``AdvLinkMTU`` / ``AdvRASrcAddress`` — empty
  strings allowed.
- ``AdvDefaultPreference`` — single-select: ``low`` / ``medium`` / ``high``.
- ``nat64prefix`` — string.

There is **no global ``enabled`` toggle**; per-entry ``enabled``
controls each interface independently.

Operator-facing snake_case names (mapped to wire on write):

- ``enabled`` -> ``enabled``
- ``mode`` -> ``mode``
- ``priority`` -> ``AdvDefaultPreference``
- ``min_interval`` -> ``MinRtrAdvInterval``
- ``max_interval`` -> ``MaxRtrAdvInterval``
- ``routes`` -> ``routes``
- ``dns_servers`` -> ``RDNSS``
- ``domain_search`` -> ``DNSSL``
- ``base6_interface`` -> ``Base6Interface``
- ``deprecate_prefix`` -> ``DeprecatePrefix``
- ``remove_adv_on_exit`` -> ``RemoveAdvOnExit``
- ``remove_route`` -> ``RemoveRoute``
- ``dns`` -> ``dns``
- ``adv_dnssl_lifetime`` -> ``AdvDNSSLLifetime``
- ``adv_default_lifetime`` -> ``AdvDefaultLifetime``
- ``adv_link_mtu`` -> ``AdvLinkMTU``
- ``adv_preferred_lifetime`` -> ``AdvPreferredLifetime``
- ``adv_ra_src_address`` -> ``AdvRASrcAddress``
- ``adv_rdnss_lifetime`` -> ``AdvRDNSSLifetime``
- ``adv_route_lifetime`` -> ``AdvRouteLifetime``
- ``adv_valid_lifetime`` -> ``AdvValidLifetime``
- ``nat64_prefix`` -> ``nat64prefix``
"""

from __future__ import annotations

import logging
from typing import Any

from infrafoundry.core.provider import ResourceConfig

from ..api_client import OPNsenseClient, RadvdClient
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService

logger = logging.getLogger(__name__)


# Operator-facing snake_case -> wire CamelCase/lowercase translation.
# Public so the manager and validator can introspect when needed.
WIRE_FIELD_MAP: dict[str, str] = {
    "enabled": "enabled",
    "interface": "interface",
    "base6_interface": "Base6Interface",
    "mode": "mode",
    "priority": "AdvDefaultPreference",
    "min_interval": "MinRtrAdvInterval",
    "max_interval": "MaxRtrAdvInterval",
    "routes": "routes",
    "dns_servers": "RDNSS",
    "domain_search": "DNSSL",
    "deprecate_prefix": "DeprecatePrefix",
    "remove_adv_on_exit": "RemoveAdvOnExit",
    "remove_route": "RemoveRoute",
    "dns": "dns",
    "adv_dnssl_lifetime": "AdvDNSSLLifetime",
    "adv_default_lifetime": "AdvDefaultLifetime",
    "adv_link_mtu": "AdvLinkMTU",
    "adv_preferred_lifetime": "AdvPreferredLifetime",
    "adv_ra_src_address": "AdvRASrcAddress",
    "adv_rdnss_lifetime": "AdvRDNSSLifetime",
    "adv_route_lifetime": "AdvRouteLifetime",
    "adv_valid_lifetime": "AdvValidLifetime",
    "nat64_prefix": "nat64prefix",
}

# Reverse map for wire -> operator (used by extract / migrate paths).
_OPERATOR_FIELD_MAP: dict[str, str] = {wire: op for op, wire in WIRE_FIELD_MAP.items()}

# Default values for an operator-facing field map. Mirrors the
# OPNsense GUI defaults observed in the empty getEntry template.
_DEFAULTS: dict[str, Any] = {
    "enabled": "1",
    "mode": "stateless",
    "priority": "medium",
    "min_interval": "200",
    "max_interval": "600",
    "routes": [],
    "dns_servers": [],
    "domain_search": [],
    "dns": "1",
    "base6_interface": "",
    "deprecate_prefix": "",
    "remove_adv_on_exit": "",
    "remove_route": "",
    "adv_dnssl_lifetime": "",
    "adv_default_lifetime": "",
    "adv_link_mtu": "",
    "adv_preferred_lifetime": "",
    "adv_ra_src_address": "",
    "adv_rdnss_lifetime": "",
    "adv_route_lifetime": "",
    "adv_valid_lifetime": "",
    "nat64_prefix": "",
}


class RadvdService(BaseService):
    """Service for OPNsense radvd operations via direct-API.

    Args:
        client: Configured ``OPNsenseClient`` instance.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize the radvd service with a RadvdClient wrapper."""
        super().__init__(client)
        self.radvd_client = RadvdClient(client)

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

    def search_records(self) -> list[dict[str, Any]]:
        """Return the list of live radvd entry rows from the wire.

        Each row carries ``uuid`` plus the wire schema fields. Multi-select
        list fields (``routes``/``RDNSS``/``DNSSL``) are returned as
        comma-joined strings on the search response — the
        :func:`extract_interface_records` call normalises them to lists.
        """
        return self.radvd_client.search_records()

    def get_record(self, uuid: str) -> dict[str, Any]:
        """Fetch a single radvd entry by UUID."""
        return self.radvd_client.get_record(uuid)

    def add_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new radvd entry."""
        return self.radvd_client.add_record(payload)

    def set_record(self, uuid: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Update an existing radvd entry."""
        return self.radvd_client.set_record(uuid, payload)

    def del_record(self, uuid: str) -> dict[str, Any]:
        """Delete an existing radvd entry."""
        return self.radvd_client.del_record(uuid)

    def reconfigure(self) -> dict[str, Any]:
        """Reconfigure the radvd daemon to apply pending changes."""
        return self.radvd_client.reconfigure()

    # ------------------------------------------------------------------
    # Field extract / build
    # ------------------------------------------------------------------

    def extract_interface_records(self) -> dict[str, dict[str, Any]]:
        """Return ``{interface_name: operator_field_map}`` from live wire state.

        Translates each live wire row into the operator-facing field map
        (snake_case keys, list-typed multi-selects). Rows without a usable
        ``interface`` value are skipped — they cannot be matched to a YAML
        entry without a natural key.

        Returns:
            Mapping keyed by the wire ``interface`` name (e.g. ``"opt1"``).
        """
        rows = self.search_records()
        records: dict[str, dict[str, Any]] = {}
        for row in rows:
            interface = _select_value(row.get("interface"))
            if not interface:
                continue
            records[interface] = _wire_row_to_operator_fields(row)
        return records

    def build_desired_interface_records(
        self, resource: ResourceConfig
    ) -> dict[str, dict[str, Any]]:
        """Build ``{interface_name: operator_field_map}`` from a YAML singleton.

        Reads the singleton's ``interfaces`` mapping (one inner mapping per
        interface) and applies defaults so the diff against extracted live
        state is symmetric.

        Args:
            resource: ``radvd`` ``ResourceConfig`` (a dict-shape singleton).

        Returns:
            Mapping keyed by interface name; each value is a fully-populated
            operator field map (defaults filled in).
        """
        config = resource.config
        interfaces_block = config.get("interfaces", {})
        if not isinstance(interfaces_block, dict):
            return {}
        out: dict[str, dict[str, Any]] = {}
        for interface_name, raw in interfaces_block.items():
            if not isinstance(interface_name, str) or not interface_name:
                continue
            inner: dict[str, Any] = {}
            if isinstance(raw, dict):
                inner = dict(raw)
            out[interface_name] = _apply_defaults(inner)
        return out

    # ------------------------------------------------------------------
    # Diff
    # ------------------------------------------------------------------

    @staticmethod
    def compute_diff(
        live: dict[str, dict[str, Any]],
        desired: dict[str, dict[str, Any]],
    ) -> tuple[set[str], set[str], set[str]]:
        """Return ``(adds, updates, deletes)`` sets of interface names.

        - ``adds``: interfaces in ``desired`` but not in ``live``.
        - ``deletes``: interfaces in ``live`` but not in ``desired``.
        - ``updates``: interfaces in both whose operator field maps
          differ. Equality is ``==`` over the normalised maps.

        Args:
            live: Output of :func:`extract_interface_records`.
            desired: Output of :func:`build_desired_interface_records`.

        Returns:
            Three sets of interface names.
        """
        live_names = set(live)
        desired_names = set(desired)
        adds = desired_names - live_names
        deletes = live_names - desired_names
        updates = {name for name in (live_names & desired_names) if live[name] != desired[name]}
        return adds, updates, deletes

    # ------------------------------------------------------------------
    # Wire payload
    # ------------------------------------------------------------------

    @staticmethod
    def wire_payload_for_interface(
        interface_name: str, operator_fields: dict[str, Any]
    ) -> dict[str, Any]:
        """Translate an operator field map into the wire add/set payload.

        The OPNsense radvd controller wraps the inner record under
        ``{"entry": {...}}`` for both ``addEntry`` and ``setEntry`` calls.
        Multi-select list fields are joined with newlines per OPNsense
        convention; empty values pass through verbatim.

        Args:
            interface_name: The wire ``interface`` field for the record.
            operator_fields: Operator-facing snake_case field map.

        Returns:
            Wire payload ready to hand to ``addEntry`` / ``setEntry``.
        """
        entry: dict[str, Any] = {"interface": interface_name}
        for op_key, value in operator_fields.items():
            if op_key == "interface":
                continue
            wire_key = WIRE_FIELD_MAP.get(op_key, op_key)
            entry[wire_key] = _value_to_wire(value)
        return {"entry": entry}

    # ------------------------------------------------------------------
    # UUID lookups
    # ------------------------------------------------------------------

    def list_uuids_by_interface(self) -> dict[str, str]:
        """Return ``{interface_name: uuid}`` for every live record.

        Used by the manager to translate interface-keyed updates and
        deletes from the diff into the per-UUID write endpoints.
        """
        rows = self.search_records()
        out: dict[str, str] = {}
        for row in rows:
            interface = _select_value(row.get("interface"))
            uuid = str(row.get("uuid", "")).strip()
            if interface and uuid:
                out[interface] = uuid
        return out

    # ------------------------------------------------------------------
    # migrate()
    # ------------------------------------------------------------------

    def export_to_yaml(self) -> str:
        """Export current radvd state as nested YAML for ``infra migrate``.

        Returns:
            YAML string under the ``opnsense.radvd`` namespace.
        """
        live = self.extract_interface_records()
        clean: dict[str, Any] = {"interfaces": live} if live else {"interfaces": {}}
        return emit_nested_singleton_yaml("radvd", clean)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _apply_defaults(inner: dict[str, Any]) -> dict[str, Any]:
    """Return a fully-populated operator field map with defaults applied."""
    out: dict[str, Any] = {}
    for op_key, default in _DEFAULTS.items():
        if op_key in inner:
            out[op_key] = _normalise_value(op_key, inner[op_key])
        else:
            # Copy so callers can't mutate the module-level default by accident.
            out[op_key] = list(default) if isinstance(default, list) else default
    return out


def _normalise_value(op_key: str, value: Any) -> Any:
    """Coerce a YAML-supplied value into the canonical operator form.

    - List-typed fields accept lists or comma-joined strings.
    - Scalar fields are stringified for diff comparability with wire state.
    - ``enabled`` and ``dns`` accept boolean / int / string truthy forms.
    """
    if op_key in ("routes", "dns_servers", "domain_search"):
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            return [s.strip() for s in value.split(",") if s.strip()]
        return []
    if op_key in ("enabled", "dns"):
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, int):
            return "1" if value != 0 else "0"
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("1", "true", "yes", "on"):
                return "1"
            if v in ("0", "false", "no", "off", ""):
                return "0"
        return str(value)
    if value is None:
        return ""
    return str(value).strip() if isinstance(value, str) else str(value)


def _select_value(value: Any) -> str:
    """Extract the selected value from an OPNsense select field.

    OPNsense returns select fields either as a flat string or as a dict
    keyed by option-id with a ``selected`` flag. The search response
    typically uses the flat form; the get/template responses use the
    dict form.
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key, info in value.items():
            if isinstance(info, dict) and info.get("selected"):
                return str(key).strip()
    return ""


def _multi_select_value(value: Any) -> list[str]:
    """Extract selected entries from an OPNsense multi-select field.

    The wire form is either a comma-joined string (search response) or a
    dict-of-options with ``selected`` flags (template / get response).
    """
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, dict):
        out: list[str] = []
        for key, info in value.items():
            if isinstance(info, dict) and info.get("selected"):
                k = str(key).strip()
                if k:
                    out.append(k)
        return out
    return []


def _wire_row_to_operator_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Translate a wire row into a fully-defaulted operator field map.

    Handles both the search-response shape (flat strings) and the
    getEntry shape (dict-of-options). Defaults fill any missing keys so
    the result is symmetric with :func:`build_desired_interface_records`
    and the diff equality check is sound.
    """
    out: dict[str, Any] = {}
    for op_key, default in _DEFAULTS.items():
        wire_key = WIRE_FIELD_MAP.get(op_key, op_key)
        if wire_key not in row:
            out[op_key] = list(default) if isinstance(default, list) else default
            continue
        raw = row[wire_key]
        if op_key in ("routes", "dns_servers", "domain_search"):
            out[op_key] = _multi_select_value(raw)
        elif isinstance(raw, dict):
            # Dict-shape select: pick the selected key.
            out[op_key] = _select_value(raw)
        else:
            out[op_key] = _normalise_value(op_key, raw)
    return out


def _value_to_wire(value: Any) -> Any:
    """Coerce an operator value into the form OPNsense's add/set expects.

    Lists are joined with newlines (OPNsense's standard multi-select wire
    format); scalars pass through unchanged.
    """
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    return value
