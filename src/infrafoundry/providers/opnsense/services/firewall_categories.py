"""Firewall category service for OPNsense direct-API operations (ADR-0014, #1286).

Manages ``firewall.categories`` over ``firewall/category/{search,get,add,set,del}Item``.
Categories are model data: the controller has no reconfigure action, so there is no
finalization hook.

Identity is the live ``name`` against the YAML ``config.name`` (falling back to the
resource name); see :func:`category_name_of`. A rename is a delete plus an add. The
box assigns ``uuid``; it is not a YAML field.

Fields
------

- ``auto`` is an optional bool (default ``False``), sent as ``"0"``/``"1"`` and always
  compared.
- ``color`` is an optional string (default ``""``), always sent and compared after
  :func:`normalize_color` (lowercase, no leading ``#``), so ``#336699`` and ``336699``
  never drift against each other.

The ``infrafoundry`` marker
---------------------------

The provider's own marker category (``_category_marker.py``) is never part of the
diff: :func:`compute_diff` drops every live row with that name before classifying, so
it is never deleted, updated or counted as unmanaged. The parser rejects a resource
whose effective name is the marker's.

Deletes
-------

Rules, NAT rules, aliases and models this provider does not manage can reference a
category by uuid, and the controller deletes safely: it refuses a category in use.
:meth:`FirewallCategoryService.apply_diff` keeps a refused row in ``Diff.blocked``
with a warning instead of failing the run.

What is verified and what is not
--------------------------------

- Verified on a test firewall (#1286): the envelope is ``category`` with ``name``,
  ``auto`` (a ``"0"``/``"1"`` string) and ``color`` (a string, stored without ``#``);
  ``searchItem`` rows carry every field.
- Verified: an in-use delete is refused with HTTP 500 whose body carries
  ``errorTitle`` ``... in use by:``. :meth:`FirewallCategoryService.delete` matches
  "in use" in that body; any other error or reply raises (ADR-0014).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from ._category_marker import INFRAFOUNDRY_CATEGORY_NAME
from ._identity import OpnsenseDriftError
from ._nested_emit import emit_nested_list_yaml
from .base import BaseService, raise_on_failed_write
from .openvpn_instances import flatten_option

logger = logging.getLogger(__name__)

_TYPE = "firewall.categories"

#: Every config key a ``firewall.categories`` resource accepts (single source for the
#: parser and the validator).
ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        # The nested loader copies the entry name into config (package_loader).
        "name",
        "auto",
        "color",
        "lock",
    }
)
#: Keys the box assigns itself.
BOX_ASSIGNED_KEYS: frozenset[str] = frozenset({"uuid"})

__all__ = [
    "ALLOWED_KEYS",
    "BOX_ASSIGNED_KEYS",
    "Diff",
    "FirewallCategoryConfig",
    "FirewallCategoryService",
    "LiveFirewallCategory",
    "category_configs_from_resources",
    "category_name_of",
    "changed_fields",
    "compute_diff",
    "normalize_color",
]


def category_name_of(name: str, config: dict[str, Any] | Any) -> str:
    """Return the wire name (the identity) of a ``firewall.categories`` resource.

    Args:
        name: Resource name, the fallback.
        config: Resource config.

    Returns:
        ``config.name`` when a non-empty string, else ``name``.
    """
    value = config.get("name") if hasattr(config, "get") else None
    if isinstance(value, str) and value:
        return value
    return name


def normalize_color(value: str) -> str:
    """Normalize a color for comparison and for the wire: lowercase, no leading ``#``."""
    text = value.strip().lower()
    return text[1:] if text.startswith("#") else text


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FirewallCategoryConfig:
    """Desired-state firewall category.

    Attributes:
        name: Operator-facing YAML resource name.
        category_name: Wire ``name`` and the identity (defaults to ``name``).
        auto: Whether the box assigns the category automatically.
        color: Color, with or without a leading ``#``; empty for none.
        lock: Per-resource safety annotation (ADR-0014 section 6).
    """

    name: str
    category_name: str
    auto: bool = False
    color: str = ""
    lock: bool = False

    @property
    def diff_key(self) -> str:
        """Identity of this category: its wire name."""
        return self.category_name

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the ``add``/``set`` envelope.

        Returns:
            ``{"category": {"name", "auto", "color"}}``.
        """
        return {
            "category": {
                "name": self.category_name,
                "auto": "1" if self.auto else "0",
                "color": normalize_color(self.color),
            }
        }


@dataclass(frozen=True)
class LiveFirewallCategory:
    """A category as currently on the box (a ``searchItem`` row).

    Attributes:
        uuid: Row UUID.
        name: Live name.
        auto: Live ``auto`` flag.
        color: Live color string.
        raw: The row as returned.
    """

    uuid: str
    name: str
    auto: bool = False
    color: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def diff_key(self) -> str:
        """Identity of this category: its name."""
        return self.name


@dataclass
class Diff:
    """Result of comparing desired categories to live ones.

    ``blocked`` holds managed live categories whose delete the box refused because
    they are in use, each with the reason (filled by ``apply_diff``).
    """

    adds: list[FirewallCategoryConfig] = field(default_factory=list)
    updates: list[tuple[LiveFirewallCategory, FirewallCategoryConfig]] = field(default_factory=list)
    deletes: list[LiveFirewallCategory] = field(default_factory=list)
    unmanaged: list[LiveFirewallCategory] = field(default_factory=list)
    locked: list[tuple[FirewallCategoryConfig, LiveFirewallCategory | None]] = field(
        default_factory=list
    )
    blocked: list[tuple[LiveFirewallCategory, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there is nothing to add, update or delete."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def changed_fields(have: LiveFirewallCategory, want: FirewallCategoryConfig) -> list[str]:
    """Return the field names whose live value differs from the desired one.

    ``name`` is the identity and never a change.

    Args:
        have: Live category.
        want: Desired category.

    Returns:
        Field names, in ``auto``, ``color`` order.
    """
    changed: list[str] = []
    if have.auto != want.auto:
        changed.append("auto")
    if normalize_color(have.color) != normalize_color(want.color):
        changed.append("color")
    return changed


def compute_diff(
    desired: list[FirewallCategoryConfig],
    current: list[LiveFirewallCategory],
    *,
    add_only: bool = False,
    managed_keys: set[str] | None = None,
) -> Diff:
    """Compare desired categories to live ones, keyed by name.

    The ``infrafoundry`` marker is dropped from ``current`` first, so it lands in no
    bucket.

    Args:
        desired: Categories the operator wants.
        current: Categories currently on the box.
        add_only: Suppress deletes.
        managed_keys: When given, only live categories in this set may be deleted
            (ADR-0018); others land in ``Diff.unmanaged``.

    Returns:
        The diff.

    Raises:
        OpnsenseDriftError: If two live categories share a name that is desired or
            managed (or any name, when ``managed_keys`` is ``None``).
    """
    desired_by_key = {c.diff_key: c for c in desired}
    locked_keys = {c.diff_key for c in desired if c.lock}

    rows: dict[str, list[LiveFirewallCategory]] = {}
    for live in current:
        if live.diff_key == INFRAFOUNDRY_CATEGORY_NAME:
            continue
        rows.setdefault(live.diff_key, []).append(live)
    current_by_key: dict[str, LiveFirewallCategory] = {}
    for key, group in rows.items():
        if len(group) > 1:
            related = key in desired_by_key or managed_keys is None or key in managed_keys
            if related:
                raise OpnsenseDriftError(
                    f"firewall categories: more than one live category is named {key!r}; "
                    f"rename or remove the extra on the box before planning"
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


# ---------------------------------------------------------------------------
# Resource-to-domain conversion
# ---------------------------------------------------------------------------


def category_configs_from_resources(
    resources: list[ResourceConfig],
) -> list[FirewallCategoryConfig]:
    """Convert ``firewall.categories`` resources to :class:`FirewallCategoryConfig`.

    Args:
        resources: Provider resources; other types are skipped.

    Returns:
        Parsed categories.

    Raises:
        ValueError: On a non-dict config, an unknown key, a mistyped value, or an
            effective name equal to the provider's ``infrafoundry`` marker. Messages
            name the resource.
    """
    configs: list[FirewallCategoryConfig] = []
    for resource in resources:
        if resource.type != _TYPE:
            continue
        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"firewall category '{resource.name}' has non-dict config")
        configs.append(_build_config(resource.name, config))
    return configs


def _build_config(name: str, config: dict[str, Any]) -> FirewallCategoryConfig:
    label = f"firewall category '{name}'"
    unknown = sorted(set(config) - ALLOWED_KEYS)
    if unknown:
        raise ValueError(f"{label} has unknown keys: {unknown}")
    wire_name = config.get("name")
    if wire_name is not None and (not isinstance(wire_name, str) or not wire_name.strip()):
        raise ValueError(f"{label} name must be a non-empty string")
    for flag in ("auto", "lock"):
        if not isinstance(config.get(flag, False), bool):
            raise ValueError(f"{label} {flag} must be a boolean")
    color = config.get("color", "")
    if not isinstance(color, str):
        raise ValueError(f"{label} color must be a string")
    category_name = category_name_of(name, config)
    if category_name == INFRAFOUNDRY_CATEGORY_NAME:
        raise ValueError(
            f"{label} uses the reserved name {INFRAFOUNDRY_CATEGORY_NAME!r} "
            f"(the provider's own marker category)"
        )
    return FirewallCategoryConfig(
        name=name,
        category_name=category_name,
        auto=bool(config.get("auto", False)),
        color=color,
        lock=bool(config.get("lock", False)),
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def _row_to_live(row: dict[str, Any]) -> LiveFirewallCategory:
    """Normalize a ``searchItem`` row into a :class:`LiveFirewallCategory`."""
    return LiveFirewallCategory(
        uuid=str(row.get("uuid", "")),
        name=flatten_option(row.get("name")),
        auto=flatten_option(row.get("auto")).strip().lower() in ("1", "true"),
        color=flatten_option(row.get("color")),
        raw=row,
    )


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "category"


class FirewallCategoryService(BaseService):
    """Service for firewall categories via ``firewall/category/*Item``."""

    def search(self) -> list[LiveFirewallCategory]:
        """Fetch every live category with one ``searchItem`` call.

        The grid rows carry every field, so no per-row ``getItem`` follows.
        """
        ep = endpoints.CATEGORY.search
        response = self.client.request(ep.method, ep.path())
        raw_rows = response.get("rows") if isinstance(response, dict) else None
        if not isinstance(raw_rows, list):
            return []
        return [_row_to_live(row) for row in raw_rows if isinstance(row, dict)]

    def add(self, config: FirewallCategoryConfig) -> dict[str, Any]:
        """Create a category; raises when OPNsense rejects it."""
        ep = endpoints.CATEGORY.add
        response = self.client.request(ep.method, ep.path(), data=config.to_payload())
        raise_on_failed_write(response, f"add firewall category {config.name!r}")
        return response

    def update(self, uuid: str, config: FirewallCategoryConfig) -> dict[str, Any]:
        """Update a category by UUID; raises when OPNsense rejects it."""
        ep = endpoints.CATEGORY.update
        response = self.client.request(ep.method, ep.path(uuid=uuid), data=config.to_payload())
        raise_on_failed_write(response, f"update firewall category {config.name!r}")
        return response

    def delete(self, live: LiveFirewallCategory) -> bool:
        """Delete a category by UUID.

        The controller deletes safely and refuses a category still in use. Verified
        on a test firewall: the refusal is HTTP 500 whose JSON body carries
        ``errorTitle`` ``Item categories.category {<name>} in use by:`` and an
        ``errorMessage`` naming the referencing items.

        Args:
            live: The category to delete.

        Returns:
            True when the box deleted it, False when it refused because the
            category is in use.

        Raises:
            APIError: On any other failure, including a reply other than
                ``{"result": "deleted"}``.
        """
        ep = endpoints.CATEGORY.delete
        try:
            response = self.client.request(ep.method, ep.path(uuid=live.uuid))
        except APIError as exc:
            if "in use" in str(exc.response or "").lower():
                return False
            raise
        action = f"delete firewall category '{live.name}'"
        raise_on_failed_write(response, action)
        if response.get("result") != "deleted":
            raise APIError(
                f"OPNsense did not confirm {action}: unexpected reply",
                response=str(response),
                provider="opnsense",
            )
        return True

    def compute_diff(
        self,
        desired: list[FirewallCategoryConfig],
        live: list[LiveFirewallCategory],
        *,
        add_only: bool = False,
        managed_keys: set[str] | None = None,
    ) -> Diff:
        """Service-method form of :func:`compute_diff`."""
        return compute_diff(desired, live, add_only=add_only, managed_keys=managed_keys)

    def apply_diff(self, diff: Diff) -> dict[str, int]:
        """Dispatch the diff. There is no reconfigure for categories.

        A delete the box refuses moves from ``diff.deletes`` to ``diff.blocked`` with
        a warning and is not counted as deleted.

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
            logger.info(
                "opnsense firewall.categories: updating %s (fields: %s)",
                want.name,
                changed_fields(live, want),
            )
            self.update(live.uuid, want)
            updated += 1
        deleted_rows: list[LiveFirewallCategory] = []
        for live in diff.deletes:
            if self.delete(live):
                deleted += 1
                deleted_rows.append(live)
                continue
            reason = "the box reports it in use"
            diff.blocked.append((live, reason))
            diff.warnings.append(f"firewall category {live.name!r} kept: {reason}")
        diff.deletes = deleted_rows
        return {"created": created, "updated": updated, "deleted": deleted}

    # ------------------------------------------------------------------
    # Migration / export
    # ------------------------------------------------------------------

    def export_to_yaml(self, reserved: Collection[str] = ()) -> str:
        """Export the live categories to InfraFoundry YAML.

        The provider's ``infrafoundry`` marker is skipped. The handle is a slug of
        the name (``-2``, ``-3`` ... on a collision with ``reserved`` or an earlier
        row); ``config.name`` always carries the exact live name.

        Args:
            reserved: Resource names already in use in the environment.

        Returns:
            YAML with the nested ``opnsense:`` namespace and a
            ``firewall.categories`` list leaf.
        """
        taken: set[str] = set(reserved)
        entries: list[dict[str, Any]] = []
        for live in self.search():
            if live.name == INFRAFOUNDRY_CATEGORY_NAME:
                continue
            base = _slug(live.name)
            handle, n = base, 1
            while handle in taken:
                n += 1
                handle = f"{base}-{n}"
            taken.add(handle)
            config: dict[str, Any] = {"name": live.name}
            if live.auto:
                config["auto"] = True
            if live.color:
                config["color"] = live.color
            entries.append({"name": handle, "config": config})
        return emit_nested_list_yaml(_TYPE, entries)
