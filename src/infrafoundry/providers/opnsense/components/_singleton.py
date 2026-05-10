"""Shared helper for OPNsense singleton component managers (#806).

Singleton components (``system.hostname``, ``system.dns``, ``system.ssh``,
``system.webgui``, ``system.firmware``, ``system.remotebackup``,
``system.tuning``, and future per-box settings under the ``opnsense.system.*``
namespace) all share the same diff shape: compare a flat-string field map
extracted from the live OPNsense response against a flat-string field map
built from the desired YAML. If they match, no apply is needed; if they
differ, apply with the desired payload.

This module owns:

1. The minimal field-comparison helper :func:`diff_singleton` so all
   singleton managers reach into the same primitive rather than each
   rolling its own slightly different equality check.
2. A tiny :class:`SingletonDiff` adapter that exposes
   ``adds``/``updates``/``deletes``/``locked``/``is_empty`` on the same
   shape ``OPNsenseDirectRunner._format_plan_summary`` consumes for
   list-shape components — so the runner doesn't need a singleton-specific
   code path.

The real change-detection work (normalization, asymmetric-field handling,
option-dict unwrapping) lives in the per-surface service classes that build
the field maps.

Reused by future singleton components (#786 firewall_log,
#787 tailscale.settings, #788 radvd, #790 acmeclient.settings,
#791 monit.settings, #792 hostwatch).
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig


def enforce_singleton(
    resources: list[ResourceConfig],
    type_name: str,
) -> None:
    """Defensive recheck that exactly one singleton was passed.

    The nested-namespace loader already enforces this via the
    ``DOTTED_RESOURCE_SHAPES`` table (a dict-shape path emits exactly one
    ``ResourceConfig`` with ``name="settings"``), but a malformed
    resource-centric YAML could in principle slip past, so every
    singleton manager rechecks here at the manager boundary.

    Args:
        resources: Resource list passed to ``plan`` / ``apply``.
        type_name: The dotted type name for the singleton (e.g.,
            ``"system.hostname"``); used in the error message.

    Raises:
        InvalidConfigurationError: If ``len(resources) != 1``.
    """
    if len(resources) != 1:
        raise InvalidConfigurationError(
            f"{type_name} expects exactly one singleton resource, got {len(resources)}"
        )


def diff_singleton(
    live: dict[str, Any],
    desired: dict[str, Any],
) -> dict[str, Any] | None:
    """Compute a singleton-shape diff between live and desired field maps.

    The contract:

    - Both ``live`` and ``desired`` are flat ``{field_name: value}`` mappings
      built by the caller's per-surface ``extract_*_fields`` /
      ``build_desired_*_fields`` helpers. Equality compares every key in
      either map.
    - Returns ``None`` when the maps are equal — the singleton is in sync,
      the manager's ``apply()`` should skip the write call.
    - Returns the ``desired`` map (caller-owned) on any difference. The
      caller is responsible for translating that map into the wire envelope
      its API client accepts.

    The function is deliberately ``mutating`` neither argument and does
    NOT clone ``desired`` — the caller may safely consume the returned
    reference.

    Args:
        live: Field map extracted from the live OPNsense GET response.
        desired: Field map built from the desired YAML.

    Returns:
        ``None`` if equal (no change), else ``desired``.
    """
    if live == desired:
        return None
    return desired


class SingletonDiff:
    """Plan-shape adapter for singleton diffs.

    Mirrors the ``adds``/``updates``/``deletes``/``locked``/``is_empty``
    surface that ``OPNsenseDirectRunner._format_plan_summary`` reads off
    list-shape components' ``_Diff`` classes. For singletons:

    - ``adds`` and ``deletes`` are always empty lists.
    - ``updates`` carries zero (no change) or one entry — the desired
      field map.
    - ``locked`` is always empty — singletons have no per-row lock.
    - ``is_empty`` is True iff there's no update entry.

    Args:
        update: The desired field map when the singleton is drifted, else
            ``None`` for an in-sync singleton.
    """

    def __init__(self, update: dict[str, Any] | None) -> None:
        """Initialize the singleton diff."""
        self.adds: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = [update] if update is not None else []
        self.deletes: list[Any] = []
        self.locked: list[Any] = []

    @property
    def is_empty(self) -> bool:
        """Return True when there are no updates to apply."""
        return not self.updates
