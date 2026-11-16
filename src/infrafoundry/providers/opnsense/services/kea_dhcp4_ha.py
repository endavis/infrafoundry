"""Kea DHCPv4 high-availability services for OPNsense direct-API operations (#1392).

Two surfaces on the ``kea/dhcpv4`` controller:

- :class:`KeaHASettingsService` manages the ``dhcpv4.ha`` section through
  ``GET kea/dhcpv4/get`` and ``POST kea/dhcpv4/set`` (``kea.dhcp4.ha``, a singleton).
- :class:`KeaHAPeerService` manages the peer grid through
  ``kea/dhcpv4/{searchPeer,getPeer,addPeer,setPeer,delPeer}`` (``kea.dhcp4.ha_peers``, a
  managed-set list keyed by the peer ``name``).

Both are applied by the shared ``kea_reconfigure`` finalization hook
(``kea/service/reconfigure``).

Settings YAML keys (all optional; only declared keys are compared and written):

- ``enabled``              -> ``enabled`` (bool)
- ``this_server_name``     -> ``this_server_name`` (string, ``""`` = the node's hostname)
- ``max_unacked_clients``  -> ``max_unacked_clients`` (non-negative int)

The write body is ``{"dhcpv4": {"ha": {...}}}`` only: MVC ``set`` updates just the nodes
posted, so ``general`` and ``lexpire`` are never echoed. Read-only ``%``-prefixed display
values (``%this_server_name``) are dropped from the write.

Peer YAML keys: ``name``, ``role`` (``primary`` or ``standby``), ``url`` and ``lock``.
The box assigns ``uuid``; it is not a YAML field.

What is verified and what is not
--------------------------------

- Verified by a read-only probe (#1392): the ``dhcpv4.ha`` section of ``get`` and the
  ``searchPeer`` grid; the ``getPeer`` template returns envelope ``peer`` with ``name``,
  ``role`` (an option dict) and ``url``. The 26.1.x OpenAPI specs list every action above.
- Not verified until the #1392 live test: the ``{"peer": {...}}`` write envelope on
  ``addPeer`` / ``setPeer``, the ``delPeer`` reply, and ``set`` leaving ``general`` alone.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from ._identity import OpnsenseDriftError
from ._nested_emit import emit_nested_list_yaml, emit_nested_singleton_yaml
from .base import BaseService, raise_on_failed_write
from .openvpn_instances import flatten_option

logger = logging.getLogger(__name__)

_PEER_TYPE = "kea.dhcp4.ha_peers"
_HA_TYPE = "kea.dhcp4.ha"

#: YAML key -> wire key under ``dhcpv4.ha``.
HA_FIELD_MAP: dict[str, str] = {
    "enabled": "enabled",
    "this_server_name": "this_server_name",
    "max_unacked_clients": "max_unacked_clients",
}
HA_BOOL_FIELDS: frozenset[str] = frozenset({"enabled"})
HA_STRING_FIELDS: frozenset[str] = frozenset({"this_server_name"})
HA_INT_FIELDS: frozenset[str] = frozenset({"max_unacked_clients"})

#: Every config key a ``kea.dhcp4.ha_peers`` resource accepts (parser and validator).
PEER_ALLOWED_KEYS: frozenset[str] = frozenset({"name", "role", "url", "lock"})
#: Keys the box assigns itself.
PEER_BOX_ASSIGNED_KEYS: frozenset[str] = frozenset({"uuid"})
PEER_ROLES: tuple[str, ...] = ("primary", "standby")

__all__ = [
    "HA_BOOL_FIELDS",
    "HA_FIELD_MAP",
    "HA_INT_FIELDS",
    "HA_STRING_FIELDS",
    "PEER_ALLOWED_KEYS",
    "PEER_BOX_ASSIGNED_KEYS",
    "PEER_ROLES",
    "Diff",
    "KeaHAPeerConfig",
    "KeaHAPeerService",
    "KeaHASettingsService",
    "LiveKeaHAPeer",
    "changed_fields",
    "compute_diff",
    "peer_configs_from_resources",
    "serialize_ha_setting",
]


def serialize_ha_setting(key: str, value: Any) -> str:
    """Serialize one HA settings value to its wire string.

    Raises:
        InvalidConfigurationError: On a wrong type or out-of-range value (no value shown).
    """
    label = f"{_HA_TYPE} {key}"
    if key in HA_BOOL_FIELDS:
        if not isinstance(value, bool):
            raise InvalidConfigurationError(f"{label} must be a boolean")
        return "1" if value else "0"
    if key in HA_STRING_FIELDS:
        if not isinstance(value, str):
            raise InvalidConfigurationError(f"{label} must be a string")
        return value
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidConfigurationError(f"{label} must be an integer")
    if value < 0:
        raise InvalidConfigurationError(f"{label} must be a non-negative integer")
    return str(value)


class KeaHASettingsService(BaseService):
    """Service for the ``dhcpv4.ha`` settings singleton."""

    def get_settings(self) -> Any:
        """Fetch the Kea DHCPv4 settings document."""
        ep = endpoints.KEA_DHCPV4_GET
        return self.client.request(ep.method, ep.path())

    def set_settings(self, payload: dict[str, Any]) -> Any:
        """Write the HA section.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        ep = endpoints.KEA_DHCPV4_SET
        response = self.client.request(ep.method, ep.path(), data=payload)
        return raise_on_failed_write(response, "set kea dhcpv4 ha settings")

    def live_ha(self, response: Any) -> dict[str, Any]:
        """Return ``response["dhcpv4"]["ha"]``.

        Raises:
            APIError: If the section is missing, so a write is never built from nothing.
        """
        dhcpv4 = response.get("dhcpv4") if isinstance(response, dict) else None
        ha = dhcpv4.get("ha") if isinstance(dhcpv4, dict) else None
        if not isinstance(ha, dict):
            raise APIError(
                "OPNsense kea/dhcpv4/get returned no dhcpv4.ha section",
                response=str(sorted(response)) if isinstance(response, dict) else "",
                provider="opnsense",
            )
        return ha

    def build_desired(self, resource: ResourceConfig) -> dict[str, str]:
        """Build the desired wire strings for the declared keys only.

        Raises:
            InvalidConfigurationError: On unknown keys or wrongly typed values.
        """
        config = resource.config
        unknown = sorted(set(config) - set(HA_FIELD_MAP))
        if unknown:
            raise InvalidConfigurationError(f"{_HA_TYPE} has unknown key(s): {', '.join(unknown)}")
        return {
            key: serialize_ha_setting(key, config[key]) for key in HA_FIELD_MAP if key in config
        }

    def extract_live(self, ha: dict[str, Any], keys: Iterable[str]) -> dict[str, str]:
        """Extract the given YAML keys from the live section, as wire strings.

        Raises:
            APIError: For an absent field.
        """
        live: dict[str, str] = {}
        for key in keys:
            wire = HA_FIELD_MAP[key]
            if wire not in ha:
                raise APIError(
                    f"OPNsense kea/dhcpv4/get returned no ha '{wire}' field",
                    response=str(sorted(ha))[:200],
                    provider="opnsense",
                )
            live[key] = flatten_option(ha[wire])
        return live

    def drift(self, live: dict[str, str], desired: dict[str, str]) -> dict[str, str] | None:
        """Compare declared keys; return ``desired`` on any difference."""
        for key, value in desired.items():
            if live.get(key) != value:
                return desired
        return None

    def build_set_payload(self, ha: dict[str, Any], desired: dict[str, str]) -> dict[str, Any]:
        """Build the write body: the flattened live ``ha`` section, declared fields set.

        ``%``-prefixed read-only display values are dropped. Only ``dhcpv4.ha`` is sent.
        """
        flat = {key: flatten_option(value) for key, value in ha.items() if not key.startswith("%")}
        for key, value in desired.items():
            flat[HA_FIELD_MAP[key]] = value
        return {"dhcpv4": {"ha": flat}}

    def export_to_yaml(self) -> str:
        """Export every mapped field present on the box as nested YAML."""
        ha = self.live_ha(self.get_settings())
        present = [key for key, wire in HA_FIELD_MAP.items() if wire in ha]
        live = self.extract_live(ha, present)
        clean: dict[str, Any] = {}
        for key in present:
            text = live[key]
            if key in HA_BOOL_FIELDS:
                clean[key] = text == "1"
            elif key in HA_STRING_FIELDS:
                clean[key] = text
            elif text.isascii() and text.isdigit():
                clean[key] = int(text)
            else:
                logger.warning("%s: non-integer %s; omitted", _HA_TYPE, key)
        return emit_nested_singleton_yaml(_HA_TYPE, clean)


@dataclass(frozen=True)
class KeaHAPeerConfig:
    """Desired-state HA peer.

    Attributes:
        name: Peer name; the identity (Kea requires it unique).
        role: ``primary`` or ``standby``.
        url: Peer control-agent URL.
        lock: Per-resource safety annotation (ADR-0014 section 6).
    """

    name: str
    role: str
    url: str
    lock: bool = False

    @property
    def diff_key(self) -> str:
        """Identity of this peer: its name."""
        return self.name

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the ``add``/``set`` envelope."""
        return {"peer": {"name": self.name, "role": self.role, "url": self.url}}


@dataclass(frozen=True)
class LiveKeaHAPeer:
    """A peer as currently on the box."""

    uuid: str
    name: str
    role: str = ""
    url: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def diff_key(self) -> str:
        """Identity of this peer: its name."""
        return self.name


@dataclass
class Diff:
    """Result of comparing desired peers to live ones."""

    adds: list[KeaHAPeerConfig] = field(default_factory=list)
    updates: list[tuple[LiveKeaHAPeer, KeaHAPeerConfig]] = field(default_factory=list)
    deletes: list[LiveKeaHAPeer] = field(default_factory=list)
    unmanaged: list[LiveKeaHAPeer] = field(default_factory=list)
    locked: list[tuple[KeaHAPeerConfig, LiveKeaHAPeer | None]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there is nothing to add, update or delete."""
        return not (self.adds or self.updates or self.deletes)


def changed_fields(have: LiveKeaHAPeer, want: KeaHAPeerConfig) -> list[str]:
    """Return the field names whose live value differs; the name is the identity."""
    changed: list[str] = []
    if have.role != want.role:
        changed.append("role")
    if have.url != want.url:
        changed.append("url")
    return changed


def compute_diff(
    desired: list[KeaHAPeerConfig],
    current: list[LiveKeaHAPeer],
    *,
    add_only: bool = False,
    managed_keys: set[str] | None = None,
) -> Diff:
    """Compare desired peers to live ones, keyed by name.

    Args:
        desired: Peers the operator wants.
        current: Peers currently on the box.
        add_only: Suppress deletes.
        managed_keys: When given, only live peers in this set may be deleted
            (ADR-0018); others land in ``Diff.unmanaged``.

    Raises:
        OpnsenseDriftError: If two live peers share a name that is desired or managed
            (or any name, when ``managed_keys`` is ``None``).
    """
    desired_by_key = {c.diff_key: c for c in desired}
    locked_keys = {c.diff_key for c in desired if c.lock}

    rows: dict[str, list[LiveKeaHAPeer]] = {}
    for live in current:
        rows.setdefault(live.diff_key, []).append(live)
    current_by_key: dict[str, LiveKeaHAPeer] = {}
    for key, group in rows.items():
        if len(group) > 1:
            related = key in desired_by_key or managed_keys is None or key in managed_keys
            if related:
                raise OpnsenseDriftError(
                    f"kea ha peers: more than one live peer is named {key!r}; "
                    f"remove the extra on the box before planning"
                )
            continue
        current_by_key[key] = group[0]

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
        else:
            diff.deletes.append(have)
    return diff


def peer_configs_from_resources(resources: list[ResourceConfig]) -> list[KeaHAPeerConfig]:
    """Convert ``kea.dhcp4.ha_peers`` resources to :class:`KeaHAPeerConfig`.

    Raises:
        ValueError: On a non-dict config, an unknown key, a missing name, role or url, a
            bad role, or a mistyped value. Messages name the resource.
    """
    configs: list[KeaHAPeerConfig] = []
    for resource in resources:
        if resource.type != _PEER_TYPE:
            continue
        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"kea ha peer '{resource.name}' has non-dict config")
        configs.append(_build_config(resource.name, config))
    return configs


def _build_config(resource_name: str, config: dict[str, Any]) -> KeaHAPeerConfig:
    label = f"kea ha peer '{resource_name}'"
    unknown = sorted(set(config) - PEER_ALLOWED_KEYS)
    if unknown:
        raise ValueError(f"{label} has unknown keys: {unknown}")
    name = config.get("name", resource_name)
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{label} requires a name")
    role = config.get("role")
    if role not in PEER_ROLES:
        raise ValueError(f"{label} role must be one of: {', '.join(PEER_ROLES)}")
    url = config.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError(f"{label} requires a url")
    if not isinstance(config.get("lock", False), bool):
        raise ValueError(f"{label} lock must be a boolean")
    return KeaHAPeerConfig(
        name=name.strip(),
        role=role,
        url=url.strip(),
        lock=bool(config.get("lock", False)),
    )


def _slug(text: str, fallback: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or fallback


class KeaHAPeerService(BaseService):
    """Service for HA peers via ``kea/dhcpv4/*Peer``."""

    def search(self) -> list[LiveKeaHAPeer]:
        """Fetch every live peer: one search, then ``getPeer/{uuid}`` per row.

        The search rows may carry display labels, so they supply only ``uuid`` and
        ``name``; ``role`` (an option dict on ``get``) and ``url`` come from ``getPeer``.
        """
        crud = endpoints.KEA_CRUD[("dhcpv4", "Peer")]
        response = self.client.request(crud.search.method, crud.search.path())
        raw_rows = response.get("rows") if isinstance(response, dict) else None
        if not isinstance(raw_rows, list):
            return []
        assert crud.get is not None
        peers: list[LiveKeaHAPeer] = []
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            uuid = str(row.get("uuid", ""))
            detail = self.client.request(crud.get.method, crud.get.path(uuid=uuid))
            body = detail.get("peer") if isinstance(detail, dict) else None
            if not isinstance(body, dict):
                body = row
            peers.append(
                LiveKeaHAPeer(
                    uuid=uuid,
                    name=flatten_option(row.get("name", body.get("name"))).strip(),
                    role=flatten_option(body.get("role")),
                    url=flatten_option(body.get("url")).strip(),
                    raw=row,
                )
            )
        return peers

    def add(self, config: KeaHAPeerConfig) -> dict[str, Any]:
        """Create a peer; raises when OPNsense rejects it."""
        ep = endpoints.KEA_CRUD[("dhcpv4", "Peer")].add
        response = self.client.request(ep.method, ep.path(), data=config.to_payload())
        raise_on_failed_write(response, f"add kea ha peer {config.name!r}")
        return response

    def update(self, uuid: str, config: KeaHAPeerConfig) -> dict[str, Any]:
        """Update a peer by UUID; raises when OPNsense rejects it."""
        ep = endpoints.KEA_CRUD[("dhcpv4", "Peer")].update
        response = self.client.request(ep.method, ep.path(uuid=uuid), data=config.to_payload())
        raise_on_failed_write(response, f"update kea ha peer {config.name!r}")
        return response

    def delete(self, live: LiveKeaHAPeer) -> None:
        """Delete a peer by UUID.

        Raises:
            APIError: On a failed write or a reply other than ``{"result": "deleted"}``.
        """
        ep = endpoints.KEA_CRUD[("dhcpv4", "Peer")].delete
        response = self.client.request(ep.method, ep.path(uuid=live.uuid))
        action = f"delete kea ha peer '{live.name}'"
        raise_on_failed_write(response, action)
        if not isinstance(response, dict) or response.get("result") != "deleted":
            raise APIError(
                f"OPNsense did not confirm {action}: unexpected reply",
                response=str(response),
                provider="opnsense",
            )

    def reconfigure(self) -> Any:
        """Apply the saved Kea configuration (used by a manager's destroy)."""
        ep = endpoints.KEA_RECONFIGURE
        response = self.client.request(ep.method, ep.path())
        return raise_on_failed_write(response, "reconfigure kea")

    def compute_diff(
        self,
        desired: list[KeaHAPeerConfig],
        live: list[LiveKeaHAPeer],
        *,
        add_only: bool = False,
        managed_keys: set[str] | None = None,
    ) -> Diff:
        """Service-method form of :func:`compute_diff`."""
        return compute_diff(desired, live, add_only=add_only, managed_keys=managed_keys)

    def apply_diff(self, diff: Diff) -> dict[str, int]:
        """Dispatch the diff. Reconfigure is left to the finalization hook.

        Returns:
            ``{"created": N, "updated": M, "deleted": K}``.
        """
        created = updated = deleted = 0
        for config in diff.adds:
            self.add(config)
            created += 1
        for live, want in diff.updates:
            logger.info(
                "opnsense kea.dhcp4.ha_peers: updating %s (fields: %s)",
                want.name,
                changed_fields(live, want),
            )
            self.update(live.uuid, want)
            updated += 1
        for live in diff.deletes:
            self.delete(live)
            deleted += 1
        return {"created": created, "updated": updated, "deleted": deleted}

    def export_to_yaml(self, reserved: Collection[str] = ()) -> str:
        """Export the live peers to InfraFoundry YAML.

        The handle is a slug of the name (``-2``, ``-3`` ... on a collision with
        ``reserved`` or an earlier row).
        """
        taken: set[str] = set(reserved)
        entries: list[dict[str, Any]] = []
        for live in self.search():
            base = _slug(live.name, "peer")
            handle, n = base, 1
            while handle in taken:
                n += 1
                handle = f"{base}-{n}"
            taken.add(handle)
            config: dict[str, Any] = {"name": live.name, "role": live.role, "url": live.url}
            entries.append({"name": handle, "config": config})
        return emit_nested_list_yaml(_PEER_TYPE, entries)
