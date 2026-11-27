"""Planner, applier and destroyer for a MikroTik device.

``MikroTikManager.plan`` reads each needed REST path once, diffs the declared
objects against the live rows, orders the writes into phases and refuses a plan whose
end state would cut the management connection. ``apply`` runs a plan's steps and stops
at the first error; ``destroy`` deletes the declared objects that exist on the device.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from infrafoundry.core.managed_set import ReleasedResource
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..client import RouterOSClient, RouterOSWriter
from ..schema import (
    DEPENDENCY_ORDER,
    SPECS,
    DesiredObject,
    desired_from_resources,
    key_of,
)
from ..settings import MikroTikSettings, load_settings, management_host
from ._managed import managed_index, managed_keys
from .certificate_bootstrap import check_certificate_changes
from .diff import CREATE, DELETE, SIGN, UPDATE, Change, TypeDiff, _label, compute_type_diff
from .executor import execute_steps
from .ordering import (
    PHASE_TITLES,
    IPAddress,
    Step,
    check_management_path,
    check_service_changes,
    end_state,
    live_management_path,
    order_changes,
)

_STRUCTURAL = (
    "interface.bridge",
    "interface.bridge.port",
    "interface.bridge.vlan",
    "interface.vlan",
    "ip.address",
    "ip.dhcp-client",
)

logger = logging.getLogger(__name__)

ClientFactory = Callable[[MikroTikSettings], RouterOSWriter]
HostResolver = Callable[[str], IPAddress | None]


def resolve_host(host: str) -> IPAddress | None:
    """Return the IP for an IP literal or a hostname (resolved once), else ``None``."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    try:
        info = socket.getaddrinfo(host, None)
        return ipaddress.ip_address(info[0][4][0])
    except (OSError, ValueError, IndexError):
        return None


@dataclass
class MikroTikPlan:
    """The outcome of planning one environment against one device."""

    diffs: dict[str, TypeDiff] = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    resources: list[ResourceConfig] = field(default_factory=list)
    """The YAML resources the plan was built from (apply derives the released names)."""
    add_only: bool = False
    managed_resources: Mapping[str, list[ResourceConfig]] | None = None

    @property
    def counts(self) -> dict[str, int]:
        """Number of creates, updates and deletes across all types."""
        counts = {
            kind: sum(d.count(kind) for d in self.diffs.values())
            for kind in (CREATE, UPDATE, DELETE)
        }
        counts[UPDATE] += sum(d.count(SIGN) for d in self.diffs.values())
        return counts

    @property
    def has_changes(self) -> bool:
        """True when any type has a change."""
        return any(not d.is_empty for d in self.diffs.values())

    @property
    def unmanaged(self) -> dict[str, list[str]]:
        """Undeclared live objects that stay, per type."""
        return {t: d.unmanaged for t, d in self.diffs.items() if d.unmanaged}

    def summary_lines(self) -> list[str]:
        """One line per type with changes or kept objects, then the phase order."""
        lines: list[str] = []
        for type_name, diff in self.diffs.items():
            if diff.is_empty and not diff.unmanaged:
                continue
            text = (
                f"{type_name}: {diff.count(CREATE)} to create, {diff.count(UPDATE)} to update, "
                f"{diff.count(DELETE)} to delete"
            )
            if diff.count(SIGN):
                text += f", {diff.count(SIGN)} to sign"
            if diff.unmanaged:
                text += f", {len(diff.unmanaged)} unmanaged (kept)"
            lines.append(text)
        for phase, title in PHASE_TITLES.items():
            count = sum(1 for s in self.steps if s.phase == phase)
            if count:
                lines.append(f"phase {phase} ({title}): {count} step(s)")
        return lines


@dataclass
class MikroTikApplyResult:
    """The outcome of running a plan's steps."""

    completed: list[Step] = field(default_factory=list)
    failed: Step | None = None
    error: str | None = None
    refusals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    outcomes: list[ResourceOutcome] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    released: list[ReleasedResource] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """True when nothing was refused and every step ran."""
        return not self.refusals and self.failed is None and self.error is None


def _failure_message(
    steps: list[Step], completed: list[Step], failed: Step, error: str, connection_lost: bool
) -> str:
    """Name the failed step, RouterOS's message and the steps that already ran."""
    index = len(completed) + 1
    lines = [
        f"mikrotik apply failed at step {index} of {len(steps)} "
        f"(phase {failed.phase}: {failed.kind} {failed.type_name} '{failed.resource_name}'): "
        f"{error}"
    ]
    if connection_lost:
        lines.append(
            f"The device stopped answering after step {len(completed)}; "
            "check console access before running again."
        )
    if completed:
        lines.append(f"{len(completed)} step(s) completed before it:")
        lines.extend(f"- {s.kind} {s.type_name} '{s.resource_name}'" for s in completed)
    else:
        lines.append("No step completed before it.")
    return "\n".join(lines)


_ACTION_RANK = {CREATE: 0, DELETE: 1, UPDATE: 2, SIGN: 3}


def _outcomes(
    steps: list[Step], names: dict[str, dict[tuple[Any, ...], str]]
) -> list[ResourceOutcome]:
    """One outcome per resource: create beats delete beats update."""
    best: dict[tuple[str, tuple[Any, ...]], Step] = {}
    for step in steps:
        ident = (step.type_name, step.key)
        current = best.get(ident)
        if current is None or _ACTION_RANK[step.kind] < _ACTION_RANK[current.kind]:
            best[ident] = step
    outcomes: list[ResourceOutcome] = []
    for (type_name, key), step in best.items():
        name = step.resource_name
        if step.kind == DELETE and name == _label(key):
            name = names.get(type_name, {}).get(key, name)
        address = f"mikrotik_{SPECS[type_name].slug}.{name}"
        action = UPDATE if step.kind == SIGN else step.kind
        outcomes.append(ResourceOutcome(address=address, action=action, resource_name=name))
    return outcomes


class MikroTikManager:
    """Plans, applies and destroys changes for one RouterOS device."""

    def __init__(
        self,
        config_dir: Path,
        client_factory: ClientFactory | None = None,
        host_resolver: HostResolver | None = None,
    ) -> None:
        """Initialize the manager.

        Args:
            config_dir: Configuration directory (for the settings).
            client_factory: Builds the REST client from settings; replaced in tests.
            host_resolver: Resolves ``api_url``'s host to an IP; replaced in tests.
        """
        self.config_dir = config_dir
        self._client_factory: ClientFactory = client_factory or RouterOSClient
        self._resolver: HostResolver = host_resolver or resolve_host

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: Mapping[str, list[ResourceConfig]] | None = None,
        target_resources: list[str] | None = None,
    ) -> MikroTikPlan:
        """Diff the declared objects against the device and order the writes.

        Args:
            env_name: Environment name (for the settings).
            resources: The provider's resources.
            add_only: Suppress deletes (drift runs).
            managed_resources: Managed rows by type; only these are deleted when undeclared.
            target_resources: Restrict to these resource names; implies add-only.

        Returns:
            The plan. ``refusals`` is non-empty when the end state is unsafe.
        """
        settings = load_settings(self.config_dir, env_name)
        client = self._client_factory(settings)
        desired = desired_from_resources(resources)
        if target_resources:
            wanted = set(target_resources)
            desired = [d for d in desired if d.resource_name in wanted]
            add_only = True
        by_type: dict[str, list[DesiredObject]] = {t: [] for t in SPECS}
        for obj in desired:
            by_type[obj.type_name].append(obj)

        live: dict[str, list[dict[str, str]]] = {}

        def read(type_name: str) -> list[dict[str, str]]:
            if type_name not in live:
                live[type_name] = client.get(SPECS[type_name].path)
            return live[type_name]

        plan = MikroTikPlan(
            resources=list(resources), add_only=add_only, managed_resources=managed_resources
        )
        for type_name in DEPENDENCY_ORDER:
            spec = SPECS[type_name]
            managed = (
                managed_resources.get(type_name, []) if managed_resources is not None else None
            )
            if not by_type[type_name] and not managed:
                continue
            plan.diffs[type_name] = compute_type_diff(
                spec,
                by_type[type_name],
                read(type_name),
                add_only=add_only,
                managed_keys=managed_keys(managed, type_name),
            )
        return self._finish(plan, settings, live, read)

    def _finish(
        self,
        plan: MikroTikPlan,
        settings: MikroTikSettings,
        live: dict[str, list[dict[str, str]]],
        read: Callable[[str], list[dict[str, str]]],
    ) -> MikroTikPlan:
        """Order the diffs into steps and run the lock-out checks."""
        if not plan.has_changes:
            return plan

        structural = any(not d.is_empty for t, d in plan.diffs.items() if t in _STRUCTURAL)
        mgmt_ip: IPAddress | None = None
        if structural:
            for type_name in _STRUCTURAL:
                read(type_name)
            mgmt_ip = self._resolver(management_host(settings.api_url))
        path = live_management_path(live, mgmt_ip)
        plan.steps = order_changes(plan.diffs, live, path)

        service = check_service_changes(
            plan.diffs.get("ip.service"), settings.scheme, settings.port
        )
        plan.refusals.extend(service.refusals)
        plan.warnings.extend(service.warnings)
        if "certificate" in plan.diffs or "ip.service" in plan.diffs:
            read("certificate")
            read("ip.service")
            certs = check_certificate_changes(
                plan.diffs, live, scheme=settings.scheme, verify_ssl=settings.verify_ssl
            )
            plan.refusals.extend(certs.refusals)
            plan.warnings.extend(certs.warnings)
        for diff in plan.diffs.values():
            plan.warnings.extend(diff.warnings)
        if structural:
            if mgmt_ip is None:
                plan.refusals.append(
                    f"cannot resolve the management host '{management_host(settings.api_url)}', "
                    "so the plan cannot prove it keeps the management connection"
                )
            else:
                check = check_management_path(end_state(plan.diffs, live), mgmt_ip)
                plan.refusals.extend(check.refusals)
                plan.warnings.extend(check.warnings)
        return plan

    def plan_destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        target_resources: list[str] | None = None,
    ) -> MikroTikPlan:
        """Plan the deletion of the declared objects that exist on the device.

        Only declared objects of deletable types are removed, and only when they exist
        live and are neither built-in nor dynamic. ``absent: true`` entries, ``ip.service``
        and undeclared rows are never touched. The end state goes through the same
        management-path check as ``plan``.

        Args:
            env_name: Environment name (for the settings).
            resources: The provider's resources.
            target_resources: Restrict to these resource names.

        Returns:
            The plan. ``refusals`` is non-empty when the deletes would cut the
            management connection.
        """
        settings = load_settings(self.config_dir, env_name)
        client = self._client_factory(settings)
        desired = [d for d in desired_from_resources(resources) if not d.absent]
        if target_resources:
            wanted = set(target_resources)
            desired = [d for d in desired if d.resource_name in wanted]

        live: dict[str, list[dict[str, str]]] = {}

        def read(type_name: str) -> list[dict[str, str]]:
            if type_name not in live:
                live[type_name] = client.get(SPECS[type_name].path)
            return live[type_name]

        plan = MikroTikPlan(resources=list(resources), add_only=True)
        for type_name in DEPENDENCY_ORDER:
            spec = SPECS[type_name]
            declared = [d for d in desired if d.type_name == type_name]
            if not declared or not spec.deletable:
                continue
            rows: dict[tuple[Any, ...], dict[str, str]] = {}
            for row in read(type_name):
                key = key_of(spec, row)
                if key is not None and not _flag(row, "dynamic") and not _flag(row, "builtin"):
                    rows.setdefault(key, row)
            diff = TypeDiff(type_name)
            for obj in declared:
                found = rows.get(obj.key)
                if found is not None:
                    diff.changes.append(
                        Change(
                            DELETE, type_name, obj.key, obj.resource_name, found.get(".id"), found
                        )
                    )
            plan.diffs[type_name] = diff
        return self._finish(plan, settings, live, read)

    def apply(self, env_name: str, plan: MikroTikPlan) -> MikroTikApplyResult:
        """Run a plan's steps, stopping at the first error.

        A plan with refusals is never written: the refusals come back and nothing is sent.

        Args:
            env_name: Environment name (for the settings).
            plan: A plan built against the device in this run.

        Returns:
            What ran, what failed, the per-resource outcomes and the released managed rows.
        """
        result = MikroTikApplyResult(refusals=list(plan.refusals), warnings=list(plan.warnings))
        if plan.refusals:
            return result
        client = self._client_factory(load_settings(self.config_dir, env_name))
        executed = execute_steps(client, plan.steps)
        result.completed = executed.completed

        names = self._managed_names(plan)
        result.outcomes = _outcomes(executed.completed, names)
        result.counts = {
            kind: sum(1 for o in result.outcomes if o.action == kind)
            for kind in (CREATE, UPDATE, DELETE)
        }
        if executed.failed is not None:
            result.failed = executed.failed
            result.error = _failure_message(
                plan.steps,
                executed.completed,
                executed.failed,
                executed.error or "unknown error",
                executed.connection_lost,
            )
            logger.error(
                "mikrotik apply failed at %s '%s'",
                executed.failed.type_name,
                executed.failed.resource_name,
            )
            return result
        result.released = self._released(plan)
        return result

    @staticmethod
    def _managed_names(plan: MikroTikPlan) -> dict[str, dict[tuple[Any, ...], str]]:
        """Map each managed type's keys to the managed row names."""
        if plan.managed_resources is None:
            return {}
        return {
            type_name: managed_index(rows, type_name).names
            for type_name, rows in plan.managed_resources.items()
            if type_name in SPECS
        }

    @staticmethod
    def _released(plan: MikroTikPlan) -> list[ReleasedResource]:
        """List managed rows that left the YAML (ADR-0018), after a full-mode apply."""
        if plan.add_only or plan.managed_resources is None:
            return []
        released: list[ReleasedResource] = []
        for type_name, rows in plan.managed_resources.items():
            if type_name not in SPECS or not SPECS[type_name].deletable:
                continue
            yaml_names = {r.name for r in plan.resources if r.type == type_name}
            unparsed = managed_index(rows, type_name).unparsed
            seen: set[str] = set()
            for row in rows:
                if row.name in yaml_names or row.name in unparsed or row.name in seen:
                    continue
                seen.add(row.name)
                released.append({"resource_type": type_name, "name": row.name})
        return released

    def destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        target_resources: list[str] | None = None,
    ) -> MikroTikApplyResult:
        """Delete the declared objects that exist on the device.

        Args:
            env_name: Environment name (for the settings).
            resources: The provider's resources.
            target_resources: Restrict to these resource names.
        """
        return self.apply(
            env_name, self.plan_destroy(env_name, resources, target_resources=target_resources)
        )

    def resource_ids(self, env_name: str, resources: list[ResourceConfig]) -> dict[str, str]:
        """Return ``{resource_name: .id}`` for the declared objects that exist live.

        Args:
            env_name: Environment name (for the settings).
            resources: The provider's resources.
        """
        client = self._client_factory(load_settings(self.config_dir, env_name))
        desired = [d for d in desired_from_resources(resources) if not d.absent]
        rows_by_type: dict[str, dict[tuple[Any, ...], str]] = {}
        ids: dict[str, str] = {}
        for obj in desired:
            if obj.type_name not in rows_by_type:
                spec = SPECS[obj.type_name]
                rows_by_type[obj.type_name] = {
                    key: row[".id"]
                    for row in client.get(spec.path)
                    if (key := key_of(spec, row)) is not None and row.get(".id")
                }
            row_id = rows_by_type[obj.type_name].get(obj.key)
            if row_id:
                ids[obj.resource_name] = row_id
        return ids


def _flag(row: dict[str, str], name: str) -> bool:
    return str(row.get(name, "")).strip().lower() in ("true", "yes")
