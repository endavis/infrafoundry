"""Unbound host-override service for OPNsense direct-API extraction (read-only; #748).

Manages OPNsense Unbound DNS host overrides via the
``unbound/settings/searchHostOverride`` controller. **Read-side only** —
this service exposes ``search`` and ``export_to_yaml`` for the
``foundry config migrate`` command. Writes still flow through the
terraform path (``unbound_host_override.tf.j2`` +
``browningluke/opnsense_unbound_host_override``) per ADR-0014
§"Per-component decisions"; host overrides are *not* on the direct-API
write path yet.

Endpoint surface (the ``unbound/settings`` controller in OPNsense 26.x;
the same controller already used by
:mod:`services.unbound_host_alias` for parent UUID resolution and by
:mod:`validator` for cross-reference validation):

- ``POST unbound/settings/searchHostOverride`` — list rows for the
  dataTable view. Response shape
  ``{"rows": [...], "rowCount": N, "current": 1, "total": N}``. Each row
  exposes flat ``hostname``, ``domain``, ``server``, ``description``,
  ``rr`` (selected dict — ``A`` / ``AAAA`` / ``MX``), ``mxprio`` (string;
  MX records only), ``mx`` (string; MX records only), and ``enabled``
  (string ``"0"``/``"1"``).

No system-internal filtering needed — host overrides are entirely
operator-defined. Unlike aliases (which carry OPNsense-internal
``internal``/``external`` types regenerated server-side), every host
override the API returns is operator-writable via the terraform path.

YAML schema (extended in #748 — must agree with the terraform template):

The base fields (``hostname``, ``domain``, ``enabled``, ``server``,
``description``) match what the terraform template has accepted since
day one; the type-specific fields below are emitted only when the live
record carries a non-default value, so existing 5-field operator YAML
continues to round-trip identically.

- ``rr`` (str) — record type. ``A`` (default), ``AAAA``, or ``MX``.
  Omitted from YAML when ``A``.
- ``mxprio`` (str, MX only) — MX priority. Preserved as a string because
  OPNsense renders it as a numeric string and we don't want to round-trip
  lose precision (mirrors ``updatefreq`` handling on aliases).
- ``mx`` (str, MX only) — MX target hostname.

Wire→YAML translation rules (mirrors ``services.alias._normalize_field``
— the established pattern for OPNsense select dicts):

- ``enabled``: wire ``"0"`` / ``"1"`` string → YAML bool.
- ``rr``: wire is a selected-dict (``{A: {selected: 1, value: A}, ...}``)
  on ``searchHostOverride`` → string. Default ``A``; emit only when
  non-``A``.
- ``hostname`` / ``domain`` / ``server`` / ``description`` / ``mx``: wire
  is a string → emit verbatim.
- ``mxprio``: wire is a string (numeric) → preserved as a string.

Operator-facing ``name`` is the resource name; the operator can rename
after import (terraform keys on the ``hostname``/``domain`` pair, not the
top-level ``name``). The exporter synthesizes ``name`` as
``<hostname>-<domain-with-dots-as-hyphens>`` (lowercased; mirrors
``services.unbound_forward._synthesize_name``) so the synthesized name
is a valid terraform identifier — the template's
``{{ name | replace('-', '_') }}`` filter accepts hyphens and underscores
but rejects dots. When ``rr`` is non-default (``AAAA`` or ``MX``), it is
appended as a suffix (e.g., ``web-example-com-aaaa``) so an A and an
AAAA record on the same hostname don't collide on the same key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from .base import BaseService

# Controller base for all host-override read endpoints (shared with
# host-alias parent UUID resolution and validator cross-references).
_HOST_OVERRIDE_BASE = "unbound/settings"

# Default record type. ``A`` is the most common shape and is also what
# OPNsense assigns when the operator leaves the ``rr`` field unset in
# the GUI; emit ``rr`` to YAML only when the live record carries a
# non-default value so existing 5-field operator YAML round-trips.
_DEFAULT_RR = "A"


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveUnboundHostOverride:
    """An Unbound host override as currently configured on the OPNsense box.

    ``raw`` is the ``searchHostOverride`` row, which carries every field
    we need to round-trip the override to YAML (no separate
    ``getHostOverride`` call needed — the search row is dense).

    Attributes:
        uuid: OPNsense-assigned UUID for the host override.
        hostname: Hostname label (e.g., ``"web"`` in
            ``web.example.com``).
        domain: Parent domain (e.g., ``"example.com"``).
        rr: Record type — ``A`` / ``AAAA`` / ``MX``.
        raw: Full original ``searchHostOverride`` row.
    """

    uuid: str
    hostname: str
    domain: str
    rr: str
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class UnboundHostOverrideService(BaseService):
    """Read-only service for OPNsense Unbound host override extraction.

    Exposes ``search`` (list live host overrides) and ``export_to_yaml``
    (dump live state as InfraFoundry YAML for the ``config migrate``
    command). Write operations stay on the terraform path; this service
    is intentionally read-only until host overrides are migrated to
    direct-API writes (separate ADR decision).
    """

    def search(self) -> list[LiveUnboundHostOverride]:
        """Fetch the live host-override list.

        Returns:
            ``LiveUnboundHostOverride`` instances normalized from the
            ``searchHostOverride`` rows. Defensive against non-dict
            responses and missing ``rows`` key — both yield ``[]``
            (mirrors ``services.alias.search``).
        """
        response = self.client.request("POST", f"{_HOST_OVERRIDE_BASE}/searchHostOverride")

        rows: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw_rows = response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]

        return [_row_to_live(row) for row in rows]

    def export_to_yaml(self) -> str:
        """Export the current host overrides to InfraFoundry YAML.

        For each live host override the ``searchHostOverride`` row
        already carries every field we need (no extra
        ``getHostOverride`` round-trip required). Operator-facing
        ``name`` is synthesized from ``hostname.domain`` for stable,
        human-readable resource keys (mirrors the ``hostname.domain``
        cross-reference form already accepted by the
        ``unbound_host_alias`` validator). The operator can rename after
        import — the terraform write path keys on the
        ``hostname``/``domain`` pair, not the top-level ``name``.

        Returns:
            YAML string with ``provider/type/name/config`` entries.
        """
        live = self.search()
        resources = [
            {
                "provider": "opnsense",
                "type": "unbound_host_override",
                "name": _synthesize_name(override),
                "config": _live_to_export_config(override),
            }
            for override in live
        ]
        return yaml.safe_dump({"resources": resources}, sort_keys=False)


# ---------------------------------------------------------------------------
# Internal helpers (row parsing / export)
# ---------------------------------------------------------------------------


def _normalize_field(value: Any) -> str:
    """Collapse an OPNsense field value to a comparable string.

    Mirrors ``services.alias._normalize_field``: select fields returned
    as option dicts (``{value: {selected: 1, value: ...}}``) have their
    selected key extracted; ``None`` becomes ``""``; plain scalars are
    stringified.

    Note: bools are never produced on the wire by OPNsense's host
    override controller (it serializes them as ``"0"`` / ``"1"``
    strings). Boolean conversion happens explicitly in
    ``_live_to_export_config``.
    """
    if value is None:
        return ""
    if isinstance(value, dict):
        for option_key, option_value in value.items():
            if isinstance(option_value, dict) and option_value.get("selected"):
                return str(option_key)
        return ""
    return str(value)


def _row_to_live(row: dict[str, Any]) -> LiveUnboundHostOverride:
    """Normalize a ``searchHostOverride`` row into a ``LiveUnboundHostOverride``."""
    uuid = str(row.get("uuid", ""))
    hostname = _normalize_field(row.get("hostname"))
    domain = _normalize_field(row.get("domain"))
    rr = _normalize_field(row.get("rr")) or _DEFAULT_RR
    return LiveUnboundHostOverride(uuid=uuid, hostname=hostname, domain=domain, rr=rr, raw=row)


def _synthesize_name(override: LiveUnboundHostOverride) -> str:
    """Build a resource ``name`` from a live host override.

    Uses the ``<hostname>-<dot-replaced-domain>`` form (mirrors
    ``services.unbound_forward._synthesize_name``) so the result is a
    valid terraform identifier — the template's ``replace('-', '_')``
    filter accepts hyphens but not dots. When ``rr`` is non-default
    (``AAAA`` / ``MX``), the record type is appended as a suffix so an
    A and an AAAA (or MX) record on the same hostname produce distinct
    resource names rather than colliding.

    Falls back gracefully when either part is missing (defensive —
    should not happen in practice but keeps the extractor robust against
    malformed rows).
    """
    parts: list[str] = []
    if override.hostname:
        parts.append(override.hostname)
    if override.domain:
        parts.append(override.domain.replace(".", "-"))
    if override.rr and override.rr != _DEFAULT_RR:
        parts.append(override.rr)
    if not parts:
        return override.uuid.lower()
    return "-".join(parts).lower()


def _live_to_export_config(override: LiveUnboundHostOverride) -> dict[str, Any]:
    """Build a YAML-friendly config dict from a ``LiveUnboundHostOverride``.

    Always emits the base fields (``hostname``, ``domain``, ``enabled``);
    optional fields (``server``, ``description``, ``rr``, ``mxprio``,
    ``mx``) are only emitted when the live record carries a non-default
    value so existing 5-field operator YAML round-trips identically.
    """
    raw = override.raw

    config: dict[str, Any] = {
        "hostname": override.hostname,
        "domain": override.domain,
        "enabled": _normalize_field(raw.get("enabled")) != "0",
    }

    # ``server`` — IPv4 / IPv6 address; commonly absent on MX records.
    server = _normalize_field(raw.get("server"))
    if server:
        config["server"] = server

    # ``description`` — operator note; only emit when non-empty.
    description = _normalize_field(raw.get("description"))
    if description:
        config["description"] = description

    # ``rr`` — record type. Default ``A``; emit only when non-default.
    if override.rr and override.rr != _DEFAULT_RR:
        config["rr"] = override.rr

    # ``mxprio`` / ``mx`` — MX records only; preserved as strings.
    mxprio = _normalize_field(raw.get("mxprio"))
    if mxprio:
        config["mxprio"] = mxprio

    mx = _normalize_field(raw.get("mx"))
    if mx:
        config["mx"] = mx

    return config
