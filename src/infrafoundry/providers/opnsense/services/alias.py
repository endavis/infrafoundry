"""Alias service for OPNsense direct-API operations (ADR-0014, #747, #775).

Manages OPNsense firewall aliases via the ``firewall/alias/*`` controller.
Identity is the natural-key alias ``name`` — OPNsense enforces uniqueness
across aliases server-side, so two aliases with the same ``name`` are the
same record by the diff engine. Updating ``name`` is a delete + add (the
tuple no longer matches anything in YAML and a new tuple appears with no
live counterpart). The operator-facing YAML ``name`` and ``config.name``
are required to agree on extraction (the migrate output writes both
identically); the operator can rename freely after import — the diff
engine uses ``config.name`` (the wire identity) as the diff key.

Endpoint surface (the ``firewall/alias`` controller in OPNsense 26.x;
re-confirmed live on ``opnsense-a`` running ``26.1.6_2``):

- ``POST firewall/alias/searchItem`` — list rows for the dataTable view.
  Response shape ``{"rows": [...], "rowCount": N, "current": 1, "total": N}``.
  Each row exposes flat ``name``, ``type`` (selected dict), ``description``,
  ``content`` (newline-separated string), ``enabled`` (string ``"0"``/``"1"``),
  ``proto`` (selected dict; geoip only), ``updatefreq`` (string; urltable),
  ``categories`` (selected-dict map of UUIDs), ``counters`` (string), and
  ``interface`` (selected dict; dynipv6host only).
- ``GET  firewall/alias/getItem/<uuid>`` — full record under
  ``{"alias": {...}}`` envelope, with ``type`` / ``proto`` / ``interface``
  rendered as option dicts. Used by the migrate path's per-alias fetch.
- ``POST firewall/alias/addItem`` — body envelope ``{"alias": {...}}``;
  response ``{"result": "saved", "uuid": "..."}`` on success or
  ``{"result": "failed", "validations": {<field>: <message>}}`` on
  server-side validation failure.
- ``POST firewall/alias/setItem/<uuid>`` — same body envelope as add.
- ``POST firewall/alias/delItem/<uuid>`` — response
  ``{"result": "deleted"}``.
- ``POST firewall/alias/reconfigure`` — typed response
  ``{"status": "ok"|"failed"}``.

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

Both categories are silently filtered from ``export_to_yaml`` output and
also from the diff engine's view of live state — including them would
produce spurious "delete" entries for aliases the operator can neither
write nor remove.

Wire ↔ YAML schema (preserved from #747; identical for read and write):

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

YAML→wire translation rules (write path; #775):

- ``content``: YAML list → ``"\\n"``-joined string on the wire (the form
  ``addItem`` accepts).
- ``enabled``: YAML bool → ``"0"`` / ``"1"`` string.
- ``counters``: YAML bool → ``"0"`` / ``"1"`` string. Always serialized
  (default ``"0"``) so the diff engine compares apples to apples.
- ``categories``: YAML list of UUIDs → comma-separated string on the wire
  (``addItem`` accepts a comma string for multi-select multi-value
  fields; the search response renders them as a select-dict on read).
- ``type`` / ``proto`` / ``interface`` / ``updatefreq``: pass-through
  strings (``addItem`` accepts the bare value; ``searchItem`` echoes it
  back as a select-dict on read).

Identity contract recap:

- Two aliases with the same ``name`` are the same record by the diff
  engine. Updating ``type`` / ``content`` / ``description`` / etc. is an
  in-place ``setItem`` (preserves UUID); updating ``name`` is a delete +
  add.
- Operator-facing top-level YAML ``name`` and ``config.name`` agree on
  extraction (the migrate output writes both identically). The diff
  engine reads ``config.name`` as the wire identity; the top-level
  ``name`` is operator metadata used for ``ResourceOutcome.address``.
- ``lock: true`` is honored: locked entries appear in ``Diff.locked``
  and are never added, updated, or deleted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from infrafoundry.core.provider import ResourceConfig

from .base import BaseService

# Controller base for all alias CRUD + reconfigure endpoints.
_ALIAS_BASE = "firewall/alias"

# Alias types that OPNsense maintains internally and that the operator
# cannot create / edit / delete via the public alias controller. Filtered
# from both ``export_to_yaml`` output and the live-state view used by the
# diff engine — including them in either place produces spurious deletes
# and breaks idempotency.
_SYSTEM_ALIAS_TYPES: frozenset[str] = frozenset({"internal", "external"})


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AliasConfig:
    """Desired-state firewall alias configuration.

    The operator-facing top-level YAML ``name`` and the ``config.name``
    field agree on extraction (the migrate output writes both identically).
    The diff engine matches on the wire ``name`` (OPNsense-enforced
    unique). The class-level ``name`` field here is the wire identity;
    operators who prefer divergent metadata names can rename the
    top-level ``name`` after import without touching ``config.name``.

    ``lock`` is a per-resource safety annotation (ADR-0014 §6) — locked
    entries appear in ``Diff.locked`` but are never added, updated, or
    deleted.

    Attributes:
        name: Alias name (wire identity, OPNsense-enforced unique).
        type: Alias type (host / network / port / url / urltable /
            urltable_ports / geoip / networkgroup / mac / asn / bgpasn /
            dynipv6host / openvpn / authgroup / etc.).
        description: Operator-facing free-form description.
        content: Type-specific list of values (IPs, CIDRs, ports, URLs,
            country codes, etc.).
        enabled: Whether the alias is active.
        proto: ``IPv4`` / ``IPv6`` for geoip; empty otherwise.
        updatefreq: Refresh frequency in days (urltable family).
        categories: Sorted list of OPNsense category UUIDs.
        counters: Emit pf counters for this alias.
        interface: Interface name for dynipv6host.
        lock: Per-resource safety annotation (ADR-0014 §6).
    """

    name: str
    type: str
    description: str = ""
    content: tuple[str, ...] = ()
    enabled: bool = True
    proto: str = ""
    updatefreq: str = ""
    categories: tuple[str, ...] = ()
    counters: bool = False
    interface: str = ""
    lock: bool = False

    @property
    def diff_key(self) -> str:
        """Identity of this alias: the wire ``name`` (OPNsense-enforced unique)."""
        return self.name

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the ``addItem``/``setItem`` envelope.

        Returns:
            ``{"alias": {<fields>}}``. Booleans stringified to
            ``"0"``/``"1"``; tuples joined to the wire's expected
            shapes (newlines for ``content``, commas for ``categories``).
            Empty optional fields are sent as empty strings to make the
            update-detection symmetric with the live record.
        """
        return {
            "alias": {
                "name": self.name,
                "type": self.type,
                "description": self.description,
                "content": "\n".join(self.content),
                "enabled": _bool_str(self.enabled),
                "proto": self.proto,
                "updatefreq": self.updatefreq,
                "categories": ",".join(self.categories),
                "counters": _bool_str(self.counters),
                "interface": self.interface,
            }
        }


@dataclass(frozen=True)
class LiveAlias:
    """An alias as currently configured on the OPNsense box.

    ``raw`` is the ``searchItem`` row, which carries every field needed
    to compute the diff against a desired ``AliasConfig`` without an
    extra ``getItem`` round-trip — verified empirically on
    ``opnsense-a`` running ``26.1.6_2``.

    Attributes:
        uuid: OPNsense-assigned UUID for the alias.
        name: Alias name (OPNsense-enforced unique across aliases).
        type: Alias type (normalized from the wire's selected-dict).
        raw: Full original ``searchItem`` row.
    """

    uuid: str
    name: str
    type: str
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def diff_key(self) -> str:
        """Identity of this alias: the wire ``name`` (OPNsense-enforced unique)."""
        return self.name


@dataclass
class Diff:
    """Result of comparing desired YAML state to live OPNsense state.

    Mirrors ``services.unbound_host_alias.Diff``: adds / updates /
    deletes / locked, plus ``is_empty``. Updates carry the live record
    alongside the desired record so the caller has the UUID. Locked
    entries pair desired YAML with their (possibly missing) live record.
    """

    adds: list[AliasConfig] = field(default_factory=list)
    updates: list[tuple[LiveAlias, AliasConfig]] = field(default_factory=list)
    deletes: list[LiveAlias] = field(default_factory=list)
    locked: list[tuple[AliasConfig, LiveAlias | None]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there are no add/update/delete operations to apply."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def compute_diff(
    desired: list[AliasConfig],
    current: list[LiveAlias],
    *,
    add_only: bool = False,
) -> Diff:
    """Compare desired YAML state to live state, keyed by alias ``name``.

    System aliases (``type: internal`` / ``type: external``) are filtered
    from ``current`` here so they never appear as deletes or updates —
    the operator can neither write nor remove them, and including them
    in the diff would break idempotency on every apply.

    Args:
        desired: Aliases the operator wants to exist.
        current: Aliases currently on the box.
        add_only: If True, never emit deletes for live aliases that don't
            appear in ``desired``. Adds and updates still happen.

    Returns:
        ``Diff`` with adds / updates / deletes plus locked entries.
    """
    desired_by_key: dict[str, AliasConfig] = {a.diff_key: a for a in desired}
    current_by_key: dict[str, LiveAlias] = {
        a.diff_key: a for a in current if a.type not in _SYSTEM_ALIAS_TYPES
    }
    locked_keys: set[str] = {a.diff_key for a in desired if a.lock}

    adds: list[AliasConfig] = []
    updates: list[tuple[LiveAlias, AliasConfig]] = []
    deletes: list[LiveAlias] = []
    locked: list[tuple[AliasConfig, LiveAlias | None]] = []

    for key, want in desired_by_key.items():
        have = current_by_key.get(key)
        if want.lock:
            locked.append((want, have))
            continue
        if have is None:
            adds.append(want)
        elif _needs_update(have, want):
            updates.append((have, want))

    if not add_only:
        for key, have in current_by_key.items():
            if key in locked_keys:
                continue
            if key not in desired_by_key:
                deletes.append(have)

    return Diff(adds=adds, updates=updates, deletes=deletes, locked=locked)


def _needs_update(have: LiveAlias, want: AliasConfig) -> bool:
    """Return True if the live row differs from the desired payload.

    Compares each field independently against the appropriate wire
    representation on ``have.raw`` — ``searchItem`` returns ``type`` /
    ``proto`` / ``interface`` as select-dicts and ``categories`` as a
    selected-dict map, so we use the same normalization helpers the read
    path uses (``_normalize_field``, ``_split_content``,
    ``_selected_uuids``) instead of the trivial string-vs-string compare
    that other simpler resources can get away with.
    """
    raw = have.raw

    if want.type != _normalize_field(raw.get("type")):
        return True
    if want.description != _normalize_field(raw.get("description")):
        return True
    if list(want.content) != _split_content(raw.get("content")):
        return True
    if _bool_str(want.enabled) != _normalize_field(raw.get("enabled")):
        return True
    if want.proto != _normalize_field(raw.get("proto")):
        return True
    if want.updatefreq != _normalize_field(raw.get("updatefreq")):
        return True
    if list(want.categories) != _selected_uuids(raw.get("categories")):
        return True
    if _bool_str(want.counters) != _normalize_field(raw.get("counters")):
        return True
    return want.interface != _normalize_field(raw.get("interface"))


# ---------------------------------------------------------------------------
# Resource-to-domain conversion
# ---------------------------------------------------------------------------


def alias_configs_from_resources(
    resources: list[ResourceConfig],
) -> list[AliasConfig]:
    """Convert ``ResourceConfig`` entries to ``AliasConfig`` instances.

    Validation here is intentionally minimal — the validator handles
    cross-field semantics (per-type content shape, name charset) and
    operator-friendly error messages; this parser only enforces type
    sanity so manager code can rely on field invariants.

    The diff engine keys on the *wire* identity ``config.name``, not
    the operator-facing top-level ``ResourceConfig.name``. The migrate
    output writes both identically, so the operator can rename the
    top-level name freely after import; ``config.name`` is what the
    diff engine cares about and what travels on the wire.

    Args:
        resources: All provider resources from a ConfigManager load.
            Non-``aliases`` entries are silently skipped.

    Returns:
        Validated ``AliasConfig`` list.

    Raises:
        ValueError: If an entry has a non-dict config, missing required
            fields, or non-bool booleans / non-string fields.
    """
    configs: list[AliasConfig] = []
    for resource in resources:
        if resource.type != "firewall.aliases":
            continue

        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"alias '{resource.name}' has non-dict config")

        # ``config.name`` is the wire identity; fall back to the
        # operator-facing top-level name when omitted (post-migrate the
        # two agree, but operators may drop ``config.name`` to lean on
        # the top-level value).
        wire_name = config.get("name", resource.name)
        if not isinstance(wire_name, str) or not wire_name:
            raise ValueError(
                f"alias '{resource.name}' requires a non-empty string 'name' "
                f"(or a non-empty top-level resource name)"
            )

        alias_type = config.get("type", "")
        if not isinstance(alias_type, str) or not alias_type:
            raise ValueError(f"alias '{resource.name}' requires a non-empty string 'type'")

        description = config.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"alias '{resource.name}' description must be a string")

        content_raw = config.get("content", [])
        if not isinstance(content_raw, list):
            raise ValueError(f"alias '{resource.name}' content must be a list")
        content: list[str] = []
        for item in content_raw:
            if not isinstance(item, str):
                raise ValueError(
                    f"alias '{resource.name}' content entries must be strings, "
                    f"got {type(item).__name__}"
                )
            content.append(item)

        proto = config.get("proto", "")
        if not isinstance(proto, str):
            raise ValueError(f"alias '{resource.name}' proto must be a string")

        updatefreq = config.get("updatefreq", "")
        if not isinstance(updatefreq, str):
            raise ValueError(f"alias '{resource.name}' updatefreq must be a string")

        categories_raw = config.get("categories", [])
        if not isinstance(categories_raw, list):
            raise ValueError(f"alias '{resource.name}' categories must be a list")
        categories: list[str] = []
        for cat in categories_raw:
            if not isinstance(cat, str):
                raise ValueError(
                    f"alias '{resource.name}' categories entries must be strings, "
                    f"got {type(cat).__name__}"
                )
            categories.append(cat)

        interface = config.get("interface", "")
        if not isinstance(interface, str):
            raise ValueError(f"alias '{resource.name}' interface must be a string")

        enabled = _require_bool(config, "enabled", default=True, resource_name=resource.name)
        counters = _require_bool(config, "counters", default=False, resource_name=resource.name)
        lock = _require_bool(config, "lock", default=False, resource_name=resource.name)

        configs.append(
            AliasConfig(
                name=wire_name,
                type=alias_type,
                description=description,
                content=tuple(content),
                enabled=enabled,
                proto=proto,
                updatefreq=updatefreq,
                categories=tuple(categories),
                counters=counters,
                interface=interface,
                lock=lock,
            )
        )

    return configs


def _require_bool(
    config: dict[str, Any], field_name: str, *, default: bool, resource_name: str
) -> bool:
    value = config.get(field_name, default)
    if not isinstance(value, bool):
        raise ValueError(
            f"alias '{resource_name}' {field_name} must be a boolean (true/false), "
            f"got {type(value).__name__}"
        )
    return value


def _bool_str(value: bool) -> str:
    """Convert a Python bool to OPNsense's ``"0"``/``"1"`` representation."""
    return "1" if value else "0"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AliasService(BaseService):
    """Service for OPNsense alias operations via direct API.

    Single controller, single endpoint family — no per-kind dispatch.
    Identity is the natural-key alias ``name``, so the diff engine
    matches operator YAML directly to live records by name.
    """

    # ------------------------------------------------------------------
    # API operations (CRUD + reconfigure)
    # ------------------------------------------------------------------

    def search(self) -> list[LiveAlias]:
        """Fetch the live alias list.

        Returns:
            ``LiveAlias`` instances normalized from the ``searchItem``
            rows. Defensive against non-dict responses and missing
            ``rows`` key — both yield ``[]``.
        """
        response = self.client.request("POST", f"{_ALIAS_BASE}/searchItem")

        rows: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw_rows = response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]

        return [_row_to_live(row) for row in rows]

    def get(self, uuid: str) -> dict[str, Any]:
        """Fetch the full alias record by UUID.

        Returns the raw envelope ``{"alias": {...}}`` — used for parity
        with peer services (`unbound_host_alias`, `static_route`); the
        diff engine reads everything from the ``searchItem`` row.
        """
        return self.client.request("GET", f"{_ALIAS_BASE}/getItem/{uuid}")

    def add(self, alias: AliasConfig) -> dict[str, Any]:
        """Create an alias.

        Args:
            alias: Desired-state alias configuration.

        Returns:
            API response dict (typically ``{"result": "saved", "uuid": ...}``).
        """
        return self.client.request(
            "POST",
            f"{_ALIAS_BASE}/addItem",
            data=alias.to_payload(),
        )

    def update(self, uuid: str, alias: AliasConfig) -> dict[str, Any]:
        """Update an existing alias by UUID.

        Args:
            uuid: OPNsense-assigned alias UUID.
            alias: New desired-state configuration.

        Returns:
            API response dict.
        """
        return self.client.request(
            "POST",
            f"{_ALIAS_BASE}/setItem/{uuid}",
            data=alias.to_payload(),
        )

    def delete(self, uuid: str) -> dict[str, Any]:
        """Delete an alias by UUID.

        Args:
            uuid: OPNsense-assigned alias UUID.

        Returns:
            API response dict (typically ``{"result": "deleted"}``).
        """
        return self.client.request("POST", f"{_ALIAS_BASE}/delItem/{uuid}")

    def reconfigure(self) -> dict[str, Any]:
        """Apply pending alias changes (commit staged config to running system).

        Must be called after add/update/delete operations to activate them.
        Response shape per the OpenAPI spec is ``{"status": "ok" | "failed"}``.
        """
        return self.client.request("POST", f"{_ALIAS_BASE}/reconfigure")

    # ------------------------------------------------------------------
    # Diff + apply orchestration
    # ------------------------------------------------------------------

    def compute_diff(
        self,
        desired: list[AliasConfig],
        live: list[LiveAlias],
        *,
        add_only: bool = False,
    ) -> Diff:
        """Compute the add/update/delete diff between desired and live state.

        Thin wrapper over the module-level ``compute_diff`` for callers
        that prefer the service-method form.
        """
        return compute_diff(desired, live, add_only=add_only)

    def apply_diff(self, diff: Diff) -> dict[str, int]:
        """Dispatch the operations described by ``diff``, then reconfigure.

        Returns:
            Counts of operations actually performed:
            ``{"created": N, "updated": M, "deleted": K}``. ``reconfigure``
            is called once at the end if any mutation happened.
        """
        created = 0
        updated = 0
        deleted = 0

        for alias in diff.adds:
            self.add(alias)
            created += 1

        for live, want in diff.updates:
            self.update(live.uuid, want)
            updated += 1

        for live in diff.deletes:
            self.delete(live.uuid)
            deleted += 1

        if created or updated or deleted:
            self.reconfigure()

        return {"created": created, "updated": updated, "deleted": deleted}

    # ------------------------------------------------------------------
    # Migration / export
    # ------------------------------------------------------------------

    def export_to_yaml(self) -> str:
        """Export the current alias configuration to InfraFoundry YAML.

        Aliases whose ``type`` is ``internal`` or ``external`` are
        silently skipped — those are OPNsense system-internal entries
        (``__lan_network``, ``bogons``, etc.) that the operator cannot
        write via the alias controller. Including them would produce
        YAML that the direct-API write path would attempt to (re)create
        on apply.

        For each remaining live alias the ``searchItem`` row already
        carries every field we need (no extra ``getItem`` round-trip
        required — verified empirically). Operator-facing ``name`` is
        the alias name verbatim; the operator can rename after import
        (the diff engine keys on ``config.name``, not the top-level
        ``name``).

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
    in ``_live_to_export_config`` and in the diff engine.
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
