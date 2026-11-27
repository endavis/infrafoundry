"""Resource specs, value normalization and schema checks for the MikroTik provider.

YAML field names are the RouterOS names (``vlan-filtering``, ``vlan-ids``, ``tagged``,
``pvid``, ...), so they map to the REST body with no rename table. The resource type
with ``.`` replaced by ``/`` is the REST path.

RouterOS returns every value as a string (``"true"``, ``"yes"``, ``"10"``,
``"ether1,bridge"``). Comparison runs on normalized values so a converged device
plans clean.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel

KIND_STR = "str"
KIND_BOOL = "bool"
KIND_INT = "int"
KIND_LIST = "list"
KIND_VLANS = "vlans"

VLAN_MIN = 1
VLAN_MAX = 4094
DAYS_VALID_MAX = 36500

SIGN_FIELD = "fingerprint"
"""The live field that is non-empty only on a signed certificate (not live-probed)."""

_TRUE = {"true", "yes"}
_FALSE = {"false", "no"}
_MISSING_DEFAULTS: dict[str, Any] = {"disabled": False, "comment": ""}


@dataclass(frozen=True)
class ResourceSpec:
    """What one RouterOS resource type looks like."""

    type_name: str
    key_fields: tuple[str, ...]
    fields: dict[str, str]
    required: tuple[str, ...] = ()
    creatable: bool = True
    deletable: bool = True
    updatable: tuple[str, ...] | None = None
    """Fields that may change on an existing row; ``None`` means every field."""

    @property
    def path(self) -> str:
        """The REST path (without ``/rest/``)."""
        return self.type_name.replace(".", "/")

    @property
    def slug(self) -> str:
        """The type name as an identifier fragment (``interface_bridge_port``)."""
        return self.type_name.replace(".", "_").replace("-", "_")


_COMMON: dict[str, str] = {"comment": KIND_STR, "disabled": KIND_BOOL}

SPECS: dict[str, ResourceSpec] = {
    "interface.bridge": ResourceSpec(
        "interface.bridge",
        ("name",),
        {
            "name": KIND_STR,
            "vlan-filtering": KIND_BOOL,
            "pvid": KIND_INT,
            "protocol-mode": KIND_STR,
            "frame-types": KIND_STR,
            "ingress-filtering": KIND_BOOL,
            "mtu": KIND_INT,
            **_COMMON,
        },
        required=("name",),
    ),
    "interface.bridge.port": ResourceSpec(
        "interface.bridge.port",
        ("interface",),
        {
            "interface": KIND_STR,
            "bridge": KIND_STR,
            "pvid": KIND_INT,
            "frame-types": KIND_STR,
            "ingress-filtering": KIND_BOOL,
            "edge": KIND_STR,
            **_COMMON,
        },
        required=("interface", "bridge"),
    ),
    "interface.bridge.vlan": ResourceSpec(
        "interface.bridge.vlan",
        ("bridge", "vlan-ids"),
        {
            "bridge": KIND_STR,
            "vlan-ids": KIND_VLANS,
            "tagged": KIND_LIST,
            "untagged": KIND_LIST,
            **_COMMON,
        },
        required=("bridge", "vlan-ids"),
    ),
    "interface.vlan": ResourceSpec(
        "interface.vlan",
        ("name",),
        {
            "name": KIND_STR,
            "interface": KIND_STR,
            "vlan-id": KIND_INT,
            "mtu": KIND_INT,
            **_COMMON,
        },
        required=("name", "interface", "vlan-id"),
    ),
    "ip.address": ResourceSpec(
        "ip.address",
        ("address",),
        {"address": KIND_STR, "interface": KIND_STR, "network": KIND_STR, **_COMMON},
        required=("address", "interface"),
    ),
    "ip.dhcp-client": ResourceSpec(
        "ip.dhcp-client",
        ("interface",),
        {
            "interface": KIND_STR,
            "add-default-route": KIND_BOOL,
            "use-peer-dns": KIND_BOOL,
            "use-peer-ntp": KIND_BOOL,
            "default-route-distance": KIND_INT,
            **_COMMON,
        },
        required=("interface",),
    ),
    "certificate": ResourceSpec(
        "certificate",
        ("name",),
        {
            "name": KIND_STR,
            "common-name": KIND_STR,
            "subject-alt-name": KIND_STR,
            "key-size": KIND_STR,
            "days-valid": KIND_INT,
            "key-usage": KIND_LIST,
            "comment": KIND_STR,
        },
        required=("name", "common-name"),
        updatable=("comment",),
    ),
    "ip.service": ResourceSpec(
        "ip.service",
        ("name",),
        {
            "name": KIND_STR,
            "port": KIND_INT,
            "address": KIND_STR,
            "certificate": KIND_STR,
            "disabled": KIND_BOOL,
        },
        required=("name",),
        creatable=False,
        deletable=False,
    ),
}

DEPENDENCY_ORDER: tuple[str, ...] = (
    "interface.bridge",
    "interface.vlan",
    "interface.bridge.vlan",
    "interface.bridge.port",
    "ip.address",
    "ip.dhcp-client",
    "certificate",
    "ip.service",
)
"""Types in creation order; deletes run in reverse."""


@dataclass(frozen=True)
class SchemaFinding:
    """One schema finding for a resource."""

    resource: str
    level: ValidationLevel
    message: str


@dataclass(frozen=True)
class DesiredObject:
    """One declared RouterOS object."""

    type_name: str
    resource_name: str
    key: tuple[Any, ...]
    fields: dict[str, Any] = field(default_factory=dict)
    absent: bool = False


def parse_vlan_ids(value: Any) -> frozenset[int]:
    """Expand VLAN ids given as an int, ``"10,20-22"``, or a list of those.

    Args:
        value: The configured or live ``vlan-ids`` value.

    Raises:
        ValueError: If a token is not an id or a ``lo-hi`` range.
    """
    if isinstance(value, bool):
        raise ValueError(f"invalid vlan id {value!r}")
    if isinstance(value, int):
        return frozenset({value})
    if isinstance(value, (list, tuple, set, frozenset)):
        ids: set[int] = set()
        for item in value:
            ids |= parse_vlan_ids(item)
        return frozenset(ids)
    result: set[int] = set()
    for token in str(value).split(","):
        token = token.strip()
        if not token:
            continue
        low, sep, high = token.partition("-")
        if sep:
            first, last = int(low), int(high)
            if first > last:
                raise ValueError(f"invalid vlan range '{token}'")
            result.update(range(first, last + 1))
        else:
            result.add(int(token))
    return frozenset(result)


def normalize_value(kind: str, value: Any, name: str = "") -> Any:
    """Normalize a configured or live value so the two compare equal when equivalent.

    Args:
        kind: One of the ``KIND_*`` constants.
        value: The raw value (``None`` when a live row omits the field).
        name: The field name, to apply the default of an omitted ``disabled``/``comment``.

    Raises:
        ValueError: If the value cannot be read as ``kind``.
    """
    if value is None:
        return _MISSING_DEFAULTS.get(name)
    if kind == KIND_BOOL:
        text = str(value).strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        raise ValueError(f"'{value}' is not a boolean")
    if kind == KIND_INT:
        if isinstance(value, bool):
            raise ValueError(f"'{value}' is not an integer")
        return int(value)
    if kind == KIND_LIST:
        items = value if isinstance(value, (list, tuple, set, frozenset)) else str(value).split(",")
        return frozenset(str(i).strip() for i in items if str(i).strip())
    if kind == KIND_VLANS:
        return parse_vlan_ids(value)
    return str(value)


def to_rest_value(kind: str, value: Any) -> str:
    """Render a normalized value as RouterOS expects it in a REST body."""
    if kind == KIND_BOOL:
        return "yes" if normalize_value(kind, value) else "no"
    if kind == KIND_LIST:
        return ",".join(sorted(normalize_value(kind, value)))
    if kind == KIND_VLANS:
        return ",".join(str(i) for i in sorted(parse_vlan_ids(value)))
    return str(value)


def key_of(spec: ResourceSpec, row: dict[str, Any]) -> tuple[Any, ...] | None:
    """Return a row's identity key, or ``None`` when a key field is missing or unreadable."""
    parts: list[Any] = []
    for name in spec.key_fields:
        raw = row.get(name)
        if raw is None or raw == "":
            return None
        try:
            parts.append(normalize_value(spec.fields[name], raw, name))
        except ValueError:
            return None
    return tuple(parts)


def _effective_config(spec: ResourceSpec, resource: ResourceConfig) -> dict[str, Any]:
    """Return the resource config; ``name`` stays only for types with a name field."""
    config = dict(resource.config or {})
    if "name" not in spec.fields:
        config.pop("name", None)  # loaders copy the resource name into the config
    elif not config.get("name"):
        config["name"] = resource.name
    return config


def desired_from_resources(resources: list[ResourceConfig]) -> list[DesiredObject]:
    """Turn the provider's resources into declared objects.

    Args:
        resources: Resources of any type; other providers' types are skipped.

    Raises:
        ValueError: If a resource has no usable key (run ``check_resources`` first).
    """
    desired: list[DesiredObject] = []
    for resource in resources:
        spec = SPECS.get(resource.type)
        if spec is None:
            continue
        config = _effective_config(spec, resource)
        absent = bool(config.pop("absent", False))
        key = key_of(spec, config)
        if key is None:
            raise ValueError(f"{resource.type} '{resource.name}' has no usable key")
        desired.append(DesiredObject(resource.type, resource.name, key, config, absent))
    return desired


def _range_ok(value: int) -> bool:
    return VLAN_MIN <= value <= VLAN_MAX


def check_resources(resources: list[ResourceConfig]) -> list[SchemaFinding]:
    """Check each MikroTik resource against its spec.

    Args:
        resources: Resources of any type; only MikroTik types are checked.

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

    keys: Counter[tuple[str, tuple[Any, ...]]] = Counter()
    for resource in resources:
        spec = SPECS.get(resource.type)
        if spec is None:
            continue
        config = _effective_config(spec, resource)
        absent = bool(config.pop("absent", False))
        if absent and not spec.deletable:
            error(resource, "'absent' is not allowed; built-in services cannot be deleted")
            continue
        unknown = sorted(set(config) - set(spec.fields))
        if unknown:
            error(resource, "unknown field(s): " + ", ".join(unknown))
        needed = spec.key_fields if absent else spec.required
        missing = [name for name in needed if config.get(name) in (None, "")]
        if missing:
            error(resource, "missing required field(s): " + ", ".join(missing))
        if absent:
            extra = sorted(set(config) - set(spec.key_fields) - {"comment"})
            if extra:
                error(resource, "'absent' may carry only key fields, got: " + ", ".join(extra))
        bad = False
        for name, value in config.items():
            kind = spec.fields.get(name)
            if kind is None or value in (None, ""):
                continue
            try:
                normalized = normalize_value(kind, value, name)
            except ValueError as exc:
                error(resource, f"field '{name}': {exc}")
                bad = True
                continue
            if (kind == KIND_VLANS and not all(_range_ok(i) for i in normalized)) or (
                name in ("pvid", "vlan-id") and not _range_ok(normalized)
            ):
                error(resource, f"'{name}' must be within {VLAN_MIN}-{VLAN_MAX}")
            elif name == "port" and not 1 <= normalized <= 65535:
                error(resource, "'port' must be within 1-65535")
            elif name == "days-valid" and not 1 <= normalized <= DAYS_VALID_MAX:
                error(resource, f"'days-valid' must be within 1-{DAYS_VALID_MAX}")
        if not missing and not bad:
            key = key_of(spec, config)
            if key is not None:
                keys[(resource.type, key)] += 1
                if keys[(resource.type, key)] == 2:
                    error(resource, f"duplicate identity key {key!r}")
    return findings
