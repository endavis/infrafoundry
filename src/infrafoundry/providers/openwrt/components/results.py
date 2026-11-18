"""Parse the ``ansible.posix.json`` output of a run into resource outcomes.

The runner executes ``ansible-playbook`` with the JSON stdout callback. Each staging
task is named ``infrafoundry|<type>|<name>`` (``infrafoundry|absent|<type>|<name>``
for a delete), so its result maps back to the resource that produced it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.managed_set import ReleasedResource
from infrafoundry.core.types import ResourceOutcome

from ..schema import Desired
from .management import management_refusals
from .playbook import ROLLBACK_MARKER, TASK_PREFIX, task_name

_NO_DIFF: dict[str, Any] = {}


class ResultsError(ValueError):
    """The run's output could not be read."""


@dataclass(frozen=True)
class TaskResult:
    """One task's result for the device."""

    name: str
    changed: bool = False
    failed: bool = False
    unreachable: bool = False
    skipped: bool = False
    msg: str = ""
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


@dataclass
class RunSpec:
    """What a rendered run was asked to do, kept to interpret its output."""

    mode: str
    """``apply`` or ``destroy``."""
    items: list[Desired]
    """Every object in the playbook, staged or absent."""
    managed_names: set[tuple[str, str]] = field(default_factory=set)
    removal_names: set[str] = field(default_factory=set)
    """Names of the items that delete a managed row no longer declared."""
    forgotten: list[ReleasedResource] = field(default_factory=list)
    """Rows released without a device change (forgotten types, or skipped by a destroy)."""
    forgotten_items: list[Desired] = field(default_factory=list)
    """Declared objects a destroy forgets without a device change."""
    tags: list[str] = field(default_factory=list)


@dataclass
class OpenWrtRunResult:
    """The interpreted result of one ``ansible-playbook`` run."""

    success: bool = True
    error: str | None = None
    rollback_pending: bool = False
    refusals: list[str] = field(default_factory=list)
    reconnect_host: str | None = None
    outcomes: list[ResourceOutcome] = field(default_factory=list)
    released: list[ReleasedResource] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=lambda: {"create": 0, "update": 0, "delete": 0})
    changed: list[str] = field(default_factory=list)
    """Task names that changed (or would change) the device."""
    diffs: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        """True when any object changes."""
        return any(self.counts.values())

    def summary_lines(self) -> list[str]:
        """Human-readable summary lines."""
        lines = [f"{kind}: {count}" for kind, count in self.counts.items() if count]
        lines.extend(f"change: {name.split('|', 1)[1]}" for name in self.changed)
        return lines


def _diff_sides(diff: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return the first diff entry's before/after section values; ``None`` when unreadable."""
    entries = diff if isinstance(diff, list) else [diff]
    for entry in entries:
        if not isinstance(entry, dict):
            continue

        def side(key: str, entry: dict[str, Any] = entry) -> dict[str, Any] | None:
            value = entry.get(key)
            if isinstance(value, dict):
                return value
            return {} if value in (None, "") else None

        return side("before"), side("after")
    return None, None


def parse_output(raw: str) -> list[TaskResult]:
    """Read the JSON document of ``ansible.posix.json``.

    Args:
        raw: The captured stdout.

    Returns:
        One result per task that ran on a host, in run order.

    Raises:
        ResultsError: If the output is not the expected JSON document.
    """
    try:
        document = json.loads(raw)
    except ValueError as exc:
        raise ResultsError("ansible-playbook did not print the JSON result document") from exc
    if not isinstance(document, dict) or not isinstance(document.get("plays"), list):
        raise ResultsError("the JSON result document has no plays")
    results: list[TaskResult] = []
    for play in document["plays"]:
        for task in play.get("tasks", []):
            name = str(task.get("task", {}).get("name", ""))
            for host in (task.get("hosts") or {}).values():
                before, after = _diff_sides(host.get("diff")) if host.get("diff") else (None, None)
                results.append(
                    TaskResult(
                        name=name,
                        changed=bool(host.get("changed", False)),
                        failed=bool(host.get("failed", False)),
                        unreachable=bool(host.get("unreachable", False)),
                        skipped=bool(host.get("skipped", False)),
                        msg=str(host.get("msg", "") or ""),
                        before=before,
                        after=after,
                    )
                )
    return results


def _first_failure(tasks: list[TaskResult]) -> TaskResult | None:
    """Return the root failure: the first failed task that is not a rescue task."""
    failed = [t for t in tasks if (t.failed or t.unreachable) and not t.skipped]
    for task in failed:
        if "|rescue|" not in task.name:
            return task
    return failed[0] if failed else None


def interpret(
    tasks: list[TaskResult],
    spec: RunSpec,
    *,
    address: str,
    check: bool,
    resolve: Any = None,
) -> OpenWrtRunResult:
    """Turn task results into counts, outcomes, refusals and an error.

    Args:
        tasks: Result of :func:`parse_output`.
        spec: What the run was asked to do.
        address: The settings address, for the management check.
        check: True for a check-mode pass (nothing was written).
        resolve: Resolver for the settings address, replaced in tests.

    Returns:
        The interpreted result.
    """
    result = OpenWrtRunResult()
    by_name = {t.name: t for t in tasks if t.name.startswith(f"{TASK_PREFIX}|")}

    if any(ROLLBACK_MARKER in t.msg for t in tasks):
        result.success = False
        result.rollback_pending = True
        result.error = (
            "the device did not confirm the change and reverts it by itself "
            f"({ROLLBACK_MARKER}); check the device and run again"
        )
        return result
    failure = _first_failure(tasks)
    if failure is not None:
        result.success = False
        detail = failure.msg or "no message"
        kind = "the device is unreachable" if failure.unreachable else "a task failed"
        result.error = f"openwrt run failed: {kind} ({failure.name}): {detail}"
        return result

    managed_changed: list[tuple[Desired, dict[str, Any] | None, dict[str, Any] | None]] = []
    for item in spec.items:
        task = by_name.get(task_name(item))
        if task is None or task.skipped:
            continue
        if task.changed:
            result.changed.append(task.name)
            if task.before is not None or task.after is not None:
                result.diffs[task.name] = {"before": task.before, "after": task.after}
        if item.absent:
            if task.changed:
                result.counts["delete"] += 1
            declared = item.name not in spec.removal_names
            if spec.mode == "destroy" or (task.changed and declared):
                result.outcomes.append(ResourceOutcome(item.address, "delete", item.name))
            if spec.mode != "destroy" and (item.type_name, item.name) in spec.managed_names:
                result.released.append(
                    ReleasedResource(resource_type=item.type_name, name=item.name)
                )
            continue
        managed = (item.type_name, item.name) in spec.managed_names
        if task.changed:
            result.counts["update" if managed else "create"] += 1
            result.outcomes.append(
                ResourceOutcome(item.address, "update" if managed else "create", item.name)
            )
            if item.type_name == "network.interface":
                managed_changed.append((item, task.before, task.after))
        elif not managed:
            result.outcomes.append(ResourceOutcome(item.address, "create", item.name))
    for item in spec.forgotten_items:
        result.outcomes.append(ResourceOutcome(item.address, "delete", item.name))
    result.released.extend(spec.forgotten)
    if managed_changed and check:
        kwargs: dict[str, Any] = {} if resolve is None else {"resolve": resolve}
        result.refusals, result.reconnect_host = management_refusals(
            address, managed_changed, **kwargs
        )
    return result
