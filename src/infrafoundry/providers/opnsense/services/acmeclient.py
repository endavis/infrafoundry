"""ACME-client list services for OPNsense direct-API operations (ADR-0014, #790).

Manages the four list types of the ``os-acme-client`` plugin through one table-driven
engine: ``acmeclient.accounts``, ``acmeclient.validations``, ``acmeclient.actions``
and ``acmeclient.certs``. Each is a :class:`ListSpec`; the singleton
``acmeclient.settings`` has its own service (:mod:`.acmeclient_settings`).

Identity
--------

The YAML ``name`` is the cross-reference *handle*. The wire ``name`` is the identity:

- accounts, validations, actions: ``config.display_name`` when set, else the handle;
- certs: ``config.common_name`` (required), which is the certificate's CN.

A change of identity is a delete plus an add. The loader injects ``name`` into every
list entry's ``config``; it is ignored here.

Wire shape
----------

Controllers ``acmeclient/{accounts,validations,certificates,actions}`` offer
``search`` (GET), ``get/{uuid}``, ``add``, ``update/{uuid}`` and ``del/{uuid}``. The
``get`` and write envelopes use the singular item key (``account``, ``validation``,
``certificate``, ``action``). ``id``, ``key``, ``statusCode``, ``statusLastUpdate``,
``lastUpdate`` and ``certRefId`` are server-managed: never diffed, never sent.

Sparse comparison
-----------------

Only declared fields are compared and written. Set-valued fields compare as sets.
References (certs to accounts, validations and actions) are given as handles and
compared once resolved to live UUIDs.

Pass-through fields
-------------------

Validations carry about 255 per-provider credential fields (``dns_<provider>_<field>``)
and actions carry per-type fields (``sftp_*``, ``remote_ssh_*``, ``configd*``,
``acme_<type>_*``). They are accepted verbatim, not listed here. At plan the manager
rejects any pass-through key that the plugin's item template does not know.

Secrets
-------

``eab_hmac``, every ``dns_<provider>_*`` field and action fields named like a
credential take ``secret://`` URIs. The manager resolves them before this module runs.
Values are never logged, put in a message or shown in a ``repr``; log lines and
``changed_fields`` carry field names only.

Never called
------------

``register``, ``sign``, ``revoke``, ``removekey``, ``automation``, ``import``,
``signallcerts`` and ``toggle`` contact a CA or a remote host and are not registered.

What is verified and what is not
--------------------------------

See ``docs/development/opnsense-resource-coverage.md`` (section "ACME client").
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

from infrafoundry.core.exceptions import InvalidConfigurationError, ReferenceValidationError
from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from ._identity import OpnsenseDriftError
from ._nested_emit import emit_nested_list_yaml
from .base import BaseService, raise_on_failed_write
from .openvpn_instances import flatten_option, search_uuids

logger = logging.getLogger(__name__)

BOOL = "bool"
INT = "int"
STR = "str"
ENUM = "enum"
SET = "set"
REF = "ref"
REFSET = "refset"

#: Wire fields the box assigns. Never diffed, never sent.
SERVER_MANAGED: frozenset[str] = frozenset(
    {"id", "uuid", "key", "statusCode", "statusLastUpdate", "lastUpdate", "certRefId", "UpdateCron"}
)

_ACCOUNT_CAS: tuple[str, ...] = (
    "buypass",
    "buypass_test",
    "google",
    "google_test",
    "letsencrypt",
    "letsencrypt_test",
    "sslcom",
    "zerossl",
    "custom",
)
_VALIDATION_METHODS: tuple[str, ...] = ("http01", "dns01", "tlsalpn01")
_KEY_LENGTHS: tuple[str, ...] = ("key_2048", "key_3072", "key_4096", "key_ec256", "key_ec384")
_ALIAS_MODES: tuple[str, ...] = ("none", "automatic", "domain", "challenge")

#: Action ``type`` -> prefixes of the pass-through fields it may carry.
ACTION_TYPE_PREFIXES: dict[str, tuple[str, ...]] = {
    "configd_restart_gui": (),
    "configd_restart_haproxy": (),
    "configd_restart_nginx": (),
    "configd_reload_caddy": (),
    "configd_upload_sftp": ("sftp_",),
    "configd_remote_ssh": ("remote_ssh_",),
    "configd_generic": ("configd",),
    "acme_fritzbox": ("acme_fritzbox_",),
    "acme_panos": ("acme_panos_",),
    "acme_proxmoxbs": ("acme_proxmoxbs_",),
    "acme_proxmoxve": ("acme_proxmoxve_",),
    "acme_ruckus": ("acme_ruckus_",),
    "acme_vault": ("acme_vault_",),
    "acme_synology_dsm": ("acme_synology_dsm_",),
    "acme_truenas": ("acme_truenas_",),
    "acme_truenas_ws": ("acme_truenas_ws_",),
    "acme_zyxel_gs1900": ("acme_zyxel_gs1900_",),
    "acme_unifi": ("acme_unifi_",),
}

_ACTION_PASSTHROUGH_PREFIXES: tuple[str, ...] = ("sftp_", "remote_ssh_", "configd", "acme_")
_ACTION_SECRET = re.compile(r"(?i)(_password|_pass|_tokenkey|_apikey|_token|_key)$")
_DNS_PASSTHROUGH = re.compile(r"^dns_[A-Za-z0-9]+_\w+$")
#: Validation ``dns_*`` fields that are not provider credentials.
DNS_NAMED_FIELDS: frozenset[str] = frozenset({"dns_service", "dns_sleep", "dns_lexicon_provider"})

#: Credential fields required per DNS provider (curated; other providers get a warning).
REQUIRED_DNS_FIELDS: dict[str, tuple[str, ...]] = {"dns_cf": ("dns_cf_token",)}


@dataclass(frozen=True)
class FieldSpec:
    """How one YAML key maps to the wire.

    Attributes:
        wire: Wire field name.
        kind: ``bool``, ``int``, ``str``, ``enum``, ``set``, ``ref`` or ``refset``.
        choices: Allowed values for ``enum``.
        low: Smallest allowed ``int``.
        high: Largest allowed ``int``, or ``None``.
        ref_sub: For ``ref`` and ``refset``, the list type referenced (``accounts``,
            ``validations`` or ``actions``).
    """

    wire: str
    kind: str
    choices: tuple[str, ...] = ()
    low: int = 0
    high: int | None = None
    ref_sub: str = ""


@dataclass(frozen=True)
class ListSpec:
    """One ACME list type.

    Attributes:
        type_name: Dotted resource type (``acmeclient.accounts``).
        sub: Controller (``accounts``) and the name used in references.
        noun: Singular noun for messages and addresses (``account``).
        item_key: Envelope key (``account``).
        crud: Endpoints of the controller.
        template: Endpoint that returns the empty item template.
        fields: YAML key -> :class:`FieldSpec`, except the identity.
        passthrough: True for a YAML key accepted verbatim (wire name = key).
        is_secret: True for a YAML key that must hold a ``secret://`` URI.
        identity_key: YAML key carrying the wire name (``common_name`` for certs), or
            ``None`` when ``display_name`` or the handle does.
    """

    type_name: str
    sub: str
    noun: str
    item_key: str
    crud: endpoints.CrudEndpoints
    template: endpoints.Endpoint
    fields: dict[str, FieldSpec]
    passthrough: Callable[[str], bool] = lambda key: False
    is_secret: Callable[[str], bool] = lambda key: False
    identity_key: str | None = None

    @property
    def meta_keys(self) -> frozenset[str]:
        """Config keys that are not fields: the loader-injected ``name``, ``lock``, identity."""
        identity = self.identity_key or "display_name"
        return frozenset({"name", "lock", identity})

    @property
    def allowed_keys(self) -> frozenset[str]:
        """Every named config key (pass-through keys are matched by predicate)."""
        return self.meta_keys | frozenset(self.fields)

    def accepts(self, key: str) -> bool:
        """Return True when ``key`` is a legal config key of this type."""
        return key in self.allowed_keys or (
            key not in SERVER_MANAGED and key not in self.fields and self.passthrough(key)
        )


def _validation_passthrough(key: str) -> bool:
    return key not in DNS_NAMED_FIELDS and bool(_DNS_PASSTHROUGH.match(key))


def _action_passthrough(key: str) -> bool:
    return key != "type" and key.startswith(_ACTION_PASSTHROUGH_PREFIXES)


ACCOUNTS = ListSpec(
    type_name="acmeclient.accounts",
    sub="accounts",
    noun="account",
    item_key="account",
    crud=endpoints.ACMECLIENT_ACCOUNT,
    template=endpoints.ACMECLIENT_ACCOUNT_TEMPLATE,
    fields={
        "enabled": FieldSpec("enabled", BOOL),
        "description": FieldSpec("description", STR),
        "email": FieldSpec("email", STR),
        "ca": FieldSpec("ca", ENUM, _ACCOUNT_CAS),
        "custom_ca": FieldSpec("custom_ca", STR),
        "eab_kid": FieldSpec("eab_kid", STR),
        "eab_hmac": FieldSpec("eab_hmac", STR),
    },
    is_secret=lambda key: key == "eab_hmac",
)

VALIDATIONS = ListSpec(
    type_name="acmeclient.validations",
    sub="validations",
    noun="validation",
    item_key="validation",
    crud=endpoints.ACMECLIENT_VALIDATION,
    template=endpoints.ACMECLIENT_VALIDATION_TEMPLATE,
    fields={
        "enabled": FieldSpec("enabled", BOOL),
        "description": FieldSpec("description", STR),
        "method": FieldSpec("method", ENUM, _VALIDATION_METHODS),
        "http_service": FieldSpec("http_service", ENUM, ("opnsense", "haproxy")),
        "http_opn_autodiscovery": FieldSpec("http_opn_autodiscovery", BOOL),
        "http_opn_interface": FieldSpec("http_opn_interface", STR),
        "http_opn_ipaddresses": FieldSpec("http_opn_ipaddresses", SET),
        "http_haproxy_inject": FieldSpec("http_haproxyInject", BOOL),
        "http_haproxy_frontends": FieldSpec("http_haproxyFrontends", SET),
        "tlsalpn_service": FieldSpec("tlsalpn_service", STR),
        "tlsalpn_acme_autodiscovery": FieldSpec("tlsalpn_acme_autodiscovery", BOOL),
        "tlsalpn_acme_interface": FieldSpec("tlsalpn_acme_interface", STR),
        "tlsalpn_acme_ipaddresses": FieldSpec("tlsalpn_acme_ipaddresses", SET),
        "dns_service": FieldSpec("dns_service", STR),
        "dns_sleep": FieldSpec("dns_sleep", INT),
        "dns_lexicon_provider": FieldSpec("dns_lexicon_provider", STR),
    },
    passthrough=_validation_passthrough,
    is_secret=_validation_passthrough,
)

ACTIONS = ListSpec(
    type_name="acmeclient.actions",
    sub="actions",
    noun="action",
    item_key="action",
    crud=endpoints.ACMECLIENT_ACTION,
    template=endpoints.ACMECLIENT_ACTION_TEMPLATE,
    fields={
        "enabled": FieldSpec("enabled", BOOL),
        "description": FieldSpec("description", STR),
        "type": FieldSpec("type", ENUM, tuple(ACTION_TYPE_PREFIXES)),
    },
    passthrough=_action_passthrough,
    is_secret=lambda key: _action_passthrough(key) and bool(_ACTION_SECRET.search(key)),
)

CERTS = ListSpec(
    type_name="acmeclient.certs",
    sub="certs",
    noun="certificate",
    item_key="certificate",
    crud=endpoints.ACMECLIENT_CERTIFICATE,
    template=endpoints.ACMECLIENT_CERTIFICATE_TEMPLATE,
    fields={
        "enabled": FieldSpec("enabled", BOOL),
        "description": FieldSpec("description", STR),
        "alt_names": FieldSpec("altNames", SET),
        "account": FieldSpec("account", REF, ref_sub="accounts"),
        "validation": FieldSpec("validationMethod", REF, ref_sub="validations"),
        "restart_actions": FieldSpec("restartActions", REFSET, ref_sub="actions"),
        "key_length": FieldSpec("keyLength", ENUM, _KEY_LENGTHS),
        "ocsp": FieldSpec("ocsp", BOOL),
        "auto_renewal": FieldSpec("autoRenewal", BOOL),
        "renew_interval": FieldSpec("renewInterval", INT, low=1),
        "alias_mode": FieldSpec("aliasmode", ENUM, _ALIAS_MODES),
        "domain_alias": FieldSpec("domainalias", STR),
        "challenge_alias": FieldSpec("challengealias", STR),
    },
    identity_key="common_name",
)

SPECS: dict[str, ListSpec] = {s.sub: s for s in (ACCOUNTS, VALIDATIONS, ACTIONS, CERTS)}

#: Controller used for each reference target (certs reference ``certs``-less subs).
REF_SUBS: tuple[str, ...] = ("accounts", "validations", "actions")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def serialize_value(label: str, key: str, spec: FieldSpec, value: Any) -> str:
    """Serialize one config value to its wire string.

    ``ref`` and ``refset`` values are handles; they serialize to the comma-joined
    handles and are resolved to UUIDs later.

    Args:
        label: Resource label for error messages.
        key: Config key.
        spec: The key's :class:`FieldSpec`.
        value: The YAML value.

    Returns:
        The wire string (sets sorted and de-duplicated).

    Raises:
        ValueError: On a wrong type or out-of-range value; never includes the value.
    """
    kind = spec.kind
    if kind == BOOL:
        if not isinstance(value, bool):
            raise ValueError(f"{label} {key} must be a boolean (true/false)")
        return "1" if value else "0"
    if kind == INT:
        if not _is_int(value):
            raise ValueError(f"{label} {key} must be an integer")
        if value < spec.low or (spec.high is not None and value > spec.high):
            bound = f"{spec.low}-{spec.high}" if spec.high is not None else f">= {spec.low}"
            raise ValueError(f"{label} {key} must be in range {bound}")
        return str(value)
    if kind in {SET, REFSET}:
        if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
            raise ValueError(f"{label} {key} must be a list of non-empty strings")
        if any("," in v for v in value):
            raise ValueError(f"{label} {key} entries must not contain commas")
        items = [v.strip() for v in value]
        return ",".join(sorted(set(items)) if kind == SET else items)
    if not isinstance(value, str):
        raise ValueError(f"{label} {key} must be a string")
    if kind == ENUM and value not in spec.choices:
        raise ValueError(f"{label} {key} must be one of {list(spec.choices)}")
    if kind == REF and not value:
        raise ValueError(f"{label} {key} must be a non-empty string")
    return value


def _serialize_passthrough(label: str, key: str, value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int | str):
        return str(value)
    raise ValueError(f"{label} {key} must be a string, integer or boolean")


def ref_handle(value: str, sub: str) -> str:
    """Return the handle of a reference to a ``sub`` resource.

    Accepts ``<handle>``, ``<sub>.<handle>`` and ``acmeclient.<sub>.<handle>``.

    Args:
        value: The reference as written in YAML.
        sub: The expected list type (``accounts``, ``validations`` or ``actions``).

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
    elif len(parts) == 3 and parts[0] == "acmeclient" and parts[1] == sub:
        handle = parts[2]
    else:
        raise InvalidConfigurationError(
            f"reference {value!r} must be '<name>', '{sub}.<name>' or 'acmeclient.{sub}.<name>'"
        )
    if not handle:
        raise InvalidConfigurationError(f"reference {value!r} has an empty name")
    return handle


def slug_handle(text: str) -> str:
    """Return ``text`` as a handle: lowercase, ``[a-z0-9_-]`` only, no dots.

    Args:
        text: The wire name.

    Returns:
        The slug; empty when nothing usable remains.
    """
    return re.sub(r"[^a-z0-9_-]+", "-", text.lower()).strip("-")


def assign_handles(sub: str, items: Sequence[LiveAcmeItem]) -> dict[str, str]:
    """Give each live row a stable, collision-free handle.

    Args:
        sub: The list type, used for rows whose name slugs to nothing.
        items: Live rows, in search order.

    Returns:
        ``{uuid: handle}``. A collision gets ``-2``, ``-3`` ... in search order.
    """
    taken: set[str] = set()
    result: dict[str, str] = {}
    for index, item in enumerate(items, start=1):
        base = slug_handle(item.name) or f"{sub}-{index}"
        handle, n = base, 1
        while handle in taken:
            n += 1
            handle = f"{base}-{n}"
        taken.add(handle)
        result[item.uuid] = handle
    return result


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AcmeItemConfig:
    """Desired-state ACME list row.

    Attributes:
        name: YAML name, the cross-reference handle.
        wire_name: Wire ``name`` and the identity.
        fields: Sorted ``(wire, serialized_value, kind)`` triples the operator set
            (values may be secrets; never shown in ``repr``).
        refs: ``(wire, target_sub, handles)`` triples, resolved to UUIDs at apply.
        extra_wires: Wires of pass-through fields among ``fields``.
        secret_wires: Wires of secret fields among ``fields``.
        lock: Per-resource safety annotation (ADR-0014 section 6).
    """

    name: str
    wire_name: str
    fields: tuple[tuple[str, str, str], ...] = field(default=(), repr=False)
    refs: tuple[tuple[str, str, tuple[str, ...]], ...] = ()
    extra_wires: frozenset[str] = frozenset()
    secret_wires: frozenset[str] = frozenset()
    lock: bool = False

    @property
    def diff_key(self) -> str:
        """Identity of this row: its wire name."""
        return self.wire_name

    def to_payload(self, item_key: str, ref_uuids: Mapping[tuple[str, str], str]) -> dict[str, Any]:
        """Serialize to the ``add``/``update`` envelope.

        Args:
            item_key: Envelope key.
            ref_uuids: ``(sub, handle)`` -> live UUID, for every ref of this row.

        Returns:
            ``{item_key: {...}}`` holding the name and the declared fields only.
        """
        body: dict[str, Any] = {"name": self.wire_name}
        for wire, value, _ in self.fields:
            body[wire] = value
        for wire, sub, handles in self.refs:
            body[wire] = ",".join(ref_uuids[(sub, h)] for h in handles)
        return {item_key: body}

    def pending_refs(self, ref_uuids: Mapping[tuple[str, str], str]) -> list[tuple[str, str]]:
        """Return the ``(sub, handle)`` references with no live UUID."""
        return [
            (sub, h) for _, sub, handles in self.refs for h in handles if (sub, h) not in ref_uuids
        ]


@dataclass(frozen=True)
class LiveAcmeItem:
    """An ACME row as currently on the box (a ``get`` result).

    Attributes:
        uuid: Row UUID.
        name: Live wire name.
        raw: The item object returned by ``get`` (may hold secrets; hidden in ``repr``).
    """

    uuid: str
    name: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def diff_key(self) -> str:
        """Identity of this row: its wire name."""
        return self.name


@dataclass
class Diff:
    """Result of comparing desired ACME rows to live ones."""

    adds: list[AcmeItemConfig] = field(default_factory=list)
    updates: list[tuple[LiveAcmeItem, AcmeItemConfig]] = field(default_factory=list)
    deletes: list[LiveAcmeItem] = field(default_factory=list)
    unmanaged: list[LiveAcmeItem] = field(default_factory=list)
    locked: list[tuple[AcmeItemConfig, LiveAcmeItem | None]] = field(default_factory=list)
    matched: list[tuple[LiveAcmeItem, AcmeItemConfig]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there is nothing to add, update or delete."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def _live_value(have: LiveAcmeItem, wire: str, kind: str) -> str:
    flat = flatten_option(have.raw.get(wire)).strip()
    if kind == BOOL:
        return "1" if flat == "1" else "0"
    return flat


def changed_fields(
    have: LiveAcmeItem,
    want: AcmeItemConfig,
    ref_uuids: Mapping[tuple[str, str], str] | None = None,
) -> list[str]:
    """Return the wire keys whose live value differs from the desired one.

    Args:
        have: Live row.
        want: Desired row.
        ref_uuids: ``(sub, handle)`` -> live UUID. A reference with no entry is
            pending and counts as changed.

    Returns:
        Field names only, never values (some are secrets).
    """
    known = ref_uuids or {}
    changed: list[str] = []
    for wire, value, kind in want.fields:
        live = _live_value(have, wire, kind)
        if kind == SET:
            if frozenset(_split(live)) != frozenset(_split(value)):
                changed.append(wire)
        elif live != value:
            changed.append(wire)
    for wire, sub, handles in want.refs:
        resolved = [known[(sub, h)] for h in handles if (sub, h) in known]
        if len(resolved) != len(handles):
            changed.append(wire)
            continue
        live_ids = frozenset(_split(flatten_option(have.raw.get(wire))))
        if live_ids != frozenset(resolved):
            changed.append(wire)
    return changed


def compute_diff(
    spec: ListSpec,
    desired: list[AcmeItemConfig],
    current: list[LiveAcmeItem],
    *,
    add_only: bool = False,
    managed_keys: set[str] | None = None,
    ref_uuids: Mapping[tuple[str, str], str] | None = None,
) -> Diff:
    """Compare desired rows to live rows, keyed by wire name.

    Args:
        spec: The list type, for messages.
        desired: Rows the operator wants.
        current: Every live row.
        add_only: Suppress deletes.
        managed_keys: When given, only live rows in this set may be deleted
            (ADR-0018); others land in ``Diff.unmanaged``.
        ref_uuids: ``(sub, handle)`` -> live UUID for references.

    Returns:
        The diff.

    Raises:
        OpnsenseDriftError: If two live rows share a name.
    """
    live_by_key: dict[str, LiveAcmeItem] = {}
    for live in current:
        if live.diff_key in live_by_key:
            raise OpnsenseDriftError(
                f"acmeclient {spec.sub}: more than one live row is named {live.diff_key!r}; "
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


# ---------------------------------------------------------------------------
# Resource-to-domain conversion
# ---------------------------------------------------------------------------


def configs_from_resources(
    spec: ListSpec, resources: Sequence[ResourceConfig]
) -> list[AcmeItemConfig]:
    """Convert resources of ``spec.type_name`` to :class:`AcmeItemConfig`.

    Args:
        spec: The list type.
        resources: Provider resources; other types are skipped.

    Returns:
        Parsed rows. ``secret://`` URIs stay URIs until the manager resolves them.

    Raises:
        ValueError: On a non-dict config, an unknown key, a missing required key or a
            mistyped value. Messages name the resource and the field, never a value.
        InvalidConfigurationError: On a malformed reference.
    """
    configs: list[AcmeItemConfig] = []
    for resource in resources:
        if resource.type != spec.type_name:
            continue
        if not isinstance(resource.config, dict):
            raise ValueError(f"acmeclient {spec.noun} '{resource.name}' has non-dict config")
        configs.append(_build_config(spec, resource.name, resource.config))
    return configs


def wire_name_of(spec: ListSpec, name: str, config: Mapping[str, Any]) -> str:
    """Return the identity of a resource: its wire name.

    Args:
        spec: The list type.
        name: Resource name (the handle).
        config: Resource config.

    Returns:
        ``common_name`` for certs, else ``display_name`` when a non-empty string, else
        ``name``. Empty for a cert without a usable ``common_name``.
    """
    key = spec.identity_key or "display_name"
    value = config.get(key)
    if isinstance(value, str) and value:
        return value
    return "" if spec.identity_key else name


def _build_config(spec: ListSpec, name: str, config: dict[str, Any]) -> AcmeItemConfig:
    label = f"acmeclient {spec.noun} '{name}'"
    unknown = sorted(key for key in config if not spec.accepts(key))
    if unknown:
        raise ValueError(f"{label} has unknown keys: {unknown}")
    if not isinstance(config.get("lock", False), bool):
        raise ValueError(f"{label} lock must be a boolean")
    identity_key = spec.identity_key or "display_name"
    identity = config.get(identity_key)
    if identity is not None and not isinstance(identity, str):
        raise ValueError(f"{label} {identity_key} must be a string")
    wire_name = wire_name_of(spec, name, config)
    if not wire_name:
        raise ValueError(f"{label} requires a non-empty string '{identity_key}'")

    values: dict[str, tuple[str, str]] = {}
    refs: list[tuple[str, str, tuple[str, ...]]] = []
    extra: set[str] = set()
    secrets: set[str] = set()
    for key, fspec in spec.fields.items():
        if key not in config:
            continue
        text = serialize_value(label, key, fspec, config[key])
        if fspec.kind in {REF, REFSET}:
            raw = config[key]
            handles = tuple(
                ref_handle(h, fspec.ref_sub) for h in (raw if fspec.kind == REFSET else [raw])
            )
            refs.append((fspec.wire, fspec.ref_sub, handles))
            continue
        values[fspec.wire] = (text, fspec.kind)
        if spec.is_secret(key):
            secrets.add(fspec.wire)
    for key, raw_value in config.items():
        if key in spec.fields or key in spec.meta_keys or not spec.passthrough(key):
            continue
        values[key] = (_serialize_passthrough(label, key, raw_value), STR)
        extra.add(key)
        if spec.is_secret(key):
            secrets.add(key)
    return AcmeItemConfig(
        name=name,
        wire_name=wire_name,
        fields=tuple((wire, text, kind) for wire, (text, kind) in sorted(values.items())),
        refs=tuple(sorted(refs)),
        extra_wires=frozenset(extra),
        secret_wires=frozenset(secrets),
        lock=bool(config.get("lock", False)),
    )


def exports_passthrough(spec: ListSpec, raw: Mapping[str, Any], key: str) -> bool:
    """Return whether migrate emits a live pass-through field.

    Every row holds the fields of every DNS provider (validations) or action type
    (actions), and the plugin gives many of them non-empty defaults. Only the fields
    of the row's own provider or type describe it.

    Args:
        spec: The list type being exported.
        raw: The live row.
        key: A pass-through wire field of that row.

    Returns:
        True for a validation's ``<dns_service>_*`` field when its method is dns01, or
        an action's field under one of its type's prefixes. True for any other type.
    """
    if spec.item_key == "validation":
        method = flatten_option(raw.get("method")).strip()
        dns_service = flatten_option(raw.get("dns_service")).strip()
        return method == "dns01" and bool(dns_service) and key.startswith(f"{dns_service}_")
    if spec.item_key == "action":
        action_type = flatten_option(raw.get("type")).strip()
        prefixes = ACTION_TYPE_PREFIXES.get(action_type, ())
        return any(key.startswith(p) for p in prefixes)
    return True


def stale_provider_fields(
    raw: Mapping[str, Any],
    dns_service: str,
    defaults: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return live ``dns_*`` credential fields left over from another provider.

    The plugin gives some provider fields a non-empty default (a port, a host, an
    ``insecure`` flag), so every new validation carries them. A field still at its
    template default is not stale.

    Args:
        raw: A live validation item.
        dns_service: The selected DNS provider (``dns_cf``).
        defaults: The plugin's empty item template (``validations/get`` with no UUID).

    Returns:
        Sorted field names (never values) that are non-empty, differ from the template
        default, and belong to a provider other than ``dns_service``.
    """
    defaults = defaults or {}
    stale: list[str] = []
    for key, value in raw.items():
        if not _validation_passthrough(key) or key.startswith(f"{dns_service}_"):
            continue
        current = flatten_option(value).strip()
        if current and current != flatten_option(defaults.get(key, "")).strip():
            stale.append(key)
    return sorted(stale)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AcmeListService(BaseService):
    """Service for one ACME list type; subclasses set :attr:`SPEC`."""

    SPEC: ClassVar[ListSpec]

    def search(self) -> list[LiveAcmeItem]:
        """Fetch every live row.

        ``search`` rows are read only for their uuids; each row is then read with
        ``get/{uuid}`` for its full field set.
        """
        spec = self.SPEC
        search, get = spec.crud.search, spec.crud.read
        live: list[LiveAcmeItem] = []
        for uuid in search_uuids(self.client.request(search.method, search.path())):
            response = self.client.request(get.method, get.path(uuid=uuid))
            item = response.get(spec.item_key) if isinstance(response, dict) else None
            if not isinstance(item, dict):
                continue
            live.append(LiveAcmeItem(uuid=uuid, name=flatten_option(item.get("name")), raw=item))
        return live

    def template_item(self) -> dict[str, Any]:
        """Return the plugin's empty item template (field names and their defaults)."""
        spec = self.SPEC
        response = self.client.request(spec.template.method, spec.template.path())
        item = response.get(spec.item_key) if isinstance(response, dict) else None
        return dict(item) if isinstance(item, dict) else {}

    def template_keys(self) -> set[str]:
        """Return the field names of the plugin's empty item template."""
        return set(self.template_item())

    def add(self, config: AcmeItemConfig, ref_uuids: Mapping[tuple[str, str], str]) -> Any:
        """Create a row; raises when OPNsense rejects it."""
        spec = self.SPEC
        ep = spec.crud.add
        response = self.client.request(
            ep.method, ep.path(), data=config.to_payload(spec.item_key, ref_uuids)
        )
        return raise_on_failed_write(response, f"add acmeclient {spec.noun} {config.name!r}")

    def update(
        self, uuid: str, config: AcmeItemConfig, ref_uuids: Mapping[tuple[str, str], str]
    ) -> Any:
        """Update a row by UUID; raises when OPNsense rejects it."""
        spec = self.SPEC
        ep = spec.crud.update
        response = self.client.request(
            ep.method, ep.path(uuid=uuid), data=config.to_payload(spec.item_key, ref_uuids)
        )
        return raise_on_failed_write(response, f"update acmeclient {spec.noun} {config.name!r}")

    def delete(self, live: LiveAcmeItem) -> Any:
        """Delete a row by UUID."""
        spec = self.SPEC
        ep = spec.crud.delete
        response = self.client.request(ep.method, ep.path(uuid=live.uuid))
        return raise_on_failed_write(response, f"delete acmeclient {spec.noun} {live.name!r}")

    def reconfigure(self) -> Any:
        """Apply the saved ACME-client configuration.

        Called only by the provider's ``acmeclient_reconfigure`` finalization hook (and
        by the manager's destroy, which the hook does not cover).
        """
        ep = endpoints.ACMECLIENT_RECONFIGURE
        response = self.client.request(ep.method, ep.path())
        return raise_on_failed_write(response, "reconfigure acmeclient")

    def apply_diff(
        self, diff: Diff, ref_uuids: Mapping[tuple[str, str], str] | None = None
    ) -> dict[str, int]:
        """Dispatch the diff. The caller reconfigures through the finalization hook.

        Args:
            diff: The diff to apply.
            ref_uuids: ``(sub, handle)`` -> live UUID for references.

        Returns:
            ``{"created": N, "updated": M, "deleted": K}``.

        Raises:
            ReferenceValidationError: If an added or updated row references something
                not on the box. Checked before any write.
        """
        known = ref_uuids or {}
        for config in [*diff.adds, *(want for _, want in diff.updates)]:
            pending = config.pending_refs(known)
            if pending:
                names = ", ".join(f"{sub}.{handle}" for sub, handle in pending)
                raise ReferenceValidationError(
                    f"acmeclient {self.SPEC.noun} '{config.name}' references {names}, which "
                    f"is not on the box; apply it first"
                )
        created = updated = deleted = 0
        for config in diff.adds:
            self.add(config, known)
            created += 1
        for live, want in diff.updates:
            logger.info(
                "opnsense %s: updating %s (fields: %s)",
                self.SPEC.type_name,
                want.name,
                changed_fields(live, want, known),
            )
            self.update(live.uuid, want, known)
            updated += 1
        for live in diff.deletes:
            self.delete(live)
            deleted += 1
        return {"created": created, "updated": updated, "deleted": deleted}

    def export_rows(
        self,
        items: list[LiveAcmeItem],
        ref_handles: Mapping[str, Mapping[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Build the nested-YAML entries for live rows.

        Args:
            items: Live rows (from :meth:`search`).
            ref_handles: ``sub`` -> ``{uuid: handle}`` for reference fields.

        Returns:
            One ``{"name": handle, "config": {...}}`` per row. Secrets become
            ``secret://`` placeholders, never values. Empty fields are omitted, except
            booleans.
        """
        spec = self.SPEC
        handles = assign_handles(spec.sub, items)
        known = ref_handles or {}
        rows: list[dict[str, Any]] = []
        for item in items:
            handle = handles[item.uuid]
            config: dict[str, Any] = {}
            if spec.identity_key:
                config[spec.identity_key] = item.name
            elif item.name != handle:
                config["display_name"] = item.name
            for key, fspec in spec.fields.items():
                self._export_field(config, item, key, fspec, known, handle)
            for raw_key in sorted(item.raw):
                if raw_key in spec.fields or not spec.passthrough(raw_key):
                    continue
                if not exports_passthrough(spec, item.raw, raw_key):
                    continue
                flat = flatten_option(item.raw[raw_key]).strip()
                if not flat:
                    continue
                config[raw_key] = (
                    f"secret://env_secrets/opnsense/acmeclient/{spec.sub}/{handle}/{raw_key}"
                    if spec.is_secret(raw_key)
                    else flat
                )
            rows.append({"name": handle, "config": config})
        return rows

    def _export_field(
        self,
        config: dict[str, Any],
        item: LiveAcmeItem,
        key: str,
        fspec: FieldSpec,
        ref_handles: Mapping[str, Mapping[str, str]],
        handle: str,
    ) -> None:
        spec = self.SPEC
        flat = flatten_option(item.raw.get(fspec.wire)).strip()
        if fspec.kind == BOOL:
            config[key] = flat == "1"
            return
        if not flat:
            return
        if spec.is_secret(key):
            config[key] = f"secret://env_secrets/opnsense/acmeclient/{spec.sub}/{handle}/{key}"
        elif fspec.kind == INT:
            if flat.isascii() and flat.isdigit():
                config[key] = int(flat)
            else:
                logger.warning("acmeclient %s: non-integer %s; omitted", spec.sub, key)
        elif fspec.kind == SET:
            config[key] = sorted(_split(flat))
        elif fspec.kind in {REF, REFSET}:
            mapping = ref_handles.get(fspec.ref_sub, {})
            found: list[str] = []
            for uuid in _split(flat):
                if uuid in mapping:
                    found.append(mapping[uuid])
                else:
                    logger.warning(
                        "acmeclient %s: %s references an unknown %s row; dropped",
                        spec.sub,
                        key,
                        fspec.ref_sub,
                    )
            if found:
                config[key] = found if fspec.kind == REFSET else found[0]
        else:
            config[key] = flat

    def export_to_yaml(self, ref_handles: Mapping[str, Mapping[str, str]] | None = None) -> str:
        """Export every live row as nested YAML for ``config migrate``."""
        return emit_nested_list_yaml(
            self.SPEC.type_name, self.export_rows(self.search(), ref_handles)
        )


class AcmeAccountsService(AcmeListService):
    """Service for ``acmeclient.accounts``."""

    SPEC = ACCOUNTS


class AcmeValidationsService(AcmeListService):
    """Service for ``acmeclient.validations``."""

    SPEC = VALIDATIONS


class AcmeActionsService(AcmeListService):
    """Service for ``acmeclient.actions``."""

    SPEC = ACTIONS


class AcmeCertsService(AcmeListService):
    """Service for ``acmeclient.certs``."""

    SPEC = CERTS


#: Service class per reference target.
REF_SERVICES: dict[str, type[AcmeListService]] = {
    "accounts": AcmeAccountsService,
    "validations": AcmeValidationsService,
    "actions": AcmeActionsService,
}
