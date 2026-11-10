"""OpenVPN static-key service for OPNsense direct-API operations (ADR-0014, #1319).

Manages the static keys (tls-auth, tls-crypt, tls-crypt-v2) an OpenVPN instance
references through its ``tls_key`` field. They live in a sub-API of the instances
controller: ``openvpn/instances/{search,get,add,set,del}StaticKey``. Static keys
sit before ``openvpn.instances`` in the dispatch table; an instance names one with
``tls_key_ref``.

Identity is the live ``description`` against the YAML ``description`` (falling back
to the resource name). A change of description is a delete plus an add. The box
assigns ``uuid``; it is not a YAML field.

Mode
----

``mode`` is required and one of ``auth``, ``crypt`` or ``crypt-v2``. The model's
empty template silently selects ``crypt``, and a wrong mode breaks the tunnel, so
the mode is always sent and compared.

Key material
------------

``key`` is required and must be a ``secret://`` URI in YAML (the validator rejects
literals). The manager resolves it before this module runs. It is never logged,
put in an exception message or shown in a ``repr``; log lines name changed fields
only.

A static key file usually opens with ``#`` comment lines before its
``-----BEGIN`` marker line (OPNsense ``genKey`` and
``openvpn --genkey`` both write them), so :func:`key_block` keeps only the
BEGIN..END block, whitespace-normalized; the marker check and the comparison use it.

``key`` is compared only when the live row returns a non-empty value, with
:func:`key_block` on both sides. When the box does not return it, the
key is write-only: sent on add; on update only when the comparison found a
difference or ``update_key: true`` is set.

What is verified and what is not
--------------------------------

- Verified live on a test firewall (#1319): the envelope is ``statickey`` with
  ``mode``, ``key`` and ``description``; ``getStaticKey/{uuid}`` echoes ``key``;
  ``searchStaticKey`` rows carry ``uuid``, ``description``, ``mode``, ``%mode`` and
  ``key``. The code still treats an empty live ``key`` as write-only.
- Not verified: ``crypt-v2`` on a box.
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from ._identity import OpnsenseDriftError
from .base import BaseService, raise_on_failed_write
from .openvpn_instances import description_of, flatten_option, search_uuids
from .trust import normalize_pem

logger = logging.getLogger(__name__)

_BEGIN = "-----BEGIN "
_END = "-----END "


def key_block(value: str) -> str:
    """Return the BEGIN..END block of a static key, whitespace-normalized.

    Lines before the BEGIN line (``#`` comments) and after the END line are
    dropped, so a key with or without its comment header compares equal.

    Args:
        value: Key text, possibly empty.

    Returns:
        The normalized block, or ``""`` when there is no BEGIN line followed by
        an END line.
    """
    lines = normalize_pem(value).splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(_BEGIN)), None)
    if start is None:
        return ""
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith(_END)), None)
    if end is None:
        return ""
    return "\n".join(lines[start : end + 1])


_TYPE = "openvpn.static_keys"

#: Modes the model offers.
MODES: tuple[str, ...] = ("auth", "crypt", "crypt-v2")

#: Every config key an ``openvpn.static_keys`` resource accepts (single source for
#: the parser and the validator).
ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        # The nested loader copies the entry name into config (package_loader).
        "name",
        "description",
        "mode",
        "key",
        "update_key",
        "lock",
    }
)
#: Keys the box assigns itself.
BOX_ASSIGNED_KEYS: frozenset[str] = frozenset({"uuid"})

__all__ = [
    "ALLOWED_KEYS",
    "BOX_ASSIGNED_KEYS",
    "MODES",
    "Diff",
    "LiveStaticKey",
    "OpenVpnStaticKeyConfig",
    "OpenVpnStaticKeyService",
    "changed_fields",
    "compute_diff",
    "description_of",
    "key_block",
    "static_key_configs_from_resources",
    "static_key_uuids_by_name",
]


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OpenVpnStaticKeyConfig:
    """Desired-state OpenVPN static key.

    Attributes:
        name: Operator-facing YAML name.
        description: Wire ``description`` and the identity (defaults to ``name``).
        mode: ``auth``, ``crypt`` or ``crypt-v2``.
        key: Key material (a ``secret://`` URI until the manager resolves it;
            plaintext afterwards). Never shown in ``repr``.
        update_key: Send ``key`` on update too, whatever the comparison found.
        lock: Per-resource safety annotation (ADR-0014 section 6).
    """

    name: str
    description: str
    mode: str
    key: str = field(default="", repr=False)
    update_key: bool = False
    lock: bool = False

    @property
    def diff_key(self) -> str:
        """Identity of this key: its description."""
        return self.description

    def to_payload(self, *, include_key: bool = True) -> dict[str, Any]:
        """Serialize to the ``add``/``set`` envelope.

        Args:
            include_key: Add ``key``. True on add; on update only when the key
                changed or ``update_key`` is set.

        Returns:
            ``{"statickey": {...}}``.
        """
        body: dict[str, Any] = {"description": self.description, "mode": self.mode}
        if include_key:
            body["key"] = self.key
        return {"statickey": body}


@dataclass(frozen=True)
class LiveStaticKey:
    """A static key as currently on the box (a ``getStaticKey`` result).

    Attributes:
        uuid: Row UUID.
        description: Live description.
        mode: Flattened live mode.
        key: Live key material, empty when the box does not return it. Never
            shown in ``repr``.
        raw: The ``statickey`` object returned by ``get``. Never shown in ``repr``.
    """

    uuid: str
    description: str
    mode: str
    key: str = field(default="", repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def diff_key(self) -> str:
        """Identity of this key: its description."""
        return self.description


@dataclass
class Diff:
    """Result of comparing desired static keys to live ones.

    ``blocked`` holds managed live keys that would be deleted but must stay because
    a live instance still references them, each with the reason.
    """

    adds: list[OpenVpnStaticKeyConfig] = field(default_factory=list)
    updates: list[tuple[LiveStaticKey, OpenVpnStaticKeyConfig]] = field(default_factory=list)
    deletes: list[LiveStaticKey] = field(default_factory=list)
    unmanaged: list[LiveStaticKey] = field(default_factory=list)
    locked: list[tuple[OpenVpnStaticKeyConfig, LiveStaticKey | None]] = field(default_factory=list)
    blocked: list[tuple[LiveStaticKey, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there is nothing to add, update or delete."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def changed_fields(have: LiveStaticKey, want: OpenVpnStaticKeyConfig) -> list[str]:
    """Return the field names whose live value differs from the desired one.

    ``description`` is the identity and never a change. ``mode`` always compares.
    ``key`` compares only when the live row returns a non-empty value; otherwise it
    appears only with ``update_key`` (the live value is write-only).

    Args:
        have: Live key.
        want: Desired key, with the key material resolved.

    Returns:
        Field names only, never values.
    """
    changed: list[str] = []
    if have.mode != want.mode:
        changed.append("mode")
    if have.key.strip():
        if key_block(have.key) != key_block(want.key):
            changed.append("key")
    elif want.update_key and want.key:
        changed.append("key")
    return changed


def compute_diff(
    desired: list[OpenVpnStaticKeyConfig],
    current: list[LiveStaticKey],
    *,
    add_only: bool = False,
    managed_keys: set[str] | None = None,
    in_use_uuids: Collection[str] | None = None,
) -> Diff:
    """Compare desired static keys to live ones, keyed by description.

    Args:
        desired: Keys the operator wants.
        current: Keys currently on the box.
        add_only: Suppress deletes.
        managed_keys: When given, only live keys in this set may be deleted
            (ADR-0018); others land in ``Diff.unmanaged``.
        in_use_uuids: Uuids of keys a live instance still references. A managed
            delete in this set goes to ``Diff.blocked`` with a warning.

    Returns:
        The diff.

    Raises:
        OpnsenseDriftError: If two live keys share a description.
    """
    in_use = set(in_use_uuids or ())
    current_by_key: dict[str, LiveStaticKey] = {}
    for live in current:
        if live.diff_key in current_by_key:
            raise OpnsenseDriftError(
                f"openvpn static keys: more than one live key has description "
                f"{live.diff_key!r}; rename one on the box before planning"
            )
        current_by_key[live.diff_key] = live
    desired_by_key = {c.diff_key: c for c in desired}
    locked_keys = {c.diff_key for c in desired if c.lock}

    diff = Diff()
    for key, want in desired_by_key.items():
        have = current_by_key.get(key)
        if want.lock:
            diff.locked.append((want, have))
        elif have is None:
            diff.adds.append(want)
        elif changed_fields(have, want):
            diff.updates.append((have, want))

    if add_only:
        return diff
    for key, have in current_by_key.items():
        if key in locked_keys or key in desired_by_key:
            continue
        if managed_keys is not None and key not in managed_keys:
            diff.unmanaged.append(have)
        elif have.uuid in in_use:
            reason = "a live instance still references it"
            diff.blocked.append((have, reason))
            diff.warnings.append(f"openvpn static key {key!r} kept: {reason}")
        else:
            diff.deletes.append(have)
    return diff


def static_key_uuids_by_name(
    resources: list[ResourceConfig], live: list[LiveStaticKey]
) -> dict[str, str]:
    """Map each ``openvpn.static_keys`` resource name to the uuid of its live row.

    Args:
        resources: Resources of any type; only ``openvpn.static_keys`` are read
            (secrets need not be resolved).
        live: Live keys from :meth:`OpenVpnStaticKeyService.search`.

    Returns:
        ``{resource_name: uuid}``; a key with no live row is left out.
    """
    uuid_by_descr = {row.description: row.uuid for row in live if row.uuid}
    result: dict[str, str] = {}
    for resource in resources:
        if resource.type != _TYPE:
            continue
        uuid = uuid_by_descr.get(description_of(resource.name, resource.config))
        if uuid:
            result[resource.name] = uuid
    return result


# ---------------------------------------------------------------------------
# Resource-to-domain conversion
# ---------------------------------------------------------------------------


def static_key_configs_from_resources(
    resources: list[ResourceConfig], *, require_key: bool = False
) -> list[OpenVpnStaticKeyConfig]:
    """Convert ``openvpn.static_keys`` resources to :class:`OpenVpnStaticKeyConfig`.

    Args:
        resources: Provider resources; other types are skipped.
        require_key: Check that ``key`` carries PEM BEGIN/END markers. True only
            after secret resolution; managed rows still hold URIs and parse with
            False.

    Returns:
        Parsed keys.

    Raises:
        ValueError: On a non-dict config, an unknown key, a missing or invalid
            ``mode``, a missing ``key``, or a mistyped value. Messages name the
            resource and the field, never a value.
    """
    configs: list[OpenVpnStaticKeyConfig] = []
    for resource in resources:
        if resource.type != _TYPE:
            continue
        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"openvpn static key '{resource.name}' has non-dict config")
        configs.append(_build_config(resource.name, config, require_key=require_key))
    return configs


def _build_config(
    name: str, config: dict[str, Any], *, require_key: bool
) -> OpenVpnStaticKeyConfig:
    label = f"openvpn static key '{name}'"
    unknown = sorted(set(config) - ALLOWED_KEYS)
    if unknown:
        raise ValueError(f"{label} has unknown keys: {unknown}")
    description = config.get("description")
    if description is not None and not isinstance(description, str):
        raise ValueError(f"{label} description must be a string")
    for flag in ("lock", "update_key"):
        if not isinstance(config.get(flag, False), bool):
            raise ValueError(f"{label} {flag} must be a boolean")
    mode = config.get("mode")
    if mode not in MODES:
        raise ValueError(f"{label} requires 'mode' to be one of {list(MODES)}")
    key = config.get("key")
    if not isinstance(key, str) or not key.strip():
        raise ValueError(f"{label} requires a non-empty string 'key'")
    if require_key and not key_block(key):
        raise ValueError(f"{label} key does not look like a PEM block (missing BEGIN/END markers)")
    return OpenVpnStaticKeyConfig(
        name=name,
        description=description if isinstance(description, str) and description else name,
        mode=str(mode),
        key=key,
        update_key=bool(config.get("update_key", False)),
        lock=bool(config.get("lock", False)),
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class OpenVpnStaticKeyService(BaseService):
    """Service for OpenVPN static keys via the ``openvpn/instances`` controller."""

    def search(self) -> list[LiveStaticKey]:
        """Fetch every live static key.

        ``searchStaticKey`` rows are read only for their uuids; each key is then
        read with ``getStaticKey/{uuid}`` for its full field set.
        """
        search = endpoints.OPENVPN_STATIC_KEY.search
        get = endpoints.OPENVPN_STATIC_KEY.read
        live: list[LiveStaticKey] = []
        for uuid in search_uuids(self.client.request(search.method, search.path())):
            response = self.client.request(get.method, get.path(uuid=uuid))
            row = response.get("statickey") if isinstance(response, dict) else None
            if not isinstance(row, dict):
                continue
            live.append(
                LiveStaticKey(
                    uuid=uuid,
                    description=flatten_option(row.get("description")),
                    mode=flatten_option(row.get("mode")),
                    key=flatten_option(row.get("key")),
                    raw=row,
                )
            )
        return live

    def add(self, config: OpenVpnStaticKeyConfig) -> dict[str, Any]:
        """Create a static key; raises when OPNsense rejects it."""
        ep = endpoints.OPENVPN_STATIC_KEY.add
        response = self.client.request(ep.method, ep.path(), data=config.to_payload())
        raise_on_failed_write(response, f"add openvpn static key {config.name!r}")
        return response

    def update(
        self, uuid: str, config: OpenVpnStaticKeyConfig, *, include_key: bool
    ) -> dict[str, Any]:
        """Update a static key by UUID; raises when OPNsense rejects it.

        Args:
            uuid: Row UUID.
            config: Desired key.
            include_key: Send the key material too.
        """
        ep = endpoints.OPENVPN_STATIC_KEY.update
        response = self.client.request(
            ep.method, ep.path(uuid=uuid), data=config.to_payload(include_key=include_key)
        )
        raise_on_failed_write(response, f"update openvpn static key {config.name!r}")
        return response

    def delete(self, live: LiveStaticKey) -> dict[str, Any]:
        """Delete a static key by UUID."""
        ep = endpoints.OPENVPN_STATIC_KEY.delete
        response = self.client.request(ep.method, ep.path(uuid=live.uuid))
        raise_on_failed_write(response, f"delete openvpn static key {live.description!r}")
        return response

    def reconfigure(self) -> dict[str, Any]:
        """Apply pending changes (``openvpn/service/reconfigure``).

        Called by the provider's ``openvpn_reconfigure`` finalization hook and by
        the manager's destroy, which the hook does not cover.
        """
        ep = endpoints.OPENVPN_RECONFIGURE
        response = self.client.request(ep.method, ep.path())
        raise_on_failed_write(response, "reconfigure openvpn")
        return response

    def compute_diff(
        self,
        desired: list[OpenVpnStaticKeyConfig],
        live: list[LiveStaticKey],
        *,
        add_only: bool = False,
        managed_keys: set[str] | None = None,
        in_use_uuids: Collection[str] | None = None,
    ) -> Diff:
        """Service-method form of :func:`compute_diff`."""
        return compute_diff(
            desired,
            live,
            add_only=add_only,
            managed_keys=managed_keys,
            in_use_uuids=in_use_uuids,
        )

    def apply_diff(self, diff: Diff) -> dict[str, int]:
        """Dispatch the diff. The caller reconfigures through the finalization hook.

        Args:
            diff: The diff to apply.

        Returns:
            ``{"created": N, "updated": M, "deleted": K}``.
        """
        created = updated = deleted = 0
        for config in diff.adds:
            self.add(config)
            created += 1
        for live, want in diff.updates:
            fields = changed_fields(live, want)
            logger.info("opnsense openvpn.static_keys: updating %s (fields: %s)", want.name, fields)
            self.update(live.uuid, want, include_key="key" in fields or want.update_key)
            updated += 1
        for live in diff.deletes:
            self.delete(live)
            deleted += 1
        return {"created": created, "updated": updated, "deleted": deleted}
