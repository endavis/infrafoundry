"""Interface-assignment service for OPNsense direct-API operations (ADR-0014, #720).

This service provides full CRUD for OPNsense interface assignments via
the in-tree gist-derived REST controller (see
``providers/opnsense/extensions/interface_assignments/AssignSettingsController.php``).
The OPNsense GUI's "Interfaces → Assignments" page edits ``config.xml``
via legacy PHP form posts; no stock REST write endpoint exists, so we
ship a forked + extended PHP controller and drive it over the standard
``/api/interfaces/assign_settings/<command>`` surface.

Read path: ``client.request("GET", "interfaces/overview/interfacesInfo")``
returns ``{"rows": [...]}`` where each row carries ``identifier``
(logical interface name like ``lan``/``wan``/``opt1``), ``device``
(physical NIC or VLAN child), ``description``, ``ipv4``/``ipv6`` (raw
dicts), ``is_physical``, and others. Rows with empty ``identifier``
are physical NICs that are not assigned to any logical interface — the
service skips them.

Write path: the controller exposes ``addItem``, ``setItem`` (in-place
update), ``delItem``, ``getItem``, and ``searchItem``. Each call
triggers ``interface reconfigure all`` on the box server-side via
configd, so there is **no end-of-batch reconfigure step** (differs
from VLAN's pattern).

Diff identity is the logical interface name (``InterfaceAssignmentConfig.
diff_key = name``); that's the intrinsic key on a box. ``lock: true``
in the YAML config block marks an entry as observed-but-untouchable —
the diff engine records the matching live record under ``Diff.locked``
but never adds, updates, or deletes it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from infrafoundry.core.provider import ResourceConfig

from .base import BaseService

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# OPNsense's MVC URL routing converts ``AssignSettingsController`` to
# ``assign_settings`` (snake_case). The live REST path therefore has the
# underscore.
_ASSIGN_ENDPOINT_PREFIX = "interfaces/assign_settings"

# Closed sets of supported IPv4/IPv6 modes (the fork's PHP controller
# rejects anything outside this set with a server-side 400).
_IPV4_TYPES: tuple[str, ...] = ("static", "dhcp", "none")
_IPV6_TYPES: tuple[str, ...] = ("static", "dhcp", "track-interface", "none")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveInterfaceAssignment:
    """An interface assignment as currently configured on the OPNsense box.

    Attributes:
        identifier: Logical interface name (e.g., ``"lan"``, ``"wan"``,
            ``"opt1"``). Used as the resource ``name`` in YAML.
        device: Physical NIC or VLAN child device (e.g., ``"ixl0"``,
            ``"ixl0_vlan4000"``).
        description: Free-form description from the GUI.
        is_physical: ``True`` if ``device`` is a real NIC (not a VLAN
            child).
        ipv4: Raw ipv4 config from the API (mode, address, gateway,
            etc.).
        ipv6: Raw ipv6 config from the API.
        macaddr: Effective MAC address.
        mtu: Configured MTU (0 if unset).
    """

    identifier: str
    device: str
    description: str
    is_physical: bool
    ipv4: dict[str, Any]
    ipv6: dict[str, Any]
    macaddr: str
    mtu: int

    @property
    def diff_key(self) -> str:
        """Identity on the box: the logical interface name (e.g. 'opt3')."""
        return self.identifier


@dataclass(frozen=True)
class InterfaceAssignmentConfig:
    """Desired-state interface-assignment configuration.

    The diff key is the logical interface name (``opt3``, ``lan``,
    etc.); that's the intrinsic identity of an assignment on a box,
    matching the operator-facing YAML ``name``.

    Attributes:
        name: Operator-facing identifier; equals ``identifier`` on the
            box.
        device: Physical NIC or VLAN child device.
        description: Free-form description.
        enabled: Whether the interface is enabled on the box.
            Defaults to ``True``.
        lock: ``True`` marks the entry as observed-but-untouchable;
            the diff engine never adds/updates/deletes a locked
            entry. Defaults to ``False``.
        spoof_mac: Optional MAC override. Emitted as ``spoofMac`` in
            the controller payload when set.
        ipv4_type: IPv4 configuration mode. One of
            ``"static" | "dhcp" | "none"``.
        ipv4_address: Required when ``ipv4_type == "static"``.
        ipv4_subnet: Required when ``ipv4_type == "static"``; CIDR
            prefix length.
        ipv6_type: IPv6 configuration mode. One of
            ``"static" | "dhcp" | "track-interface" | "none"``.
        ipv6_address: Required when ``ipv6_type == "static"``.
        ipv6_subnet: Required when ``ipv6_type == "static"``; CIDR
            prefix length.
        ipv6_track: Required when ``ipv6_type == "track-interface"``;
            name of the upstream interface to track (typically
            ``wan``).
    """

    name: str
    device: str
    description: str
    enabled: bool = True
    lock: bool = False
    spoof_mac: str | None = None
    # IPv4 fields
    ipv4_type: str = "none"  # static | dhcp | none
    ipv4_address: str | None = None
    ipv4_subnet: int | None = None
    # IPv6 fields
    ipv6_type: str = "none"  # static | dhcp | track-interface | none
    ipv6_address: str | None = None
    ipv6_subnet: int | None = None
    ipv6_track: str | None = None

    @property
    def diff_key(self) -> str:
        """Identity on the box: the logical interface name (e.g. 'opt3')."""
        return self.name

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the dict shape the PHP controller expects.

        The controller accepts ``{"assign": {<fields>}}`` for both
        ``addItem`` and ``setItem``. ``name`` is forwarded explicitly
        (the controller's explicit-name extension binds the literal
        rather than auto-numbering).

        Returns:
            Dict with a single ``assign`` key whose value carries
            the controller-shape fields.
        """
        assign: dict[str, Any] = {
            "device": self.device,
            "description": self.description,
            "enable": self.enabled,
            "name": self.name,
            "ipv4Type": self.ipv4_type,
            "ipv6Type": self.ipv6_type,
        }
        if self.spoof_mac:
            assign["spoofMac"] = self.spoof_mac
        if self.ipv4_type == "static":
            assign["ipv4Address"] = self.ipv4_address
            assign["ipv4Subnet"] = self.ipv4_subnet
        if self.ipv6_type == "static":
            assign["ipv6Address"] = self.ipv6_address
            assign["ipv6Subnet"] = self.ipv6_subnet
        if self.ipv6_type == "track-interface":
            assign["ipv6Track"] = self.ipv6_track
        return {"assign": assign}


@dataclass
class Diff:
    """Result of comparing desired YAML state to live OPNsense state.

    Attributes:
        adds: New assignments to create.
        updates: ``(live, want)`` pairs that need a ``setItem`` call.
        deletes: Live assignments to remove.
        locked: Locked YAML entries paired with their live
            counterpart (or ``None`` if declared-but-missing).
            Always reported in the plan output, never acted on by
            apply.
    """

    adds: list[InterfaceAssignmentConfig] = field(default_factory=list)
    updates: list[tuple[LiveInterfaceAssignment, InterfaceAssignmentConfig]] = field(
        default_factory=list
    )
    deletes: list[LiveInterfaceAssignment] = field(default_factory=list)
    locked: list[tuple[InterfaceAssignmentConfig, LiveInterfaceAssignment | None]] = field(
        default_factory=list
    )

    @property
    def is_empty(self) -> bool:
        """Return ``True`` if there are no add/update/delete operations to apply."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Resource-to-domain conversion
# ---------------------------------------------------------------------------


def interface_assignment_configs_from_resources(
    resources: list[ResourceConfig],
) -> list[InterfaceAssignmentConfig]:
    """Convert ``ResourceConfig`` entries to ``InterfaceAssignmentConfig`` instances.

    Non-matching resource types are silently skipped. Validation runs
    here as a defensive second check after the validator; values that
    pass validation may still be re-checked here for type sanity so
    manager code can rely on the typed dataclass invariants.

    Args:
        resources: All provider resources from ConfigManager.

    Returns:
        Validated ``InterfaceAssignmentConfig`` list.

    Raises:
        ValueError: If an entry has a non-dict config, missing
            ``device``, non-bool ``enabled``/``lock``, malformed
            ``ipv4``/``ipv6`` block, or an out-of-range subnet.
    """
    configs: list[InterfaceAssignmentConfig] = []
    for resource in resources:
        if resource.type != "interface_assignments":
            continue

        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"interface_assignment '{resource.name}' has non-dict config")

        device = config.get("device")
        if not isinstance(device, str) or not device:
            raise ValueError(f"interface_assignment '{resource.name}' missing string 'device'")

        description = config.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"interface_assignment '{resource.name}' description must be a string")

        enabled_raw = config.get("enabled", True)
        if not isinstance(enabled_raw, bool):
            raise ValueError(f"interface_assignment '{resource.name}' enabled must be a boolean")

        # ``lock`` lives under ``config:`` per ADR-0014 §6 amendment.
        lock_raw = config.get("lock", False)
        if not isinstance(lock_raw, bool):
            raise ValueError(f"interface_assignment '{resource.name}' lock must be a boolean")

        spoof_mac_raw = config.get("spoof_mac")
        if spoof_mac_raw is not None and not isinstance(spoof_mac_raw, str):
            raise ValueError(f"interface_assignment '{resource.name}' spoof_mac must be a string")

        ipv4_type, ipv4_address, ipv4_subnet = _parse_ipv4_block(
            config.get("ipv4", {}), resource.name
        )
        ipv6_type, ipv6_address, ipv6_subnet, ipv6_track = _parse_ipv6_block(
            config.get("ipv6", {}), resource.name
        )

        configs.append(
            InterfaceAssignmentConfig(
                name=resource.name,
                device=device,
                description=description,
                enabled=enabled_raw,
                lock=lock_raw,
                spoof_mac=spoof_mac_raw,
                ipv4_type=ipv4_type,
                ipv4_address=ipv4_address,
                ipv4_subnet=ipv4_subnet,
                ipv6_type=ipv6_type,
                ipv6_address=ipv6_address,
                ipv6_subnet=ipv6_subnet,
                ipv6_track=ipv6_track,
            )
        )

    return configs


def _parse_ipv4_block(block: Any, name: str) -> tuple[str, str | None, int | None]:
    """Parse the ``ipv4`` sub-block of an interface_assignments config.

    Returns:
        ``(type, address, subnet)``. Defaults to
        ``("none", None, None)``.

    Raises:
        ValueError: If the block is non-mapping, the type is
            unsupported, required fields are missing for ``static``,
            or extra fields are supplied for ``dhcp``/``none``.
    """
    # YAML "ipv4:" with no value parses as None — accept and normalize.
    if block is None:
        return ("none", None, None)
    if not isinstance(block, dict):
        raise ValueError(f"interface_assignment '{name}' ipv4 must be a mapping")
    if not block:
        return ("none", None, None)

    ipv4_type = block.get("type", "none")
    if ipv4_type not in _IPV4_TYPES:
        raise ValueError(
            f"interface_assignment '{name}' ipv4.type must be one of: {', '.join(_IPV4_TYPES)}"
        )

    address = block.get("address")
    subnet = block.get("subnet")

    if ipv4_type == "static":
        if not isinstance(address, str) or not address:
            raise ValueError(
                f"interface_assignment '{name}' ipv4.address required when type is 'static'"
            )
        if subnet is None:
            raise ValueError(
                f"interface_assignment '{name}' ipv4.subnet required when type is 'static'"
            )
        try:
            subnet_int = int(subnet)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"interface_assignment '{name}' ipv4.subnet must be an integer 1-32"
            ) from exc
        if not 1 <= subnet_int <= 32:
            raise ValueError(
                f"interface_assignment '{name}' ipv4.subnet {subnet_int} out of range 1-32"
            )
        return ("static", address, subnet_int)

    # dhcp / none — extra fields not allowed.
    if address or subnet is not None:
        raise ValueError(
            f"interface_assignment '{name}' ipv4.address/subnet only valid when type is 'static'"
        )
    return (ipv4_type, None, None)


def _parse_ipv6_block(block: Any, name: str) -> tuple[str, str | None, int | None, str | None]:
    """Parse the ``ipv6`` sub-block of an interface_assignments config.

    Returns:
        ``(type, address, subnet, track)``. Defaults to
        ``("none", None, None, None)``.

    Raises:
        ValueError: If the block is non-mapping, the type is
            unsupported, required fields are missing for ``static``
            or ``track-interface``, or extra fields are supplied for
            ``dhcp``/``none``.
    """
    # YAML "ipv6:" with no value parses as None — accept and normalize.
    if block is None:
        return ("none", None, None, None)
    if not isinstance(block, dict):
        raise ValueError(f"interface_assignment '{name}' ipv6 must be a mapping")
    if not block:
        return ("none", None, None, None)

    ipv6_type = block.get("type", "none")
    if ipv6_type not in _IPV6_TYPES:
        raise ValueError(
            f"interface_assignment '{name}' ipv6.type must be one of: {', '.join(_IPV6_TYPES)}"
        )

    address = block.get("address")
    subnet = block.get("subnet")
    track = block.get("track")

    if ipv6_type == "static":
        if not isinstance(address, str) or not address:
            raise ValueError(
                f"interface_assignment '{name}' ipv6.address required when type is 'static'"
            )
        if subnet is None:
            raise ValueError(
                f"interface_assignment '{name}' ipv6.subnet required when type is 'static'"
            )
        try:
            subnet_int = int(subnet)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"interface_assignment '{name}' ipv6.subnet must be an integer 1-128"
            ) from exc
        if not 1 <= subnet_int <= 128:
            raise ValueError(
                f"interface_assignment '{name}' ipv6.subnet {subnet_int} out of range 1-128"
            )
        return ("static", address, subnet_int, None)

    if ipv6_type == "track-interface":
        if not isinstance(track, str) or not track:
            raise ValueError(
                f"interface_assignment '{name}' ipv6.track required when type is 'track-interface'"
            )
        return ("track-interface", None, None, track)

    # dhcp / none — extra fields not allowed.
    if address or subnet is not None or track:
        raise ValueError(
            f"interface_assignment '{name}' ipv6.address/subnet/track only valid for "
            "type 'static' or 'track-interface'"
        )
    return (ipv6_type, None, None, None)


# ---------------------------------------------------------------------------
# Live → typed projector
# ---------------------------------------------------------------------------


# IPv6 mode tokens that may appear in the ``interfacesInfo`` ``ipaddrv6``
# field. Anything not in this map raises ``ValueError`` (loud failure
# per the #720 plan — operator must explicitly add support or
# exclude).
_IPV6_LIVE_MODE_MAP: dict[str, str] = {
    "": "none",
    "dhcp6": "dhcp",
    "track6": "track-interface",
    "track-interface": "track-interface",
}


def _parse_live_to_config(
    live: LiveInterfaceAssignment, *, lock: bool = False, enabled: bool = True
) -> InterfaceAssignmentConfig:
    """Project a ``LiveInterfaceAssignment`` into a typed ``InterfaceAssignmentConfig``.

    Used by ``_needs_update`` so deep equality compares like-shaped
    typed values rather than mixed live-dict vs. typed-config fields.

    Unmapped IPv4/IPv6 modes (PPPoE, L2TP, GIF, GRE, etc.) raise
    ``ValueError`` rather than silently degrading to ``"none"`` —
    operators must explicitly add support or exclude such interfaces
    from IaC management.

    Args:
        live: Live assignment row from ``interfacesInfo``.
        lock: Forwarded onto the projected typed config (the live
            dict carries no lock metadata).
        enabled: Forwarded onto the projected typed config (the live
            dict has no per-row enabled flag at this level — that
            information lives in ``<interfaces>`` XML).

    Returns:
        Typed ``InterfaceAssignmentConfig`` with the same identity
        (``name == live.identifier``).

    Raises:
        ValueError: If the IPv4 or IPv6 mode strings on the live row
            are not in the supported set.
    """
    ipv4_type, ipv4_address, ipv4_subnet = _project_live_ipv4(live)
    ipv6_type, ipv6_address, ipv6_subnet, ipv6_track = _project_live_ipv6(live)

    spoof_mac = _project_live_spoof_mac(live)

    return InterfaceAssignmentConfig(
        name=live.identifier,
        device=live.device,
        description=live.description,
        enabled=enabled,
        lock=lock,
        spoof_mac=spoof_mac,
        ipv4_type=ipv4_type,
        ipv4_address=ipv4_address,
        ipv4_subnet=ipv4_subnet,
        ipv6_type=ipv6_type,
        ipv6_address=ipv6_address,
        ipv6_subnet=ipv6_subnet,
        ipv6_track=ipv6_track,
    )


def _project_live_ipv4(
    live: LiveInterfaceAssignment,
) -> tuple[str, str | None, int | None]:
    """Project the ``ipv4`` raw dict on a live row to typed (type, address, subnet)."""
    raw = live.ipv4 or {}
    # Mode tokens we accept on read. Anything else surfaces as a loud
    # ValueError (PPPoE, L2TP, GIF, GRE, ...). The historical
    # ``interfacesInfo`` payload uses ``ipaddr`` to carry either a
    # mode keyword (``"dhcp"``) or an actual IP string for static.
    mode_raw = raw.get("ipaddr", "")
    if not isinstance(mode_raw, str):
        mode_raw = ""

    if mode_raw == "":
        return ("none", None, None)
    if mode_raw == "dhcp":
        return ("dhcp", None, None)

    # Anything that looks like a mode keyword we don't support must
    # surface as a loud ValueError before we try to interpret it as
    # an IP address. PPPoE / L2TP / GIF / GRE / etc. land here.
    if _looks_like_mode_keyword(mode_raw):
        raise ValueError(
            f"interface_assignment '{live.identifier}' has unsupported IPv4 mode "
            f"{mode_raw!r}; add explicit support or exclude this interface from IaC"
        )

    # Treat as static — ``ipaddr`` carries the address; ``subnet`` is
    # a separate field on the live dict (controllers normalize it to
    # a string).
    address = mode_raw
    subnet_raw: Any = raw.get("subnet")
    if subnet_raw is None or subnet_raw == "":
        # The address was supplied without a subnet — refuse to guess.
        raise ValueError(
            f"interface_assignment '{live.identifier}' has IPv4 address "
            f"'{address}' but no subnet on the live row; cannot project to typed config"
        )
    try:
        subnet_int = int(subnet_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"interface_assignment '{live.identifier}' live ipv4 subnet "
            f"{subnet_raw!r} is not an integer"
        ) from exc

    return ("static", address, subnet_int)


def _project_live_ipv6(
    live: LiveInterfaceAssignment,
) -> tuple[str, str | None, int | None, str | None]:
    """Project the ``ipv6`` raw dict on a live row to typed (type, address, subnet, track)."""
    raw = live.ipv6 or {}
    mode_raw = raw.get("ipaddrv6", "")
    if not isinstance(mode_raw, str):
        mode_raw = ""

    # Direct mode-keyword mapping first (none / dhcp / track-interface).
    mapped = _IPV6_LIVE_MODE_MAP.get(mode_raw)
    if mapped == "none":
        return ("none", None, None, None)
    if mapped == "dhcp":
        return ("dhcp", None, None, None)
    if mapped == "track-interface":
        track = raw.get("track6-interface")
        if not isinstance(track, str) or not track:
            raise ValueError(
                f"interface_assignment '{live.identifier}' has IPv6 mode "
                "'track-interface' but no track6-interface on the live row"
            )
        return ("track-interface", None, None, track)

    # Anything else either is a static address or an unmapped mode
    # keyword. We treat IPv6-shaped values as static and raise on
    # anything else.
    if _looks_like_mode_keyword(mode_raw):
        raise ValueError(
            f"interface_assignment '{live.identifier}' has unsupported IPv6 mode "
            f"{mode_raw!r}; add explicit support or exclude this interface from IaC"
        )

    address = mode_raw
    subnet_raw: Any = raw.get("subnetv6")
    if subnet_raw is None or subnet_raw == "":
        raise ValueError(
            f"interface_assignment '{live.identifier}' has IPv6 address "
            f"'{address}' but no subnetv6 on the live row; cannot project to typed config"
        )
    try:
        subnet_int = int(subnet_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"interface_assignment '{live.identifier}' live ipv6 subnet "
            f"{subnet_raw!r} is not an integer"
        ) from exc
    return ("static", address, subnet_int, None)


def _project_live_spoof_mac(live: LiveInterfaceAssignment) -> str | None:
    """Return the spoof MAC if the live row carries one in the ipv4/ipv6 raw dict.

    The ``interfacesInfo`` payload doesn't surface ``spoofmac`` directly;
    operators set it in the GUI and the value lives in
    ``<interfaces>`` XML. For projection purposes we treat absence as
    ``None`` and rely on the controller's ``getItem`` for full
    parity when it's needed.
    """
    raw_v4 = live.ipv4 or {}
    spoof = raw_v4.get("spoofmac")
    if isinstance(spoof, str) and spoof:
        return spoof
    raw_v6 = live.ipv6 or {}
    spoof = raw_v6.get("spoofmac")
    if isinstance(spoof, str) and spoof:
        return spoof
    return None


# Mode keywords we deliberately refuse to silently accept. Anything in
# the live ``ipaddr``/``ipaddrv6`` field that matches this regex but
# isn't in the explicit handled set above raises ``ValueError``. The
# pattern intentionally accepts only the legacy mode keywords (no
# digits, no IP-shaped strings).
_MODE_KEYWORD_RE = re.compile(r"^[a-z][a-z0-9_-]+$")


def _looks_like_mode_keyword(value: str) -> bool:
    """Return ``True`` if the value looks like a mode keyword (vs. an IP address).

    Used by the IPv4/IPv6 projectors to decide whether an unrecognized
    value is an IP we should treat as static, or an unsupported mode
    we should raise on. IPv4/IPv6 addresses contain dots or colons,
    so a lowercase token without those is taken as a mode keyword.
    """
    if "." in value or ":" in value:
        return False
    return bool(_MODE_KEYWORD_RE.match(value))


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def _needs_update(have: LiveInterfaceAssignment, want: InterfaceAssignmentConfig) -> bool:
    """Return ``True`` if a live assignment differs enough from desired to setItem.

    Projects the live row to a typed config (``_parse_live_to_config``)
    and compares typed-vs-typed equality on the fields the controller
    can write. This closes the spike's gap (line 686-698 of
    ``interface_assignment_gist_rest.py``) where only ``device`` and
    ``description`` were compared.

    Args:
        have: Live assignment from ``interfacesInfo``.
        want: Desired-state config from YAML.

    Returns:
        ``True`` if the typed projection of ``have`` differs from
        ``want`` on any controller-writable field.

    Raises:
        ValueError: If the live row carries an unmapped IPv4/IPv6
            mode (operator must add support explicitly).
    """
    have_typed = _parse_live_to_config(have, lock=want.lock, enabled=want.enabled)

    # Compare on the fields the controller actually writes.
    return (
        have_typed.device,
        have_typed.description,
        have_typed.spoof_mac,
        have_typed.ipv4_type,
        have_typed.ipv4_address,
        have_typed.ipv4_subnet,
        have_typed.ipv6_type,
        have_typed.ipv6_address,
        have_typed.ipv6_subnet,
        have_typed.ipv6_track,
    ) != (
        want.device,
        want.description,
        want.spoof_mac,
        want.ipv4_type,
        want.ipv4_address,
        want.ipv4_subnet,
        want.ipv6_type,
        want.ipv6_address,
        want.ipv6_subnet,
        want.ipv6_track,
    )


def compute_diff(
    desired: list[InterfaceAssignmentConfig],
    current: list[LiveInterfaceAssignment],
    *,
    add_only: bool = False,
) -> Diff:
    """Compare desired YAML state to live state, keyed by logical name.

    Args:
        desired: Assignments the operator wants to exist.
        current: Assignments the OPNsense box currently has.
        add_only: If ``True``, never emit deletes for live resources
            that don't appear in ``desired``. Adds and updates still
            happen normally. Useful for partial migrations.

    Returns:
        ``Diff`` describing what apply would do. Locked YAML entries
        (``lock: true``) are recorded in ``Diff.locked`` and never
        appear in ``adds``/``updates``/``deletes``.
    """
    desired_by_key: dict[str, InterfaceAssignmentConfig] = {v.diff_key: v for v in desired}
    current_by_key: dict[str, LiveInterfaceAssignment] = {v.diff_key: v for v in current}
    locked_keys: set[str] = {v.diff_key for v in desired if v.lock}

    adds: list[InterfaceAssignmentConfig] = []
    updates: list[tuple[LiveInterfaceAssignment, InterfaceAssignmentConfig]] = []
    deletes: list[LiveInterfaceAssignment] = []
    locked: list[tuple[InterfaceAssignmentConfig, LiveInterfaceAssignment | None]] = []

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


# ---------------------------------------------------------------------------
# Lockout-prevention
# ---------------------------------------------------------------------------


def find_lockout_conflicts(diff: Diff, current: list[LiveInterfaceAssignment]) -> list[str]:
    """Return human-readable messages for any apply-time lockout risks.

    Refuses to apply if a planned ``add`` targets a ``device`` that is
    already bound to another logical interface. For ``setItem``
    (updates), only flags when the device is changing AND the new
    device is bound to a *different* interface than the one being
    updated.

    Args:
        diff: Pending diff from ``compute_diff``.
        current: Current live state (used to look up device bindings).

    Returns:
        List of human-readable conflict messages; empty when no
        conflicts.
    """
    msgs: list[str] = []
    by_device: dict[str, str] = {entry.device: entry.identifier for entry in current}

    for want in diff.adds:
        existing_holder = by_device.get(want.device)
        if existing_holder is not None:
            msgs.append(
                f"add {want.name!r}: device '{want.device}' is already bound to "
                f"'{existing_holder}'. Refusing to apply."
            )

    for live, want in diff.updates:
        if live.device == want.device:
            continue  # device isn't changing
        existing_holder = by_device.get(want.device)
        if existing_holder is not None and existing_holder != want.name:
            msgs.append(
                f"update {want.name!r}: new device '{want.device}' is already bound "
                f"to '{existing_holder}'. Refusing to apply."
            )

    return msgs


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class InterfaceAssignmentService(BaseService):
    """Full-CRUD service for OPNsense interface assignments via direct API.

    The service is environment-agnostic: it operates on the live
    OPNsense box bound to the ``OPNsenseClient`` it was constructed
    with. The PHP controller installed by
    ``providers.opnsense.extensions.interface_assignments.installer``
    must already be present on the box; the manager (one layer up)
    handles ``ensure_installed()`` before the first service call.

    Method names follow ``VlanService`` for cross-component
    consistency. There is no ``reconfigure`` method — each
    ``addItem``/``setItem``/``delItem`` triggers ``interface
    reconfigure all`` server-side via configd.
    """

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------

    # NOTE: ``list`` and ``search`` are defined at the *end* of the class
    # body to avoid shadowing the ``list`` builtin in subsequent type
    # annotations (mypy resolves ``list[...]`` referenced after a
    # ``def list()`` to the method itself with PEP 563 deferred
    # evaluation, breaking type-check). Those methods live below
    # ``export_to_yaml`` for that reason.

    def get(self, identifier: str) -> dict[str, Any]:
        """Fetch a single assignment via the controller's ``getItem`` endpoint.

        Args:
            identifier: Logical interface name (e.g., ``"opt3"``).

        Returns:
            Raw response dict from the controller.
        """
        return self.client.request("GET", f"{_ASSIGN_ENDPOINT_PREFIX}/getItem/{identifier}")

    # ------------------------------------------------------------------
    # Write paths
    # ------------------------------------------------------------------

    def add(self, config: InterfaceAssignmentConfig) -> dict[str, Any]:
        """Create a new interface assignment via the controller's ``addItem`` endpoint.

        Args:
            config: Desired-state configuration.

        Returns:
            API response dict (typically
            ``{"result": "saved", "ifname": "opt5"}``).
        """
        return self.client.request(
            "POST", f"{_ASSIGN_ENDPOINT_PREFIX}/addItem", data=config.to_payload()
        )

    def update(self, identifier: str, config: InterfaceAssignmentConfig) -> dict[str, Any]:
        """Update an existing assignment via the controller's ``setItem`` endpoint.

        Args:
            identifier: Logical interface name (e.g., ``"opt3"``).
            config: New desired-state configuration.

        Returns:
            API response dict.
        """
        return self.client.request(
            "POST",
            f"{_ASSIGN_ENDPOINT_PREFIX}/setItem/{identifier}",
            data=config.to_payload(),
        )

    def delete(self, identifier: str) -> dict[str, Any]:
        """Delete an assignment via the controller's ``delItem`` endpoint.

        Args:
            identifier: Logical interface name (e.g., ``"opt3"``).

        Returns:
            API response dict.
        """
        return self.client.request("POST", f"{_ASSIGN_ENDPOINT_PREFIX}/delItem/{identifier}")

    # ------------------------------------------------------------------
    # Diff + apply orchestration
    # ------------------------------------------------------------------

    def compute_diff(
        self,
        desired: list[InterfaceAssignmentConfig],
        live: list[LiveInterfaceAssignment],
        *,
        add_only: bool = False,
    ) -> Diff:
        """Compute the add/update/delete diff between desired and live state.

        Thin wrapper over the module-level ``compute_diff`` for
        callers that prefer the service-method form.
        """
        return compute_diff(desired, live, add_only=add_only)

    def apply_diff(self, diff: Diff) -> ApplyDiffResult:
        """Dispatch the operations described by ``diff`` to the controller.

        Each ``add``/``update``/``delete`` call triggers ``interface
        reconfigure all`` server-side via configd; there is **no
        end-of-batch reconfigure step**.

        Per ADR-0014 §6 (option-c rollback semantics), the first
        controller failure (HTTP 400 with ``"result": "failed"``)
        stops further ops and returns the partial-success counts in
        the ``ApplyDiffResult``. Operators get a coherent failure
        mode and an explicit list of what succeeded so manual
        continuation is possible.

        Args:
            diff: Pending diff from ``compute_diff``.

        Returns:
            ``ApplyDiffResult`` with per-operation counts plus a
            ``failure_message`` populated when partial application
            occurred.
        """
        result = ApplyDiffResult()

        for cfg in diff.adds:
            response = self.add(cfg)
            if not _is_success(response):
                result.failure_message = _describe_failure(response, f"add {cfg.name}")
                return result
            result.created += 1

        for live, want in diff.updates:
            response = self.update(live.identifier, want)
            if not _is_success(response):
                result.failure_message = _describe_failure(response, f"setItem {want.name}")
                return result
            result.updated += 1

        for live in diff.deletes:
            response = self.delete(live.identifier)
            if not _is_success(response):
                result.failure_message = _describe_failure(response, f"delItem {live.identifier}")
                return result
            result.deleted += 1

        return result

    # ------------------------------------------------------------------
    # Migration / export
    # ------------------------------------------------------------------

    def export_to_yaml(self) -> str:
        """Export the current interface assignments to InfraFoundry YAML.

        Produces a resource-centric YAML document where each row's
        ``identifier`` becomes both ``name`` (operator-facing) and
        the future-state binding key. ``ipv4``/``ipv6`` are emitted
        verbatim from the live raw dicts for forward-compat.

        Returns:
            YAML string suitable for placement under
            ``envs/<env>/resources/`` or
            ``envs/<env>/opnsense/interface_assignments.yaml``.
        """
        live = self.list()
        resources = [
            {
                "provider": "opnsense",
                "type": "interface_assignments",
                "name": entry.identifier,
                "config": {
                    "device": entry.device,
                    "description": entry.description,
                    "enabled": True,
                    "ipv4": entry.ipv4,
                    "ipv6": entry.ipv6,
                },
            }
            for entry in live
        ]
        return yaml.safe_dump({"resources": resources}, sort_keys=False)

    # ------------------------------------------------------------------
    # Read paths (``list`` is defined LAST so it doesn't shadow the
    # builtin in earlier annotations; ``search`` aliases it but must
    # also precede the ``def list()`` so its ``list[...]`` annotation
    # binds to the builtin too)
    # ------------------------------------------------------------------

    def search(self) -> list[LiveInterfaceAssignment]:
        """Alias for ``list()`` — VLAN-style call name for cross-service parity."""
        return self.list()

    def list(self) -> list[LiveInterfaceAssignment]:
        """Return all interface assignments currently configured on the box.

        Skips rows with an empty ``identifier`` — those are physical
        NICs that are not assigned to any logical interface.

        Returns:
            ``LiveInterfaceAssignment`` entries normalized from the
            ``interfacesInfo`` API.
        """
        response = self.client.request("GET", "interfaces/overview/interfacesInfo")

        rows: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw_rows = response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]

        return [_row_to_live_assignment(row) for row in rows if row.get("identifier")]


# ---------------------------------------------------------------------------
# ApplyDiffResult
# ---------------------------------------------------------------------------


@dataclass
class ApplyDiffResult:
    """Counts + optional failure message returned by ``apply_diff``.

    Attributes:
        created: Number of ``addItem`` calls that succeeded.
        updated: Number of ``setItem`` calls that succeeded.
        deleted: Number of ``delItem`` calls that succeeded.
        failure_message: Human-readable description of the first
            failure encountered (option-c rollback). ``None`` when
            apply completed without errors.
    """

    created: int = 0
    updated: int = 0
    deleted: int = 0
    failure_message: str | None = None

    @property
    def succeeded(self) -> bool:
        """Return ``True`` if every planned operation completed without failure."""
        return self.failure_message is None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_live_assignment(row: dict[str, Any]) -> LiveInterfaceAssignment:
    """Normalize an ``interfacesInfo`` row into a ``LiveInterfaceAssignment``."""
    identifier = str(row.get("identifier", ""))
    device = str(row.get("device", ""))
    description = str(row.get("description", "") or "")
    is_physical = bool(row.get("is_physical", False))
    macaddr = str(row.get("macaddr", "") or "")

    ipv4_raw = row.get("ipv4", {})
    ipv4: dict[str, Any] = ipv4_raw if isinstance(ipv4_raw, dict) else {}

    ipv6_raw = row.get("ipv6", {})
    ipv6: dict[str, Any] = ipv6_raw if isinstance(ipv6_raw, dict) else {}

    try:
        mtu = int(row.get("mtu", 0) or 0)
    except (TypeError, ValueError):
        mtu = 0

    return LiveInterfaceAssignment(
        identifier=identifier,
        device=device,
        description=description,
        is_physical=is_physical,
        ipv4=ipv4,
        ipv6=ipv6,
        macaddr=macaddr,
        mtu=mtu,
    )


_SUCCESS_TOKENS: frozenset[str] = frozenset({"saved", "deleted", "ok"})


def _is_success(response: dict[str, Any] | Any) -> bool:
    """Return ``True`` if a controller response indicates success."""
    if not isinstance(response, dict):
        return False
    return response.get("result") in _SUCCESS_TOKENS


def _describe_failure(response: dict[str, Any] | Any, action: str) -> str:
    """Return a human-readable description of a controller failure response."""
    if isinstance(response, dict):
        msg = response.get("errorMessage")
        if isinstance(msg, str) and msg:
            return f"{action}: {msg}"
        return f"{action}: {response}"
    return f"{action}: {response!r}"
