"""Resource types, declared objects, schema checks and live parsers for QNAP config (ADR-0039).

Two config types are managed over the switch's JSON API:

* ``vlan``: key ``id``; fields ``tagged`` and ``untagged`` (lists of ports) and ``absent``.
  The switch has no VLAN name and no separate PVID: a port's untagged VLAN is its PVID.
* ``lacp.group``: key ``group``; fields ``mode`` (the switch's ``AggrMode``, verbatim),
  ``members`` (physical ports) and ``absent``.
* ``port``: key ``port`` (a physical port number); fields ``alias``, ``shutdown``, ``speed``,
  ``duplex``, ``flow_control``, ``fec`` and ``mtu``. A port is never created or deleted, so
  there is no ``absent``; undeclared fields and ports keep their live values.

A port is an integer (a physical port) or ``"lagN"``, the interface of LACP group ``N``,
numbered ``N + StartIndex`` (``lacp/info``). That numbering is taken from the web UI's
code and is not verified on a device.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel

from .client import QnapApiDriftError
from .components.firmware import SchemaFinding

VLAN_TYPE = "vlan"
LACP_TYPE = "lacp.group"
PORT_TYPE = "port"
CONFIG_TYPES = (VLAN_TYPE, LACP_TYPE, PORT_TYPE)
DELETABLE_TYPES = (VLAN_TYPE, LACP_TYPE)
"""Types InfraFoundry can delete; a ``port`` row is released, never deleted."""
VLAN_ADDRESS_PREFIX = "qnap_vlan"
LACP_ADDRESS_PREFIX = "qnap_lacp_group"
PORT_ADDRESS_PREFIX = "qnap_port"
PORTLIST_TIMEOUT = 60
"""Socket timeout of ``PUT portlist``, as the web UI uses."""
LAG_ROW_TYPE = "ieee8023ad"
"""``Type`` of the LACP interface rows ``GET ports`` returns next to the physical ports."""
AUTO_SPEED_WIRE = "autoNegMode"
SPEED_WIRE = {
    "10M": "tenMBPS",
    "100M": "hundredMBPS",
    "1G": "oneGB",
    "2.5G": "twothousandfivehundredMBPS",
    "5G": "fivethousandMBPS",
    "10G": "tenGB",
}
HALF_DUPLEX_SPEEDS = frozenset({"10M", "100M"})
FEC_WIRE = {"auto": "auto", "rs": "RS_FEC", "fc": "FC_FEC", "none": "none"}
FEC_ENABLED_WIRE = frozenset({"auto", "RS_FEC", "FC_FEC"})
FEC_NOT_AVAILABLE = "N/A"
PORT_FIELD_ORDER = ("alias", "shutdown", "speed", "duplex", "flow_control", "fec", "mtu")
VLAN_MIN = 1
VLAN_MAX = 4000
DEFAULT_VLAN_ID = 1

Port = int | str
"""A declared port: a physical port number or ``"lagN"``."""

_LAG_RE = re.compile(r"^lag([1-9][0-9]*)$")
_VLAN_FIELDS = {"id", "tagged", "untagged"}
_LAG_FIELDS = {"group", "mode", "members"}
_PORT_FIELDS = {"port", *PORT_FIELD_ORDER}


def parse_port(value: Any) -> Port:
    """Return a declared port: an integer >= 1 or ``"lagN"`` with ``N`` >= 1.

    Args:
        value: The YAML value.

    Raises:
        ValueError: If the value is neither.
    """
    if isinstance(value, bool):
        raise ValueError("a port is not a boolean")
    if isinstance(value, int):
        if value < 1:
            raise ValueError("a port number must be 1 or more")
        return value
    if isinstance(value, str) and _LAG_RE.match(value):
        return value
    raise ValueError("a port is a number or 'lagN'")


def resolve_port(token: Port, start_index: int) -> int:
    """Return the switch's interface number of a declared port.

    Args:
        token: A physical port number or ``"lagN"``.
        start_index: ``lacp/info.StartIndex``.
    """
    if isinstance(token, int):
        return token
    return int(token[3:]) + start_index


def port_label(number: int, start_index: int) -> str:
    """Return a switch interface number as the YAML spells it (``5`` or ``lag1``)."""
    if number > start_index:
        return f"lag{number - start_index}"
    return str(number)


def _ports_field(value: Any) -> frozenset[Port]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError("must be a list of ports")
    return frozenset(parse_port(item) for item in value)


@dataclass(frozen=True)
class DesiredVlan:
    """A declared VLAN. A ``None`` list is undeclared and keeps the live members."""

    id: int
    resource_name: str
    tagged: frozenset[Port] | None
    untagged: frozenset[Port] | None
    absent: bool = False

    @property
    def key(self) -> tuple[Any, ...]:
        """Identity key of the object."""
        return (self.id,)

    @property
    def type_name(self) -> str:
        """The resource type."""
        return VLAN_TYPE


@dataclass(frozen=True)
class DesiredLag:
    """A declared LACP group. A ``None`` field is undeclared and keeps the live value."""

    group: int
    resource_name: str
    mode: str | None
    members: frozenset[Port] | None
    absent: bool = False

    @property
    def key(self) -> tuple[Any, ...]:
        """Identity key of the object."""
        return (self.group,)

    @property
    def type_name(self) -> str:
        """The resource type."""
        return LACP_TYPE


@dataclass(frozen=True)
class DesiredPort:
    """Declared settings of a physical port. A ``None`` field is undeclared (kept live)."""

    port: int
    resource_name: str
    alias: str | None = None
    shutdown: bool | None = None
    speed: str | None = None
    duplex: str | None = None
    flow_control: bool | None = None
    fec: str | None = None
    mtu: int | None = None

    @property
    def key(self) -> tuple[Any, ...]:
        """Identity key of the object."""
        return (self.port,)

    @property
    def type_name(self) -> str:
        """The resource type."""
        return PORT_TYPE


def _config(resource: ResourceConfig) -> dict[str, Any]:
    config = dict(resource.config or {})
    config.pop("name", None)  # the loaders copy the resource name into the config
    return config


def desired_vlans(resources: Iterable[ResourceConfig]) -> list[DesiredVlan]:
    """Return the declared VLANs.

    Raises:
        ValueError: If a resource has no usable key or list (run ``check_resources`` first).
    """
    out: list[DesiredVlan] = []
    for resource in resources:
        if resource.type != VLAN_TYPE:
            continue
        config = _config(resource)
        vlan_id = config.get("id")
        if isinstance(vlan_id, bool) or not isinstance(vlan_id, int):
            raise ValueError(f"{VLAN_TYPE} '{resource.name}' has no usable id")
        tagged = _ports_field(config["tagged"]) if config.get("tagged") is not None else None
        untagged = _ports_field(config["untagged"]) if config.get("untagged") is not None else None
        out.append(
            DesiredVlan(vlan_id, resource.name, tagged, untagged, bool(config.get("absent", False)))
        )
    return out


def desired_lags(resources: Iterable[ResourceConfig]) -> list[DesiredLag]:
    """Return the declared LACP groups.

    Raises:
        ValueError: If a resource has no usable key or field (run ``check_resources`` first).
    """
    out: list[DesiredLag] = []
    for resource in resources:
        if resource.type != LACP_TYPE:
            continue
        config = _config(resource)
        group = config.get("group")
        if isinstance(group, bool) or not isinstance(group, int):
            raise ValueError(f"{LACP_TYPE} '{resource.name}' has no usable group")
        mode = config.get("mode")
        members = _ports_field(config["members"]) if config.get("members") is not None else None
        out.append(
            DesiredLag(
                group,
                resource.name,
                str(mode) if mode is not None else None,
                members,
                bool(config.get("absent", False)),
            )
        )
    return out


def desired_ports(resources: Iterable[ResourceConfig]) -> list[DesiredPort]:
    """Return the declared port settings.

    Raises:
        ValueError: If a resource has no usable key (run ``check_resources`` first).
    """
    out: list[DesiredPort] = []
    for resource in resources:
        if resource.type != PORT_TYPE:
            continue
        config = _config(resource)
        port = config.get("port")
        if isinstance(port, bool) or not isinstance(port, int) or port < 1:
            raise ValueError(f"{PORT_TYPE} '{resource.name}' has no usable port")
        alias, shutdown = config.get("alias"), config.get("shutdown")
        flow, mtu = config.get("flow_control"), config.get("mtu")
        out.append(
            DesiredPort(
                port,
                resource.name,
                str(alias) if alias is not None else None,
                shutdown if isinstance(shutdown, bool) else None,
                str(config["speed"]) if config.get("speed") is not None else None,
                str(config["duplex"]) if config.get("duplex") is not None else None,
                flow if isinstance(flow, bool) else None,
                str(config["fec"]) if config.get("fec") is not None else None,
                mtu if _is_int(mtu) else None,
            )
        )
    return out


def desired_from_resources(
    resources: list[ResourceConfig],
) -> list[DesiredVlan | DesiredLag | DesiredPort]:
    """Return the declared VLANs, LACP groups and ports; other types are skipped.

    Raises:
        ValueError: If a resource has no usable key (run ``check_resources`` first).
    """
    return [*desired_vlans(resources), *desired_lags(resources), *desired_ports(resources)]


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def check_resources(resources: list[ResourceConfig]) -> list[SchemaFinding]:
    """Check each ``vlan``, ``lacp.group`` and ``port`` resource.

    Args:
        resources: Resources of any type; only the config types are checked.

    Returns:
        Findings; all at ERROR level.
    """
    findings: list[SchemaFinding] = []
    vlan_keys: Counter[int] = Counter()
    lag_keys: Counter[int] = Counter()
    port_keys: Counter[int] = Counter()
    port_mtus: list[int] = []
    untagged_in: dict[Port, int] = {}
    member_of: dict[Port, int] = {}

    def error(resource: ResourceConfig, message: str) -> None:
        findings.append(
            SchemaFinding(
                resource.name,
                ValidationLevel.ERROR,
                f"{resource.type} '{resource.name}': {message}",
            )
        )

    def ports(resource: ResourceConfig, config: dict[str, Any], name: str) -> frozenset[Port]:
        if config.get(name) is None:
            return frozenset()
        try:
            return _ports_field(config[name])
        except ValueError as exc:
            error(resource, f"'{name}' {exc}")
            return frozenset()

    for resource in resources:
        if resource.type not in CONFIG_TYPES:
            continue
        config = _config(resource)
        if resource.type == PORT_TYPE:
            _check_port(resource, config, error, port_keys, port_mtus)
            continue
        absent = config.pop("absent", False)
        if not isinstance(absent, bool):
            error(resource, "'absent' must be true or false")
            absent = False
        if resource.type == VLAN_TYPE:
            _check_vlan(resource, config, absent, error, ports, vlan_keys, untagged_in)
        else:
            _check_lag(resource, config, absent, error, ports, lag_keys, member_of)
    return findings


def _check_vlan(
    resource: ResourceConfig,
    config: dict[str, Any],
    absent: bool,
    error: Any,
    ports: Any,
    keys: Counter[int],
    untagged_in: dict[Port, int],
) -> None:
    unknown = sorted(set(config) - _VLAN_FIELDS)
    if unknown:
        error(resource, "unknown field(s): " + ", ".join(unknown))
    vlan_id = config.get("id")
    if vlan_id is None:
        error(resource, "missing required field(s): id")
        return
    if not _is_int(vlan_id) or not VLAN_MIN <= vlan_id <= VLAN_MAX:
        error(resource, f"'id' must be an integer within {VLAN_MIN}-{VLAN_MAX}")
        return
    if absent:
        if vlan_id == DEFAULT_VLAN_ID:
            error(
                resource, "'absent' is not allowed for VLAN 1; the default VLAN cannot be deleted"
            )
        extra = sorted(set(config) - {"id"})
        if extra:
            error(resource, "'absent' may carry only key fields, got: " + ", ".join(extra))
    tagged = ports(resource, config, "tagged")
    untagged = ports(resource, config, "untagged")
    both = sorted(map(str, tagged & untagged))
    if both and not absent:
        error(resource, "port(s) both tagged and untagged: " + ", ".join(both))
    keys[vlan_id] += 1
    if keys[vlan_id] == 2:
        error(resource, f"duplicate identity key ({vlan_id},)")
    if absent:
        return
    for port in sorted(untagged, key=str):
        other = untagged_in.setdefault(port, vlan_id)
        if other != vlan_id:
            error(resource, f"port {port} is untagged in VLAN {other} and VLAN {vlan_id}")


def _check_lag(
    resource: ResourceConfig,
    config: dict[str, Any],
    absent: bool,
    error: Any,
    ports: Any,
    keys: Counter[int],
    member_of: dict[Port, int],
) -> None:
    unknown = sorted(set(config) - _LAG_FIELDS)
    if unknown:
        error(resource, "unknown field(s): " + ", ".join(unknown))
    group = config.get("group")
    if group is None:
        error(resource, "missing required field(s): group")
        return
    if not _is_int(group) or group < 1:
        error(resource, "'group' must be an integer of 1 or more")
        return
    keys[group] += 1
    if keys[group] == 2:
        error(resource, f"duplicate identity key ({group},)")
    if absent:
        extra = sorted(set(config) - {"group"})
        if extra:
            error(resource, "'absent' may carry only key fields, got: " + ", ".join(extra))
        return
    missing = [n for n in ("mode", "members") if config.get(n) in (None, "")]
    if missing:
        error(resource, "missing required field(s): " + ", ".join(missing))
    mode = config.get("mode")
    if mode is not None and (not isinstance(mode, str) or not mode.strip()):
        error(resource, "'mode' must be a non-empty string")
    members = ports(resource, config, "members")
    lag_members = sorted(str(m) for m in members if isinstance(m, str))
    if lag_members:
        error(resource, "members must be physical ports, not " + ", ".join(lag_members))
    for port in sorted((m for m in members if isinstance(m, int)), key=int):
        other = member_of.setdefault(port, group)
        if other != group:
            error(resource, f"port {port} is a member of group {other} and group {group}")


def _check_port(
    resource: ResourceConfig,
    config: dict[str, Any],
    error: Any,
    keys: Counter[int],
    mtus: list[int],
) -> None:
    unknown = sorted(set(config) - _PORT_FIELDS)
    if "absent" in unknown:
        error(resource, "'absent' is not allowed: a port is never created or deleted")
        unknown.remove("absent")
    if unknown:
        error(resource, "unknown field(s): " + ", ".join(unknown))
    port = config.get("port")
    if port is None:
        error(resource, "missing required field(s): port")
        return
    if not _is_int(port) or port < 1:
        error(
            resource, "'port' must be a physical port number of 1 or more (lagN is not supported)"
        )
        return
    keys[port] += 1
    if keys[port] == 2:
        error(resource, f"duplicate identity key ({port},)")
    alias = config.get("alias")
    if alias is not None and not isinstance(alias, str):
        error(resource, "'alias' must be a string")
    for name in ("shutdown", "flow_control"):
        if config.get(name) is not None and not isinstance(config[name], bool):
            error(resource, f"'{name}' must be true or false")
    speed, duplex = config.get("speed"), config.get("duplex")
    speeds = ["auto", *SPEED_WIRE]
    if speed is not None and speed not in speeds:
        error(resource, "'speed' must be one of " + ", ".join(speeds))
    if duplex is not None:
        if duplex not in ("full", "half"):
            error(resource, "'duplex' must be 'full' or 'half'")
        elif speed is None or speed == "auto":
            error(resource, "'duplex' needs a fixed 'speed' (not auto)")
        elif duplex == "half" and speed not in HALF_DUPLEX_SPEEDS:
            error(resource, "'duplex: half' is allowed only at speed 10M or 100M")
    fec = config.get("fec")
    if fec is not None and fec not in FEC_WIRE:
        error(resource, "'fec' must be one of " + ", ".join(FEC_WIRE))
    mtu = config.get("mtu")
    if mtu is not None:
        if not _is_int(mtu) or mtu < 1:
            error(resource, "'mtu' must be a positive integer")
        else:
            if mtus and mtu != mtus[0]:
                error(resource, f"'mtu' {mtu} differs from {mtus[0]}: the MTU is switch-wide")
            mtus.append(mtu)


# -- live parsers


@dataclass(frozen=True)
class LiveVlan:
    """A VLAN on the switch: ``members`` maps a port interface number to its Tagged flag."""

    id: int
    members: Mapping[int, bool]


@dataclass(frozen=True)
class LiveLag:
    """A LACP group on the switch."""

    group: int
    mode: Any
    members: frozenset[int]
    member_as_str: bool | None
    """Whether ``PortMembers`` holds strings; ``None`` when the group has no members."""


@dataclass(frozen=True)
class LivePort:
    """One row of ``GET ports``. ``raw`` is the whole ``val``, which a write echoes back."""

    key: int
    raw: Mapping[str, Any]

    @property
    def is_lag(self) -> bool:
        """True for a LACP interface row (not a physical port)."""
        return self.raw.get("Type") == LAG_ROW_TYPE

    @property
    def auto_mode(self) -> bool:
        """Whether the port negotiates its speed."""
        return bool(self.raw.get("AutoMode"))

    @property
    def speed(self) -> str:
        """``Speed``: the negotiated speed while ``auto_mode`` is on."""
        return str(self.raw.get("Speed", ""))

    @property
    def fdx(self) -> bool:
        """Whether the port runs full duplex."""
        return bool(self.raw.get("Fdx"))

    @property
    def fec(self) -> str:
        """``FEC`` (``N/A`` when the port has none)."""
        return str(self.raw.get("FEC", ""))

    @property
    def mtu(self) -> int:
        """``MTU``."""
        return int(self.raw.get("MTU", 0))


@dataclass(frozen=True)
class LacpInfo:
    """``lacp/info``: where LAG interface numbers start and the limits."""

    start_index: int
    max_channels: int
    max_ports: int


def _drift(what: str) -> QnapApiDriftError:
    return QnapApiDriftError(f"the switch's '{what}' reply has an unexpected shape")


def _int(value: Any, what: str) -> int:
    if isinstance(value, bool):
        raise _drift(what)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise _drift(what) from exc


def parse_vlans(result: Any) -> list[LiveVlan]:
    """Parse ``GET vlan``.

    A VLAN with no member ports comes back as ``"val": null`` (seen on a real
    switch), which is parsed as no members.

    Raises:
        QnapApiDriftError: If the reply is not a list of
            ``{key, val: [{Port, Tagged}] | null}``.
    """
    if not isinstance(result, list):
        raise _drift("vlan")
    vlans: list[LiveVlan] = []
    for item in result:
        if not isinstance(item, dict) or "val" not in item:
            raise _drift("vlan")
        rows = item["val"] if item["val"] is not None else []
        if not isinstance(rows, list):
            raise _drift("vlan")
        members: dict[int, bool] = {}
        for entry in rows:
            if not isinstance(entry, dict) or not isinstance(entry.get("Tagged"), bool):
                raise _drift("vlan")
            members[_int(entry.get("Port"), "vlan")] = entry["Tagged"]
        vlans.append(LiveVlan(_int(item.get("key"), "vlan"), members))
    return vlans


def parse_lags(result: Any) -> list[LiveLag]:
    """Parse ``GET lacp/group``.

    Raises:
        QnapApiDriftError: If the reply is not a list of ``{key, val: {AggrMode, PortMembers}}``.
    """
    if not isinstance(result, list):
        raise _drift("lacp/group")
    lags: list[LiveLag] = []
    for item in result:
        val = item.get("val") if isinstance(item, dict) else None
        if not isinstance(val, dict) or not isinstance(val.get("PortMembers"), list):
            raise _drift("lacp/group")
        raw = val["PortMembers"]
        as_str: bool | None = None
        if raw:
            as_str = isinstance(raw[0], str)
        lags.append(
            LiveLag(
                _int(item.get("key"), "lacp/group"),
                val.get("AggrMode"),
                frozenset(_int(m, "lacp/group") for m in raw),
                as_str,
            )
        )
    return lags


def parse_lacp_info(result: Any) -> LacpInfo:
    """Parse ``GET lacp/info``.

    Raises:
        QnapApiDriftError: If a limit is missing or not a number.
    """
    if not isinstance(result, dict):
        raise _drift("lacp/info")
    return LacpInfo(
        _int(result.get("StartIndex"), "lacp/info"),
        _int(result.get("MaxPortChannels"), "lacp/info"),
        _int(result.get("MaxPortsPerPortChannel"), "lacp/info"),
    )


_PORT_TYPES: dict[str, type] = {
    "Alias": str,
    "AutoMode": bool,
    "FC": bool,
    "FEC": str,
    "Fdx": bool,
    "Shutdown": bool,
    "Speed": str,
}


def _is_lag_row(item: Any) -> bool:
    val = item.get("val") if isinstance(item, dict) else None
    return isinstance(val, dict) and val.get("Type") == LAG_ROW_TYPE


def count_ports(result: Any) -> int:
    """Return the number of physical ports in ``GET ports``.

    The reply also holds one row per LACP group interface (``Type`` ``ieee8023ad``); those
    are not physical ports and are not counted.

    Raises:
        QnapApiDriftError: If the reply is not a list.
    """
    if not isinstance(result, list):
        raise _drift("ports")
    return sum(1 for item in result if not _is_lag_row(item))


def parse_ports(result: Any) -> list[LivePort]:
    """Parse ``GET ports``, type-checking every physical row (a write echoes the whole row).

    Raises:
        QnapApiDriftError: If the reply is not a list of ``{key, val: {...}}`` or a
            physical row lacks a field this provider reads.
    """
    if not isinstance(result, list):
        raise _drift("ports")
    rows: list[LivePort] = []
    for item in result:
        val = item.get("val") if isinstance(item, dict) else None
        if not isinstance(val, dict):
            raise _drift("ports")
        key = _int(item.get("key"), "ports")
        if val.get("Type") != LAG_ROW_TYPE:
            for name, kind in _PORT_TYPES.items():
                if not isinstance(val.get(name), kind):
                    raise _drift("ports")
            mtu = val.get("MTU")
            if isinstance(mtu, bool) or not isinstance(mtu, int):
                raise _drift("ports")
        rows.append(LivePort(key, dict(val)))
    return rows


# -- write bodies (unverified on a device)


def vlan_body(vlan_id: int, members: Mapping[int, bool]) -> dict[str, Any]:
    """Return the body of ``POST vlan`` / ``PUT vlan``: the complete member list."""
    return {
        "data": [
            {
                "key": str(vlan_id),
                "val": [{"Port": str(p), "Tagged": members[p]} for p in sorted(members)],
            }
        ]
    }


def vlan_delete_body(vlan_id: int) -> dict[str, Any]:
    """Return the body of ``DELETE vlan``: a list of string keys, as the switch's web UI sends."""
    return {"idx": [str(vlan_id)]}


def lag_body(group: int, mode: Any, members: Iterable[int], member_as_str: bool) -> dict[str, Any]:
    """Return the body of ``POST lacp/group`` / ``PUT lacp/group``."""
    ordered = sorted(members)
    return {
        "idx": str(group),
        "data": {
            "AggrMode": mode,
            "PortMembers": [str(m) for m in ordered] if member_as_str else ordered,
        },
    }


def lag_delete_body(group: int) -> dict[str, Any]:
    """Return the body of ``DELETE lacp/group``."""
    return {"idx": [str(group)]}


def port_changed_fields(live: LivePort, desired: DesiredPort) -> tuple[str, ...]:
    """Return the declared fields of ``desired`` that differ from ``live``, in a fixed order.

    ``speed: auto`` is compared against ``AutoMode``, never against ``Speed`` (which holds
    the negotiated speed); a fixed speed matches only with ``AutoMode`` off.
    """
    changed: list[str] = []
    if desired.alias is not None and live.raw.get("Alias") != desired.alias:
        changed.append("alias")
    if desired.shutdown is not None and live.raw.get("Shutdown") is not desired.shutdown:
        changed.append("shutdown")
    if desired.speed == "auto":
        speed_differs = not live.auto_mode
    elif desired.speed is not None:
        speed_differs = live.auto_mode or live.speed != SPEED_WIRE[desired.speed]
    else:
        speed_differs = False
    if speed_differs:
        changed.append("speed")
    if desired.duplex is not None and live.fdx is not (desired.duplex == "full"):
        changed.append("duplex")
    if desired.flow_control is not None and live.raw.get("FC") is not desired.flow_control:
        changed.append("flow_control")
    if desired.fec is not None and live.fec != FEC_WIRE[desired.fec]:
        changed.append("fec")
    if desired.mtu is not None and live.mtu != desired.mtu:
        changed.append("mtu")
    return tuple(changed)


def port_matches(live: LivePort, desired: DesiredPort) -> bool:
    """Return whether every declared field of ``desired`` already holds on ``live``."""
    return not port_changed_fields(live, desired)


def port_write_data(live: LivePort, desired: DesiredPort) -> dict[str, Any]:
    """Return the ``data`` of a ``PUT portlist`` entry: the live ``val`` with the edits applied.

    The web UI sends the whole ``val`` of each changed port. A port in auto mode is sent
    with ``Speed`` ``autoNegMode`` and ``AutoMode`` true. Moving to a fixed speed keeps the
    live duplex unless one is declared; a change from auto, or to a speed without half
    duplex, writes full duplex.
    """
    data = dict(live.raw)
    if desired.alias is not None:
        data["Alias"] = desired.alias
    if desired.shutdown is not None:
        data["Shutdown"] = desired.shutdown
    if desired.flow_control is not None:
        data["FC"] = desired.flow_control
    if desired.fec is not None:
        data["FEC"] = FEC_WIRE[desired.fec]
    if desired.mtu is not None:
        data["MTU"] = desired.mtu
    if desired.speed == "auto" or (desired.speed is None and live.auto_mode):
        data["Speed"], data["AutoMode"] = AUTO_SPEED_WIRE, True
        return data
    data["AutoMode"] = False
    if desired.speed is None:
        return data
    data["Speed"] = SPEED_WIRE[desired.speed]
    if desired.duplex is not None:
        data["Fdx"] = desired.duplex == "full"
    elif live.auto_mode or desired.speed not in HALF_DUPLEX_SPEEDS:
        data["Fdx"] = True
    return data


def port_body(entries: Iterable[tuple[int, Mapping[str, Any]]]) -> list[dict[str, Any]]:
    """Return the body of ``PUT portlist``: an array of ``{"idx", "data"}``, one per port."""
    return [{"idx": str(port), "data": dict(data)} for port, data in entries]


def member_style(lags: Iterable[LiveLag]) -> bool:
    """Return whether ``PortMembers`` holds strings: the live groups' type, else strings."""
    for lag in lags:
        if lag.member_as_str is not None:
            return lag.member_as_str
    return True


__all__ = [
    "CONFIG_TYPES",
    "DEFAULT_VLAN_ID",
    "DELETABLE_TYPES",
    "FEC_ENABLED_WIRE",
    "FEC_NOT_AVAILABLE",
    "FEC_WIRE",
    "LACP_ADDRESS_PREFIX",
    "LACP_TYPE",
    "LAG_ROW_TYPE",
    "PORTLIST_TIMEOUT",
    "PORT_ADDRESS_PREFIX",
    "PORT_FIELD_ORDER",
    "PORT_TYPE",
    "SPEED_WIRE",
    "VLAN_ADDRESS_PREFIX",
    "VLAN_TYPE",
    "DesiredLag",
    "DesiredPort",
    "DesiredVlan",
    "LacpInfo",
    "LiveLag",
    "LivePort",
    "LiveVlan",
    "Port",
    "check_resources",
    "count_ports",
    "desired_from_resources",
    "desired_lags",
    "desired_ports",
    "desired_vlans",
    "lag_body",
    "lag_delete_body",
    "member_style",
    "parse_lacp_info",
    "parse_lags",
    "parse_port",
    "parse_ports",
    "parse_vlans",
    "port_body",
    "port_changed_fields",
    "port_label",
    "port_matches",
    "port_write_data",
    "resolve_port",
    "vlan_body",
    "vlan_delete_body",
]
