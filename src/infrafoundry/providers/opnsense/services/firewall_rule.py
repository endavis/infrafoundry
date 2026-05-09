"""Firewall-rule service for OPNsense direct-API operations (ADR-0014, ADR-0015, #742).

Manages stateful firewall rules via the OPNsense MVC ``firewall/filter/*``
controller. The 2026-05-05 live probe of ``opnsense-a`` running ``26.1.6_2``
confirmed a 53-field surface that covers 100% of the production rule
features driving #742 — policy-based routing (``gateway``), floating
(``state-policy=floating``), direction (in / out / **any**), ``quick``,
``statetype`` (5 values), source/destination negation, ``<any>`` sentinels,
multi-valued ``categories``, and TCP-flag / ICMP / rate-limit knobs.

Identity strategy
-----------------

Firewall rules have no clean intrinsic key — two rules can share
``(interface, source, destination, port, action)`` with different
behavior depending on order. This service mirrors the ``nat_rules``
identity scheme: ``description`` carries an
``<operator description> [infrafoundry:<resource-name>]`` suffix tag and
the rule's multi-valued ``categories`` list contains the per-box
``infrafoundry`` category UUID as a fleet-wide marker. Live rows without
the suffix tag are unmanaged and silently ignored by the diff.

The categories field is **multi-valued** in the MVC controller (vs.
legacy's single ``<category>`` element), so the identity marker can
coexist with operator-set categories without collision — the service's
write path appends the ``infrafoundry`` UUID to operator UUIDs rather
than overwriting them. This is the load-bearing difference from
``nat_rules.NATRuleService`` whose ``_payload_with_category`` overwrites
the (single-valued there) categories field.

Wire-key conventions
--------------------

Several MVC fields use hyphenated wire keys that are illegal Python
identifiers. The dataclass attribute is the underscored form; the
service serializes via the module-level ``_PAYLOAD_FIELD_MAP`` table
which records the wire key, dataclass attribute, and value kind
(string / bool / int / category-multi). The hyphenated wire keys are:
``state-policy``, ``max-src-conn``, ``max-src-conn-rate``,
``max-src-conn-rates``, ``max-src-nodes``, ``max-src-states``,
``set-prio``, ``set-prio-low``, ``divert-to``, ``udp-first``,
``udp-multiple``, ``udp-single``, ``disablereplyto``. Operators MUST
use the underscored form in YAML.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from infrafoundry.core.exceptions import APIError, InfraFoundryError
from infrafoundry.core.provider import ResourceConfig

from ._category_marker import INFRAFOUNDRY_CATEGORY_NAME as _SHARED_CATEGORY_NAME
from ._category_marker import ensure_infrafoundry_category
from ._nested_emit import emit_nested_list_yaml
from .base import BaseService

logger = logging.getLogger(__name__)

# Regex for parsing the description-suffix identity tag. Operator-supplied
# free-form text leads, followed by whitespace, followed by
# ``\[infrafoundry:<name>\]`` at the end of the string. ``_IDENTITY_PROBE``
# is a position-agnostic detector used both by the parser (to flag
# malformed tags) and the validator (to reject operator-set descriptions
# that contain the tag in any position).
_IDENTITY_PATTERN = re.compile(r"^(?:(.+?)\s+)?\[infrafoundry:([a-z0-9-]+)\]\s*$")
_IDENTITY_PROBE = re.compile(r"\[infrafoundry:[^\]]*\]")

# MVC stateful filter base (single controller, all rules go through here).
_FILTER_BASE = "firewall/filter"

# Default sequence for new rules — matches the OPNsense schema default.
DEFAULT_SEQUENCE = 100

# Closed-set enums per the live probe and ADR-0015 §"Field coverage".
ACTION_CHOICES: tuple[str, ...] = ("pass", "block", "reject")
DIRECTION_CHOICES: tuple[str, ...] = ("in", "out", "any")
IPPROTOCOL_CHOICES: tuple[str, ...] = ("inet", "inet6", "inet46")
STATE_POLICY_CHOICES: tuple[str, ...] = ("", "default", "if-bound", "floating")
STATETYPE_CHOICES: tuple[str, ...] = (
    "",
    "keep state",
    "sloppy state",
    "modulate state",
    "synproxy state",
    "none",
)

# Wire-key serialization kinds for ``_PAYLOAD_FIELD_MAP`` entries. ``str``
# fields pass through; ``bool`` fields become ``"0"``/``"1"``; ``int``
# fields stringify; ``category-multi`` is the special-cased multi-valued
# categories serializer (see ``_payload_with_category``).
_FieldKind = Literal["str", "bool", "int"]


# Module-level mapping from dataclass attr → wire key + kind. Drives
# ``to_payload`` and ``_needs_update``. Order is the canonical wire order.
_PAYLOAD_FIELD_MAP: tuple[tuple[str, str, _FieldKind], ...] = (
    # Core / match
    ("enabled", "enabled", "bool"),
    ("sequence", "sequence", "int"),
    ("sort_order", "sort_order", "str"),
    ("action", "action", "str"),
    ("quick", "quick", "bool"),
    ("interface", "interface", "str"),
    ("interfacenot", "interfacenot", "bool"),
    ("direction", "direction", "str"),
    ("ipprotocol", "ipprotocol", "str"),
    ("protocol", "protocol", "str"),
    ("source_net", "source_net", "str"),
    ("source_not", "source_not", "bool"),
    ("source_port", "source_port", "str"),
    ("destination_net", "destination_net", "str"),
    ("destination_not", "destination_not", "bool"),
    ("destination_port", "destination_port", "str"),
    ("log", "log", "bool"),
    ("description", "description", "str"),
    # State
    ("statetype", "statetype", "str"),
    ("state_policy", "state-policy", "str"),
    ("statetimeout", "statetimeout", "str"),
    ("adaptivestart", "adaptivestart", "str"),
    ("adaptiveend", "adaptiveend", "str"),
    # Routing
    ("gateway", "gateway", "str"),
    ("divert_to", "divert-to", "str"),
    ("replyto", "replyto", "str"),
    ("disablereplyto", "disablereplyto", "bool"),
    # Categorization (categories is special-cased via _payload_with_category)
    ("tag", "tag", "str"),
    ("tagged", "tagged", "str"),
    # ICMP / TCP
    ("icmptype", "icmptype", "str"),
    ("icmp6type", "icmp6type", "str"),
    ("tcpflags1", "tcpflags1", "str"),
    ("tcpflags2", "tcpflags2", "str"),
    ("tcpflags_any", "tcpflags_any", "bool"),
    # Limits
    ("max", "max", "str"),
    ("max_src_conn", "max-src-conn", "str"),
    ("max_src_conn_rate", "max-src-conn-rate", "str"),
    ("max_src_conn_rates", "max-src-conn-rates", "str"),
    ("max_src_nodes", "max-src-nodes", "str"),
    ("max_src_states", "max-src-states", "str"),
    ("overload", "overload", "str"),
    # QoS
    ("prio", "prio", "str"),
    ("prio_group", "prio_group", "str"),
    ("set_prio", "set-prio", "str"),
    ("set_prio_low", "set-prio-low", "str"),
    ("tos", "tos", "str"),
    # UDP / pfsync
    ("udp_first", "udp-first", "str"),
    ("udp_multiple", "udp-multiple", "str"),
    ("udp_single", "udp-single", "str"),
    ("nopfsync", "nopfsync", "bool"),
    ("nosync", "nosync", "bool"),
    # Misc
    ("allowopts", "allowopts", "bool"),
)


class OpnsenseDriftError(InfraFoundryError):
    """A managed rule's identity tag is malformed on the live box.

    Raised by the diff engine when a live rule's ``description`` looks
    like it carries an InfraFoundry tag but does not match the strict
    identity regex. The operator must repair the description in the GUI
    (or via API) before the next plan/apply.
    """


# ---------------------------------------------------------------------------
# Identity-prefix helpers
# ---------------------------------------------------------------------------


def encode_identity(resource_name: str, user_description: str) -> str:
    """Encode the description with the InfraFoundry identity suffix.

    Args:
        resource_name: Operator-facing YAML name; becomes the diff key.
        user_description: Free-form description from YAML (may be empty).

    Returns:
        ``"<user_description> [infrafoundry:<name>]"`` when the user
        description is non-empty; ``"[infrafoundry:<name>]"`` otherwise.
    """
    if user_description:
        return f"{user_description} [infrafoundry:{resource_name}]"
    return f"[infrafoundry:{resource_name}]"


def parse_identity(description: str) -> tuple[str | None, str]:
    """Parse the description-suffix identity tag.

    Args:
        description: ``description`` field from a live rule row.

    Returns:
        ``(resource_name, user_description)``. ``resource_name`` is
        ``None`` when the description has no tag (unmanaged rule).

    Raises:
        OpnsenseDriftError: If the description contains the
            ``[infrafoundry:...]`` marker but does not match the strict
            suffix-only regex.
    """
    match = _IDENTITY_PATTERN.match(description)
    if match is not None:
        user_desc = match.group(1) or ""
        return match.group(2), user_desc
    if _IDENTITY_PROBE.search(description):
        raise OpnsenseDriftError(
            f"Firewall rule description contains an InfraFoundry identity tag but is malformed: "
            f"{description!r}. Expected '<user description> [infrafoundry:<name>]' (or just "
            f"'[infrafoundry:<name>]') where <name> matches [a-z0-9-]+ (non-empty) and the "
            f"tag is the LAST token in the description."
        )
    return None, description


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FirewallRuleConfig:
    """Desired-state firewall-rule configuration.

    All ~50 fields from ADR-0015 §"Field coverage" are represented as
    optional dataclass attributes with sensible defaults. ``sched``,
    ``shaper1``, and ``shaper2`` are punted (require resources we don't
    manage yet).

    **Wire key naming convention:** dataclass attributes are always
    underscored (e.g., ``state_policy``, ``max_src_conn``). The
    corresponding wire keys are hyphenated for several fields (see
    ``_PAYLOAD_FIELD_MAP``). Operators must use the underscored form in
    YAML — ``state-policy:`` will not parse.

    Attributes:
        name: Operator-facing YAML name; becomes the diff key.
        enabled: Whether the rule is active.
        log: Whether matching packets are logged.
        sequence: Position in the rule list (lower runs earlier).
        sort_order: Free-form ordering supplement to ``sequence``.
        interface: Logical interface name (e.g., ``"lan"``). Empty
            allowed when ``state_policy=floating``.
        description: Operator-facing free-form description (no identity
            prefix; the prefix is added at serialization time).
        lock: Per-resource safety annotation (ADR-0014 §6).

        Core / match:
            action: ``"pass"`` / ``"block"`` / ``"reject"``.
            quick: Match-and-stop on this rule.
            interfacenot: Negate the interface-list match.
            direction: ``"in"`` / ``"out"`` / ``"any"``.
            ipprotocol: ``"inet"`` / ``"inet6"`` / ``"inet46"``.
            protocol: ``"any"``, ``"TCP"``, ``"UDP"``, etc.
            source_net: Alias name, CIDR, IP, ``"any"``, or
                ``"<iface>net"``.
            source_not: Negate source.
            source_port: Port (or empty).
            destination_net: Same shape as ``source_net``.
            destination_not: Negate destination.
            destination_port: Port (or empty).

        State:
            statetype: ``""`` / ``"keep state"`` / ``"sloppy state"`` /
                ``"modulate state"`` / ``"synproxy state"`` / ``"none"``.
            state_policy: ``""`` / ``"default"`` / ``"if-bound"`` /
                ``"floating"``. Wire key is ``state-policy``.
            statetimeout: Custom state timeout (string).
            adaptivestart: Adaptive state-table start threshold.
            adaptiveend: Adaptive state-table end threshold.

        Routing:
            gateway: Gateway name (system or managed) for policy-based
                routing.
            divert_to: Transparent-proxy port. Wire key is ``divert-to``.
            replyto: Reply-to gateway.
            disablereplyto: Disable reply-to behavior.

        Categorization:
            categories: List of operator-supplied category UUIDs. The
                ``infrafoundry`` UUID is appended at serialization time.
            tag: pf rule tag for set-by-rule.
            tagged: Match on incoming tag.

        ICMP / TCP:
            icmptype: IPv4 ICMP type (``"echoreq"`` / ``"unreach"`` /
                etc.).
            icmp6type: IPv6 ICMP type.
            tcpflags1: Match-set TCP flags.
            tcpflags2: Out-of-set TCP flags.
            tcpflags_any: Match any TCP flags (mutex with
                ``tcpflags1``/``tcpflags2``).

        Limits:
            max: Max simultaneous states (string for direct serialization).
            max_src_conn: Wire key ``max-src-conn``.
            max_src_conn_rate: Wire key ``max-src-conn-rate``.
            max_src_conn_rates: Wire key ``max-src-conn-rates``.
            max_src_nodes: Wire key ``max-src-nodes``.
            max_src_states: Wire key ``max-src-states``.
            overload: Auto-block table on rate hit.

        QoS:
            prio: Match incoming priority (0-7 as string).
            prio_group: Queue group.
            set_prio: Wire key ``set-prio``.
            set_prio_low: Wire key ``set-prio-low``.
            tos: DSCP/ToS marking value.

        UDP / pfsync:
            udp_first: Wire key ``udp-first``.
            udp_multiple: Wire key ``udp-multiple``.
            udp_single: Wire key ``udp-single``.
            nopfsync: Exclude rule from pfsync.
            nosync: Exclude state from sync.

        Misc:
            allowopts: Allow IP options.
    """

    name: str
    enabled: bool = True
    log: bool = False
    sequence: int = DEFAULT_SEQUENCE
    sort_order: str = ""
    interface: str = ""
    description: str = ""
    lock: bool = False

    # Core / match
    action: str = "pass"
    quick: bool = True
    interfacenot: bool = False
    direction: str = "in"
    ipprotocol: str = "inet"
    protocol: str = "any"
    source_net: str = "any"
    source_not: bool = False
    source_port: str = ""
    destination_net: str = "any"
    destination_not: bool = False
    destination_port: str = ""

    # State
    statetype: str = ""
    state_policy: str = ""
    statetimeout: str = ""
    adaptivestart: str = ""
    adaptiveend: str = ""

    # Routing
    gateway: str = ""
    divert_to: str = ""
    replyto: str = ""
    disablereplyto: bool = False

    # Categorization
    categories: tuple[str, ...] = ()
    tag: str = ""
    tagged: str = ""

    # ICMP / TCP
    icmptype: str = ""
    icmp6type: str = ""
    tcpflags1: str = ""
    tcpflags2: str = ""
    tcpflags_any: bool = False

    # Limits
    max: str = ""
    max_src_conn: str = ""
    max_src_conn_rate: str = ""
    max_src_conn_rates: str = ""
    max_src_nodes: str = ""
    max_src_states: str = ""
    overload: str = ""

    # QoS
    prio: str = ""
    prio_group: str = ""
    set_prio: str = ""
    set_prio_low: str = ""
    tos: str = ""

    # UDP / pfsync
    udp_first: str = ""
    udp_multiple: str = ""
    udp_single: str = ""
    nopfsync: bool = False
    nosync: bool = False

    # Misc
    allowopts: bool = False

    def encoded_description(self) -> str:
        """Description with the InfraFoundry identity prefix applied."""
        return encode_identity(self.name, self.description)

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the ``addRule``/``setRule`` envelope OPNsense expects.

        Returns:
            ``{"rule": {<wire-keyed fields>}}``. Booleans serialize to
            ``"0"``/``"1"`` per OPNsense convention; ints stringify.
            The ``description`` field carries the identity suffix tag.
            The ``categories`` field is **not** included here — it is
            populated at the service layer via
            ``_payload_with_category``.
        """
        inner: dict[str, Any] = {}
        for attr, wire_key, kind in _PAYLOAD_FIELD_MAP:
            value: Any = getattr(self, attr)
            if attr == "description":
                value = self.encoded_description()
            if kind == "bool":
                inner[wire_key] = _bool_str(bool(value))
            elif kind == "int":
                inner[wire_key] = str(int(value))
            else:
                inner[wire_key] = str(value)
        return {"rule": inner}


@dataclass(frozen=True)
class LiveFirewallRule:
    """A firewall rule as currently configured on the OPNsense box.

    Identity-tagged rows have ``managed_name`` set to the parsed
    resource name; unmanaged rows have it set to ``None`` and are
    filtered out of the diff entirely.

    Attributes:
        uuid: OPNsense-assigned rule UUID.
        managed_name: Parsed InfraFoundry name (``None`` if unmanaged).
        description: Free-form description with the prefix stripped.
        raw: Full original row dict from ``searchRule`` for field
            comparison during update detection.
    """

    uuid: str
    managed_name: str | None
    description: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Diff:
    """Result of comparing desired YAML state to live OPNsense state.

    Mirrors the surface of ``services.nat_rule.Diff``
    (``adds``/``updates``/``deletes``/``locked``) plus ``is_empty``.
    Updates carry the live record alongside the desired record so the
    caller has the UUID.
    """

    adds: list[FirewallRuleConfig] = field(default_factory=list)
    updates: list[tuple[LiveFirewallRule, FirewallRuleConfig]] = field(default_factory=list)
    deletes: list[LiveFirewallRule] = field(default_factory=list)
    locked: list[tuple[FirewallRuleConfig, LiveFirewallRule | None]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there are no add/update/delete operations to apply."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def compute_diff(
    desired: list[FirewallRuleConfig],
    current: list[LiveFirewallRule],
    *,
    add_only: bool = False,
) -> Diff:
    """Compare desired YAML state to live state.

    Unmanaged live rows (``managed_name is None``) are silently ignored:
    not deleted, not updated, never reported. Rules tagged
    ``[infrafoundry:...]`` but malformed are surfaced as
    ``OpnsenseDriftError`` at parse time, before this function runs.

    Args:
        desired: Firewall rules the operator wants to exist.
        current: Firewall rules currently on the box.
        add_only: If True, never emit deletes for managed live rules
            that don't appear in ``desired``. Adds and updates still
            happen.

    Returns:
        ``Diff`` with adds/updates/deletes plus locked entries.
    """
    desired_by_name: dict[str, FirewallRuleConfig] = {d.name: d for d in desired}
    current_managed: dict[str, LiveFirewallRule] = {
        live.managed_name: live for live in current if live.managed_name is not None
    }
    locked_names: set[str] = {d.name for d in desired if d.lock}

    adds: list[FirewallRuleConfig] = []
    updates: list[tuple[LiveFirewallRule, FirewallRuleConfig]] = []
    deletes: list[LiveFirewallRule] = []
    locked: list[tuple[FirewallRuleConfig, LiveFirewallRule | None]] = []

    for name, want in desired_by_name.items():
        have = current_managed.get(name)
        if want.lock:
            locked.append((want, have))
            continue
        if have is None:
            adds.append(want)
        elif _needs_update(have, want):
            updates.append((have, want))

    if not add_only:
        for name, have in current_managed.items():
            if name in locked_names:
                continue
            if name not in desired_by_name:
                deletes.append(have)

    return Diff(adds=adds, updates=updates, deletes=deletes, locked=locked)


def _needs_update(have: LiveFirewallRule, want: FirewallRuleConfig) -> bool:
    """Return True if the live row's fields differ from the desired payload."""
    payload = want.to_payload()["rule"]
    for key, want_value in payload.items():
        have_value = _normalize_field(have.raw.get(key))
        if str(want_value) != have_value:
            return True
    return False


def _normalize_field(value: Any) -> str:
    """Collapse an OPNsense field value to a comparable string.

    OPNsense returns single-select fields as dicts of options keyed by
    their machine value; the active option has ``"selected": 1``. We
    extract that option and return its key (matching what we'd send on
    update). Empty/None values become ``""``. Plain scalars are
    stringified verbatim.
    """
    if value is None:
        return ""
    if isinstance(value, dict):
        for option_key, option_value in value.items():
            if isinstance(option_value, dict) and option_value.get("selected"):
                return str(option_key)
        return ""
    return str(value)


def _normalize_categories(value: Any) -> set[str]:
    """Collapse the ``categories`` field on a live row to a set of UUIDs.

    OPNsense returns multi-select fields as dicts of options keyed by
    UUID, with ``"selected": 1`` on chosen entries. The wire send-side
    is a comma-separated string. Both shapes are normalized to the set
    of selected UUIDs here.
    """
    if value is None or value == "":
        return set()
    if isinstance(value, str):
        return {part.strip() for part in value.split(",") if part.strip()}
    if isinstance(value, dict):
        return {
            str(uuid)
            for uuid, info in value.items()
            if isinstance(info, dict) and info.get("selected")
        }
    if isinstance(value, list):
        return {str(item) for item in value if item}
    return set()


# ---------------------------------------------------------------------------
# Resource-to-domain conversion
# ---------------------------------------------------------------------------


def firewall_rule_configs_from_resources(
    resources: list[ResourceConfig],
) -> list[FirewallRuleConfig]:
    """Convert ``ResourceConfig`` entries to ``FirewallRuleConfig`` instances.

    Validation here is intentionally light — the validator handles
    cross-resource references and operator-friendly error messages; the
    service only enforces type sanity so manager code can rely on field
    invariants.

    Args:
        resources: All provider resources from a ConfigManager load.
            Non-``firewall_rules`` entries are silently skipped.

    Returns:
        Validated ``FirewallRuleConfig`` list.

    Raises:
        ValueError: If an entry has a non-dict config, missing/invalid
            required fields, non-bool booleans / non-int ``sequence`` /
            forged identity prefix in ``description``, or invalid enum
            values.
    """
    configs: list[FirewallRuleConfig] = []
    for resource in resources:
        if resource.type != "firewall.rules":
            continue

        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"firewall_rule '{resource.name}' has non-dict config")

        configs.append(_build_config(resource.name, config))
    return configs


def _build_config(name: str, config: dict[str, Any]) -> FirewallRuleConfig:
    """Build a single ``FirewallRuleConfig`` from a YAML config dict."""
    description = config.get("description", "")
    if not isinstance(description, str):
        raise ValueError(f"firewall_rule '{name}' description must be a string")
    if _IDENTITY_PROBE.search(description):
        raise ValueError(
            f"firewall_rule '{name}' description must not contain "
            f"'[infrafoundry:<name>]' — that tag is reserved for InfraFoundry's "
            f"identity suffix, which is added automatically at apply time"
        )

    sequence_raw = config.get("sequence", DEFAULT_SEQUENCE)
    try:
        sequence = int(sequence_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"firewall_rule '{name}' sequence must be an integer, got {sequence_raw!r}"
        ) from exc

    enabled = _require_bool(config, "enabled", default=True, name=name)
    log = _require_bool(config, "log", default=False, name=name)
    lock = _require_bool(config, "lock", default=False, name=name)
    quick = _require_bool(config, "quick", default=True, name=name)
    interfacenot = _require_bool(config, "interfacenot", default=False, name=name)
    source_not = _require_bool(config, "source_not", default=False, name=name)
    destination_not = _require_bool(config, "destination_not", default=False, name=name)
    disablereplyto = _require_bool(config, "disablereplyto", default=False, name=name)
    tcpflags_any = _require_bool(config, "tcpflags_any", default=False, name=name)
    nopfsync = _require_bool(config, "nopfsync", default=False, name=name)
    nosync = _require_bool(config, "nosync", default=False, name=name)
    allowopts = _require_bool(config, "allowopts", default=False, name=name)

    action = _string_field(config, "action", default="pass", name=name)
    if action not in ACTION_CHOICES:
        raise ValueError(
            f"firewall_rule '{name}' action must be one of {ACTION_CHOICES}, got {action!r}"
        )

    direction = _string_field(config, "direction", default="in", name=name)
    if direction not in DIRECTION_CHOICES:
        raise ValueError(
            f"firewall_rule '{name}' direction must be one of {DIRECTION_CHOICES}, "
            f"got {direction!r}"
        )

    ipprotocol = _string_field(config, "ipprotocol", default="inet", name=name)
    if ipprotocol not in IPPROTOCOL_CHOICES:
        raise ValueError(
            f"firewall_rule '{name}' ipprotocol must be one of {IPPROTOCOL_CHOICES}, "
            f"got {ipprotocol!r}"
        )

    state_policy = _string_field(config, "state_policy", default="", name=name)
    if state_policy not in STATE_POLICY_CHOICES:
        raise ValueError(
            f"firewall_rule '{name}' state_policy must be one of {STATE_POLICY_CHOICES}, "
            f"got {state_policy!r}"
        )

    statetype = _string_field(config, "statetype", default="", name=name)
    if statetype not in STATETYPE_CHOICES:
        raise ValueError(
            f"firewall_rule '{name}' statetype must be one of {STATETYPE_CHOICES}, "
            f"got {statetype!r}"
        )

    # tcpflags_any vs explicit tcpflags1/tcpflags2 mutex enforced at
    # the validator level; the service layer accepts the YAML and lets
    # the validator surface a friendlier message.
    interface = _string_field(config, "interface", default="", name=name)

    categories_raw = config.get("categories", [])
    if isinstance(categories_raw, str):
        categories: tuple[str, ...] = tuple(
            part.strip() for part in categories_raw.split(",") if part.strip()
        )
    elif isinstance(categories_raw, list):
        categories = tuple(str(item) for item in categories_raw if item)
    else:
        raise ValueError(
            f"firewall_rule '{name}' categories must be a list or comma-separated string"
        )

    return FirewallRuleConfig(
        name=name,
        enabled=enabled,
        log=log,
        sequence=sequence,
        sort_order=_string_field(config, "sort_order", default="", name=name),
        interface=interface,
        description=description,
        lock=lock,
        action=action,
        quick=quick,
        interfacenot=interfacenot,
        direction=direction,
        ipprotocol=ipprotocol,
        protocol=_string_field(config, "protocol", default="any", name=name),
        source_net=_string_field(config, "source_net", default="any", name=name),
        source_not=source_not,
        source_port=_string_field(config, "source_port", default="", name=name),
        destination_net=_string_field(config, "destination_net", default="any", name=name),
        destination_not=destination_not,
        destination_port=_string_field(config, "destination_port", default="", name=name),
        statetype=statetype,
        state_policy=state_policy,
        statetimeout=_string_field(config, "statetimeout", default="", name=name),
        adaptivestart=_string_field(config, "adaptivestart", default="", name=name),
        adaptiveend=_string_field(config, "adaptiveend", default="", name=name),
        gateway=_string_field(config, "gateway", default="", name=name),
        divert_to=_string_field(config, "divert_to", default="", name=name),
        replyto=_string_field(config, "replyto", default="", name=name),
        disablereplyto=disablereplyto,
        categories=categories,
        tag=_string_field(config, "tag", default="", name=name),
        tagged=_string_field(config, "tagged", default="", name=name),
        icmptype=_string_field(config, "icmptype", default="", name=name),
        icmp6type=_string_field(config, "icmp6type", default="", name=name),
        tcpflags1=_string_field(config, "tcpflags1", default="", name=name),
        tcpflags2=_string_field(config, "tcpflags2", default="", name=name),
        tcpflags_any=tcpflags_any,
        max=_string_field(config, "max", default="", name=name),
        max_src_conn=_string_field(config, "max_src_conn", default="", name=name),
        max_src_conn_rate=_string_field(config, "max_src_conn_rate", default="", name=name),
        max_src_conn_rates=_string_field(config, "max_src_conn_rates", default="", name=name),
        max_src_nodes=_string_field(config, "max_src_nodes", default="", name=name),
        max_src_states=_string_field(config, "max_src_states", default="", name=name),
        overload=_string_field(config, "overload", default="", name=name),
        prio=_string_field(config, "prio", default="", name=name),
        prio_group=_string_field(config, "prio_group", default="", name=name),
        set_prio=_string_field(config, "set_prio", default="", name=name),
        set_prio_low=_string_field(config, "set_prio_low", default="", name=name),
        tos=_string_field(config, "tos", default="", name=name),
        udp_first=_string_field(config, "udp_first", default="", name=name),
        udp_multiple=_string_field(config, "udp_multiple", default="", name=name),
        udp_single=_string_field(config, "udp_single", default="", name=name),
        nopfsync=nopfsync,
        nosync=nosync,
        allowopts=allowopts,
    )


def _require_bool(config: dict[str, Any], field_name: str, *, default: bool, name: str) -> bool:
    value = config.get(field_name, default)
    if not isinstance(value, bool):
        raise ValueError(
            f"firewall_rule '{name}' {field_name} must be a boolean (true/false), "
            f"got {type(value).__name__}"
        )
    return value


def _string_field(config: dict[str, Any], field_name: str, *, default: str, name: str) -> str:
    value = config.get(field_name, default)
    if not isinstance(value, str):
        raise ValueError(
            f"firewall_rule '{name}' {field_name} must be a string, got {type(value).__name__}"
        )
    return value


def _bool_str(value: bool) -> str:
    """Convert a Python bool to OPNsense's ``"0"``/``"1"`` representation."""
    return "1" if value else "0"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FirewallRuleService(BaseService):
    """Service for OPNsense firewall-rule operations via direct API.

    Single MVC controller (``firewall/filter/*``); one service instance
    handles all rules. Every managed rule carries the per-box
    ``infrafoundry`` OPNsense category UUID as a fleet-wide marker (in
    addition to the per-rule identity suffix in ``description``). The
    category is created on demand at first apply and its UUID is cached
    on the service instance.

    The category is **multi-valued** in MVC, so the marker is appended
    to operator-supplied UUIDs rather than replacing them — operators
    can use any number of additional categories without breaking
    InfraFoundry's identity model.
    """

    # Class attribute kept for backward compatibility with existing
    # tests and downstream references; forwards to the module-level
    # constant in ``_category_marker``.
    INFRAFOUNDRY_CATEGORY_NAME = _SHARED_CATEGORY_NAME

    def __init__(self, client: Any) -> None:
        """Initialize the service and prepare the per-instance category cache."""
        super().__init__(client)
        # Per-instance fast-path cache: once an instance has resolved
        # the category UUID via the shared helper, subsequent calls on
        # the same instance skip even the helper's dict lookup. The
        # process-wide cache and the search+create critical section
        # both live in ``_category_marker``.
        self._category_uuid: str | None = None

    # ------------------------------------------------------------------
    # Category bootstrap (fleet-wide marker)
    # ------------------------------------------------------------------

    def _ensure_infrafoundry_category(self) -> str:
        """Return the UUID of the ``infrafoundry`` category, creating it if absent.

        Thin wrapper around the shared
        ``_category_marker.ensure_infrafoundry_category`` helper. The
        helper holds the process-wide cache and the lock that
        serializes the search+create critical section across concurrent
        callers (#746) — both ``FirewallRuleService`` and
        ``NATRuleService`` delegate here, so a single ``addItem`` ever
        fires per OPNsense box per process even if dispatch ever
        becomes concurrent.

        The per-instance ``self._category_uuid`` cache is preserved as
        a fast-path: an instance that has already resolved the UUID
        does not pay even the helper's dict-lookup cost on subsequent
        calls.

        Returns:
            UUID string for the OPNsense category named ``infrafoundry``.

        Raises:
            InfraFoundryError: If neither search nor create yields a
                UUID (propagated unchanged from the helper).
        """
        if self._category_uuid is not None:
            return self._category_uuid

        uuid = ensure_infrafoundry_category(self.client)
        self._category_uuid = uuid
        return uuid

    def _payload_with_category(self, rule: FirewallRuleConfig) -> dict[str, Any]:
        """Build the API payload for a rule with the InfraFoundry category appended.

        **Append, not overwrite** — ``categories`` is multi-valued in
        MVC. Operator-supplied UUIDs are joined with the
        ``infrafoundry`` marker UUID into a comma-separated string
        (OPNsense's wire format for multi-valued select fields).
        """
        payload = rule.to_payload()
        marker_uuid = self._ensure_infrafoundry_category()
        # Preserve operator-supplied order; append the marker at the end
        # if not already present.
        existing = list(rule.categories)
        if marker_uuid not in existing:
            existing.append(marker_uuid)
        payload["rule"]["categories"] = ",".join(existing)
        return payload

    # ------------------------------------------------------------------
    # API operations (CRUD + apply + savepoint)
    # ------------------------------------------------------------------

    def search(self) -> list[LiveFirewallRule]:
        """Fetch the live rule list.

        Returns:
            ``LiveFirewallRule`` instances normalized from the search
            rows.

        Raises:
            OpnsenseDriftError: If any row has a malformed identity tag.
        """
        response = self.client.request("POST", f"{_FILTER_BASE}/searchRule")
        rows: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw_rows = response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]
        return [_row_to_live(row) for row in rows]

    def search_tolerant(self) -> list[LiveFirewallRule]:
        """Migrate-only variant of :meth:`search` that tolerates a missing controller.

        Some OPNsense builds may ship without the ``firewall/filter`` MVC
        controller. For ``export_to_yaml`` — which feeds
        ``foundry config migrate`` — a missing controller must not abort
        the entire extraction; instead, the migrate should produce an
        empty resource list and log a WARNING so the operator knows what
        was skipped. Other ``APIError`` status codes (5xx, 401/403, etc.)
        propagate unchanged.

        The strict :meth:`search` (used by apply-time logic) keeps
        loud-fail semantics: a missing controller at apply time is a
        real error.

        Returns:
            ``LiveFirewallRule`` instances from the box, or ``[]`` when
            the controller responds with HTTP 404.
        """
        try:
            return self.search()
        except APIError as exc:
            if exc.status_code == 404:
                logger.warning(
                    "OPNsense firewall filter controller is not available "
                    "(HTTP 404 on %s/searchRule); skipping during migrate.",
                    _FILTER_BASE,
                )
                return []
            raise

    def add(self, rule: FirewallRuleConfig) -> dict[str, Any]:
        """Create a firewall rule.

        Args:
            rule: Desired-state rule configuration.

        Returns:
            API response dict.
        """
        return self.client.request(
            "POST",
            f"{_FILTER_BASE}/addRule",
            data=self._payload_with_category(rule),
        )

    def update(self, uuid: str, rule: FirewallRuleConfig) -> dict[str, Any]:
        """Update an existing firewall rule by UUID."""
        return self.client.request(
            "POST",
            f"{_FILTER_BASE}/setRule/{uuid}",
            data=self._payload_with_category(rule),
        )

    def delete(self, uuid: str) -> dict[str, Any]:
        """Delete a firewall rule by UUID."""
        return self.client.request("POST", f"{_FILTER_BASE}/delRule/{uuid}")

    def apply_changes(self) -> dict[str, Any]:
        """Apply pending firewall changes (commit staged config to running system)."""
        return self.client.request("POST", f"{_FILTER_BASE}/apply")

    def savepoint(self) -> dict[str, Any]:
        """Create a transactional rollback savepoint.

        Exposed for operator/manual use only — not auto-wired into the
        apply flow per ADR-0014's default rollback strategy (rely on
        per-call server-side validation; OPNsense's auto-snapshot is
        the residual safety net).
        """
        return self.client.request("POST", f"{_FILTER_BASE}/savepoint")

    # ------------------------------------------------------------------
    # Diff + apply orchestration
    # ------------------------------------------------------------------

    def compute_diff(
        self,
        desired: list[FirewallRuleConfig],
        live: list[LiveFirewallRule],
        *,
        add_only: bool = False,
    ) -> Diff:
        """Compute the add/update/delete diff."""
        return compute_diff(desired, live, add_only=add_only)

    def apply_diff(self, diff: Diff) -> dict[str, int]:
        """Dispatch the operations in ``diff`` and apply pending changes.

        ``apply`` is called once if any mutation occurred, mirroring
        the single-controller granularity of the OPNsense API.

        Returns:
            ``{"created": N, "updated": M, "deleted": K}`` counts.
        """
        created = 0
        updated = 0
        deleted = 0

        for rule in diff.adds:
            self.add(rule)
            created += 1

        for live_rule, want in diff.updates:
            self.update(live_rule.uuid, want)
            updated += 1

        for live_rule in diff.deletes:
            self.delete(live_rule.uuid)
            deleted += 1

        if created or updated or deleted:
            self.apply_changes()

        return {"created": created, "updated": updated, "deleted": deleted}

    # ------------------------------------------------------------------
    # Migration / export
    # ------------------------------------------------------------------

    def export_to_yaml(self) -> str:
        """Export the current managed firewall rules to InfraFoundry YAML.

        Only managed rules (those with the InfraFoundry identity suffix)
        are exported. The ``infrafoundry`` marker UUID is filtered out
        of ``categories`` so the round-tripped YAML reflects the
        operator's view (any operator-supplied UUIDs survive).

        Uses :meth:`search_tolerant` so a missing ``firewall/filter``
        controller (HTTP 404) does not abort the entire migrate — the
        export degrades to an empty resource list with a WARNING log.

        Output is the nested ``opnsense:`` schema defined by ADR-0016
        (#793 Phase 4); firewall rules land at ``opnsense.firewall.rules``
        as a YAML sequence.

        Returns:
            YAML string with the nested ``opnsense:`` namespace and a
            ``firewall.rules`` list leaf.
        """
        rules: list[LiveFirewallRule] = self.search_tolerant()
        managed = [r for r in rules if r.managed_name is not None]
        marker_uuid = self._category_uuid  # may be None if cache cold
        entries = [
            {
                "name": r.managed_name,
                "config": _live_to_export_config(r, marker_uuid),
            }
            for r in managed
        ]
        return emit_nested_list_yaml("firewall.rules", entries)


# ---------------------------------------------------------------------------
# Internal helpers (row parsing / export)
# ---------------------------------------------------------------------------


def _row_to_live(row: dict[str, Any]) -> LiveFirewallRule:
    """Normalize a ``searchRule`` row into a ``LiveFirewallRule``.

    Parses the ``description`` field for the InfraFoundry identity
    suffix. Raises ``OpnsenseDriftError`` (via ``parse_identity``) if
    the suffix marker is present but malformed.
    """
    uuid = str(row.get("uuid", ""))
    description = str(row.get("description", "") or "")
    managed_name, user_description = parse_identity(description)
    return LiveFirewallRule(
        uuid=uuid,
        managed_name=managed_name,
        description=user_description,
        raw=row,
    )


def _live_to_export_config(live: LiveFirewallRule, marker_uuid: str | None) -> dict[str, Any]:
    """Build a YAML-friendly config dict from a managed live rule.

    Hyphenated wire keys are mapped back to underscored YAML keys via
    ``_PAYLOAD_FIELD_MAP``. The ``infrafoundry`` marker UUID is removed
    from ``categories`` so the export reflects the operator's intent.
    """
    raw = live.raw
    config: dict[str, Any] = {}
    for attr, wire_key, kind in _PAYLOAD_FIELD_MAP:
        if attr == "description":
            config["description"] = live.description
            continue
        normalized = _normalize_field(raw.get(wire_key))
        if kind == "bool":
            config[attr] = normalized == "1"
        elif kind == "int":
            try:
                config[attr] = int(normalized) if normalized else DEFAULT_SEQUENCE
            except ValueError:
                config[attr] = DEFAULT_SEQUENCE
        else:
            config[attr] = normalized

    # categories is multi-valued; reconstruct as a sorted list (excluding
    # the marker UUID).
    cats = _normalize_categories(raw.get("categories"))
    if marker_uuid:
        cats.discard(marker_uuid)
    config["categories"] = sorted(cats)
    return config
