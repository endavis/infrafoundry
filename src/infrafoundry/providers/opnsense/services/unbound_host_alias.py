"""Unbound host-alias service for OPNsense direct-API operations (ADR-0014, #724).

Manages OPNsense Unbound DNS host aliases via the
``unbound/settings/{search,get,add,set,del,toggle}HostAlias`` controller. A
host alias attaches an extra ``hostname.domain`` label to an existing
``unbound_host_override`` record so the override's IP answers for additional
DNS names without duplicating the override entry.

Identity is the natural-key tuple ``(host_uuid, hostname)`` at the wire — at
the API level the alias is keyed by the parent override's UUID and the alias
hostname. The operator-facing YAML uses ``(host_name, hostname)`` (where
``host_name`` is the operator's own resource name for a managed
``unbound_host_override`` resource); the component manager resolves
``host_name`` to ``host_uuid`` at apply time by reading
``searchHostOverride`` rows. ``host_uuid`` is *not* exposed in YAML.

Endpoint surface (confirmed live on ``opnsense-a`` running ``26.1.6_2``,
2026-05-04 probe):

- ``POST unbound/settings/searchHostAlias`` — list rows for the dataTable view.
  Response shape ``{"rows": [...], "rowCount": N, "total": N, "current": 1}``;
  rows expose the parent ``host`` UUID (selected key) plus a flat
  ``hostname``/``domain``/``description``/``enabled`` columns.
- ``GET  unbound/settings/getHostAlias/<uuid>`` — full record under
  ``{"alias": {...}}`` envelope, with ``host`` rendered as an option dict
  (``{<parent_uuid>: {"value": "...", "selected": 0|1}, ...}``).
- ``POST unbound/settings/addHostAlias`` — body envelope ``{"alias": {...}}``;
  response ``{"result": "saved", "uuid": "..."}`` on success or
  ``{"result": "failed", "validations": {<field>: <message>}}`` on
  server-side validation failure.
- ``POST unbound/settings/setHostAlias/<uuid>`` — same body envelope as add.
- ``POST unbound/settings/delHostAlias/<uuid>`` — response ``{"result": "deleted"}``.
- ``POST unbound/settings/toggleHostAlias/<uuid>`` — flips ``enabled``
  (not used by this service; operator-facing ``enabled`` is set via
  add/set instead).
- ``POST unbound/service/reconfigure`` — typed response
  ``{"status": "ok"|"failed"}``.

Field schema (probe-derived, recorded here so a follow-up doesn't need to
re-probe). All write fields are simple strings on the wire:

- Required: ``host`` (parent override UUID), ``hostname`` (label),
  ``domain`` (parent override's domain).
- Booleans serialized as ``"0"``/``"1"`` strings: ``enabled``.
- Strings: ``description``.

The wire surface here mirrors what the OPNsense GUI's "Aliases for host
overrides → Add" form exposes; no extra knobs.

Identity contract recap:

- Two aliases with the same ``(host_uuid, hostname)`` tuple are the same
  record by the diff engine; updating either of those fields is a delete
  + add. Updating ``description``, ``domain``, or ``enabled`` only is an
  in-place ``setHostAlias`` (preserves UUID).
- Operator-facing YAML ``name`` is metadata only — used for
  ``ResourceOutcome.address``-style addressing — and is never sent on the
  wire as identity.
- ``lock: true`` is honored: locked entries appear in ``Diff.locked`` and
  are never added, updated, or deleted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from infrafoundry.core.provider import ResourceConfig

from .base import BaseService

# Controller base for all host-alias CRUD endpoints.
_HOST_ALIAS_BASE = "unbound/settings"
# The Unbound service's reconfigure verb is shared across every
# Unbound-managed component (host overrides / aliases / forwards).
_RECONFIGURE_PATH = "unbound/service/reconfigure"


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnboundHostAliasConfig:
    """Desired-state Unbound host-alias configuration.

    The operator-facing YAML ``name`` is metadata only — used for
    ``ResourceOutcome`` addresses — and never travels on the wire. The
    diff engine matches on the natural-key tuple ``(host_uuid, hostname)``,
    where ``host_uuid`` is resolved from ``host_name`` at apply time by the
    component manager.

    ``lock`` is a per-resource safety annotation (ADR-0014 §6) — locked
    entries appear in ``Diff.locked`` but are never added, updated, or
    deleted.

    Attributes:
        name: Operator-facing YAML name; metadata only.
        host_name: Operator-facing reference to a managed
            ``unbound_host_override`` resource name (or a live override
            hostname); resolved to ``host_uuid`` at apply time.
        host_uuid: Parent host_override's UUID. Empty until the manager
            resolves it from ``host_name``.
        hostname: The alias's leftmost label.
        domain: The alias's parent domain (matches the override's domain).
        enabled: Whether the alias is active.
        description: Operator-facing free-form description.
        lock: Per-resource safety annotation (ADR-0014 §6).
    """

    name: str
    host_name: str
    hostname: str
    domain: str
    host_uuid: str = ""
    enabled: bool = True
    description: str = ""
    lock: bool = False

    @property
    def diff_key(self) -> tuple[str, str]:
        """Identity of this alias: the ``(host_uuid, hostname)`` tuple."""
        return (self.host_uuid, self.hostname)

    def with_host_uuid(self, host_uuid: str) -> UnboundHostAliasConfig:
        """Return a copy with the resolved ``host_uuid`` set.

        Used by the component manager once it has resolved the operator-
        facing ``host_name`` to the parent override's UUID via
        ``searchHostOverride``.

        Args:
            host_uuid: The resolved UUID for the parent override.

        Returns:
            A new ``UnboundHostAliasConfig`` with ``host_uuid`` replaced.
        """
        return UnboundHostAliasConfig(
            name=self.name,
            host_name=self.host_name,
            hostname=self.hostname,
            domain=self.domain,
            host_uuid=host_uuid,
            enabled=self.enabled,
            description=self.description,
            lock=self.lock,
        )

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the ``addHostAlias``/``setHostAlias`` envelope.

        Returns:
            ``{"alias": {<fields>}}``. Booleans are stringified to
            ``"0"``/``"1"`` (``enabled`` stays as ``enabled`` on the wire,
            unlike the static-route's inverted ``disabled``). The
            operator-facing ``name`` is intentionally NOT sent — it is
            metadata only.
        """
        return {
            "alias": {
                "host": self.host_uuid,
                "hostname": self.hostname,
                "domain": self.domain,
                "enabled": _bool_str(self.enabled),
                "description": self.description,
            }
        }


@dataclass(frozen=True)
class LiveUnboundHostAlias:
    """An Unbound host alias as currently configured on the OPNsense box.

    ``raw`` is the ``searchHostAlias`` row, which exposes the parent
    ``host`` UUID (selected key, not the option dict) plus
    ``hostname``/``domain``/``description``/``enabled`` flat columns. The
    ``getHostAlias`` envelope is read separately during ``export_to_yaml``
    to recover the option-dict-rendered ``host`` field.

    Attributes:
        uuid: OPNsense-assigned UUID for the alias.
        host_uuid: Parent host_override's UUID (the selected key from the
            row's ``host`` field).
        hostname: The alias's leftmost label.
        raw: Full original ``searchHostAlias`` row for field comparison
            during update detection.
    """

    uuid: str
    host_uuid: str
    hostname: str
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def diff_key(self) -> tuple[str, str]:
        """Identity of this alias: the ``(host_uuid, hostname)`` tuple."""
        return (self.host_uuid, self.hostname)


@dataclass
class Diff:
    """Result of comparing desired YAML state to live OPNsense state.

    Mirrors ``services.static_route.Diff``: adds / updates / deletes /
    locked, plus ``is_empty``. Updates carry the live record alongside
    the desired record so the caller has the UUID. Locked entries pair
    desired YAML with their (possibly missing) live record.

    Note that changing ``host_name`` (which resolves to ``host_uuid``) or
    ``hostname`` on a YAML resource produces a delete + add, not an update —
    the live record's tuple no longer matches anything in YAML and a new
    tuple appears with no live counterpart.
    """

    adds: list[UnboundHostAliasConfig] = field(default_factory=list)
    updates: list[tuple[LiveUnboundHostAlias, UnboundHostAliasConfig]] = field(default_factory=list)
    deletes: list[LiveUnboundHostAlias] = field(default_factory=list)
    locked: list[tuple[UnboundHostAliasConfig, LiveUnboundHostAlias | None]] = field(
        default_factory=list
    )

    @property
    def is_empty(self) -> bool:
        """Return True if there are no add/update/delete operations to apply."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def compute_diff(
    desired: list[UnboundHostAliasConfig],
    current: list[LiveUnboundHostAlias],
    *,
    add_only: bool = False,
) -> Diff:
    """Compare desired YAML state to live state, keyed by ``(host_uuid, hostname)``.

    Args:
        desired: Aliases the operator wants to exist. Each must already
            have ``host_uuid`` resolved by the component manager.
        current: Aliases currently on the box.
        add_only: If True, never emit deletes for live aliases that don't
            appear in ``desired``. Adds and updates still happen.

    Returns:
        ``Diff`` with adds / updates / deletes plus locked entries.
    """
    desired_by_key: dict[tuple[str, str], UnboundHostAliasConfig] = {a.diff_key: a for a in desired}
    current_by_key: dict[tuple[str, str], LiveUnboundHostAlias] = {a.diff_key: a for a in current}
    locked_keys: set[tuple[str, str]] = {a.diff_key for a in desired if a.lock}

    adds: list[UnboundHostAliasConfig] = []
    updates: list[tuple[LiveUnboundHostAlias, UnboundHostAliasConfig]] = []
    deletes: list[LiveUnboundHostAlias] = []
    locked: list[tuple[UnboundHostAliasConfig, LiveUnboundHostAlias | None]] = []

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


def _needs_update(have: LiveUnboundHostAlias, want: UnboundHostAliasConfig) -> bool:
    """Return True if the live row's fields differ from the desired payload.

    Compares the inner ``alias`` payload from ``want.to_payload()`` against
    the corresponding fields on ``have.raw``. ``searchHostAlias`` returns
    ``host`` as a flat string (the selected option key) — same shape as
    ``want.to_payload()`` — so ``_normalize_field`` is mostly pass-through,
    but it keeps update detection robust if the API surface changes.
    """
    payload = want.to_payload()["alias"]
    for key, want_value in payload.items():
        have_value = _normalize_field(have.raw.get(key))
        if str(want_value) != have_value:
            return True
    return False


def _normalize_field(value: Any) -> str:
    """Collapse an OPNsense field value to a comparable string.

    Booleans are serialized as ``"1"`` / ``"0"`` to match what we'd send.
    Select fields returned as option dicts (from ``getHostAlias``) extract
    the selected key. Plain scalars are stringified verbatim. ``None``
    becomes ``""``.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, dict):
        for option_key, option_value in value.items():
            if isinstance(option_value, dict) and option_value.get("selected"):
                return str(option_key)
        return ""
    return str(value)


# ---------------------------------------------------------------------------
# Resource-to-domain conversion
# ---------------------------------------------------------------------------


def unbound_host_alias_configs_from_resources(
    resources: list[ResourceConfig],
) -> list[UnboundHostAliasConfig]:
    """Convert ``ResourceConfig`` entries to ``UnboundHostAliasConfig`` instances.

    Validation here is intentionally minimal — the validator handles
    cross-resource references (host ref) and operator-friendly error
    messages; this parser only enforces type sanity so manager code can
    rely on field invariants.

    Args:
        resources: All provider resources from a ConfigManager load.
            Non-``unbound_host_alias`` entries are silently skipped.

    Returns:
        Validated ``UnboundHostAliasConfig`` list. Each instance has an
        empty ``host_uuid`` — the component manager resolves it to a real
        UUID at apply time.

    Raises:
        ValueError: If an entry has a non-dict config, missing required
            fields, or non-bool booleans / non-string fields.
    """
    configs: list[UnboundHostAliasConfig] = []
    for resource in resources:
        if resource.type != "unbound_host_alias":
            continue

        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"unbound_host_alias '{resource.name}' has non-dict config")

        host_name = config.get("host", "")
        if not isinstance(host_name, str) or not host_name:
            raise ValueError(
                f"unbound_host_alias '{resource.name}' requires a non-empty string 'host'"
            )

        hostname = config.get("hostname", "")
        if not isinstance(hostname, str) or not hostname:
            raise ValueError(
                f"unbound_host_alias '{resource.name}' requires a non-empty string 'hostname'"
            )

        domain = config.get("domain", "")
        if not isinstance(domain, str) or not domain:
            raise ValueError(
                f"unbound_host_alias '{resource.name}' requires a non-empty string 'domain'"
            )

        description = config.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"unbound_host_alias '{resource.name}' description must be a string")

        enabled = _require_bool(config, "enabled", default=True, resource_name=resource.name)
        lock = _require_bool(config, "lock", default=False, resource_name=resource.name)

        configs.append(
            UnboundHostAliasConfig(
                name=resource.name,
                host_name=host_name,
                hostname=hostname,
                domain=domain,
                enabled=enabled,
                description=description,
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
            f"unbound_host_alias '{resource_name}' {field_name} must be a boolean (true/false), "
            f"got {type(value).__name__}"
        )
    return value


def _bool_str(value: bool) -> str:
    """Convert a Python bool to OPNsense's ``"0"``/``"1"`` representation."""
    return "1" if value else "0"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class UnboundHostAliasService(BaseService):
    """Service for OPNsense Unbound host-alias operations via direct API.

    Identity is the natural-key ``(host_uuid, hostname)`` tuple — the
    diff engine matches operator YAML directly to live records by tuple.
    The operator-facing ``name`` never travels on the wire, and
    ``host_name`` is resolved to ``host_uuid`` by the component manager
    before the service ever sees the config.
    """

    # ------------------------------------------------------------------
    # API operations (CRUD + reconfigure)
    # ------------------------------------------------------------------

    def search(self) -> list[LiveUnboundHostAlias]:
        """Fetch the live host-alias list.

        Returns:
            ``LiveUnboundHostAlias`` instances normalized from the search rows.
        """
        response = self.client.request("POST", f"{_HOST_ALIAS_BASE}/searchHostAlias")

        rows: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw_rows = response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]

        return [_row_to_live(row) for row in rows]

    def get(self, uuid: str) -> dict[str, Any]:
        """Fetch the full host-alias record by UUID.

        Used by ``export_to_yaml`` to read the option-dict-rendered ``host``
        field that ``searchHostAlias`` doesn't expose. Returns the raw
        envelope ``{"alias": {...}}``.
        """
        return self.client.request("GET", f"{_HOST_ALIAS_BASE}/getHostAlias/{uuid}")

    def add(self, alias: UnboundHostAliasConfig) -> dict[str, Any]:
        """Create a host alias.

        Args:
            alias: Desired-state host-alias configuration with
                ``host_uuid`` already resolved.

        Returns:
            API response dict (typically ``{"result": "saved", "uuid": ...}``).
        """
        return self.client.request(
            "POST",
            f"{_HOST_ALIAS_BASE}/addHostAlias",
            data=alias.to_payload(),
        )

    def update(self, uuid: str, alias: UnboundHostAliasConfig) -> dict[str, Any]:
        """Update an existing host alias by UUID.

        Args:
            uuid: OPNsense-assigned alias UUID.
            alias: New desired-state configuration with ``host_uuid``
                already resolved.

        Returns:
            API response dict.
        """
        return self.client.request(
            "POST",
            f"{_HOST_ALIAS_BASE}/setHostAlias/{uuid}",
            data=alias.to_payload(),
        )

    def delete(self, uuid: str) -> dict[str, Any]:
        """Delete a host alias by UUID.

        Args:
            uuid: OPNsense-assigned alias UUID.

        Returns:
            API response dict (typically ``{"result": "deleted"}``).
        """
        return self.client.request("POST", f"{_HOST_ALIAS_BASE}/delHostAlias/{uuid}")

    def reconfigure(self) -> dict[str, Any]:
        """Apply pending Unbound changes (commit staged config to running system).

        Must be called after add/update/delete operations to activate them.
        Response shape per the OpenAPI spec is ``{"status": "ok" | "failed"}``.
        """
        return self.client.request("POST", _RECONFIGURE_PATH)

    def search_host_overrides(self) -> list[dict[str, Any]]:
        """Fetch the live host-override rows for ``host_name`` → UUID resolution.

        Returns:
            Raw ``searchHostOverride`` rows; each carries at least a
            ``uuid``, ``hostname``, and ``domain`` column.
        """
        response = self.client.request("POST", f"{_HOST_ALIAS_BASE}/searchHostOverride")
        rows: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw_rows = response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]
        return rows

    # ------------------------------------------------------------------
    # Diff + apply orchestration
    # ------------------------------------------------------------------

    def compute_diff(
        self,
        desired: list[UnboundHostAliasConfig],
        live: list[LiveUnboundHostAlias],
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
        """Export the current host-alias configuration to InfraFoundry YAML.

        For each live alias we issue a ``getHostAlias/<uuid>`` to capture
        the option-dict-rendered ``host`` field at full fidelity, and
        cross-reference parent overrides by UUID via ``searchHostOverride``
        so we can emit a YAML-friendly ``host: <hostname>`` reference
        instead of the raw UUID. Operator-facing ``name`` is synthesized
        from ``(parent_hostname, alias_hostname, domain)`` since OPNsense
        has no name field — the operator can rename freely after import;
        identity is the tuple, not the name.

        Returns:
            YAML string with ``provider/type/name/config`` entries.
        """
        live = self.search()
        # Build a UUID → "hostname.domain" map from the live host-override
        # rows so the export YAML uses a name-shaped reference instead of
        # an opaque UUID. If a parent override is missing we fall back to
        # the UUID string itself.
        host_overrides = self.search_host_overrides()
        uuid_to_label: dict[str, str] = {}
        for row in host_overrides:
            uuid = str(row.get("uuid", ""))
            hostname = str(row.get("hostname", "")) or ""
            domain = str(row.get("domain", "")) or ""
            label = ".".join(part for part in (hostname, domain) if part)
            if uuid:
                uuid_to_label[uuid] = label or uuid

        resources = [
            {
                "provider": "opnsense",
                "type": "unbound_host_alias",
                "name": _synthesize_name(alias),
                "config": _live_to_export_config(self.get(alias.uuid), uuid_to_label),
            }
            for alias in live
        ]
        return yaml.safe_dump({"resources": resources}, sort_keys=False)


# ---------------------------------------------------------------------------
# Internal helpers (row parsing / export)
# ---------------------------------------------------------------------------


def _row_to_live(row: dict[str, Any]) -> LiveUnboundHostAlias:
    """Normalize a ``searchHostAlias`` row into a ``LiveUnboundHostAlias``."""
    uuid = str(row.get("uuid", ""))
    host_uuid = _normalize_field(row.get("host"))
    hostname = str(row.get("hostname", ""))
    return LiveUnboundHostAlias(uuid=uuid, host_uuid=host_uuid, hostname=hostname, raw=row)


def _synthesize_name(alias: LiveUnboundHostAlias) -> str:
    """Build a YAML-friendly synthetic name from a ``LiveUnboundHostAlias``.

    Uses the alias's ``hostname`` plus the parent UUID (truncated for
    readability). The operator can rename after import; identity is the
    tuple, not the name.
    """
    parent_short = alias.host_uuid.split("-")[0] if alias.host_uuid else "unknown"
    return f"alias-{alias.hostname}-{parent_short}".lower()


def _live_to_export_config(
    get_response: dict[str, Any],
    uuid_to_label: dict[str, str],
) -> dict[str, Any]:
    """Build a YAML-friendly config dict from a ``getHostAlias`` envelope.

    Reads the option-dict ``host`` via ``_normalize_field`` to recover
    the selected parent UUID, then maps it to a name-shaped label via
    the ``uuid_to_label`` mapping.

    Args:
        get_response: Raw envelope returned by ``getHostAlias``.
        uuid_to_label: Mapping from parent override UUID to a
            ``hostname.domain`` label, built from
            ``searchHostOverride`` rows.

    Returns:
        Operator-facing config dict (``host``, ``hostname``, ``domain``,
        ``description``, ``enabled``).
    """
    item = get_response.get("alias", {}) if isinstance(get_response, dict) else {}
    host_uuid = _normalize_field(item.get("host"))
    return {
        "host": uuid_to_label.get(host_uuid, host_uuid),
        "hostname": _normalize_field(item.get("hostname")),
        "domain": _normalize_field(item.get("domain")),
        "description": _normalize_field(item.get("description")),
        "enabled": _normalize_field(item.get("enabled")) == "1",
    }
