"""NAT rule service for OPNsense direct-API operations (ADR-0014, #713, #725).

Manages **outbound**, **1:1**, and **port_forward** NAT rules via the OPNsense
REST API. The 2026-05-04 re-probe of ``opnsense-a`` running ``26.1.6_2``
found that the stock ``DNatController`` (extending ``FilterBaseController`` —
the same base class as ``SourceNatController`` and ``OneToOneController``)
exposes the standard CRUD verbs at ``firewall/d_nat/<action>``. The original
2026-05-03 probe used ``firewall/dnat/...`` (concatenated, no underscore);
the actual URL is the snake-case routing (``D`` + ``Nat`` → ``d_nat``). All
three kinds use the same identity strategy and per-kind diff isolation; the
component manager and apply orchestration are kind-agnostic. See ADR-0013
implementation-order item #2 (#725) for the deferral history.

Identity strategy
-----------------

NAT rules have no clean intrinsic key — two rules can share
``(interface, source, destination, port)`` with completely different
behavior depending on order. ADR-0014 takes no position on a state DB for
direct-API resources, so the only stateless option is encoding identity in
a free-form rule field. The service writes ``description`` as
``<operator-supplied description> [infrafoundry:<resource-name>]`` (or just
``[infrafoundry:<resource-name>]`` when the operator description is empty).
The identity tag is a **suffix** so the operator's free-form text leads the
display in the OPNsense GUI. On read, ``_row_to_live`` parses the suffix
with a strict regex; live rows without the suffix are **unmanaged** and
silently ignored by the diff (not deleted, not updated). Live rows with a
malformed identity tag (wrong position, empty name, extra text after the
tag, etc.) raise ``OpnsenseDriftError`` at plan time.

Every managed rule also carries the OPNsense ``infrafoundry`` category as
a fleet-wide marker (the category is created on demand at first apply and
its UUID is cached per service instance). The category enables a one-click
"show me everything InfraFoundry manages" filter in the OPNsense GUI; the
identity suffix is what carries per-rule resource-name mapping.

Per-kind isolation
------------------

The diff is computed per-kind: ``compute_diff`` accepts a list of mixed-kind
``NATRuleConfig`` and dispatches to a per-kind diff internally, joining the
results into a single ``Diff`` object. An outbound rule named ``foo`` and a
1:1 rule named ``foo`` co-exist as separate identities (different
controllers; same name allowed).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

import yaml

from infrafoundry.core.exceptions import APIError, InfraFoundryError
from infrafoundry.core.provider import ResourceConfig

from ._category_marker import INFRAFOUNDRY_CATEGORY_NAME as _SHARED_CATEGORY_NAME
from ._category_marker import ensure_infrafoundry_category
from .base import BaseService

logger = logging.getLogger(__name__)

# Type alias for NAT rule kinds — the discriminator on every entry.
NATRuleKind = Literal["outbound", "one_to_one", "port_forward"]
ALLOWED_KINDS: tuple[NATRuleKind, ...] = ("outbound", "one_to_one", "port_forward")

# Strict regex for parsing the description-suffix identity tag. The
# (optional) free-form user description leads, followed by whitespace,
# followed by ``\[infrafoundry:<name>\]`` at the end of the string. The
# resource name must be a non-empty match of ``[a-z0-9-]+``; live rows
# without the tag are unmanaged, and rows with a malformed tag — empty
# name, wrong position, trailing text after the tag, etc. — raise
# ``OpnsenseDriftError``. ``_IDENTITY_PROBE`` is a position-agnostic
# detector used both by the parser (to flag malformed tags) and by the
# validator (to reject operator-set descriptions that include the tag
# pattern, since InfraFoundry adds it automatically).
_IDENTITY_PATTERN = re.compile(r"^(?:(.+?)\s+)?\[infrafoundry:([a-z0-9-]+)\]\s*$")
_IDENTITY_PROBE = re.compile(r"\[infrafoundry:[^\]]*\]")

# Outbound endpoint suffix on ``firewall/source_nat`` controller.
_OUTBOUND_BASE = "firewall/source_nat"
# 1:1 endpoint suffix on ``firewall/one_to_one`` controller.
_ONE_TO_ONE_BASE = "firewall/one_to_one"
# Port-forward endpoint suffix on ``firewall/d_nat`` controller. Note the
# snake-case routing: OPNsense's MVC controller is ``DNatController``
# which OPNsense camelCase→snake_case routing renders as ``d_nat`` (not
# ``dnat``). The 2026-05-03 probe missed this and incorrectly concluded the
# controller was absent; the 2026-05-04 re-probe confirmed it ships stock.
_PORT_FORWARD_BASE = "firewall/d_nat"

# Default sequence for new rules — matches the OPNsense schema default.
DEFAULT_SEQUENCE = 100


class OpnsenseDriftError(InfraFoundryError):
    """A managed rule's identity tag is malformed on the live box.

    Raised by the diff engine when a live rule's ``description`` looks like
    it carries an InfraFoundry prefix (begins with ``[infrafoundry:``) but
    does not match the strict identity regex. The operator must repair the
    description in the GUI (or via API) before the next plan/apply.
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
        ``(resource_name, user_description)``. ``resource_name`` is ``None``
        when the description has no tag (unmanaged rule).

    Raises:
        OpnsenseDriftError: If the description contains the
            ``[infrafoundry:...]`` marker but does not match the strict
            suffix-only regex — empty name, uppercase, tag in the middle
            with text after, etc.
    """
    match = _IDENTITY_PATTERN.match(description)
    if match is not None:
        user_desc = match.group(1) or ""
        return match.group(2), user_desc
    if _IDENTITY_PROBE.search(description):
        raise OpnsenseDriftError(
            f"NAT rule description contains an InfraFoundry identity tag but is malformed: "
            f"{description!r}. Expected '<user description> [infrafoundry:<name>]' (or just "
            f"'[infrafoundry:<name>]') where <name> matches [a-z0-9-]+ (non-empty) and the "
            f"tag is the LAST token in the description."
        )
    return None, description


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NATRuleConfig:
    """Desired-state NAT rule configuration.

    Captures all three kinds in a single dataclass; per-kind fields default
    to sentinel values that ``to_payload`` interprets according to ``kind``.

    Attributes:
        name: Operator-facing YAML name; becomes the diff key.
        kind: ``"outbound"``, ``"one_to_one"``, or ``"port_forward"``.
        enabled: Whether the rule is active.
        log: Whether matching packets are logged.
        sequence: Position in the rule list (lower runs earlier).
        interface: Logical interface name (e.g., ``"wan"``).
        description: Operator-facing free-form description (no identity
            prefix; the prefix is added at serialization time).
        lock: Per-resource safety annotation (ADR-0014 §6).

        Outbound-specific:
            ipprotocol: ``"inet"`` or ``"inet6"``.
            protocol: ``"any"``, ``"TCP"``, ``"UDP"``, etc.
            source_net: Alias name, CIDR, or ``"any"``.
            source_not: Negate source.
            source_port: Port (or empty).
            destination_net: Alias name, CIDR, or ``"any"``.
            destination_not: Negate destination.
            destination_port: Port (or empty).
            target: Alias name, IP, or ``"wanip"``.
            target_port: Port (or empty).
            staticnatport: Preserve source port.
            nonat: If True, this is a "do not NAT" exclusion rule.

        1:1-specific:
            type: ``"binat"`` or ``"nat"``.
            external: External IP / alias.
            natreflection: ``""``, ``"enable"``, or ``"disable"``
                (1:1 model accepts these three values).

        Port-forward-specific:
            target: Redirect destination (alias, IP, or ``"wanip"``).
                **Note:** ``target`` is shared with outbound but carries
                different semantics — outbound's ``target`` is the
                source-NAT translation target; port_forward's ``target``
                is the redirect destination IP/alias.
            local_port: Redirect destination port (or alias). Wire
                key is ``local-port`` (hyphenated); converted in payload.
            nordr: "no rdr" — exclude this match from forwarding (deny).
            pass_action: ``""`` (manual), ``"pass"`` (implicit allow rule
                injected), or ``"rule"`` (companion filter rule). Wire
                key is ``pass`` (Python keyword conflict avoided).
            poolopts: Pool selection algorithm (``""`` /
                ``"round-robin"`` / ``"round-robin sticky-address"`` /
                ``"random"`` / ``"random sticky-address"`` /
                ``"source-hash"`` / ``"bitmask"``).
            tag: Free-form rule tag.
            tagged: Match-by-tag selector.
            nosync: Exclude this rule from XMLRPC sync.

            ``natreflection`` is also used by port_forward but with a
            different value set — DNat model accepts ``""`` /
            ``"purenat"`` / ``"disable"`` (note: ``"purenat"``, not
            ``"enable"``). The validator handles per-kind dispatch.
    """

    name: str
    kind: NATRuleKind
    enabled: bool = True
    log: bool = False
    sequence: int = DEFAULT_SEQUENCE
    interface: str = ""
    description: str = ""
    lock: bool = False

    # Outbound fields
    ipprotocol: str = "inet"
    protocol: str = "any"
    source_net: str = "any"
    source_not: bool = False
    source_port: str = ""
    destination_net: str = "any"
    destination_not: bool = False
    destination_port: str = ""
    target: str = ""
    target_port: str = ""
    staticnatport: bool = False
    nonat: bool = False

    # 1:1 fields
    type: str = "binat"
    external: str = ""
    natreflection: str = ""

    # Port-forward-specific fields. ``target`` (redirect destination) is
    # shared with outbound; see class docstring for the semantic note.
    local_port: str = ""
    nordr: bool = False
    pass_action: str = ""
    poolopts: str = ""
    tag: str = ""
    tagged: str = ""
    nosync: bool = False

    @property
    def diff_key(self) -> tuple[NATRuleKind, str]:
        """Per-kind, name-based identity for this rule.

        The kind is part of the key so an outbound rule named ``foo`` and a
        1:1 rule named ``foo`` are independent identities.
        """
        return (self.kind, self.name)

    def encoded_description(self) -> str:
        """Description with the InfraFoundry identity prefix applied."""
        return encode_identity(self.name, self.description)

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the ``addRule``/``setRule`` envelope OPNsense expects.

        Returns:
            ``{"rule": {<fields>}}`` for all three kinds. Field set varies
            by ``kind``. Booleans are stringified to ``"0"``/``"1"`` per
            OPNsense convention.
        """
        if self.kind == "outbound":
            return self._to_outbound_payload()
        if self.kind == "one_to_one":
            return self._to_one_to_one_payload()
        return self._to_port_forward_payload()

    def _to_outbound_payload(self) -> dict[str, Any]:
        return {
            "rule": {
                "enabled": _bool_str(self.enabled),
                "nonat": _bool_str(self.nonat),
                "sequence": str(self.sequence),
                "interface": self.interface,
                "ipprotocol": self.ipprotocol,
                "protocol": self.protocol,
                "source_net": self.source_net,
                "source_not": _bool_str(self.source_not),
                "source_port": self.source_port,
                "destination_net": self.destination_net,
                "destination_not": _bool_str(self.destination_not),
                "destination_port": self.destination_port,
                "target": self.target,
                "target_port": self.target_port,
                "staticnatport": _bool_str(self.staticnatport),
                "log": _bool_str(self.log),
                "description": self.encoded_description(),
            }
        }

    def _to_one_to_one_payload(self) -> dict[str, Any]:
        return {
            "rule": {
                "enabled": _bool_str(self.enabled),
                "log": _bool_str(self.log),
                "sequence": str(self.sequence),
                "interface": self.interface,
                "type": self.type,
                "source_net": self.source_net,
                "source_not": _bool_str(self.source_not),
                "destination_net": self.destination_net,
                "destination_not": _bool_str(self.destination_not),
                "external": self.external,
                "natreflection": self.natreflection,
                "description": self.encoded_description(),
            }
        }

    def _to_port_forward_payload(self) -> dict[str, Any]:
        """Build the ``firewall/d_nat`` payload.

        Wire-side quirks handled here:

        - ``enabled`` (Python) → ``disabled`` (API) with polarity flip.
          OPNsense's DNat schema uses negative semantics on this field
          (matches outbound + 1:1 schemas).
        - ``local_port`` (YAML / dataclass) → ``local-port`` (hyphenated
          API key).
        - ``pass_action`` (Python; ``pass`` is a keyword) → ``pass``
          (API).
        - ``source_net`` / ``source_port`` / ``source_not`` → dotted
          ``source.network`` / ``source.port`` / ``source.not`` (the
          DNat schema uses the dotted shape; outbound + 1:1 use
          underscore-flattened forms).

        Returns:
            ``{"rule": {<dotted-and-hyphenated field names>}}``.
        """
        return {
            "rule": {
                # Polarity flip: enabled=True → disabled="0"
                "disabled": _bool_str(not self.enabled),
                "log": _bool_str(self.log),
                "sequence": str(self.sequence),
                "interface": self.interface,
                "ipprotocol": self.ipprotocol,
                "protocol": self.protocol,
                # DNat schema uses dotted source/destination, not the
                # underscore-flattened source_net/source_port forms used
                # by outbound + 1:1.
                "source.network": self.source_net,
                "source.port": self.source_port,
                "source.not": _bool_str(self.source_not),
                "destination.network": self.destination_net,
                "destination.port": self.destination_port,
                "destination.not": _bool_str(self.destination_not),
                "target": self.target,
                # Hyphenated wire key.
                "local-port": self.local_port,
                "nordr": _bool_str(self.nordr),
                # Python keyword conflict avoided: pass_action → pass.
                "pass": self.pass_action,
                "poolopts": self.poolopts,
                "natreflection": self.natreflection,
                "tag": self.tag,
                "tagged": self.tagged,
                "nosync": _bool_str(self.nosync),
                # ``descr`` is the wire key for port_forward (matches
                # OPNsense's DNat schema), not ``description``. The
                # operator-facing YAML field stays ``description``.
                "descr": self.encoded_description(),
            }
        }


@dataclass(frozen=True)
class LiveNATRule:
    """A NAT rule as currently configured on the OPNsense box.

    Identity-tagged rows have ``managed_name`` set to the parsed resource
    name; unmanaged rows have it set to ``None`` and are filtered out of
    the diff entirely.

    Attributes:
        uuid: OPNsense-assigned rule UUID.
        kind: ``"outbound"`` or ``"one_to_one"``.
        managed_name: Parsed InfraFoundry name (``None`` if unmanaged).
        description: Free-form description with the prefix stripped.
        raw: Full original row dict from ``searchRule`` for field
            comparison during update detection.
    """

    uuid: str
    kind: NATRuleKind
    managed_name: str | None
    description: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Diff:
    """Result of comparing desired YAML state to live OPNsense state.

    Mirrors the surface of ``services.vlan.Diff`` (``adds``/``updates``/
    ``deletes``/``locked``) plus ``is_empty``. Updates carry the live
    record alongside the desired record so the caller has the UUID.
    Locked entries pair desired YAML with their (possibly missing) live
    counterpart.
    """

    adds: list[NATRuleConfig] = field(default_factory=list)
    updates: list[tuple[LiveNATRule, NATRuleConfig]] = field(default_factory=list)
    deletes: list[LiveNATRule] = field(default_factory=list)
    locked: list[tuple[NATRuleConfig, LiveNATRule | None]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there are no add/update/delete operations to apply."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def compute_diff(
    desired: list[NATRuleConfig],
    current: list[LiveNATRule],
    *,
    add_only: bool = False,
) -> Diff:
    """Compare desired YAML state to live state, per-kind.

    Per-kind isolation is the key invariant: an outbound rule named
    ``foo`` never matches a 1:1 rule named ``foo`` even though both share
    the literal ``name``. The diff is computed twice (once per kind) and
    the per-kind results are joined into a single outer ``Diff``.

    Unmanaged live rows (``managed_name is None``) are silently ignored:
    not deleted, not updated, never reported. Rules tagged
    ``[infrafoundry:...]`` but malformed are surfaced as
    ``OpnsenseDriftError`` at parse time, before this function runs.

    Args:
        desired: NAT rules the operator wants to exist (may include both
            kinds).
        current: NAT rules currently on the box (mixed kinds).
        add_only: If True, never emit deletes for managed live rules that
            don't appear in ``desired``. Adds and updates still happen.

    Returns:
        A ``Diff`` with adds/updates/deletes plus locked entries.
    """
    diff = Diff()
    for kind in ALLOWED_KINDS:
        kind_desired = [d for d in desired if d.kind == kind]
        # Filter live rows to (a) this kind, (b) managed rows only.
        kind_live_managed = [
            live for live in current if live.kind == kind and live.managed_name is not None
        ]
        per_kind = _compute_diff_for_kind(kind_desired, kind_live_managed, add_only=add_only)
        diff.adds.extend(per_kind.adds)
        diff.updates.extend(per_kind.updates)
        diff.deletes.extend(per_kind.deletes)
        diff.locked.extend(per_kind.locked)
    return diff


def _compute_diff_for_kind(
    desired: list[NATRuleConfig],
    current_managed: list[LiveNATRule],
    *,
    add_only: bool,
) -> Diff:
    """Single-kind diff. Matches by ``managed_name`` against ``NATRuleConfig.name``."""
    desired_by_name: dict[str, NATRuleConfig] = {d.name: d for d in desired}
    # ``managed_name`` is non-None for every entry in ``current_managed``.
    current_by_name: dict[str, LiveNATRule] = {
        live.managed_name: live for live in current_managed if live.managed_name is not None
    }
    locked_names: set[str] = {d.name for d in desired if d.lock}

    adds: list[NATRuleConfig] = []
    updates: list[tuple[LiveNATRule, NATRuleConfig]] = []
    deletes: list[LiveNATRule] = []
    locked: list[tuple[NATRuleConfig, LiveNATRule | None]] = []

    for name, want in desired_by_name.items():
        have = current_by_name.get(name)
        if want.lock:
            locked.append((want, have))
            continue
        if have is None:
            adds.append(want)
        elif _needs_update(have, want):
            updates.append((have, want))

    if not add_only:
        for name, have in current_by_name.items():
            if name in locked_names:
                continue
            if name not in desired_by_name:
                deletes.append(have)

    return Diff(adds=adds, updates=updates, deletes=deletes, locked=locked)


def _needs_update(have: LiveNATRule, want: NATRuleConfig) -> bool:
    """Return True if the live row's fields differ from the desired payload.

    Compares the inner ``rule`` payload from ``want.to_payload()`` against
    the corresponding fields on ``have.raw``. The OPNsense API returns
    select fields (``interface``, ``protocol``, etc.) as dicts with
    ``selected`` indicators; ``_normalize_field`` collapses both shapes
    to a comparable string.
    """
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
    extract that option and return its key (matching what we'd send
    on update). Empty/None values become ``""``. Plain scalars are
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


# ---------------------------------------------------------------------------
# Resource-to-domain conversion
# ---------------------------------------------------------------------------


def nat_rule_configs_from_resources(
    resources: list[ResourceConfig],
) -> list[NATRuleConfig]:
    """Convert ``ResourceConfig`` entries to ``NATRuleConfig`` instances.

    Validation here is intentionally light — the validator handles
    cross-resource references and operator-friendly error messages; the
    service only enforces type sanity so manager code can rely on field
    invariants.

    Args:
        resources: All provider resources from a ConfigManager load.
            Non-``nat_rules`` entries are silently skipped.

    Returns:
        Validated ``NATRuleConfig`` list.

    Raises:
        ValueError: If an entry has a non-dict config, missing/invalid
            ``kind``, missing per-kind required fields, or non-bool
            booleans / non-int ``sequence`` / forged identity prefix in
            ``description``.
    """
    configs: list[NATRuleConfig] = []
    for resource in resources:
        if resource.type != "nat_rules":
            continue

        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"nat_rule '{resource.name}' has non-dict config")

        kind_raw = config.get("kind")
        if kind_raw not in ALLOWED_KINDS:
            raise ValueError(
                f"nat_rule '{resource.name}' kind must be one of {ALLOWED_KINDS}, got {kind_raw!r}"
            )
        kind: NATRuleKind = kind_raw

        description = config.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"nat_rule '{resource.name}' description must be a string")
        if _IDENTITY_PROBE.search(description):
            raise ValueError(
                f"nat_rule '{resource.name}' description must not contain "
                f"'[infrafoundry:<name>]' — that tag is reserved for InfraFoundry's "
                f"identity suffix, which is added automatically at apply time"
            )

        interface = config.get("interface", "")
        if not isinstance(interface, str):
            raise ValueError(f"nat_rule '{resource.name}' interface must be a string")

        sequence_raw = config.get("sequence", DEFAULT_SEQUENCE)
        try:
            sequence = int(sequence_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"nat_rule '{resource.name}' sequence must be an integer, got {sequence_raw!r}"
            ) from exc

        enabled = _require_bool(config, "enabled", default=True, resource_name=resource.name)
        log = _require_bool(config, "log", default=False, resource_name=resource.name)
        lock = _require_bool(config, "lock", default=False, resource_name=resource.name)

        if kind == "outbound":
            configs.append(
                _build_outbound_config(
                    resource.name,
                    config,
                    enabled=enabled,
                    log=log,
                    lock=lock,
                    sequence=sequence,
                    interface=interface,
                    description=description,
                )
            )
        elif kind == "one_to_one":
            configs.append(
                _build_one_to_one_config(
                    resource.name,
                    config,
                    enabled=enabled,
                    log=log,
                    lock=lock,
                    sequence=sequence,
                    interface=interface,
                    description=description,
                )
            )
        else:
            configs.append(
                _build_port_forward_config(
                    resource.name,
                    config,
                    enabled=enabled,
                    log=log,
                    lock=lock,
                    sequence=sequence,
                    interface=interface,
                    description=description,
                )
            )

    return configs


def _build_outbound_config(
    name: str,
    config: dict[str, Any],
    *,
    enabled: bool,
    log: bool,
    lock: bool,
    sequence: int,
    interface: str,
    description: str,
) -> NATRuleConfig:
    if not interface:
        raise ValueError(f"nat_rule '{name}' (outbound) requires 'interface'")
    target = config.get("target", "")
    if not isinstance(target, str) or not target:
        raise ValueError(f"nat_rule '{name}' (outbound) requires non-empty string 'target'")

    return NATRuleConfig(
        name=name,
        kind="outbound",
        enabled=enabled,
        log=log,
        sequence=sequence,
        interface=interface,
        description=description,
        lock=lock,
        ipprotocol=_string_field(config, "ipprotocol", default="inet", name=name),
        protocol=_string_field(config, "protocol", default="any", name=name),
        source_net=_string_field(config, "source_net", default="any", name=name),
        source_not=_require_bool(config, "source_not", default=False, resource_name=name),
        source_port=_string_field(config, "source_port", default="", name=name),
        destination_net=_string_field(config, "destination_net", default="any", name=name),
        destination_not=_require_bool(config, "destination_not", default=False, resource_name=name),
        destination_port=_string_field(config, "destination_port", default="", name=name),
        target=target,
        target_port=_string_field(config, "target_port", default="", name=name),
        staticnatport=_require_bool(config, "staticnatport", default=False, resource_name=name),
        nonat=_require_bool(config, "nonat", default=False, resource_name=name),
    )


def _build_one_to_one_config(
    name: str,
    config: dict[str, Any],
    *,
    enabled: bool,
    log: bool,
    lock: bool,
    sequence: int,
    interface: str,
    description: str,
) -> NATRuleConfig:
    if not interface:
        raise ValueError(f"nat_rule '{name}' (one_to_one) requires 'interface'")
    external = config.get("external", "")
    if not isinstance(external, str) or not external:
        raise ValueError(f"nat_rule '{name}' (one_to_one) requires non-empty string 'external'")

    type_value = _string_field(config, "type", default="binat", name=name)
    if type_value not in ("binat", "nat"):
        raise ValueError(
            f"nat_rule '{name}' (one_to_one) type must be 'binat' or 'nat', got {type_value!r}"
        )

    natreflection = _string_field(config, "natreflection", default="", name=name)
    if natreflection not in ("", "enable", "disable"):
        raise ValueError(
            f"nat_rule '{name}' (one_to_one) natreflection must be '' / 'enable' / 'disable', "
            f"got {natreflection!r}"
        )

    return NATRuleConfig(
        name=name,
        kind="one_to_one",
        enabled=enabled,
        log=log,
        sequence=sequence,
        interface=interface,
        description=description,
        lock=lock,
        type=type_value,
        external=external,
        source_net=_string_field(config, "source_net", default="any", name=name),
        source_not=_require_bool(config, "source_not", default=False, resource_name=name),
        destination_net=_string_field(config, "destination_net", default="any", name=name),
        destination_not=_require_bool(config, "destination_not", default=False, resource_name=name),
        natreflection=natreflection,
    )


# Closed sets for port-forward enum fields (match the DNat XML model).
_PORT_FORWARD_PASS_ACTIONS = ("", "pass", "rule")
_PORT_FORWARD_POOLOPTS = (
    "",
    "round-robin",
    "round-robin sticky-address",
    "random",
    "random sticky-address",
    "source-hash",
    "bitmask",
)
# Port-forward (DNat) accepts a different ``natreflection`` value set than
# 1:1 — DNat allows "" / "purenat" / "disable"; 1:1 allows
# "" / "enable" / "disable". Per-kind dispatch below.
_PORT_FORWARD_NATREFLECTION = ("", "purenat", "disable")


def _build_port_forward_config(
    name: str,
    config: dict[str, Any],
    *,
    enabled: bool,
    log: bool,
    lock: bool,
    sequence: int,
    interface: str,
    description: str,
) -> NATRuleConfig:
    if not interface:
        raise ValueError(f"nat_rule '{name}' (port_forward) requires 'interface'")
    target = config.get("target", "")
    if not isinstance(target, str) or not target:
        raise ValueError(f"nat_rule '{name}' (port_forward) requires non-empty string 'target'")

    pass_action = _string_field(config, "pass_action", default="", name=name)
    if pass_action not in _PORT_FORWARD_PASS_ACTIONS:
        raise ValueError(
            f"nat_rule '{name}' (port_forward) pass_action must be one of "
            f"{_PORT_FORWARD_PASS_ACTIONS}, got {pass_action!r}"
        )

    poolopts = _string_field(config, "poolopts", default="", name=name)
    if poolopts not in _PORT_FORWARD_POOLOPTS:
        raise ValueError(
            f"nat_rule '{name}' (port_forward) poolopts must be one of "
            f"{_PORT_FORWARD_POOLOPTS}, got {poolopts!r}"
        )

    natreflection = _string_field(config, "natreflection", default="", name=name)
    if natreflection not in _PORT_FORWARD_NATREFLECTION:
        raise ValueError(
            f"nat_rule '{name}' (port_forward) natreflection must be one of "
            f"{_PORT_FORWARD_NATREFLECTION} (note: DNat uses 'purenat' not 'enable'), "
            f"got {natreflection!r}"
        )

    return NATRuleConfig(
        name=name,
        kind="port_forward",
        enabled=enabled,
        log=log,
        sequence=sequence,
        interface=interface,
        description=description,
        lock=lock,
        ipprotocol=_string_field(config, "ipprotocol", default="", name=name),
        protocol=_string_field(config, "protocol", default="", name=name),
        source_net=_string_field(config, "source_net", default="any", name=name),
        source_not=_require_bool(config, "source_not", default=False, resource_name=name),
        source_port=_string_field(config, "source_port", default="", name=name),
        destination_net=_string_field(config, "destination_net", default="any", name=name),
        destination_not=_require_bool(config, "destination_not", default=False, resource_name=name),
        destination_port=_string_field(config, "destination_port", default="", name=name),
        target=target,
        local_port=_string_field(config, "local_port", default="", name=name),
        nordr=_require_bool(config, "nordr", default=False, resource_name=name),
        pass_action=pass_action,
        poolopts=poolopts,
        natreflection=natreflection,
        tag=_string_field(config, "tag", default="", name=name),
        tagged=_string_field(config, "tagged", default="", name=name),
        nosync=_require_bool(config, "nosync", default=False, resource_name=name),
    )


def _require_bool(
    config: dict[str, Any], field_name: str, *, default: bool, resource_name: str
) -> bool:
    value = config.get(field_name, default)
    if not isinstance(value, bool):
        raise ValueError(
            f"nat_rule '{resource_name}' {field_name} must be a boolean (true/false), "
            f"got {type(value).__name__}"
        )
    return value


def _string_field(config: dict[str, Any], field_name: str, *, default: str, name: str) -> str:
    value = config.get(field_name, default)
    if not isinstance(value, str):
        raise ValueError(
            f"nat_rule '{name}' {field_name} must be a string, got {type(value).__name__}"
        )
    return value


def _bool_str(value: bool) -> str:
    """Convert a Python bool to OPNsense's ``"0"``/``"1"`` representation."""
    return "1" if value else "0"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class NATRuleService(BaseService):
    """Service for OPNsense NAT-rule operations via direct API.

    Two controllers, one service: outbound rules go through
    ``firewall/source_nat`` and 1:1 rules go through ``firewall/one_to_one``.
    Each public method dispatches on ``kind`` so the manager has a single
    surface to call.

    Every managed rule carries a fleet-wide ``infrafoundry`` OPNsense
    category as a broad marker (in addition to the per-rule identity suffix
    in ``description``). The category is created on demand at first apply
    and its UUID is cached on the service instance.
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
    # Per-kind endpoint helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _base_for(kind: NATRuleKind) -> str:
        if kind == "outbound":
            return _OUTBOUND_BASE
        if kind == "one_to_one":
            return _ONE_TO_ONE_BASE
        return _PORT_FORWARD_BASE

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

    def _payload_with_category(self, rule: NATRuleConfig) -> dict[str, Any]:
        """Build the API payload for a rule with the InfraFoundry category injected."""
        payload = rule.to_payload()
        payload["rule"]["categories"] = self._ensure_infrafoundry_category()
        return payload

    # ------------------------------------------------------------------
    # API operations (CRUD + applyChanges)
    # ------------------------------------------------------------------

    def search(self, kind: NATRuleKind) -> list[LiveNATRule]:
        """Fetch the live rule list for one kind.

        Args:
            kind: Which controller to query.

        Returns:
            ``LiveNATRule`` instances normalized from the search rows.

        Raises:
            OpnsenseDriftError: If any row has a malformed identity prefix.
        """
        base = self._base_for(kind)
        response = self.client.request("POST", f"{base}/searchRule")

        rows: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw_rows = response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]

        return [_row_to_live(row, kind) for row in rows]

    def search_all_tolerant(self) -> list[LiveNATRule]:
        """Migrate-only variant of :meth:`search_all` that tolerates per-kind 404s.

        Some OPNsense builds ship without one or more of the NAT MVC
        controllers (e.g., an older or stripped image lacking the
        ``firewall/d_nat`` port-forward controller). For ``export_to_yaml``
        — which feeds ``foundry config migrate`` — a single missing
        controller must not abort the entire extraction; the operator
        should still be able to migrate whichever kinds the box exposes.
        On a 404 from one kind, this method logs a WARNING naming the
        skipped kind and continues with the remaining kinds. Other
        ``APIError`` status codes (5xx, 401/403, etc.) propagate
        unchanged.

        The strict :meth:`search_all` (used by apply-time logic) keeps
        loud-fail semantics: a missing controller at apply time is a
        real error.

        Returns:
            ``LiveNATRule`` instances from every kind that responded
            without a 404; kinds that 404'd contribute zero rows.
        """
        result: list[LiveNATRule] = []
        for kind in ALLOWED_KINDS:
            try:
                result.extend(self.search(kind))
            except APIError as exc:
                if exc.status_code == 404:
                    logger.warning(
                        "OPNsense NAT controller for kind %r is not available "
                        "(HTTP 404 on %s/searchRule); skipping during migrate.",
                        kind,
                        self._base_for(kind),
                    )
                    continue
                raise
        return result

    def search_all(self) -> list[LiveNATRule]:
        """Fetch the live rule list for both kinds, concatenated."""
        result: list[LiveNATRule] = []
        for kind in ALLOWED_KINDS:
            result.extend(self.search(kind))
        return result

    def add(self, rule: NATRuleConfig) -> dict[str, Any]:
        """Create a NAT rule.

        The InfraFoundry category UUID is injected into the payload so every
        managed rule carries the fleet-wide marker (in addition to the
        identity suffix in ``description``).

        Args:
            rule: Desired-state rule configuration.

        Returns:
            API response dict.
        """
        base = self._base_for(rule.kind)
        return self.client.request(
            "POST", f"{base}/addRule", data=self._payload_with_category(rule)
        )

    def update(self, uuid: str, rule: NATRuleConfig) -> dict[str, Any]:
        """Update an existing NAT rule by UUID.

        The InfraFoundry category UUID is injected into the payload (same
        reason as ``add``).

        Args:
            uuid: OPNsense-assigned rule UUID.
            rule: New desired-state configuration.

        Returns:
            API response dict.
        """
        base = self._base_for(rule.kind)
        return self.client.request(
            "POST", f"{base}/setRule/{uuid}", data=self._payload_with_category(rule)
        )

    def delete(self, uuid: str, kind: NATRuleKind) -> dict[str, Any]:
        """Delete a NAT rule by UUID.

        Args:
            uuid: OPNsense-assigned rule UUID.
            kind: Which controller to call (outbound vs 1:1).

        Returns:
            API response dict.
        """
        base = self._base_for(kind)
        return self.client.request("POST", f"{base}/delRule/{uuid}")

    def apply_changes(self, kind: NATRuleKind) -> dict[str, Any]:
        """Apply pending NAT changes (commit staged config to running system).

        OPNsense's ``firewall/source_nat`` and ``firewall/one_to_one``
        controllers use ``apply`` (vs. ``reconfigure`` for VLANs and
        ``applyChanges`` for some other controllers). Confirmed live on
        26.1.6_2 — ``applyChanges`` 404s on these specific controllers.
        Must be called after add/update/delete to activate.
        """
        base = self._base_for(kind)
        return self.client.request("POST", f"{base}/apply")

    # ------------------------------------------------------------------
    # Diff + apply orchestration
    # ------------------------------------------------------------------

    def compute_diff(
        self,
        desired: list[NATRuleConfig],
        live: list[LiveNATRule],
        *,
        add_only: bool = False,
    ) -> Diff:
        """Compute the add/update/delete diff (per-kind, joined)."""
        return compute_diff(desired, live, add_only=add_only)

    def apply_diff(self, diff: Diff) -> dict[str, int]:
        """Dispatch the operations in ``diff`` and apply pending changes.

        Each kind's ``applyChanges`` endpoint is called only if at least
        one mutation of that kind happened, mirroring the per-controller
        granularity of the OPNsense API.

        Returns:
            ``{"created": N, "updated": M, "deleted": K}`` counts.
        """
        created = 0
        updated = 0
        deleted = 0
        kinds_touched: set[NATRuleKind] = set()

        for rule in diff.adds:
            self.add(rule)
            kinds_touched.add(rule.kind)
            created += 1

        for live, want in diff.updates:
            self.update(live.uuid, want)
            kinds_touched.add(want.kind)
            updated += 1

        for live in diff.deletes:
            self.delete(live.uuid, live.kind)
            kinds_touched.add(live.kind)
            deleted += 1

        for kind in kinds_touched:
            self.apply_changes(kind)

        return {"created": created, "updated": updated, "deleted": deleted}

    # ------------------------------------------------------------------
    # Migration / export
    # ------------------------------------------------------------------

    def export_to_yaml(self) -> str:
        """Export the current managed NAT rules to InfraFoundry YAML.

        Only managed rules (those with the InfraFoundry identity prefix)
        are exported — unmanaged rules are intentionally left to the
        operator. Round-trip loss is expected: only the fields the schema
        captures are written; the prefix is stripped from ``description``.

        Uses :meth:`search_all_tolerant` so a missing per-kind controller
        (HTTP 404) does not abort the entire migrate — the kinds that
        respond cleanly are still extracted, with a WARNING log naming
        any kind that was skipped.

        Returns:
            YAML string with ``provider/type/name/config`` entries.
        """
        rules: list[LiveNATRule] = self.search_all_tolerant()
        managed = [r for r in rules if r.managed_name is not None]
        resources = [
            {
                "provider": "opnsense",
                "type": "nat_rules",
                "name": r.managed_name,
                "config": _live_to_export_config(r),
            }
            for r in managed
        ]
        return yaml.safe_dump({"resources": resources}, sort_keys=False)


# ---------------------------------------------------------------------------
# Internal helpers (row parsing / export)
# ---------------------------------------------------------------------------


def _row_to_live(row: dict[str, Any], kind: NATRuleKind) -> LiveNATRule:
    """Normalize a ``searchRule`` row into a ``LiveNATRule``.

    Parses the ``description`` field for the InfraFoundry identity prefix.
    For port_forward rows, the wire field name is ``descr`` (matching the
    DNat schema); outbound and 1:1 use ``description``. Raises
    ``OpnsenseDriftError`` (via ``parse_identity``) if the prefix marker
    is present but malformed.
    """
    uuid = str(row.get("uuid", ""))
    if kind == "port_forward":
        # DNat schema uses ``descr``; fall back to ``description`` if the
        # row was hand-built (defensive).
        description = str(row.get("descr", row.get("description", "")) or "")
    else:
        description = str(row.get("description", "") or "")
    managed_name, user_description = parse_identity(description)
    return LiveNATRule(
        uuid=uuid,
        kind=kind,
        managed_name=managed_name,
        description=user_description,
        raw=row,
    )


def _live_to_export_config(live: LiveNATRule) -> dict[str, Any]:
    """Build a YAML-friendly config dict from a managed live rule."""
    raw = live.raw
    if live.kind == "outbound":
        return {
            "kind": "outbound",
            "enabled": _normalize_field(raw.get("enabled")) == "1",
            "interface": _normalize_field(raw.get("interface")),
            "ipprotocol": _normalize_field(raw.get("ipprotocol")) or "inet",
            "protocol": _normalize_field(raw.get("protocol")) or "any",
            "source_net": _normalize_field(raw.get("source_net")) or "any",
            "source_port": _normalize_field(raw.get("source_port")),
            "destination_net": _normalize_field(raw.get("destination_net")) or "any",
            "destination_port": _normalize_field(raw.get("destination_port")),
            "target": _normalize_field(raw.get("target")),
            "target_port": _normalize_field(raw.get("target_port")),
            "staticnatport": _normalize_field(raw.get("staticnatport")) == "1",
            "nonat": _normalize_field(raw.get("nonat")) == "1",
            "log": _normalize_field(raw.get("log")) == "1",
            "description": live.description,
        }
    if live.kind == "one_to_one":
        return {
            "kind": "one_to_one",
            "enabled": _normalize_field(raw.get("enabled")) == "1",
            "type": _normalize_field(raw.get("type")) or "binat",
            "interface": _normalize_field(raw.get("interface")),
            "external": _normalize_field(raw.get("external")),
            "source_net": _normalize_field(raw.get("source_net")) or "any",
            "destination_net": _normalize_field(raw.get("destination_net")) or "any",
            "natreflection": _normalize_field(raw.get("natreflection")),
            "log": _normalize_field(raw.get("log")) == "1",
            "description": live.description,
        }
    # port_forward: DNat schema uses dotted source/destination keys and
    # negative ``disabled`` polarity (flipped to operator-facing
    # ``enabled``); ``descr`` rather than ``description``.
    return {
        "kind": "port_forward",
        # disabled="0" → enabled=True, missing/disabled="1" → enabled=False.
        "enabled": _normalize_field(raw.get("disabled")) != "1",
        "interface": _normalize_field(raw.get("interface")),
        "ipprotocol": _normalize_field(raw.get("ipprotocol")),
        "protocol": _normalize_field(raw.get("protocol")),
        "source_net": _normalize_field(raw.get("source.network")) or "any",
        "source_port": _normalize_field(raw.get("source.port")),
        "destination_net": _normalize_field(raw.get("destination.network")) or "any",
        "destination_port": _normalize_field(raw.get("destination.port")),
        "target": _normalize_field(raw.get("target")),
        "local_port": _normalize_field(raw.get("local-port")),
        "nordr": _normalize_field(raw.get("nordr")) == "1",
        "pass_action": _normalize_field(raw.get("pass")),
        "poolopts": _normalize_field(raw.get("poolopts")),
        "natreflection": _normalize_field(raw.get("natreflection")),
        "tag": _normalize_field(raw.get("tag")),
        "tagged": _normalize_field(raw.get("tagged")),
        "nosync": _normalize_field(raw.get("nosync")) == "1",
        "log": _normalize_field(raw.get("log")) == "1",
        "description": live.description,
    }
