"""NAT rule service for OPNsense direct-API operations (ADR-0014, #713).

Manages **outbound** and **1:1** NAT rules via the OPNsense REST API. Port
forwards are intentionally out of scope: live probe (2026-05-03) of
``opnsense-a`` running ``26.1.6_2`` confirmed that ``firewall/{redirect,
forward, portforward, nat_forward, rdr}/searchRule`` all return 404 and the
legacy ``<nat>/<rule>`` config.xml section is GUI-only. Port forwards become a
follow-up spike-driven issue. See the issue body and ADR-0013 for the
deferral rationale.

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

import re
from dataclasses import dataclass, field
from typing import Any, Literal

import yaml

from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.provider import ResourceConfig

from .base import BaseService

# Type alias for NAT rule kinds — the discriminator on every entry.
NATRuleKind = Literal["outbound", "one_to_one"]
ALLOWED_KINDS: tuple[NATRuleKind, ...] = ("outbound", "one_to_one")

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

    Captures both kinds in a single dataclass; per-kind fields default to
    sentinel values that ``to_payload`` interprets according to ``kind``.

    Attributes:
        name: Operator-facing YAML name; becomes the diff key.
        kind: ``"outbound"`` or ``"one_to_one"``.
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
            natreflection: ``""``, ``"enable"``, or ``"disable"``.
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
            ``{"rule": {<fields>}}`` for both kinds. Field set varies by
            ``kind``. Booleans are stringified to ``"0"``/``"1"`` per
            OPNsense convention.
        """
        if self.kind == "outbound":
            return self._to_outbound_payload()
        return self._to_one_to_one_payload()

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
        else:
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

    # Name of the OPNsense category created/used as the fleet-wide marker
    # for InfraFoundry-managed rules.
    INFRAFOUNDRY_CATEGORY_NAME = "infrafoundry"

    def __init__(self, client: Any) -> None:
        """Initialize the service and prepare the per-instance category cache."""
        super().__init__(client)
        # UUID of the OPNsense ``infrafoundry`` category, looked up or created
        # lazily on the first add/update via ``_ensure_infrafoundry_category``.
        self._category_uuid: str | None = None

    # ------------------------------------------------------------------
    # Per-kind endpoint helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _base_for(kind: NATRuleKind) -> str:
        if kind == "outbound":
            return _OUTBOUND_BASE
        return _ONE_TO_ONE_BASE

    # ------------------------------------------------------------------
    # Category bootstrap (fleet-wide marker)
    # ------------------------------------------------------------------

    def _ensure_infrafoundry_category(self) -> str:
        """Return the UUID of the ``infrafoundry`` category, creating it if absent.

        The lookup is cached on the service instance so multiple add/update
        calls in a single apply pay one round-trip total. Cache is per
        instance; long-lived service objects across multiple environments
        would need to invalidate manually, but the ``from_environment``
        factory builds a fresh service per env so that's not a concern in
        production.

        Returns:
            UUID string for the OPNsense category named ``infrafoundry``.

        Raises:
            InfraFoundryError: If neither search nor create yields a UUID.
        """
        if self._category_uuid is not None:
            return self._category_uuid

        search_response = self.client.request("POST", "firewall/category/searchItem")
        rows: list[dict[str, Any]] = []
        if isinstance(search_response, dict):
            raw_rows = search_response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]
        for row in rows:
            if row.get("name") == self.INFRAFOUNDRY_CATEGORY_NAME:
                uuid = str(row.get("uuid", ""))
                if uuid:
                    self._category_uuid = uuid
                    return uuid

        add_response = self.client.request(
            "POST",
            "firewall/category/addItem",
            data={
                "category": {
                    "name": self.INFRAFOUNDRY_CATEGORY_NAME,
                    "auto": "0",
                    "color": "",
                }
            },
        )
        if isinstance(add_response, dict):
            uuid = str(add_response.get("uuid", ""))
            if uuid:
                self._category_uuid = uuid
                return uuid

        raise InfraFoundryError(
            f"Failed to ensure '{self.INFRAFOUNDRY_CATEGORY_NAME}' category exists on "
            f"OPNsense; addItem response: {add_response!r}"
        )

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

        Returns:
            YAML string with ``provider/type/name/config`` entries.
        """
        rules: list[LiveNATRule] = self.search_all()
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
    Raises ``OpnsenseDriftError`` (via ``parse_identity``) if the prefix
    marker is present but malformed.
    """
    uuid = str(row.get("uuid", ""))
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
