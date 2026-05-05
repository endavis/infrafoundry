"""Alias service for OPNsense direct-API extraction (read-only; #747).

Manages OPNsense firewall aliases via the
``firewall/alias/{searchItem,getItem}`` controller. **Read-side only** —
this service exposes ``search`` and ``export_to_yaml`` for the
``foundry config migrate`` command. Writes still flow through the
terraform path (``aliases.tf.j2`` + ``browningluke/opnsense_firewall_alias``)
per ADR-0014 §"Per-component decisions"; aliases are *not* on the
direct-API write path yet.

Endpoint surface (the ``firewall/alias`` controller in OPNsense 26.x):

- ``POST firewall/alias/searchItem`` — list rows for the dataTable view.
  Response shape ``{"rows": [...], "rowCount": N, "current": 1, "total": N}``.
  Each row exposes flat ``name``, ``type`` (selected dict), ``description``,
  ``content`` (newline-separated string), ``enabled`` (string ``"0"``/``"1"``),
  ``proto`` (selected dict; geoip only), ``updatefreq`` (string; urltable),
  ``categories`` (selected-dict map of UUIDs), ``counters`` (string), and
  ``interface`` (selected dict; dynipv6host only).
- ``GET  firewall/alias/getItem/<uuid>`` — wrapped record under ``{"alias": {...}}``.
  Not used in the read-side extractor: the ``searchItem`` row already
  carries every field we need to round-trip aliases (verified empirically
  on ``opnsense-a`` running 26.1.6_2). Defining ``get`` here would only
  duplicate work and cost an extra round-trip per alias.

System-alias filtering
----------------------

OPNsense's ``searchItem`` returns three categories of aliases mixed
together: operator-managed entries (``host`` / ``network`` / ``port`` /
``url`` / ``urltable`` / ``geoip`` / etc.) and two categories of
system-internal entries that are NOT operator-writable:

- ``type: internal`` — per-interface auto-generated network aliases
  (e.g., ``__lan_network``, ``__lo0_network``). OPNsense regenerates
  these from interface state on every reconfigure; the operator cannot
  create / delete / edit them via the alias controller.
- ``type: external`` — system-managed tables (e.g., ``bogons``,
  ``sshlockout``, ``virusprot``). These are populated by other OPNsense
  subsystems and are surfaced through the alias API as read-only.

Both categories are silently filtered from ``export_to_yaml`` output —
including them would produce YAML that the terraform write path
(``opnsense_firewall_alias``) would attempt to create on apply,
conflicting with the aliases OPNsense regenerates server-side.

YAML schema (extended in #747 — must agree with the terraform template):

The base fields (``name``, ``type``, ``description``, ``content``,
``enabled``) are unchanged; the type-specific fields below are emitted
only when the live record carries a non-default value, so existing
configs continue to round-trip identically.

- ``proto`` (str, geoip only) — ``IPv4`` or ``IPv6``.
- ``updatefreq`` (str, urltable / urltable_ports only) — refresh
  frequency in days; preserved as a string because OPNsense renders it
  with arbitrary decimal precision and we don't want to round-trip lose
  precision.
- ``categories`` (list[str]) — sorted list of OPNsense category UUIDs.
- ``counters`` (bool) — emit pf counters for this alias.
- ``interface`` (str, dynipv6host only) — interface name to derive the
  dynamic IPv6 host from.

Wire→YAML translation rules (mirrors ``services.nat_rule._normalize_field``
and ``services.virtual_ip._normalize_field`` — the established pattern
for OPNsense select dicts):

- ``content``: wire is a ``"\\n"``-joined string → YAML list (split,
  strip, drop empties).
- ``enabled``: wire ``"0"`` / ``"1"`` string → YAML bool.
- ``counters``: wire ``"0"`` / ``"1"`` string → YAML bool; only emitted
  when ``true`` (the default is ``false``).
- ``type`` / ``proto`` / ``interface``: OPNsense returns these as a
  selected-dict (``{value: {selected: 1, value: ...}}``) on
  ``searchItem``; the service extracts the selected key.
- ``categories``: wire is a selected-dict map of UUIDs → YAML list of
  selected UUIDs (sorted for stable diffing).
- ``updatefreq``: wire is a string; YAML preserves it verbatim.

Operator-facing ``name`` is the alias name verbatim (OPNsense enforces
uniqueness across aliases server-side). The exporter emits both the
top-level ``name`` (operator-facing key) and ``config.name`` (the
OPNsense-enforced unique value); they're identical on extraction but
the operator can rename them after import — the terraform write path
keys on ``config.name``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from .base import BaseService

# Controller base for all alias read endpoints.
_ALIAS_BASE = "firewall/alias"

# Alias types that OPNsense maintains internally and that the operator
# cannot create / edit / delete via the public alias controller. Filtered
# from ``export_to_yaml`` so the migrated YAML stays apply-clean against
# the terraform write path.
_SYSTEM_ALIAS_TYPES: frozenset[str] = frozenset({"internal", "external"})


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveAlias:
    """An alias as currently configured on the OPNsense box.

    ``raw`` is the ``searchItem`` row, which carries every field we need
    to round-trip the alias to YAML (no separate ``getItem`` call needed
    — verified on ``opnsense-a`` running 26.1.6_2).

    Attributes:
        uuid: OPNsense-assigned UUID for the alias.
        name: Alias name (OPNsense-enforced unique across aliases).
        type: Alias type (host / network / port / url / urltable / geoip
            / networkgroup / mac / asn / bgpasn / dynipv6host /
            internal / external / authgroup / etc.).
        raw: Full original ``searchItem`` row.
    """

    uuid: str
    name: str
    type: str
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AliasService(BaseService):
    """Read-only service for OPNsense alias extraction via direct API.

    Exposes ``search`` (list live aliases) and ``export_to_yaml``
    (dump live state as InfraFoundry YAML for the ``config migrate``
    command). Write operations stay on the terraform path; this service
    is intentionally read-only until aliases are migrated to direct-API
    writes (separate ADR decision).
    """

    def search(self) -> list[LiveAlias]:
        """Fetch the live alias list.

        Returns:
            ``LiveAlias`` instances normalized from the ``searchItem``
            rows. Defensive against non-dict responses and missing
            ``rows`` key — both yield ``[]`` (mirrors
            ``services.nat_rule.search``).
        """
        response = self.client.request("POST", f"{_ALIAS_BASE}/searchItem")

        rows: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw_rows = response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]

        return [_row_to_live(row) for row in rows]

    def export_to_yaml(self) -> str:
        """Export the current alias configuration to InfraFoundry YAML.

        Aliases whose ``type`` is ``internal`` or ``external`` are
        silently skipped — those are OPNsense system-internal entries
        (``__lan_network``, ``bogons``, etc.) that the operator cannot
        write via the alias controller. Including them would produce
        YAML that the terraform write path (``opnsense_firewall_alias``)
        would attempt to (re)create on apply.

        For each remaining live alias the ``searchItem`` row already
        carries every field we need (no extra ``getItem`` round-trip
        required — verified empirically). Operator-facing ``name`` is
        the alias name verbatim; the operator can rename after import
        (terraform keys on ``config.name``, not the top-level ``name``).

        Returns:
            YAML string with ``provider/type/name/config`` entries.
        """
        live = self.search()
        resources = [
            {
                "provider": "opnsense",
                "type": "aliases",
                "name": alias.name,
                "config": _live_to_export_config(alias),
            }
            for alias in live
            if alias.type not in _SYSTEM_ALIAS_TYPES
        ]
        return yaml.safe_dump({"resources": resources}, sort_keys=False)


# ---------------------------------------------------------------------------
# Internal helpers (row parsing / export)
# ---------------------------------------------------------------------------


def _normalize_field(value: Any) -> str:
    """Collapse an OPNsense field value to a comparable string.

    Mirrors ``services.nat_rule._normalize_field``: select fields
    returned as option dicts (``{value: {selected: 1, value: ...}}``)
    have their selected key extracted; ``None`` becomes ``""``; plain
    scalars are stringified.

    Note: bools are never produced on the wire by OPNsense's alias
    controller (it serializes them as ``"0"`` / ``"1"`` strings), so
    this helper does not handle the bool branch — unlike the
    ``unbound_forward`` variant. Boolean conversion happens explicitly
    in ``_live_to_export_config``.
    """
    if value is None:
        return ""
    if isinstance(value, dict):
        for option_key, option_value in value.items():
            if isinstance(option_value, dict) and option_value.get("selected"):
                return str(option_key)
        return ""
    return str(value)


def _split_content(value: Any) -> list[str]:
    """Split a newline-separated content string into a YAML-friendly list.

    Strips each line, drops empties (handles trailing newlines / blank
    lines gracefully). Returns ``[]`` for ``None``, empty string, or any
    non-string input.
    """
    if not isinstance(value, str) or not value:
        return []
    return [line.strip() for line in value.split("\n") if line.strip()]


def _selected_uuids(value: Any) -> list[str]:
    """Extract the selected UUIDs from an OPNsense multi-select dict.

    OPNsense renders multi-select fields (``categories``) on
    ``searchItem`` as ``{<uuid>: {value: ..., selected: 0|1}}``. This
    helper returns the UUIDs whose ``selected`` flag is truthy, sorted
    for stable diffing. Falls back to comma-string parsing if the wire
    shape isn't a dict (defensive against API variations across OPNsense
    versions).
    """
    if isinstance(value, dict):
        selected = [
            str(uuid)
            for uuid, info in value.items()
            if isinstance(info, dict) and info.get("selected")
        ]
        return sorted(selected)
    if isinstance(value, str) and value:
        return sorted(part.strip() for part in value.split(",") if part.strip())
    return []


def _row_to_live(row: dict[str, Any]) -> LiveAlias:
    """Normalize a ``searchItem`` row into a ``LiveAlias``."""
    uuid = str(row.get("uuid", ""))
    name = _normalize_field(row.get("name"))
    alias_type = _normalize_field(row.get("type"))
    return LiveAlias(uuid=uuid, name=name, type=alias_type, raw=row)


def _live_to_export_config(alias: LiveAlias) -> dict[str, Any]:
    """Build a YAML-friendly config dict from a ``LiveAlias``.

    Always emits the base fields (``name``, ``type``, ``description``,
    ``content``, ``enabled``); type-specific fields are only emitted
    when the live record carries a non-default value so existing
    operator YAML round-trips identically.
    """
    raw = alias.raw

    config: dict[str, Any] = {
        "name": alias.name,
        "type": alias.type,
        "description": _normalize_field(raw.get("description")),
        "content": _split_content(raw.get("content")),
        "enabled": _normalize_field(raw.get("enabled")) != "0",
    }

    # ``proto`` — geoip only.
    proto = _normalize_field(raw.get("proto"))
    if proto:
        config["proto"] = proto

    # ``updatefreq`` — urltable / urltable_ports; preserved as string.
    updatefreq = _normalize_field(raw.get("updatefreq"))
    if updatefreq:
        config["updatefreq"] = updatefreq

    # ``categories`` — sorted UUID list.
    categories = _selected_uuids(raw.get("categories"))
    if categories:
        config["categories"] = categories

    # ``counters`` — only emit when true (default is false).
    counters = _normalize_field(raw.get("counters")) == "1"
    if counters:
        config["counters"] = True

    # ``interface`` — dynipv6host only.
    interface = _normalize_field(raw.get("interface"))
    if interface:
        config["interface"] = interface

    return config
