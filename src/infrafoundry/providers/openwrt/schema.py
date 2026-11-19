"""Resource specs, value normalization and schema checks for the OpenWrt provider.

YAML field names are the UCI option names, with two exceptions that the resource
loaders force: ``dhcp.host`` uses ``hostname`` for the UCI option ``name`` (the
loaders copy the resource name into ``config.name``), and the section key of a
``network.interface`` or ``dhcp.pool`` is ``interface``.

UCI stores every value as a string (``"100"``, ``"1"``, ``"tcp udp"``). Values are
rendered the same way so a converged device plans clean.
"""

from __future__ import annotations

import ipaddress
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel

from .settings import OpenWrtSettings

KIND_STR = "str"
KIND_INT = "int"
KIND_BOOL = "bool"
KIND_IPV4 = "ipv4"
KIND_NETMASK = "netmask"
KIND_MAC = "mac"
KIND_LEASETIME = "leasetime"
KIND_PORTS = "ports"
KIND_PROTO = "proto"
KIND_FLAG = "flag"
"""A framework flag (``absent``, ``confirm_management_change``), never written to UCI."""

FLAG_ABSENT = "absent"
FLAG_CONFIRM = "confirm_management_change"

_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_SECTION_RE = re.compile(r"^[A-Za-z0-9_]+$")
_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
_LEASETIME_RE = re.compile(r"^(\d+[smhdw]?|infinite)$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_PORT_RE = re.compile(r"^(\d+)(?:[-:](\d+))?$")
_UNSAFE_RE = re.compile(r"[\x00-\x1f\x7f]|\{[{%#]")
_TARGETS = {"DNAT", "SNAT"}


@dataclass(frozen=True)
class ResourceSpec:
    """What one OpenWrt resource type looks like."""

    type_name: str
    config: str
    section_type: str
    key_field: str
    fields: dict[str, str]
    required: tuple[str, ...] = ()
    deletable: bool = False
    named: bool = False
    """Section is named by its key (``network.lan``); otherwise it is matched by ``find``."""
    uci_key: str | None = None
    """UCI option holding the key when matching by ``find``; defaults to ``key_field``."""
    defaults: tuple[tuple[str, str], ...] = ()
    """UCI values applied when the resource does not set them."""

    @property
    def slug(self) -> str:
        """The type name as an identifier fragment (``dhcp_host``)."""
        return self.type_name.replace(".", "_")

    @property
    def find_option(self) -> str:
        """The UCI option a section is found by."""
        return self.uci_key or self.key_field


_FLAGS: dict[str, str] = {FLAG_CONFIRM: KIND_FLAG}

SPECS: dict[str, ResourceSpec] = {
    "network.interface": ResourceSpec(
        "network.interface",
        "network",
        "interface",
        "interface",
        {
            "interface": KIND_STR,
            "proto": KIND_STR,
            "ipaddr": KIND_IPV4,
            "netmask": KIND_NETMASK,
            **_FLAGS,
        },
        required=("ipaddr", "netmask"),
        named=True,
    ),
    "dhcp.pool": ResourceSpec(
        "dhcp.pool",
        "dhcp",
        "dhcp",
        "interface",
        {
            "interface": KIND_STR,
            "start": KIND_INT,
            "limit": KIND_INT,
            "leasetime": KIND_LEASETIME,
        },
    ),
    "dhcp.host": ResourceSpec(
        "dhcp.host",
        "dhcp",
        "host",
        "mac",
        {
            "mac": KIND_MAC,
            "ip": KIND_IPV4,
            "hostname": KIND_STR,
            "leasetime": KIND_LEASETIME,
            FLAG_ABSENT: KIND_FLAG,
        },
        required=("mac", "ip"),
        deletable=True,
    ),
    "firewall.redirect": ResourceSpec(
        "firewall.redirect",
        "firewall",
        "redirect",
        "name",
        {
            "name": KIND_STR,
            "src": KIND_STR,
            "src_dport": KIND_PORTS,
            "dest": KIND_STR,
            "dest_ip": KIND_IPV4,
            "dest_port": KIND_PORTS,
            "proto": KIND_PROTO,
            "target": KIND_STR,
            "enabled": KIND_BOOL,
            FLAG_ABSENT: KIND_FLAG,
            **_FLAGS,
        },
        required=("src_dport", "dest_ip"),
        deletable=True,
        defaults=(("src", "wan"), ("dest", "lan"), ("proto", "tcp udp"), ("target", "DNAT")),
    ),
}

_UCI_RENAMES = {"hostname": "name"}


@dataclass(frozen=True)
class SchemaFinding:
    """One schema finding for a resource."""

    resource: str
    level: ValidationLevel
    message: str


@dataclass(frozen=True)
class Desired:
    """One declared OpenWrt object."""

    spec: ResourceSpec
    name: str
    key: str
    values: dict[str, str]
    absent: bool = False
    confirm: bool = False

    @property
    def type_name(self) -> str:
        """The resource type."""
        return self.spec.type_name

    @property
    def address(self) -> str:
        """The pseudo address recorded in state (``openwrt_dhcp_host.<name>``)."""
        return f"openwrt_{self.spec.slug}.{self.name}"


def _port_ranges(value: Any) -> list[tuple[int, int]]:
    """Parse a port, range or list of them; raise ValueError when unreadable."""
    tokens = [str(value)] if isinstance(value, int) else str(value).split()
    ranges: list[tuple[int, int]] = []
    for token in tokens:
        match = _PORT_RE.match(token)
        if match is None:
            raise ValueError("expected a port, a range (1000-2000) or a space-separated list")
        low, high = int(match.group(1)), int(match.group(2) or match.group(1))
        if not 1 <= low <= high <= 65535:
            raise ValueError("ports must be within 1-65535 and ranges ascending")
        ranges.append((low, high))
    if not ranges:
        raise ValueError("expected a port, a range (1000-2000) or a space-separated list")
    return ranges


def normalize_uci_value(kind: str, value: Any, name: str = "value") -> str:
    """Return a value as UCI stores it, raising ``ValueError`` when it is invalid.

    Args:
        kind: One of the ``KIND_*`` constants.
        value: The YAML value.
        name: Field name, for messages.

    Returns:
        The string form: ints as ``"100"``, bools as ``"1"``/``"0"``, ``proto`` lists
        joined by spaces.

    Raises:
        ValueError: If the value does not fit the kind.
    """
    if kind == KIND_BOOL:
        if not isinstance(value, bool):
            raise ValueError(f"'{name}' must be true or false")
        return "1" if value else "0"
    if kind == KIND_INT:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"'{name}' must be a non-negative integer")
        return str(value)
    if kind == KIND_IPV4:
        text = str(value)
        if "/" in text:
            raise ValueError(
                f"'{name}' must be a plain IPv4 address; give the mask in a separate "
                "'netmask' field, not as CIDR"
            )
        try:
            return str(ipaddress.IPv4Address(text))
        except ValueError as exc:
            raise ValueError(f"'{name}' is not an IPv4 address") from exc
    if kind == KIND_NETMASK:
        text = str(value)
        try:
            ipaddress.IPv4Network(f"0.0.0.0/{text}")
        except ValueError as exc:
            raise ValueError(f"'{name}' must be a dotted netmask such as 255.255.255.0") from exc
        if "." not in text:
            raise ValueError(f"'{name}' must be a dotted netmask such as 255.255.255.0")
        return text
    if kind == KIND_MAC:
        text = str(value)
        if not _MAC_RE.match(text):
            raise ValueError(f"'{name}' must look like 02:00:00:00:00:01")
        return text
    if kind == KIND_LEASETIME:
        text = str(value)
        if not _LEASETIME_RE.match(text):
            raise ValueError(f"'{name}' must be seconds, a number with s/m/h/d/w, or infinite")
        return text
    if kind == KIND_PORTS:
        _port_ranges(value)
        return str(value)
    if kind == KIND_PROTO:
        tokens = [str(t) for t in value] if isinstance(value, list) else str(value).split()
        if not tokens or not all(_TOKEN_RE.match(t) for t in tokens):
            raise ValueError(f"'{name}' must be a protocol name or a list of them")
        return " ".join(tokens)
    text = str(value)
    if not text or _UNSAFE_RE.search(text):
        raise ValueError(
            f"'{name}' must be a non-empty string without control characters or Jinja markers"
        )
    return text


def _effective_config(spec: ResourceSpec, resource: ResourceConfig) -> dict[str, Any]:
    """Return the resource config with the key defaulted to the resource name."""
    config = dict(resource.config or {})
    if spec.key_field != "name":
        config.pop("name", None)  # loaders copy the resource name into the config
    if spec.key_field != "mac" and not config.get(spec.key_field):
        config[spec.key_field] = resource.name
    return config


def desired_from_resources(resources: list[ResourceConfig]) -> list[Desired]:
    """Turn the provider's resources into declared objects.

    Args:
        resources: Resources of any type; other providers' types are skipped.

    Raises:
        ValueError: If a resource is invalid (run ``check_resources`` first).
    """
    desired: list[Desired] = []
    for resource in resources:
        spec = SPECS.get(resource.type)
        if spec is None:
            continue
        config = _effective_config(spec, resource)
        absent = bool(config.pop(FLAG_ABSENT, False))
        confirm = bool(config.pop(FLAG_CONFIRM, False))
        key = normalize_uci_value(spec.fields[spec.key_field], config[spec.key_field])
        values: dict[str, str] = dict(spec.defaults)
        if not absent:
            for field_name, raw in config.items():
                if field_name == spec.key_field and spec.named:
                    continue
                kind = spec.fields[field_name]
                if kind == KIND_FLAG or raw in (None, ""):
                    continue
                values[_UCI_RENAMES.get(field_name, field_name)] = normalize_uci_value(
                    kind, raw, field_name
                )
        desired.append(Desired(spec, resource.name, key, values, absent, confirm))
    return desired


def covers_port(value: Any, port: int) -> bool:
    """Return True when a port spec (a port, a range or a list) contains ``port``."""
    try:
        return any(low <= port <= high for low, high in _port_ranges(value))
    except ValueError:
        return False


def mac_variants(mac: str) -> tuple[str, str]:
    """Return the upper- and lower-case forms of a MAC (UCI compares strings exactly)."""
    return mac.upper(), mac.lower()


def check_resources(
    resources: list[ResourceConfig], settings: OpenWrtSettings | None = None
) -> list[SchemaFinding]:
    """Check each OpenWrt resource against its spec.

    Args:
        resources: Resources of any type; only OpenWrt types are checked.
        settings: When given, a redirect that covers the SSH port needs
            ``confirm_management_change``.

    Returns:
        Findings; all at ERROR level.
    """
    findings: list[SchemaFinding] = []

    def error(resource: ResourceConfig, message: str) -> None:
        findings.append(
            SchemaFinding(
                resource.name,
                ValidationLevel.ERROR,
                f"{resource.type} '{resource.name}': {message}",
            )
        )

    keys: Counter[tuple[str, str]] = Counter()
    for resource in resources:
        spec = SPECS.get(resource.type)
        if spec is None:
            continue
        if not _NAME_RE.match(resource.name):
            error(resource, "the resource name may use only letters, digits, '_', '.' and '-'")
            continue
        config = _effective_config(spec, resource)
        absent = config.get(FLAG_ABSENT, False)
        if absent and not spec.deletable:
            error(resource, "'absent' is not allowed for this type")
            continue
        unknown = sorted(set(config) - set(spec.fields))
        if unknown:
            error(resource, "unknown field(s): " + ", ".join(unknown))
        needed = (spec.key_field,) if absent else (spec.key_field, *spec.required)
        missing = [n for n in needed if config.get(n) in (None, "")]
        if missing:
            error(resource, "missing required field(s): " + ", ".join(missing))
        bad = False
        for field_name, raw in config.items():
            kind = spec.fields.get(field_name)
            if kind is None or raw in (None, ""):
                continue
            try:
                if kind == KIND_FLAG:
                    if not isinstance(raw, bool):
                        raise ValueError(f"'{field_name}' must be true or false")
                else:
                    normalize_uci_value(kind, raw, field_name)
            except ValueError as exc:
                error(resource, str(exc))
                bad = True
        key = config.get(spec.key_field)
        if key and spec.named and not _SECTION_RE.match(str(key)):
            error(resource, f"'{spec.key_field}' may use only letters, digits and '_'")
            bad = True
        if spec.type_name == "firewall.redirect" and config.get("target", "DNAT") not in _TARGETS:
            error(resource, "'target' must be DNAT or SNAT")
            bad = True
        if bad or missing:
            continue
        identity = normalize_uci_value(spec.fields[spec.key_field], key, spec.key_field)
        if spec.key_field == "mac":
            identity = identity.lower()
        keys[(resource.type, identity)] += 1
        if keys[(resource.type, identity)] == 2:
            error(resource, f"duplicate {spec.key_field} '{identity}'")
        if (
            settings is not None
            and spec.type_name == "firewall.redirect"
            and not absent
            and config.get("src", "wan") == "wan"
            and covers_port(config["src_dport"], settings.ssh_port)
            and not config.get(FLAG_CONFIRM, False)
        ):
            error(
                resource,
                f"src_dport covers the SSH port {settings.ssh_port} on the WAN and could "
                "take over management access; set confirm_management_change: true to allow it",
            )
    return findings
