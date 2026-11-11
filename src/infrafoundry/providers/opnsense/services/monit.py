"""Monit list services for OPNsense direct-API operations (ADR-0014, #791).

Manages the three list types of the core monit module through one table-driven engine:
``monit.alerts``, ``monit.tests`` and ``monit.services``. Each is a
:class:`MonitListSpec`; the singleton ``monit.settings`` has its own service
(:mod:`.monit_settings`). The shape follows :mod:`.acmeclient`, whose field helpers it
imports; the engine pieces whose messages name the plugin are re-implemented here.

Identity
--------

The YAML ``name`` is the cross-reference *handle* (it must not contain ``.``). The wire
identity is:

- services and tests: ``config.service_name`` / ``config.test_name`` when set, else the
  handle (the wire ``name``; stock rows are called ``$HOST``, ``MemoryUsage`` ...);
- alerts: ``config.recipient``, which is required.

A change of identity is a delete plus an add. The loader injects ``name`` into every
list entry's ``config``; it is ignored here.

Wire shape
----------

One read serves all three types: ``GET monit/settings/get`` returns the whole model, with
the ``alert``, ``service`` and ``test`` rows keyed by UUID and option dicts for the
enumerated fields. Writes use ``addX``, ``setX/{uuid}`` and ``delX/{uuid}`` of the
``monit/settings`` controller; the envelope key is ``alert``, ``service`` or ``test``.
There is no per-row ``get`` and no pagination.

Sparse comparison
-----------------

Only declared fields are compared and written. List fields (alert ``events``) and
references compare as sets. References are given as handles and compared once resolved to
live UUIDs: service ``tests`` point to ``monit.tests``, service ``depends`` to
``monit.services``.

Never called
------------

``toggle*``, ``service/start|stop|restart|check`` and ``status/*`` are not registered.

What is verified and what is not
--------------------------------

See ``docs/development/opnsense-resource-coverage.md`` (section "Monit").
"""

from __future__ import annotations

import logging
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

from infrafoundry.core.exceptions import (
    APIError,
    InvalidConfigurationError,
    ReferenceValidationError,
)
from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from ._identity import OpnsenseDriftError
from ._nested_emit import emit_nested_list_yaml
from .acmeclient import (
    BOOL,
    ENUM,
    INT,
    REF,
    REFSET,
    STR,
    FieldSpec,
    next_free_handle,
    serialize_value,
)
from .base import BaseService, raise_on_failed_write
from .openvpn_instances import flatten_option

logger = logging.getLogger(__name__)

#: A list of strings, compared as a set and written in the order given.
LIST = "list"

ALERT_EVENTS: tuple[str, ...] = (
    "action",
    "checksum",
    "bytein",
    "byteout",
    "connection",
    "content",
    "data",
    "exec",
    "fsflags",
    "gid",
    "icmp",
    "instance",
    "invalid",
    "link",
    "nonexist",
    "packetin",
    "packetout",
    "permission",
    "pid",
    "ppid",
    "resource",
    "saturation",
    "size",
    "speed",
    "status",
    "timeout",
    "timestamp",
    "uid",
    "uptime",
)
SERVICE_TYPES: tuple[str, ...] = (
    "process",
    "file",
    "fifo",
    "filesystem",
    "directory",
    "host",
    "system",
    "custom",
    "network",
)
#: Test types as the box spells them (``Permisssion`` has three ``s`` on the wire).
TEST_TYPES: tuple[str, ...] = (
    "Existence",
    "SystemResource",
    "ProcessResource",
    "ProcessDiskIO",
    "FileChecksum",
    "Timestamp",
    "FileSize",
    "FileContent",
    "FilesystemMountFlags",
    "SpaceUsage",
    "InodeUsage",
    "DiskIO",
    "Permisssion",
    "UID",
    "GID",
    "PID",
    "PPID",
    "Uptime",
    "ProgramStatus",
    "NetworkInterface",
    "NetworkPing",
    "Connection",
    "Custom",
)
TEST_ACTIONS: tuple[str, ...] = ("alert", "restart", "start", "stop", "exec", "unmonitor")

#: Service types whose monit syntax cannot render without a ``path``.
PATH_REQUIRED_TYPES: frozenset[str] = frozenset(
    {"filesystem", "custom", "file", "fifo", "directory"}
)


@dataclass(frozen=True)
class MonitListSpec:
    """One monit list type.

    Attributes:
        type_name: Dotted resource type (``monit.tests``).
        sub: List name used in references and messages (``tests``).
        noun: Singular noun for messages (``test``).
        item_key: Model key and write-envelope key (``test``).
        crud: Endpoints of the controller.
        fields: YAML key -> :class:`FieldSpec`, except the identity.
        identity_key: YAML key carrying the wire identity.
        identity_wire: Wire field that holds the identity.
        identity_required: True when the identity has no handle fallback (alerts).
    """

    type_name: str
    sub: str
    noun: str
    item_key: str
    crud: endpoints.CrudEndpoints
    fields: dict[str, FieldSpec]
    identity_key: str
    identity_wire: str
    identity_required: bool = False

    @property
    def meta_keys(self) -> frozenset[str]:
        """Config keys that are not fields: the loader-injected ``name``, ``lock``, identity."""
        return frozenset({"name", "lock", self.identity_key})

    @property
    def allowed_keys(self) -> frozenset[str]:
        """Every legal config key."""
        return self.meta_keys | frozenset(self.fields)

    def accepts(self, key: str) -> bool:
        """Return True when ``key`` is a legal config key of this type."""
        return key in self.allowed_keys


ALERTS = MonitListSpec(
    type_name="monit.alerts",
    sub="alerts",
    noun="alert",
    item_key="alert",
    crud=endpoints.MONIT_ALERT,
    fields={
        "enabled": FieldSpec("enabled", BOOL),
        "noton": FieldSpec("noton", BOOL),
        "events": FieldSpec("events", LIST, ALERT_EVENTS),
        "format": FieldSpec("format", STR),
        "reminder": FieldSpec("reminder", INT),
        "description": FieldSpec("description", STR),
    },
    identity_key="recipient",
    identity_wire="recipient",
    identity_required=True,
)

TESTS = MonitListSpec(
    type_name="monit.tests",
    sub="tests",
    noun="test",
    item_key="test",
    crud=endpoints.MONIT_TEST,
    fields={
        "type": FieldSpec("type", ENUM, TEST_TYPES),
        "condition": FieldSpec("condition", STR),
        "action": FieldSpec("action", ENUM, TEST_ACTIONS),
        "path": FieldSpec("path", STR),
    },
    identity_key="test_name",
    identity_wire="name",
)

SERVICES = MonitListSpec(
    type_name="monit.services",
    sub="services",
    noun="service",
    item_key="service",
    crud=endpoints.MONIT_SERVICE,
    fields={
        "enabled": FieldSpec("enabled", BOOL),
        "description": FieldSpec("description", STR),
        "type": FieldSpec("type", ENUM, SERVICE_TYPES),
        "pidfile": FieldSpec("pidfile", STR),
        "match": FieldSpec("match", STR),
        "path": FieldSpec("path", STR),
        "timeout": FieldSpec("timeout", INT),
        "start_timeout": FieldSpec("starttimeout", INT),
        "address": FieldSpec("address", STR),
        "interface": FieldSpec("interface", STR),
        "start": FieldSpec("start", STR),
        "stop": FieldSpec("stop", STR),
        "tests": FieldSpec("tests", REFSET, ref_sub="tests"),
        "depends": FieldSpec("depends", REFSET, ref_sub="services"),
        "poll_time": FieldSpec("polltime", INT),
    },
    identity_key="service_name",
    identity_wire="name",
)

SPECS: dict[str, MonitListSpec] = {s.sub: s for s in (ALERTS, TESTS, SERVICES)}

#: Migrate order of the list types: dependencies first.
MIGRATE_ORDER: tuple[str, ...] = ("alerts", "tests", "services")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def serialize_field(label: str, key: str, spec: FieldSpec, value: Any) -> str:
    """Serialize one config value to its wire string.

    Extends :func:`.acmeclient.serialize_value` with the ``list`` kind: a list of
    non-empty strings (each in ``spec.choices`` when given), de-duplicated, in the order
    given. ``ref`` and ``refset`` values serialize to their handles.

    Args:
        label: Resource label for error messages.
        key: Config key.
        spec: The key's :class:`FieldSpec`.
        value: The YAML value.

    Returns:
        The wire string.

    Raises:
        ValueError: On a wrong type or out-of-range value; never includes the value.
    """
    if spec.kind != LIST:
        return serialize_value(label, key, spec, value)
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ValueError(f"{label} {key} must be a list of non-empty strings")
    items = [v.strip() for v in value]
    if any("," in v for v in items):
        raise ValueError(f"{label} {key} entries must not contain commas")
    if spec.choices and any(v not in spec.choices for v in items):
        raise ValueError(f"{label} {key} entries must be among {list(spec.choices)}")
    return ",".join(dict.fromkeys(items))


def ref_handle(value: str, sub: str) -> str:
    """Return the handle of a reference to a ``sub`` resource.

    Accepts ``<handle>``, ``<sub>.<handle>`` and ``monit.<sub>.<handle>``.

    Args:
        value: The reference as written in YAML.
        sub: The expected list type (``tests`` or ``services``).

    Returns:
        The handle.

    Raises:
        InvalidConfigurationError: On any other form, a wrong target type or an empty
            handle. The message never includes more than the reference's own text.
    """
    parts = value.split(".")
    if len(parts) == 1:
        handle = parts[0]
    elif len(parts) == 2 and parts[0] == sub:
        handle = parts[1]
    elif len(parts) == 3 and parts[0] == "monit" and parts[1] == sub:
        handle = parts[2]
    else:
        raise InvalidConfigurationError(
            f"reference {value!r} must be '<name>', '{sub}.<name>' or 'monit.{sub}.<name>'"
        )
    if not handle:
        raise InvalidConfigurationError(f"reference {value!r} has an empty name")
    return handle


_CAMEL_LOWER_UPPER = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_CAMEL_ACRONYM = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_LETTER_DIGIT = re.compile(r"(?<=[A-Za-z])(?=[0-9])")
_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")


def kebab_handle(text: str) -> str:
    """Return a wire name as a kebab-case handle.

    CamelCase boundaries and letter-to-digit boundaries are split, every other run of
    non-alphanumerics becomes ``-``, and the result is lowercased. ``CPUUsage`` becomes
    ``cpu-usage``, ``LoadAvg1`` ``load-avg-1``, ``$HOST`` ``host``.

    Args:
        text: The wire name (or an alert's recipient).

    Returns:
        The handle; empty when nothing usable remains.
    """
    spaced = _CAMEL_LOWER_UPPER.sub("-", text)
    spaced = _CAMEL_ACRONYM.sub("-", spaced)
    spaced = _LETTER_DIGIT.sub("-", spaced)
    return _NON_ALNUM.sub("-", spaced).lower().strip("-")


def assign_migrate_handles(
    live: Mapping[str, Sequence[LiveMonitItem]],
    existing: Mapping[str, Mapping[str, str]] | None = None,
    reserved: Collection[str] = (),
) -> dict[str, dict[str, str]]:
    """Assign handles to the live rows of all three list types at once.

    Pass 1 pins a live row whose identity already has a row of its own type in the
    environment to that row's handle (only the first live row per identity). Pass 2 gives
    every other row a kebab slug of its identity, suffixed ``-2``, ``-3`` ... until it is
    free of every reserved and already assigned handle. The result depends only on the
    inputs, so every list type's migration computes the same handles.

    Args:
        live: ``sub`` -> live rows in model order.
        existing: ``sub`` -> ``{identity: handle}`` of rows already in the environment.
        reserved: Every opnsense resource name already in the environment.

    Returns:
        ``sub`` -> ``{uuid: handle}``.
    """
    known = existing or {}
    taken: set[str] = set(reserved)
    result: dict[str, dict[str, str]] = {sub: {} for sub in MIGRATE_ORDER}
    for sub in MIGRATE_ORDER:
        pinned = known.get(sub, {})
        seen: set[str] = set()
        for item in live.get(sub, ()):
            if item.name in pinned and item.name not in seen:
                seen.add(item.name)
                result[sub][item.uuid] = pinned[item.name]
                taken.add(pinned[item.name])
    for sub in MIGRATE_ORDER:
        for index, item in enumerate(live.get(sub, ()), start=1):
            if item.uuid in result[sub]:
                continue
            result[sub][item.uuid] = next_free_handle(
                kebab_handle(item.name) or f"{sub}-{index}", taken
            )
    return result


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MonitItemConfig:
    """Desired-state monit list row.

    Attributes:
        name: YAML name, the cross-reference handle.
        wire_name: Wire identity.
        fields: Sorted ``(wire, serialized_value, kind)`` triples the operator set.
        refs: ``(wire, target_sub, handles)`` triples, resolved to UUIDs at apply.
        lock: Per-resource safety annotation (ADR-0014 section 6).
    """

    name: str
    wire_name: str
    fields: tuple[tuple[str, str, str], ...] = field(default=(), repr=False)
    refs: tuple[tuple[str, str, tuple[str, ...]], ...] = ()
    lock: bool = False

    @property
    def diff_key(self) -> str:
        """Identity of this row: its wire identity."""
        return self.wire_name

    def to_payload(
        self, spec: MonitListSpec, ref_uuids: Mapping[tuple[str, str], str]
    ) -> dict[str, Any]:
        """Serialize to the ``add``/``update`` envelope.

        Args:
            spec: The list type.
            ref_uuids: ``(sub, handle)`` -> live UUID, for every ref of this row.

        Returns:
            ``{item_key: {...}}`` holding the identity and the declared fields only.
        """
        body: dict[str, Any] = {spec.identity_wire: self.wire_name}
        for wire, value, _ in self.fields:
            body[wire] = value
        for wire, sub, handles in self.refs:
            body[wire] = ",".join(ref_uuids[(sub, h)] for h in handles)
        return {spec.item_key: body}

    def pending_refs(self, ref_uuids: Mapping[tuple[str, str], str]) -> list[tuple[str, str]]:
        """Return the ``(sub, handle)`` references with no live UUID."""
        return [
            (sub, h) for _, sub, handles in self.refs for h in handles if (sub, h) not in ref_uuids
        ]


@dataclass(frozen=True)
class LiveMonitItem:
    """A monit row as currently on the box.

    Attributes:
        uuid: Row UUID.
        name: Live wire identity.
        raw: The row object from the model (hidden in ``repr``).
    """

    uuid: str
    name: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def diff_key(self) -> str:
        """Identity of this row: its wire identity."""
        return self.name


@dataclass
class Diff:
    """Result of comparing desired monit rows to live ones.

    ``blocked`` holds managed live rows whose delete would break a reference from a
    surviving row; the manager fills it. They are kept and stay managed.
    """

    adds: list[MonitItemConfig] = field(default_factory=list)
    updates: list[tuple[LiveMonitItem, MonitItemConfig]] = field(default_factory=list)
    deletes: list[LiveMonitItem] = field(default_factory=list)
    unmanaged: list[LiveMonitItem] = field(default_factory=list)
    locked: list[tuple[MonitItemConfig, LiveMonitItem | None]] = field(default_factory=list)
    matched: list[tuple[LiveMonitItem, MonitItemConfig]] = field(default_factory=list)
    blocked: list[tuple[LiveMonitItem, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there is nothing to add, update or delete."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def _live_value(have: LiveMonitItem, wire: str, kind: str) -> str:
    flat = flatten_option(have.raw.get(wire)).strip()
    if kind == BOOL:
        return "1" if flat == "1" else "0"
    return flat


def changed_fields(
    have: LiveMonitItem,
    want: MonitItemConfig,
    ref_uuids: Mapping[tuple[str, str], str] | None = None,
) -> list[str]:
    """Return the wire keys whose live value differs from the desired one.

    Args:
        have: Live row.
        want: Desired row.
        ref_uuids: ``(sub, handle)`` -> live UUID. A reference with no entry is pending
            and counts as changed.

    Returns:
        Field names only, never values.
    """
    known = ref_uuids or {}
    changed: list[str] = []
    for wire, value, kind in want.fields:
        live = _live_value(have, wire, kind)
        if kind == LIST:
            if frozenset(_split(live)) != frozenset(_split(value)):
                changed.append(wire)
        elif live != value:
            changed.append(wire)
    for wire, sub, handles in want.refs:
        resolved = [known[(sub, h)] for h in handles if (sub, h) in known]
        if len(resolved) != len(handles):
            changed.append(wire)
            continue
        if frozenset(_split(flatten_option(have.raw.get(wire)))) != frozenset(resolved):
            changed.append(wire)
    return changed


def compute_diff(
    spec: MonitListSpec,
    desired: list[MonitItemConfig],
    current: list[LiveMonitItem],
    *,
    add_only: bool = False,
    managed_keys: set[str] | None = None,
    ref_uuids: Mapping[tuple[str, str], str] | None = None,
) -> Diff:
    """Compare desired rows to live rows, keyed by wire identity.

    Args:
        spec: The list type, for messages.
        desired: Rows the operator wants.
        current: Every live row.
        add_only: Suppress deletes.
        managed_keys: When given, only live rows in this set may be deleted (ADR-0018);
            others land in ``Diff.unmanaged``.
        ref_uuids: ``(sub, handle)`` -> live UUID for references.

    Returns:
        The diff.

    Raises:
        OpnsenseDriftError: If two live rows share an identity.
    """
    live_by_key: dict[str, LiveMonitItem] = {}
    for live in current:
        if live.diff_key in live_by_key:
            raise OpnsenseDriftError(
                f"monit {spec.sub}: more than one live row is named {live.diff_key!r}; "
                f"rename one on the box before planning"
            )
        live_by_key[live.diff_key] = live
    desired_by_key = {c.diff_key: c for c in desired}
    locked_keys = {c.diff_key for c in desired if c.lock}

    diff = Diff()
    for key, want in desired_by_key.items():
        have = live_by_key.get(key)
        if want.lock:
            diff.locked.append((want, have))
        elif have is None:
            diff.adds.append(want)
        else:
            diff.matched.append((have, want))
            if changed_fields(have, want, ref_uuids):
                diff.updates.append((have, want))

    if add_only:
        return diff
    for key, have in live_by_key.items():
        if key in locked_keys or key in desired_by_key:
            continue
        if managed_keys is not None and key not in managed_keys:
            diff.unmanaged.append(have)
        else:
            diff.deletes.append(have)
    return diff


def topo_order_adds(adds: Sequence[MonitItemConfig], sub: str) -> list[MonitItemConfig]:
    """Order added rows so a row comes after the same-type rows it references.

    Args:
        adds: Rows to add.
        sub: The list type; only references to this type count.

    Returns:
        The rows, dependencies first, otherwise in the given order.

    Raises:
        InvalidConfigurationError: On a reference cycle.
    """
    by_name = {c.name: c for c in adds}
    ordered: list[MonitItemConfig] = []
    state: dict[str, int] = {}

    def visit(config: MonitItemConfig) -> None:
        if state.get(config.name) == 2:
            return
        if state.get(config.name) == 1:
            raise InvalidConfigurationError(f"monit {sub} '{config.name}' is part of a cycle")
        state[config.name] = 1
        for _, ref_sub, handles in config.refs:
            if ref_sub != sub:
                continue
            for handle in handles:
                if handle in by_name:
                    visit(by_name[handle])
        state[config.name] = 2
        ordered.append(config)

    for config in adds:
        visit(config)
    return ordered


def order_deletes(items: Sequence[LiveMonitItem], sub: str) -> list[LiveMonitItem]:
    """Order live rows for deletion: a service goes before the services it depends on.

    Args:
        items: Rows to delete.
        sub: The list type; only ``services`` have dependencies.

    Returns:
        The rows, dependents first. A cycle is appended in the given order.
    """
    if sub != "services":
        return list(items)
    remaining = list(items)
    result: list[LiveMonitItem] = []
    while remaining:
        needed = {
            uuid
            for item in remaining
            for uuid in _split(flatten_option(item.raw.get("depends")))
            if uuid != item.uuid
        }
        ready = [item for item in remaining if item.uuid not in needed]
        if not ready:
            result.extend(remaining)
            break
        result.extend(ready)
        remaining = [item for item in remaining if item not in ready]
    return result


def references_to(model: Mapping[str, Any], wire: str) -> dict[str, list[LiveMonitItem]]:
    """Map each UUID to the live services that list it in a reference field.

    Args:
        model: The ``monit`` model object.
        wire: ``tests`` or ``depends``.

    Returns:
        ``target uuid`` -> referencing services, in model order.
    """
    found: dict[str, list[LiveMonitItem]] = {}
    for item in live_items(model, SERVICES):
        for uuid in _split(flatten_option(item.raw.get(wire))):
            found.setdefault(uuid, []).append(item)
    return found


# ---------------------------------------------------------------------------
# Resource-to-domain conversion
# ---------------------------------------------------------------------------


def configs_from_resources(
    spec: MonitListSpec, resources: Sequence[ResourceConfig]
) -> list[MonitItemConfig]:
    """Convert resources of ``spec.type_name`` to :class:`MonitItemConfig`.

    Args:
        spec: The list type.
        resources: Provider resources; other types are skipped.

    Returns:
        Parsed rows.

    Raises:
        ValueError: On a non-dict config, an unknown key, a missing identity or a
            mistyped value. Messages name the resource and the field, never a value.
        InvalidConfigurationError: On a malformed reference.
    """
    configs: list[MonitItemConfig] = []
    for resource in resources:
        if resource.type != spec.type_name:
            continue
        if not isinstance(resource.config, dict):
            raise ValueError(f"monit {spec.noun} '{resource.name}' has non-dict config")
        configs.append(_build_config(spec, resource.name, resource.config))
    return configs


def wire_name_of(spec: MonitListSpec, name: str, config: Mapping[str, Any]) -> str:
    """Return the wire identity of a resource.

    Args:
        spec: The list type.
        name: Resource name (the handle).
        config: Resource config.

    Returns:
        The identity key's value when a non-empty string, else the handle (empty for an
        alert without a usable ``recipient``).
    """
    value = config.get(spec.identity_key)
    if isinstance(value, str) and value:
        return value
    return "" if spec.identity_required else name


def _build_config(spec: MonitListSpec, name: str, config: dict[str, Any]) -> MonitItemConfig:
    label = f"monit {spec.noun} '{name}'"
    unknown = sorted(key for key in config if not spec.accepts(key))
    if unknown:
        raise ValueError(f"{label} has unknown keys: {unknown}")
    if not isinstance(config.get("lock", False), bool):
        raise ValueError(f"{label} lock must be a boolean")
    identity = config.get(spec.identity_key)
    if identity is not None and not isinstance(identity, str):
        raise ValueError(f"{label} {spec.identity_key} must be a string")
    wire_name = wire_name_of(spec, name, config)
    if not wire_name:
        raise ValueError(f"{label} requires a non-empty string '{spec.identity_key}'")

    values: dict[str, tuple[str, str]] = {}
    refs: list[tuple[str, str, tuple[str, ...]]] = []
    for key, fspec in spec.fields.items():
        if key not in config:
            continue
        text = serialize_field(label, key, fspec, config[key])
        if fspec.kind in {REF, REFSET}:
            raw = config[key]
            handles = tuple(
                ref_handle(h, fspec.ref_sub) for h in (raw if fspec.kind == REFSET else [raw])
            )
            refs.append((fspec.wire, fspec.ref_sub, handles))
            continue
        values[fspec.wire] = (text, fspec.kind)
    return MonitItemConfig(
        name=name,
        wire_name=wire_name,
        fields=tuple((wire, text, kind) for wire, (text, kind) in sorted(values.items())),
        refs=tuple(sorted(refs)),
        lock=bool(config.get("lock", False)),
    )


# ---------------------------------------------------------------------------
# Live model access
# ---------------------------------------------------------------------------


def fetch_model(client: Any) -> dict[str, Any]:
    """Fetch ``GET monit/settings/get`` and return the ``monit`` model object.

    Args:
        client: The OPNsense API client.

    Returns:
        The model: ``general`` plus the ``alert``, ``service`` and ``test`` sections.

    Raises:
        APIError: If the envelope is missing; the message carries key names only.
    """
    ep = endpoints.MONIT_SETTINGS_GET
    response = client.request(ep.method, ep.path())
    model = response.get("monit") if isinstance(response, dict) else None
    if not isinstance(model, dict):
        raise APIError(
            "OPNsense monit/settings/get returned no monit object",
            response=str(sorted(response)) if isinstance(response, dict) else "",
            provider="opnsense",
        )
    return model


def live_items(model: Mapping[str, Any], spec: MonitListSpec) -> list[LiveMonitItem]:
    """Return the live rows of one type from the ``monit`` model object.

    Args:
        model: The ``monit`` model object (``settings/get``).
        spec: The list type.

    Returns:
        Rows in model order.

    Raises:
        APIError: If the model has no section for the type, so a plan is never built from
            nothing.
    """
    if spec.item_key not in model:
        raise APIError(
            f"OPNsense monit/settings/get returned no {spec.item_key} section",
            response=str(sorted(model))[:200],
            provider="opnsense",
        )
    section = model[spec.item_key]
    if section in (None, [], {}):
        return []  # PHP serializes an empty map as []
    if not isinstance(section, dict):
        raise APIError(
            f"OPNsense monit/settings/get returned a malformed {spec.item_key} section",
            response=str(sorted(model))[:200],
            provider="opnsense",
        )
    return [
        LiveMonitItem(
            uuid=str(uuid), name=flatten_option(row.get(spec.identity_wire)), raw=dict(row)
        )
        for uuid, row in section.items()
        if isinstance(row, dict)
    ]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class MonitListService(BaseService):
    """Service for one monit list type; subclasses set :attr:`SPEC`."""

    SPEC: ClassVar[MonitListSpec]

    def get_model(self) -> dict[str, Any]:
        """Fetch ``settings/get`` and return the ``monit`` model object."""
        return fetch_model(self.client)

    def live(self, model: Mapping[str, Any] | None = None) -> list[LiveMonitItem]:
        """Return the live rows of this type (reads the model when not given)."""
        return live_items(model if model is not None else self.get_model(), self.SPEC)

    def add(self, config: MonitItemConfig, ref_uuids: Mapping[tuple[str, str], str]) -> Any:
        """Create a row; raises when OPNsense rejects it. Returns the response."""
        spec = self.SPEC
        ep = spec.crud.add
        response = self.client.request(
            ep.method, ep.path(), data=config.to_payload(spec, ref_uuids)
        )
        return raise_on_failed_write(response, f"add monit {spec.noun} {config.name!r}")

    def update(
        self, uuid: str, config: MonitItemConfig, ref_uuids: Mapping[tuple[str, str], str]
    ) -> Any:
        """Update a row by UUID; raises when OPNsense rejects it."""
        spec = self.SPEC
        ep = spec.crud.update
        response = self.client.request(
            ep.method, ep.path(uuid=uuid), data=config.to_payload(spec, ref_uuids)
        )
        return raise_on_failed_write(response, f"update monit {spec.noun} {config.name!r}")

    def delete(self, live: LiveMonitItem) -> Any:
        """Delete a row by UUID."""
        spec = self.SPEC
        ep = spec.crud.delete
        response = self.client.request(ep.method, ep.path(uuid=live.uuid))
        return raise_on_failed_write(response, f"delete monit {spec.noun} {live.name!r}")

    def reconfigure(self) -> Any:
        """Apply the saved monit configuration.

        Called only by the provider's ``monit_reconfigure`` finalization hook (and by the
        manager's destroy, which the hook does not cover).
        """
        ep = endpoints.MONIT_RECONFIGURE
        response = self.client.request(ep.method, ep.path())
        return raise_on_failed_write(response, "reconfigure monit")

    def _added_uuid(self, response: Any, config: MonitItemConfig) -> str | None:
        """Return the UUID of a row just added: from the response, else by re-reading."""
        if isinstance(response, dict) and isinstance(response.get("uuid"), str):
            return str(response["uuid"])
        for item in self.live():
            if item.diff_key == config.diff_key:
                return item.uuid
        return None

    def apply_diff(
        self, diff: Diff, ref_uuids: Mapping[tuple[str, str], str] | None = None
    ) -> dict[str, int]:
        """Dispatch the diff. The caller reconfigures through the finalization hook.

        Services are added dependencies first, and the UUID each add returns satisfies a
        later row's ``depends``. Deletes run dependents first.

        Args:
            diff: The diff to apply.
            ref_uuids: ``(sub, handle)`` -> live UUID for references.

        Returns:
            ``{"created": N, "updated": M, "deleted": K}``.

        Raises:
            ReferenceValidationError: If an added or updated row references something
                not on the box and not added by this diff. Checked before any write.
        """
        spec = self.SPEC
        known = dict(ref_uuids or {})
        in_apply = {c.name for c in diff.adds}
        for config in [*diff.adds, *(want for _, want in diff.updates)]:
            pending = [
                (sub, handle)
                for sub, handle in config.pending_refs(known)
                if not (sub == spec.sub and handle in in_apply)
            ]
            if pending:
                names = ", ".join(f"{sub}.{handle}" for sub, handle in pending)
                raise ReferenceValidationError(
                    f"monit {spec.noun} '{config.name}' references {names}, which is not on "
                    f"the box; apply it first"
                )
        created = updated = deleted = 0
        for config in topo_order_adds(diff.adds, spec.sub):
            response = self.add(config, known)
            created += 1
            if spec.sub == "services":
                uuid = self._added_uuid(response, config)
                if uuid is not None:
                    known[(spec.sub, config.name)] = uuid
        for live, want in diff.updates:
            logger.info(
                "opnsense %s: updating %s (fields: %s)",
                spec.type_name,
                want.name,
                changed_fields(live, want, known),
            )
            self.update(live.uuid, want, known)
            updated += 1
        for live in order_deletes(diff.deletes, spec.sub):
            self.delete(live)
            deleted += 1
        return {"created": created, "updated": updated, "deleted": deleted}

    def export_rows(
        self,
        items: list[LiveMonitItem],
        ref_handles: Mapping[str, Mapping[str, str]] | None = None,
        handles: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Build the nested-YAML entries for live rows.

        Args:
            items: Live rows.
            ref_handles: ``sub`` -> ``{uuid: handle}`` for reference fields.
            handles: ``{uuid: handle}`` for ``items``; computed per type when omitted.

        Returns:
            One ``{"name": handle, "config": {...}}`` per row. Empty fields are omitted,
            except booleans; the identity key is emitted when it differs from the handle
            (always for alerts).
        """
        spec = self.SPEC
        if handles is None:
            handles = assign_migrate_handles({spec.sub: items})[spec.sub]
        known = ref_handles or {}
        rows: list[dict[str, Any]] = []
        for item in items:
            handle = handles[item.uuid]
            config: dict[str, Any] = {}
            if spec.identity_required or item.name != handle:
                config[spec.identity_key] = item.name
            for key, fspec in spec.fields.items():
                self._export_field(config, item, key, fspec, known)
            rows.append({"name": handle, "config": config})
        return rows

    def _export_field(
        self,
        config: dict[str, Any],
        item: LiveMonitItem,
        key: str,
        fspec: FieldSpec,
        ref_handles: Mapping[str, Mapping[str, str]],
    ) -> None:
        spec = self.SPEC
        flat = flatten_option(item.raw.get(fspec.wire)).strip()
        if fspec.kind == BOOL:
            config[key] = flat == "1"
            return
        if not flat:
            return
        if fspec.kind == INT:
            if flat.isascii() and flat.isdigit():
                config[key] = int(flat)
            else:
                logger.warning("monit %s: non-integer %s; omitted", spec.sub, key)
        elif fspec.kind == LIST:
            config[key] = sorted(_split(flat))
        elif fspec.kind in {REF, REFSET}:
            mapping = ref_handles.get(fspec.ref_sub, {})
            found: list[str] = []
            for uuid in _split(flat):
                if uuid in mapping:
                    found.append(mapping[uuid])
                else:
                    logger.warning(
                        "monit %s: %s references an unknown %s row; dropped",
                        spec.sub,
                        key,
                        fspec.ref_sub,
                    )
            if found:
                config[key] = found
        else:
            config[key] = flat

    def export_to_yaml(
        self,
        ref_handles: Mapping[str, Mapping[str, str]] | None = None,
        *,
        items: list[LiveMonitItem] | None = None,
        handles: Mapping[str, str] | None = None,
    ) -> str:
        """Export every live row as nested YAML for ``config migrate``.

        Args:
            ref_handles: ``sub`` -> ``{uuid: handle}`` for reference fields.
            items: Live rows already fetched; read when omitted.
            handles: ``{uuid: handle}`` for the rows; computed per type when omitted.

        Returns:
            The nested YAML text.
        """
        rows = items if items is not None else self.live()
        return emit_nested_list_yaml(
            self.SPEC.type_name, self.export_rows(rows, ref_handles, handles)
        )


class MonitAlertsService(MonitListService):
    """Service for ``monit.alerts``."""

    SPEC = ALERTS


class MonitTestsService(MonitListService):
    """Service for ``monit.tests``."""

    SPEC = TESTS


class MonitServicesService(MonitListService):
    """Service for ``monit.services``."""

    SPEC = SERVICES


#: Every list type's service, in migrate order.
LIST_SERVICES: dict[str, type[MonitListService]] = {
    "alerts": MonitAlertsService,
    "tests": MonitTestsService,
    "services": MonitServicesService,
}
