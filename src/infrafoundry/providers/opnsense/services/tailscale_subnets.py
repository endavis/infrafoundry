"""Tailscale advertised-subnet service for OPNsense direct-API operations (#787).

Manages ``tailscale.subnets`` over ``tailscale/settings/{searchSubnet,addSubnet,
setSubnet,delSubnet}``. The subnets of ``os-tailscale`` are rows of the plugin's
settings model; the controller's reconfigure action is ``tailscale/service/reconfigure``,
fired by the ``tailscale_reconfigure`` finalization hook.

Identity is the normalized ``subnet`` CIDR (:func:`normalize_cidr`), so ``2001:DB8::/64``
and ``2001:db8::/64`` are the same subnet. ``description`` defaults to ``""`` and is always
compared and sent. IPv4 and IPv6 share the wire envelope ``subnet4``. The box assigns
``uuid``; it is not a YAML field.

What is verified and what is not
--------------------------------

- Verified by a read-only probe (#787): ``searchSubnet`` returns the usual grid and
  ``getSubnet`` (the template) returns envelope ``subnet4`` with ``subnet`` and
  ``description``.
- Verified on a test firewall: ``addSubnet``, ``setSubnet`` (same uuid) and
  ``delSubnet`` (reply ``{"result": "deleted"}``); search rows carry ``uuid``,
  ``subnet`` and ``description``.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from ._identity import OpnsenseDriftError
from ._nested_emit import emit_nested_list_yaml
from .base import BaseService, raise_on_failed_write
from .openvpn_instances import flatten_option

logger = logging.getLogger(__name__)

_TYPE = "tailscale.subnets"

#: Every config key a ``tailscale.subnets`` resource accepts (parser and validator).
ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        # The nested loader copies the entry name into config (package_loader).
        "name",
        "subnet",
        "description",
        "lock",
    }
)
#: Keys the box assigns itself.
BOX_ASSIGNED_KEYS: frozenset[str] = frozenset({"uuid"})

__all__ = [
    "ALLOWED_KEYS",
    "BOX_ASSIGNED_KEYS",
    "Diff",
    "LiveTailscaleSubnet",
    "TailscaleSubnetConfig",
    "TailscaleSubnetService",
    "changed_fields",
    "compute_diff",
    "normalize_cidr",
    "subnet_configs_from_resources",
]


def normalize_cidr(value: str) -> str:
    """Return the canonical form of a network, or the stripped raw string if it is not one.

    Host bits are not accepted (``strict=True``); such a value keeps its raw form.
    """
    text = value.strip()
    try:
        return str(ipaddress.ip_network(text, strict=True))
    except ValueError:
        return text


@dataclass(frozen=True)
class TailscaleSubnetConfig:
    """Desired-state advertised subnet.

    Attributes:
        name: Operator-facing YAML resource name.
        subnet: Normalized CIDR; the identity.
        description: Free text; empty for none.
        lock: Per-resource safety annotation (ADR-0014 section 6).
    """

    name: str
    subnet: str
    description: str = ""
    lock: bool = False

    @property
    def diff_key(self) -> str:
        """Identity of this subnet: its normalized CIDR."""
        return self.subnet

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the ``add``/``set`` envelope."""
        return {"subnet4": {"subnet": self.subnet, "description": self.description}}


@dataclass(frozen=True)
class LiveTailscaleSubnet:
    """A subnet as currently on the box (a ``searchSubnet`` row)."""

    uuid: str
    subnet: str
    description: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def diff_key(self) -> str:
        """Identity of this subnet: its normalized CIDR."""
        return normalize_cidr(self.subnet)


@dataclass
class Diff:
    """Result of comparing desired subnets to live ones."""

    adds: list[TailscaleSubnetConfig] = field(default_factory=list)
    updates: list[tuple[LiveTailscaleSubnet, TailscaleSubnetConfig]] = field(default_factory=list)
    deletes: list[LiveTailscaleSubnet] = field(default_factory=list)
    unmanaged: list[LiveTailscaleSubnet] = field(default_factory=list)
    locked: list[tuple[TailscaleSubnetConfig, LiveTailscaleSubnet | None]] = field(
        default_factory=list
    )
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there is nothing to add, update or delete."""
        return not (self.adds or self.updates or self.deletes)


def changed_fields(have: LiveTailscaleSubnet, want: TailscaleSubnetConfig) -> list[str]:
    """Return the field names whose live value differs; the CIDR is the identity."""
    return ["description"] if have.description != want.description else []


def compute_diff(
    desired: list[TailscaleSubnetConfig],
    current: list[LiveTailscaleSubnet],
    *,
    add_only: bool = False,
    managed_keys: set[str] | None = None,
) -> Diff:
    """Compare desired subnets to live ones, keyed by normalized CIDR.

    Args:
        desired: Subnets the operator wants.
        current: Subnets currently on the box.
        add_only: Suppress deletes.
        managed_keys: When given, only live subnets in this set may be deleted
            (ADR-0018); others land in ``Diff.unmanaged``.

    Raises:
        OpnsenseDriftError: If two live subnets share a CIDR that is desired or managed
            (or any CIDR, when ``managed_keys`` is ``None``).
    """
    desired_by_key = {c.diff_key: c for c in desired}
    locked_keys = {c.diff_key for c in desired if c.lock}

    rows: dict[str, list[LiveTailscaleSubnet]] = {}
    for live in current:
        rows.setdefault(live.diff_key, []).append(live)
    current_by_key: dict[str, LiveTailscaleSubnet] = {}
    for key, group in rows.items():
        if len(group) > 1:
            related = key in desired_by_key or managed_keys is None or key in managed_keys
            if related:
                raise OpnsenseDriftError(
                    f"tailscale subnets: more than one live subnet is {key!r}; "
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


def subnet_configs_from_resources(
    resources: list[ResourceConfig],
) -> list[TailscaleSubnetConfig]:
    """Convert ``tailscale.subnets`` resources to :class:`TailscaleSubnetConfig`.

    Raises:
        ValueError: On a non-dict config, an unknown key, a missing or invalid CIDR (host
            bits set included), or a mistyped value. Messages name the resource.
    """
    configs: list[TailscaleSubnetConfig] = []
    for resource in resources:
        if resource.type != _TYPE:
            continue
        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"tailscale subnet '{resource.name}' has non-dict config")
        configs.append(_build_config(resource.name, config))
    return configs


def _build_config(name: str, config: dict[str, Any]) -> TailscaleSubnetConfig:
    label = f"tailscale subnet '{name}'"
    unknown = sorted(set(config) - ALLOWED_KEYS)
    if unknown:
        raise ValueError(f"{label} has unknown keys: {unknown}")
    subnet = config.get("subnet")
    if not isinstance(subnet, str) or not subnet.strip():
        raise ValueError(f"{label} requires a subnet CIDR")
    try:
        normalized = str(ipaddress.ip_network(subnet.strip(), strict=True))
    except ValueError as exc:
        raise ValueError(f"{label} subnet is not a valid network CIDR") from exc
    description = config.get("description", "")
    if not isinstance(description, str):
        raise ValueError(f"{label} description must be a string")
    if not isinstance(config.get("lock", False), bool):
        raise ValueError(f"{label} lock must be a boolean")
    return TailscaleSubnetConfig(
        name=name,
        subnet=normalized,
        description=description,
        lock=bool(config.get("lock", False)),
    )


def _row_to_live(row: dict[str, Any]) -> LiveTailscaleSubnet:
    return LiveTailscaleSubnet(
        uuid=str(row.get("uuid", "")),
        subnet=flatten_option(row.get("subnet")).strip(),
        description=flatten_option(row.get("description")),
        raw=row,
    )


def _slug(text: str, fallback: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or fallback


class TailscaleSubnetService(BaseService):
    """Service for advertised subnets via ``tailscale/settings/*Subnet``."""

    def search(self) -> list[LiveTailscaleSubnet]:
        """Fetch every live subnet with one ``searchSubnet`` call."""
        ep = endpoints.TAILSCALE_SUBNET.search
        response = self.client.request(ep.method, ep.path())
        raw_rows = response.get("rows") if isinstance(response, dict) else None
        if not isinstance(raw_rows, list):
            return []
        return [_row_to_live(row) for row in raw_rows if isinstance(row, dict)]

    def add(self, config: TailscaleSubnetConfig) -> dict[str, Any]:
        """Create a subnet; raises when OPNsense rejects it."""
        ep = endpoints.TAILSCALE_SUBNET.add
        response = self.client.request(ep.method, ep.path(), data=config.to_payload())
        raise_on_failed_write(response, f"add tailscale subnet {config.subnet!r}")
        return response

    def update(self, uuid: str, config: TailscaleSubnetConfig) -> dict[str, Any]:
        """Update a subnet by UUID; raises when OPNsense rejects it."""
        ep = endpoints.TAILSCALE_SUBNET.update
        response = self.client.request(ep.method, ep.path(uuid=uuid), data=config.to_payload())
        raise_on_failed_write(response, f"update tailscale subnet {config.subnet!r}")
        return response

    def delete(self, live: LiveTailscaleSubnet) -> None:
        """Delete a subnet by UUID.

        Raises:
            APIError: On a failed write or a reply other than ``{"result": "deleted"}``.
        """
        ep = endpoints.TAILSCALE_SUBNET.delete
        response = self.client.request(ep.method, ep.path(uuid=live.uuid))
        action = f"delete tailscale subnet '{live.subnet}'"
        raise_on_failed_write(response, action)
        if not isinstance(response, dict) or response.get("result") != "deleted":
            raise APIError(
                f"OPNsense did not confirm {action}: unexpected reply",
                response=str(response),
                provider="opnsense",
            )

    def reconfigure(self) -> Any:
        """Apply the saved Tailscale configuration (used by a manager's destroy)."""
        ep = endpoints.TAILSCALE_RECONFIGURE
        response = self.client.request(ep.method, ep.path())
        return raise_on_failed_write(response, "reconfigure tailscale")

    def compute_diff(
        self,
        desired: list[TailscaleSubnetConfig],
        live: list[LiveTailscaleSubnet],
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
                "opnsense tailscale.subnets: updating %s (fields: %s)",
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
        """Export the live subnets to InfraFoundry YAML.

        The handle is a slug of the description, else of the CIDR (``-2``, ``-3`` ... on a
        collision with ``reserved`` or an earlier row).
        """
        taken: set[str] = set(reserved)
        entries: list[dict[str, Any]] = []
        for live in self.search():
            base = _slug(live.description, "") or _slug(live.diff_key, "subnet")
            handle, n = base, 1
            while handle in taken:
                n += 1
                handle = f"{base}-{n}"
            taken.add(handle)
            config: dict[str, Any] = {"subnet": live.diff_key}
            if live.description:
                config["description"] = live.description
            entries.append({"name": handle, "config": config})
        return emit_nested_list_yaml(_TYPE, entries)
