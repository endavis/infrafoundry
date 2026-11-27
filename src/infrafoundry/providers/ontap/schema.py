"""Resource schema for the ONTAP provider: ``network.ip.interface`` (data LIFs).

YAML fields (all but ``absent`` and ``name`` are the ONTAP names without nesting):

``svm``, ``name`` (defaults to the resource name), ``address``, ``netmask`` (prefix length
or dotted mask), ``home_node``, ``home_port``, ``service_policy``, ``auto_revert``.
ONTAP REST has no protocol field on an IP interface, only a service policy;
``protocols: [nfs, cifs]`` is a convenience for ``service_policy: default-data-files`` and
``[iscsi]`` or ``[nvme_tcp]`` for ``default-data-blocks``.

Identity is ``(svm, name)``. Only declared fields are compared; ``netmask`` is compared as
a prefix length so ``24`` and ``255.255.255.0`` are equal.
"""

from __future__ import annotations

import ipaddress
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel

TYPE_NAME = "network.ip.interface"
SLUG = "network_ip_interface"

FILE_POLICY = "default-data-files"
BLOCK_POLICY = "default-data-blocks"
FILE_PROTOCOLS = frozenset({"nfs", "cifs"})
BLOCK_PROTOCOLS = frozenset({"iscsi", "nvme_tcp"})

KEY_FIELDS = ("svm", "name")
COMPARED = ("address", "netmask", "home_node", "home_port", "service_policy", "auto_revert")
REQUIRED = ("svm", "address", "netmask", "home_node", "home_port")
ALLOWED = frozenset({*KEY_FIELDS, *COMPARED, "protocols", "absent"})
_STR_FIELDS = ("svm", "name", "home_node", "home_port", "service_policy")


@dataclass(frozen=True)
class SchemaFinding:
    """One schema problem, for the validation report."""

    resource: str
    level: ValidationLevel
    message: str


@dataclass(frozen=True)
class DesiredInterface:
    """One declared data LIF, normalized."""

    resource_name: str
    svm: str
    name: str
    absent: bool
    fields: dict[str, Any] = field(default_factory=dict)
    """The declared compared fields, normalized (``netmask`` as a prefix length)."""

    @property
    def key(self) -> tuple[str, str]:
        """The identity: ``(svm, name)``."""
        return (self.svm, self.name)


def normalize_netmask(value: Any) -> int:
    """Return a netmask as a prefix length.

    Args:
        value: ``24``, ``"24"``, ``"/24"`` or a dotted mask such as ``"255.255.255.0"``.

    Raises:
        ValueError: If the value is not a netmask.
    """
    if isinstance(value, bool):
        raise ValueError(f"'{value}' is not a netmask")
    if isinstance(value, int):
        prefix = value
    else:
        text = str(value).strip().removeprefix("/")
        if text.isdigit():
            prefix = int(text)
        else:
            try:
                prefix = ipaddress.IPv4Network(f"0.0.0.0/{text}").prefixlen
            except ValueError:
                raise ValueError(f"'{value}' is not a netmask") from None
    if not 0 <= prefix <= 128:
        raise ValueError(f"netmask '{value}' is out of range")
    return prefix


def normalize_address(value: Any) -> str:
    """Return an IP address in canonical text form.

    Raises:
        ValueError: If the value is not an IP address.
    """
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError:
        raise ValueError(f"'{value}' is not an IP address") from None


def policy_for_protocols(protocols: Any) -> str:
    """Map ``protocols`` to the service policy that carries them.

    Raises:
        ValueError: If the list is empty, holds an unknown protocol, or mixes file and block.
    """
    if not isinstance(protocols, (list, tuple)) or not protocols:
        raise ValueError("'protocols' must be a non-empty list")
    names = {str(p).strip().lower().replace("-", "_") for p in protocols}
    unknown = sorted(names - FILE_PROTOCOLS - BLOCK_PROTOCOLS)
    if unknown:
        raise ValueError(
            "unknown protocol(s): " + ", ".join(unknown) + "; use nfs, cifs, iscsi or nvme_tcp"
        )
    file_side, block_side = names & FILE_PROTOCOLS, names & BLOCK_PROTOCOLS
    if file_side and block_side:
        raise ValueError(
            "'protocols' mixes file (nfs, cifs) and block (iscsi, nvme_tcp) protocols; "
            "one LIF carries one kind, declare a second LIF"
        )
    return FILE_POLICY if file_side else BLOCK_POLICY


def _effective_config(resource: ResourceConfig) -> dict[str, Any]:
    """Return the resource config with ``name`` defaulted to the resource name."""
    config = dict(resource.config or {})
    if not config.get("name"):
        config["name"] = resource.name
    return config


def _normalized_fields(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize the declared compared fields; ``protocols`` becomes a service policy.

    Raises:
        ValueError: On an unreadable value or a contradictory declaration.
    """
    values: dict[str, Any] = {}
    if config.get("protocols") not in (None, "", []) and config.get("service_policy"):
        raise ValueError("give either 'service_policy' or 'protocols', not both")
    for name in COMPARED:
        raw = config.get(name)
        if raw in (None, ""):
            continue
        if name == "address":
            values[name] = normalize_address(raw)
        elif name == "netmask":
            values[name] = normalize_netmask(raw)
        elif name == "auto_revert":
            if not isinstance(raw, bool):
                raise ValueError("'auto_revert' must be true or false")
            values[name] = raw
        else:
            values[name] = str(raw)
    if config.get("protocols") not in (None, "", []):
        values["service_policy"] = policy_for_protocols(config["protocols"])
    return values


def desired_from_resources(resources: list[ResourceConfig]) -> list[DesiredInterface]:
    """Turn the provider's resources into declared interfaces.

    Args:
        resources: Resources of any type; other types are skipped.

    Raises:
        ValueError: If a resource has no usable identity or an unreadable value (run
            ``check_resources`` first).
    """
    desired: list[DesiredInterface] = []
    for resource in resources:
        if resource.type != TYPE_NAME:
            continue
        config = _effective_config(resource)
        absent = bool(config.pop("absent", False))
        svm = config.get("svm")
        if not svm:
            raise ValueError(f"{TYPE_NAME} '{resource.name}' has no svm")
        desired.append(
            DesiredInterface(
                resource.name,
                str(svm),
                str(config["name"]),
                absent,
                {} if absent else _normalized_fields(config),
            )
        )
    return desired


def check_resources(resources: list[ResourceConfig]) -> list[SchemaFinding]:
    """Check each ONTAP resource against the schema.

    Args:
        resources: Resources of any type; only ``network.ip.interface`` is checked.

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
        if resource.type != TYPE_NAME:
            continue
        config = _effective_config(resource)
        absent = bool(config.pop("absent", False))
        unknown = sorted(set(config) - ALLOWED)
        if unknown:
            error(resource, "unknown field(s): " + ", ".join(unknown))
        needed = KEY_FIELDS if absent else REQUIRED
        missing = [n for n in needed if config.get(n) in (None, "")]
        if missing:
            error(resource, "missing required field(s): " + ", ".join(missing))
        if absent:
            extra = sorted(set(config) - set(KEY_FIELDS))
            if extra:
                error(resource, "'absent' may carry only svm and name, got: " + ", ".join(extra))
        bad = bool(unknown or missing)
        for name in _STR_FIELDS:
            if name in config and not isinstance(config[name], str):
                error(resource, f"field '{name}' must be a string")
                bad = True
        if not absent and not bad:
            try:
                values = _normalized_fields(config)
            except ValueError as exc:
                error(resource, str(exc))
                bad = True
            else:
                _check_family(resource, values, error)
        if not missing and not bad:
            keys[(str(config["svm"]), str(config["name"]))] += 1
            if keys[(str(config["svm"]), str(config["name"]))] == 2:
                error(resource, f"duplicate interface '{config['name']}' in svm '{config['svm']}'")
    return findings


def _check_family(resource: ResourceConfig, values: dict[str, Any], error: Any) -> None:
    """Check the netmask against the address family."""
    address, netmask = values.get("address"), values.get("netmask")
    if address is None or netmask is None:
        return
    limit = 32 if ipaddress.ip_address(address).version == 4 else 128
    if netmask > limit:
        error(resource, f"netmask {netmask} is too long for the address family of '{address}'")


def to_api_kwargs(fields: dict[str, Any]) -> dict[str, Any]:
    """Map normalized fields to the flat dotted names the ONTAP REST client expects.

    ``home_port`` is sent with its node so the port is unambiguous.

    Args:
        fields: Normalized fields (identity and compared fields).
    """
    kwargs: dict[str, Any] = {}
    if "svm" in fields:
        kwargs["svm.name"] = fields["svm"]
    if "name" in fields:
        kwargs["name"] = fields["name"]
    if "address" in fields:
        kwargs["ip.address"] = fields["address"]
    if "netmask" in fields:
        kwargs["ip.netmask"] = str(fields["netmask"])
    if "home_node" in fields:
        kwargs["location.home_node.name"] = fields["home_node"]
    if "home_port" in fields:
        kwargs["location.home_port.name"] = fields["home_port"]
        if "home_node" in fields:
            kwargs["location.home_port.node.name"] = fields["home_node"]
    if "service_policy" in fields:
        kwargs["service_policy.name"] = fields["service_policy"]
    if "auto_revert" in fields:
        kwargs["location.auto_revert"] = fields["auto_revert"]
    return kwargs


def _dig(row: dict[str, Any], *path: str) -> Any:
    """Read a nested value from a REST row, ``None`` when any step is missing."""
    current: Any = row
    for step in path:
        if not isinstance(current, dict):
            return None
        current = current.get(step)
    return current


def live_view(row: dict[str, Any]) -> dict[str, Any]:
    """Flatten a live REST row to the schema's field names, normalized for comparison.

    Args:
        row: One ``network/ip/interfaces`` record (nested, as the REST API returns it).
    """
    address = _dig(row, "ip", "address")
    netmask = _dig(row, "ip", "netmask")
    try:
        prefix: int | None = normalize_netmask(netmask) if netmask not in (None, "") else None
    except ValueError:
        prefix = None
    try:
        canonical = normalize_address(address) if address else None
    except ValueError:
        canonical = str(address)
    return {
        "uuid": row.get("uuid"),
        "svm": _dig(row, "svm", "name") or None,
        "name": row.get("name") or None,
        "scope": row.get("scope") or None,
        "address": canonical,
        "netmask": prefix,
        "home_node": _dig(row, "location", "home_node", "name") or None,
        "home_port": _dig(row, "location", "home_port", "name") or None,
        "service_policy": _dig(row, "service_policy", "name") or None,
        "auto_revert": _dig(row, "location", "auto_revert"),
        "is_home": _dig(row, "location", "is_home"),
    }
