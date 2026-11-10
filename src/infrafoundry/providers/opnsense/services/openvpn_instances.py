"""OpenVPN client-instance service for OPNsense direct-API operations (ADR-0014, #808).

Manages OpenVPN **client** instances on the modern MVC API (``openvpn/instances``,
stock OPNsense, no plugin). The legacy ``os-openvpn-legacy`` plugin is not managed:
a cutover recreates its client as a modern instance. Server instances are out of
scope: every write sends ``role: client``, and a live server instance is never
matched, updated or deleted.

Identity is the live ``description`` against the YAML ``description`` (falling back
to the resource name). A change of description is a delete plus an add. The box
assigns ``uuid``; it is not a YAML field.

vpnid
-----

``add`` is rejected without ``vpnid`` (verified on a test firewall), and the id names
the tunnel device (``ovpncN`` for clients). ``vpnid`` is an optional YAML field.
Set, it is written and compared. Omitted, an add allocates the next free id
(max over every live instance of any role, every explicit YAML id in the apply and
ids already allocated, plus one; starting at 1) and it is never compared. An update
always sends a ``vpnid`` (the explicit one, else the live row's) so the ``set``
payload never lacks a required field.

Sparse comparison
-----------------

Only the fields the operator set are written and compared. Set-valued fields
(``data_ciphers``, ``various_flags``, ``route``, ``redirect_gateway``) compare as
sets; ``remote`` compares in order (it is a failover list).

Option fields
-------------

The model returns option fields as dicts keyed by value (``{"udp": {"value": "udp",
"selected": 1}}``) or, for ``verb``, as a list where the position is the value.
:func:`flatten_option` turns both into the comma-joined selected values.

Client certificate
------------------

``cert_ref`` is optional and names a ``trust.certs`` resource (#1320). It resolves to
that certificate's live ``refid``, sent as ``cert``. Omitted, ``cert`` is neither sent
nor compared, so a certificate set by hand is never cleared. Certificate-only,
username/password-only and combined authentication all work.

Static key
----------

``tls_key_ref`` is optional and names an ``openvpn.static_keys`` resource (#1319). It
resolves to that key's live ``uuid``, sent as ``tls_key``. Omitted, ``tls_key`` is
neither sent nor compared, so a key set by hand is never cleared. ``tls_key`` is
keyed by the static key's uuid (verified on a test firewall).

Secrets
-------

``username`` and ``password`` must be ``secret://`` URIs in YAML (the validator
rejects literals). The manager resolves them before this module runs. Neither is
ever logged, put in an exception message or shown in a ``repr``; log lines name
changed fields only. ``password`` is write-only: it is never compared, sent on add
and, on update, only with ``update_password: true``.

What is verified and what is not
--------------------------------

- Verified read-only on a test firewall: the empty model template of
  ``GET openvpn/instances/get`` (field names, option shapes, ``ca`` and ``cert`` as
  reference options, ``tls_key`` as a reference to a static key).
- Verified by a live apply on a test firewall: ``add`` requires ``vpnid`` (the
  template leaves it empty); ``set`` changes only the sent fields and keeps the
  rest; the password reads back but is deliberately not compared.
- Not verified: whether ``mssfix`` takes an integer, and tunnel behaviour.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.exceptions import ReferenceValidationError
from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from ._identity import OpnsenseDriftError
from .base import BaseService, raise_on_failed_write

logger = logging.getLogger(__name__)

_TYPE = "openvpn.instances"
ROLE_CLIENT = "client"

_DEV_TYPES: tuple[str, ...] = ("tun", "tap", "ovpn")
_PROTOS: tuple[str, ...] = ("udp", "udp4", "udp6", "tcp", "tcp4", "tcp6")
_TOPOLOGIES: tuple[str, ...] = ("net30", "p2p", "subnet")
VERB_MIN = 0
VERB_MAX = 11

# kind -> how a value is parsed, serialized and compared.
_BOOL = "bool"
_ENUM = "enum"
_INT = "int"
_STR = "str"
_LIST = "list"  # ordered
_SET = "set"  # unordered


@dataclass(frozen=True)
class FieldSpec:
    """How one YAML key maps to the wire.

    Attributes:
        wire: Wire field name.
        kind: ``bool``, ``enum``, ``int``, ``str``, ``list`` (ordered) or ``set``.
        choices: Allowed values for ``enum``.
        low: Smallest allowed ``int``.
        high: Largest allowed ``int``, or ``None``.
    """

    wire: str
    kind: str
    choices: tuple[str, ...] = ()
    low: int = 0
    high: int | None = None


#: Config key -> wire spec, for every operator-settable field except the identity,
#: the credentials and the CA reference, which are handled apart.
FIELD_SPECS: dict[str, FieldSpec] = {
    "enabled": FieldSpec("enabled", _BOOL),
    "dev_type": FieldSpec("dev_type", _ENUM, _DEV_TYPES),
    "proto": FieldSpec("proto", _ENUM, _PROTOS),
    "vpnid": FieldSpec("vpnid", _INT, low=1),
    "remote": FieldSpec("remote", _LIST),
    "port": FieldSpec("port", _INT, low=1, high=65535),
    "topology": FieldSpec("topology", _ENUM, _TOPOLOGIES),
    "auth": FieldSpec("auth", _STR),
    "data_ciphers": FieldSpec("data-ciphers", _SET),
    "data_ciphers_fallback": FieldSpec("data-ciphers-fallback", _STR),
    "remote_cert_tls": FieldSpec("remote_cert_tls", _BOOL),
    "verify_x509_name": FieldSpec("verify-x509-name", _STR),
    "various_flags": FieldSpec("various_flags", _SET),
    "route": FieldSpec("route", _SET),
    "redirect_gateway": FieldSpec("redirect_gateway", _SET),
    "keepalive_interval": FieldSpec("keepalive_interval", _INT),
    "keepalive_timeout": FieldSpec("keepalive_timeout", _INT),
    "reneg_sec": FieldSpec("reneg-sec", _INT),
    "tun_mtu": FieldSpec("tun_mtu", _INT),
    "fragment": FieldSpec("fragment", _INT),
    "mssfix": FieldSpec("mssfix", _INT),
    "verb": FieldSpec("verb", _INT, low=VERB_MIN, high=VERB_MAX),
}
_SET_WIRE_KEYS: frozenset[str] = frozenset(s.wire for s in FIELD_SPECS.values() if s.kind == _SET)
_BOOL_WIRE_KEYS: frozenset[str] = frozenset(s.wire for s in FIELD_SPECS.values() if s.kind == _BOOL)

#: Secret fields: ``secret://`` URIs only.
SECRET_FIELDS: tuple[str, ...] = ("username", "password")

#: Every config key a ``openvpn.instances`` resource accepts (single source for the
#: parser and the validator).
ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        # The nested loader copies the entry name into config (package_loader).
        "name",
        "description",
        "ca_ref",
        "cert_ref",
        "tls_key_ref",
        "update_password",
        "lock",
        *SECRET_FIELDS,
        *FIELD_SPECS,
    }
)
#: Keys the box assigns itself.
BOX_ASSIGNED_KEYS: frozenset[str] = frozenset({"uuid"})
#: Keys this type refuses, with the hint the validator shows.
REJECTED_KEY_HINTS: dict[str, str] = {
    "role": "only client instances are managed; the role is always client",
    "ca": "use 'ca_ref' with the name of a trust.cas resource",
    "cert": "use 'cert_ref' with the name of a trust.certs resource",
    "tls_key": "use 'tls_key_ref' with the name of an openvpn.static_keys resource",
    "data-ciphers": "use 'data_ciphers'",
    "data-ciphers-fallback": "use 'data_ciphers_fallback'",
    "reneg-sec": "use 'reneg_sec'",
    "verify-x509-name": "use 'verify_x509_name'",
}


def description_of(name: str, config: Mapping[str, Any]) -> str:
    """Return the identity description of a resource.

    Args:
        name: Resource name, the fallback.
        config: Resource config.

    Returns:
        ``description`` when a non-empty string, else ``name``.
    """
    description = config.get("description")
    if isinstance(description, str) and description:
        return description
    return name


def flatten_option(value: Any) -> str:
    """Flatten a live field into its comma-joined wire string.

    An option dict (``{"udp": {"value": "udp", "selected": 1}}``) flattens to the
    selected non-empty keys. An option list (``[{"value": "0", "selected": 1}]``)
    flattens to the positional indexes of the selected entries. ``None`` and empty
    containers flatten to ``""``; a scalar to its string.

    Args:
        value: A field value from ``openvpn/instances/get``.

    Returns:
        The flattened string.
    """
    if isinstance(value, list):
        return ",".join(
            str(index)
            for index, entry in enumerate(value)
            if isinstance(entry, dict) and entry.get("selected")
        )
    if isinstance(value, dict):
        return ",".join(
            str(key)
            for key, meta in value.items()
            if str(key) and isinstance(meta, dict) and meta.get("selected")
        )
    if value is None:
        return ""
    return str(value)


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OpenVpnInstanceConfig:
    """Desired-state OpenVPN client instance.

    Attributes:
        name: Operator-facing YAML name.
        description: Wire ``description`` and the identity (defaults to ``name``).
        fields: Sorted ``(wire_key, serialized_value)`` pairs the operator set.
            Set-valued fields are stored sorted.
        ca_ref: Name of the ``trust.cas`` resource, resolved to a CA refid at apply.
        cert_ref: Optional name of the ``trust.certs`` resource, resolved to the
            certificate refid at apply and sent as ``cert``. Empty: ``cert`` is
            neither sent nor compared.
        tls_key_ref: Optional name of the ``openvpn.static_keys`` resource, resolved
            to the static key uuid at apply and sent as ``tls_key``. Empty:
            ``tls_key`` is neither sent nor compared.
        username: Plaintext username (never logged or shown in ``repr``), or empty.
        password: Plaintext password (never compared, logged or shown in ``repr``).
        update_password: Send ``password`` on update too.
        lock: Per-resource safety annotation (ADR-0014 section 6).
    """

    name: str
    description: str
    fields: tuple[tuple[str, str], ...] = ()
    ca_ref: str = ""
    cert_ref: str = ""
    tls_key_ref: str = ""
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    update_password: bool = False
    lock: bool = False

    @property
    def diff_key(self) -> str:
        """Identity of this instance: its description."""
        return self.description

    def to_payload(
        self,
        ca_refid: str = "",
        *,
        include_password: bool = False,
        default_vpnid: str = "",
        cert_refid: str = "",
        tls_key_uuid: str = "",
    ) -> dict[str, Any]:
        """Serialize to the ``add``/``set`` envelope.

        Args:
            ca_refid: Resolved CA refid; omitted when empty.
            cert_refid: Resolved certificate refid; omitted when empty.
            tls_key_uuid: Resolved static key uuid, sent as ``tls_key``; omitted
                when empty.
            include_password: Add ``password`` (when set). True on add; on update
                only with ``update_password``.
            default_vpnid: ``vpnid`` to send when the config sets none (allocated on
                add, the live value on update); omitted when empty.

        Returns:
            ``{"instance": {...}}`` with ``role: client`` and the set fields only.
        """
        body: dict[str, Any] = {"role": ROLE_CLIENT, "description": self.description}
        body.update(self.fields)
        if default_vpnid and "vpnid" not in body:
            body["vpnid"] = default_vpnid
        if ca_refid:
            body["ca"] = ca_refid
        if cert_refid:
            body["cert"] = cert_refid
        if tls_key_uuid:
            body["tls_key"] = tls_key_uuid
        if self.username:
            body["username"] = self.username
        if include_password and self.password:
            body["password"] = self.password
        return {"instance": body}


@dataclass(frozen=True)
class LiveOpenVpnInstance:
    """An OpenVPN instance as currently on the box (a ``get`` result).

    Attributes:
        uuid: Row UUID.
        description: Live description.
        role: Flattened live role (``client`` or ``server``).
        raw: The ``instance`` object returned by ``get``.
    """

    uuid: str
    description: str
    role: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def diff_key(self) -> str:
        """Identity of this instance: its description."""
        return self.description

    @property
    def vpnid(self) -> str:
        """Return the live ``vpnid`` as a string, or ``""`` when absent."""
        return flatten_option(self.raw.get("vpnid")).strip()

    @property
    def is_client(self) -> bool:
        """Return True for a client instance, the only role managed here."""
        return self.role == ROLE_CLIENT


@dataclass
class Diff:
    """Result of comparing desired client instances to live ones."""

    adds: list[OpenVpnInstanceConfig] = field(default_factory=list)
    updates: list[tuple[LiveOpenVpnInstance, OpenVpnInstanceConfig]] = field(default_factory=list)
    deletes: list[LiveOpenVpnInstance] = field(default_factory=list)
    unmanaged: list[LiveOpenVpnInstance] = field(default_factory=list)
    locked: list[tuple[OpenVpnInstanceConfig, LiveOpenVpnInstance | None]] = field(
        default_factory=list
    )
    warnings: list[str] = field(default_factory=list)
    live_vpnids: list[int] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there is nothing to add, update or delete."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def _live_value(have: LiveOpenVpnInstance, wire: str) -> str:
    """Flatten and normalize one live field for comparison."""
    flat = flatten_option(have.raw.get(wire)).strip()
    if wire in _BOOL_WIRE_KEYS:
        return "1" if flat == "1" else "0"
    return flat


def changed_fields(
    have: LiveOpenVpnInstance,
    want: OpenVpnInstanceConfig,
    ca_refid: str = "",
    cert_refid: str = "",
    tls_key_uuid: str = "",
) -> list[str]:
    """Return the wire keys whose live value differs from the desired one.

    Args:
        have: Live instance.
        want: Desired instance.
        ca_refid: Resolved refid of ``want.ca_ref``; empty skips the CA comparison.
        cert_refid: Resolved refid of ``want.cert_ref``; empty skips the certificate
            comparison.
        tls_key_uuid: Resolved uuid of ``want.tls_key_ref``; empty skips the static
            key comparison.

    Returns:
        Field names only, never values (some are secrets). ``password`` appears
        only with ``update_password`` and a supplied password: the live value is
        write-only, so it is never compared.
    """
    changed: list[str] = []
    for wire, value in want.fields:
        live = _live_value(have, wire)
        if wire in _SET_WIRE_KEYS:
            if frozenset(_split(live)) != frozenset(_split(value)):
                changed.append(wire)
        elif wire == "remote":
            if _split(live) != _split(value):
                changed.append(wire)
        elif live != value:
            changed.append(wire)
    if ca_refid and flatten_option(have.raw.get("ca")).strip() != ca_refid:
        changed.append("ca")
    if cert_refid and flatten_option(have.raw.get("cert")).strip() != cert_refid:
        changed.append("cert")
    if tls_key_uuid and flatten_option(have.raw.get("tls_key")).strip() != tls_key_uuid:
        changed.append("tls_key")
    if want.username and flatten_option(have.raw.get("username")).strip() != want.username:
        changed.append("username")
    if want.update_password and want.password:
        changed.append("password")
    return changed


def compute_diff(
    desired: list[OpenVpnInstanceConfig],
    current: list[LiveOpenVpnInstance],
    *,
    add_only: bool = False,
    managed_keys: set[str] | None = None,
    ca_refids: Mapping[str, str] | None = None,
    cert_refids: Mapping[str, str] | None = None,
    static_key_uuids: Mapping[str, str] | None = None,
) -> Diff:
    """Compare desired client instances to live instances, keyed by description.

    Server instances are never matched, updated or deleted.

    Args:
        desired: Instances the operator wants.
        current: Every live instance, any role.
        add_only: Suppress deletes.
        managed_keys: When given, only live clients in this set may be deleted
            (ADR-0018); others land in ``Diff.unmanaged``.
        ca_refids: ``ca_ref`` name to live CA refid. A ``ca_ref`` missing from it
            is not compared.
        cert_refids: ``cert_ref`` name to live certificate refid. A ``cert_ref``
            missing from it is not compared.
        static_key_uuids: ``tls_key_ref`` name to live static key uuid. A
            ``tls_key_ref`` missing from it is not compared.

    Returns:
        The diff.

    Raises:
        OpnsenseDriftError: If two live clients share a description, or a desired
            description is already used by a live server instance.
    """
    refids = ca_refids or {}
    cert_ids = cert_refids or {}
    key_uuids = static_key_uuids or {}
    clients: dict[str, LiveOpenVpnInstance] = {}
    server_keys: set[str] = set()
    for live in current:
        if not live.is_client:
            server_keys.add(live.diff_key)
            continue
        if live.diff_key in clients:
            raise OpnsenseDriftError(
                f"openvpn instances: more than one live client has description "
                f"{live.diff_key!r}; rename one on the box before planning"
            )
        clients[live.diff_key] = live
    desired_by_key = {c.diff_key: c for c in desired}
    collisions = sorted(set(desired_by_key) & server_keys)
    if collisions:
        raise OpnsenseDriftError(
            f"openvpn instances: description {collisions[0]!r} is used by a live server "
            f"instance; this type manages clients only, pick another description"
        )
    locked_keys = {c.diff_key for c in desired if c.lock}

    diff = Diff(live_vpnids=[int(v) for v in (x.vpnid for x in current) if v.isdigit()])
    for key, want in desired_by_key.items():
        have = clients.get(key)
        if want.lock:
            diff.locked.append((want, have))
        elif have is None:
            diff.adds.append(want)
        elif changed_fields(
            have,
            want,
            refids.get(want.ca_ref, "") if want.ca_ref else "",
            cert_ids.get(want.cert_ref, "") if want.cert_ref else "",
            key_uuids.get(want.tls_key_ref, "") if want.tls_key_ref else "",
        ):
            diff.updates.append((have, want))

    if add_only:
        return diff
    for key, have in clients.items():
        if key in locked_keys or key in desired_by_key:
            continue
        if managed_keys is not None and key not in managed_keys:
            diff.unmanaged.append(have)
        else:
            diff.deletes.append(have)
    return diff


# ---------------------------------------------------------------------------
# Resource-to-domain conversion
# ---------------------------------------------------------------------------


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def serialize_value(label: str, key: str, spec: FieldSpec, value: Any) -> str:
    """Serialize one config value to its wire string.

    Args:
        label: Resource label for error messages.
        key: Config key.
        spec: The key's :class:`FieldSpec`.
        value: The YAML value.

    Returns:
        The wire string (set-valued fields sorted and de-duplicated).

    Raises:
        ValueError: On a wrong type or out-of-range value; never includes the value.
    """
    kind = spec.kind
    if kind == _BOOL:
        if not isinstance(value, bool):
            raise ValueError(f"{label} {key} must be a boolean (true/false)")
        return "1" if value else "0"
    if kind == _INT:
        if not _is_int(value):
            raise ValueError(f"{label} {key} must be an integer")
        if value < spec.low or (spec.high is not None and value > spec.high):
            bound = f"{spec.low}-{spec.high}" if spec.high is not None else f">= {spec.low}"
            raise ValueError(f"{label} {key} must be in range {bound}")
        return str(value)
    if kind in {_LIST, _SET}:
        if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
            raise ValueError(f"{label} {key} must be a list of non-empty strings")
        if any("," in v for v in value):
            raise ValueError(f"{label} {key} entries must not contain commas")
        items = [v.strip() for v in value]
        return ",".join(sorted(set(items)) if kind == _SET else items)
    if not isinstance(value, str):
        raise ValueError(f"{label} {key} must be a string")
    if kind == _ENUM and value not in spec.choices:
        raise ValueError(f"{label} {key} must be one of {list(spec.choices)}")
    return value


def openvpn_instance_configs_from_resources(
    resources: list[ResourceConfig],
) -> list[OpenVpnInstanceConfig]:
    """Convert ``openvpn.instances`` resources to :class:`OpenVpnInstanceConfig`.

    Args:
        resources: Provider resources; other types are skipped.

    Returns:
        Parsed instances. ``secret://`` URIs stay URIs until the manager resolves them.

    Raises:
        ValueError: On a non-dict config, an unknown key, a missing ``remote`` or
            ``ca_ref``, or a mistyped or out-of-range value. Messages name the
            resource and the field, never a value.
    """
    configs: list[OpenVpnInstanceConfig] = []
    for resource in resources:
        if resource.type != _TYPE:
            continue
        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"openvpn instance '{resource.name}' has non-dict config")
        configs.append(_build_config(resource.name, config))
    return configs


def _build_config(name: str, config: dict[str, Any]) -> OpenVpnInstanceConfig:
    label = f"openvpn instance '{name}'"
    unknown = sorted(set(config) - ALLOWED_KEYS)
    if unknown:
        raise ValueError(f"{label} has unknown keys: {unknown}")
    description = config.get("description")
    if description is not None and not isinstance(description, str):
        raise ValueError(f"{label} description must be a string")
    for key in ("lock", "update_password"):
        if not isinstance(config.get(key, False), bool):
            raise ValueError(f"{label} {key} must be a boolean")
    ca_ref = config.get("ca_ref")
    if not isinstance(ca_ref, str) or not ca_ref:
        raise ValueError(f"{label} requires a non-empty string 'ca_ref'")
    cert_ref = config.get("cert_ref")
    if cert_ref is None:
        cert_ref = ""
    elif not isinstance(cert_ref, str) or not cert_ref:
        raise ValueError(f"{label} 'cert_ref' must be a non-empty string")
    tls_key_ref = config.get("tls_key_ref")
    if tls_key_ref is None:
        tls_key_ref = ""
    elif not isinstance(tls_key_ref, str) or not tls_key_ref:
        raise ValueError(f"{label} 'tls_key_ref' must be a non-empty string")
    if not config.get("remote"):
        raise ValueError(f"{label} requires a non-empty 'remote' list")

    secrets: dict[str, str] = {}
    for key in SECRET_FIELDS:
        value = config.get(key)
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ValueError(f"{label} {key} must be a string")
        secrets[key] = value

    values: dict[str, str] = {}
    for key, spec in FIELD_SPECS.items():
        if key in config:
            values[spec.wire] = serialize_value(label, key, spec, config[key])
    return OpenVpnInstanceConfig(
        name=name,
        description=description if isinstance(description, str) and description else name,
        fields=tuple(sorted(values.items())),
        ca_ref=ca_ref,
        cert_ref=cert_ref,
        tls_key_ref=tls_key_ref,
        username=secrets["username"],
        password=secrets["password"],
        update_password=bool(config.get("update_password", False)),
        lock=bool(config.get("lock", False)),
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def search_uuids(response: Any) -> list[str]:
    """Return the row uuids of a ``search`` response, tolerating malformed bodies."""
    if not isinstance(response, dict):
        return []
    rows = response.get("rows")
    if not isinstance(rows, list):
        return []
    return [str(r["uuid"]) for r in rows if isinstance(r, dict) and r.get("uuid")]


class OpenVpnInstanceService(BaseService):
    """Service for OpenVPN client instances via the ``openvpn/instances`` controller."""

    def search(self) -> list[LiveOpenVpnInstance]:
        """Fetch every live instance, any role.

        ``search`` rows are read only for their uuids; each instance is then read
        with ``get/{uuid}`` for its role and full field set.
        """
        search = endpoints.OPENVPN_INSTANCE.search
        get = endpoints.OPENVPN_INSTANCE.read
        live: list[LiveOpenVpnInstance] = []
        for uuid in search_uuids(self.client.request(search.method, search.path())):
            response = self.client.request(get.method, get.path(uuid=uuid))
            instance = response.get("instance") if isinstance(response, dict) else None
            if not isinstance(instance, dict):
                continue
            live.append(
                LiveOpenVpnInstance(
                    uuid=uuid,
                    description=flatten_option(instance.get("description")),
                    role=flatten_option(instance.get("role")),
                    raw=instance,
                )
            )
        return live

    def add(
        self,
        config: OpenVpnInstanceConfig,
        ca_refid: str = "",
        vpnid: str = "",
        *,
        cert_refid: str = "",
        tls_key_uuid: str = "",
    ) -> dict[str, Any]:
        """Create a client instance; raises when OPNsense rejects it.

        Args:
            config: Desired instance.
            ca_refid: Resolved CA refid.
            vpnid: Allocated ``vpnid``, used when the config sets none.
            cert_refid: Resolved certificate refid, when ``cert_ref`` is set.
            tls_key_uuid: Resolved static key uuid, when ``tls_key_ref`` is set.
        """
        ep = endpoints.OPENVPN_INSTANCE.add
        response = self.client.request(
            ep.method,
            ep.path(),
            data=config.to_payload(
                ca_refid,
                include_password=True,
                default_vpnid=vpnid,
                cert_refid=cert_refid,
                tls_key_uuid=tls_key_uuid,
            ),
        )
        raise_on_failed_write(response, f"add openvpn instance {config.name!r}")
        return response

    def update(
        self,
        uuid: str,
        config: OpenVpnInstanceConfig,
        ca_refid: str = "",
        vpnid: str = "",
        *,
        cert_refid: str = "",
        tls_key_uuid: str = "",
    ) -> dict[str, Any]:
        """Update a client instance by UUID; raises when OPNsense rejects it.

        Args:
            uuid: Row UUID.
            config: Desired instance.
            ca_refid: Resolved CA refid.
            vpnid: Live ``vpnid``, sent when the config sets none.
            cert_refid: Resolved certificate refid, when ``cert_ref`` is set.
            tls_key_uuid: Resolved static key uuid, when ``tls_key_ref`` is set.
        """
        ep = endpoints.OPENVPN_INSTANCE.update
        response = self.client.request(
            ep.method,
            ep.path(uuid=uuid),
            data=config.to_payload(
                ca_refid,
                include_password=config.update_password,
                default_vpnid=vpnid,
                cert_refid=cert_refid,
                tls_key_uuid=tls_key_uuid,
            ),
        )
        raise_on_failed_write(response, f"update openvpn instance {config.name!r}")
        return response

    def delete(self, live: LiveOpenVpnInstance) -> dict[str, Any]:
        """Delete a client instance by UUID.

        Raises:
            ValueError: If ``live`` is not a client instance.
        """
        if not live.is_client:
            raise ValueError("refusing to delete an openvpn instance that is not a client")
        ep = endpoints.OPENVPN_INSTANCE.delete
        response = self.client.request(ep.method, ep.path(uuid=live.uuid))
        raise_on_failed_write(response, f"delete openvpn instance {live.description!r}")
        return response

    def reconfigure(self) -> dict[str, Any]:
        """Apply pending changes.

        Called only by the provider's ``openvpn_reconfigure`` finalization hook (and
        by the manager's destroy, which the hook does not cover).
        """
        ep = endpoints.OPENVPN_RECONFIGURE
        response = self.client.request(ep.method, ep.path())
        raise_on_failed_write(response, "reconfigure openvpn")
        return response

    def compute_diff(
        self,
        desired: list[OpenVpnInstanceConfig],
        live: list[LiveOpenVpnInstance],
        *,
        add_only: bool = False,
        managed_keys: set[str] | None = None,
        ca_refids: Mapping[str, str] | None = None,
        cert_refids: Mapping[str, str] | None = None,
        static_key_uuids: Mapping[str, str] | None = None,
    ) -> Diff:
        """Service-method form of :func:`compute_diff`."""
        return compute_diff(
            desired,
            live,
            add_only=add_only,
            managed_keys=managed_keys,
            ca_refids=ca_refids,
            cert_refids=cert_refids,
            static_key_uuids=static_key_uuids,
        )

    def apply_diff(
        self,
        diff: Diff,
        ca_refids: Mapping[str, str] | None = None,
        cert_refids: Mapping[str, str] | None = None,
        static_key_uuids: Mapping[str, str] | None = None,
    ) -> dict[str, int]:
        """Dispatch the diff. The caller reconfigures through the finalization hook.

        Args:
            diff: The diff to apply.
            ca_refids: ``ca_ref`` name to live CA refid.
            cert_refids: ``cert_ref`` name to live certificate refid.
            static_key_uuids: ``tls_key_ref`` name to live static key uuid.

        Returns:
            ``{"created": N, "updated": M, "deleted": K}``.

        Raises:
            ReferenceValidationError: If an added or updated instance's ``ca_ref``
                has no live CA, or its ``cert_ref`` has no live certificate, or its
                ``tls_key_ref`` has no live static key. Checked before any write.
        """
        refids = ca_refids or {}
        cert_ids = cert_refids or {}
        resolved: dict[str, str] = {}
        resolved_certs: dict[str, str] = {}
        resolved_keys: dict[str, str] = {}
        key_ids = static_key_uuids or {}
        for config in [*diff.adds, *(want for _, want in diff.updates)]:
            if config.ca_ref not in refids:
                raise ReferenceValidationError(
                    f"openvpn instance '{config.name}' ca_ref '{config.ca_ref}' does not "
                    f"match any live CA; apply the trust.cas resource first"
                )
            resolved[config.name] = refids[config.ca_ref]
            if config.cert_ref:
                if config.cert_ref not in cert_ids:
                    raise ReferenceValidationError(
                        f"openvpn instance '{config.name}' cert_ref '{config.cert_ref}' does "
                        f"not match any live certificate; apply the trust.certs resource first"
                    )
                resolved_certs[config.name] = cert_ids[config.cert_ref]
            if config.tls_key_ref:
                if config.tls_key_ref not in key_ids:
                    raise ReferenceValidationError(
                        f"openvpn instance '{config.name}' tls_key_ref '{config.tls_key_ref}' "
                        f"does not match any live static key; apply the openvpn.static_keys "
                        f"resource first"
                    )
                resolved_keys[config.name] = key_ids[config.tls_key_ref]

        taken = [*diff.live_vpnids]
        desired = [*diff.adds, *(want for _, want in diff.updates), *(w for w, _ in diff.locked)]
        for config in desired:
            explicit = dict(config.fields).get("vpnid", "")
            if explicit.isdigit():
                taken.append(int(explicit))
        next_vpnid = max(taken, default=0) + 1

        created = updated = deleted = 0
        for config in diff.adds:
            allocated = ""
            if "vpnid" not in dict(config.fields):
                allocated = str(next_vpnid)
                next_vpnid += 1
            self.add(
                config,
                resolved[config.name],
                allocated,
                cert_refid=resolved_certs.get(config.name, ""),
                tls_key_uuid=resolved_keys.get(config.name, ""),
            )
            created += 1
        for live, want in diff.updates:
            logger.info(
                "opnsense openvpn.instances: updating %s (fields: %s)",
                want.name,
                changed_fields(
                    live,
                    want,
                    resolved[want.name],
                    resolved_certs.get(want.name, ""),
                    resolved_keys.get(want.name, ""),
                ),
            )
            self.update(
                live.uuid,
                want,
                resolved[want.name],
                live.vpnid,
                cert_refid=resolved_certs.get(want.name, ""),
                tls_key_uuid=resolved_keys.get(want.name, ""),
            )
            updated += 1
        for live in diff.deletes:
            self.delete(live)
            deleted += 1
        return {"created": created, "updated": updated, "deleted": deleted}
