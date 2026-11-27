"""Planner, applier and destroyer for the data LIFs of one ONTAP cluster.

``OntapManager.plan`` reads the interfaces of the SVMs the YAML (and the managed set)
mention once, diffs the declared LIFs against them and turns the changes into ordered
write steps. ``apply`` runs the steps and stops at the first error; ``destroy`` deletes
the declared LIFs that exist. Create is read-first: the plan, built from the live read of
the same run, decides, because a POST is not idempotent.
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
from infrafoundry.providers._netapp.ontap import OntapError, OntapService, connect_ontap

from ..schema import SLUG, TYPE_NAME, DesiredInterface, desired_from_resources, to_api_kwargs
from ..settings import OntapSettings, load_settings
from ._managed import managed_index
from .interface import (
    CREATE,
    DELETE,
    UPDATE,
    Change,
    InterfaceDiff,
    compute_interface_diff,
    label,
    lockout_refusals,
)

logger = logging.getLogger(__name__)

ServiceFactory = Callable[[OntapSettings], OntapService]
HostResolver = Callable[[str], str | None]

_ACTION_RANK = {CREATE: 0, DELETE: 1, UPDATE: 2}
_KIND_ORDER = {DELETE: 0, UPDATE: 1, CREATE: 2}
"""Deletes first (they free addresses), then updates, then creates."""


def default_service_factory(settings: OntapSettings) -> OntapService:
    """Connect to the cluster the settings name."""
    return connect_ontap(settings.connection_params())


def resolve_host(host: str) -> str | None:
    """Return the canonical IP of an IP literal or a host name, else ``None``."""
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    try:
        return str(ipaddress.ip_address(socket.getaddrinfo(host, None)[0][4][0]))
    except (OSError, ValueError, IndexError):
        return None


@dataclass(frozen=True)
class Step:
    """One write to the cluster."""

    kind: str
    resource_name: str
    key: tuple[str, str]
    part: str
    """What changes: ``interface`` (create, delete), ``settings``, ``address`` or ``home``."""
    uuid: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    """Flat dotted REST field names for the write."""


@dataclass
class OntapPlan:
    """The outcome of planning one environment against one cluster."""

    diff: InterfaceDiff = field(default_factory=InterfaceDiff)
    steps: list[Step] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    resources: list[ResourceConfig] = field(default_factory=list)
    """The YAML resources the plan was built from (apply derives the released names)."""
    add_only: bool = False
    managed_resources: Mapping[str, list[ResourceConfig]] | None = None
    names: dict[tuple[str, str], str] = field(default_factory=dict)
    """Managed row names by identity key, for the outcomes of deletes."""

    @property
    def counts(self) -> dict[str, int]:
        """Number of creates, updates and deletes."""
        return {kind: self.diff.count(kind) for kind in (CREATE, UPDATE, DELETE)}

    @property
    def has_changes(self) -> bool:
        """True when there is a change."""
        return not self.diff.is_empty

    @property
    def unmanaged(self) -> dict[str, list[str]]:
        """Undeclared live LIFs that stay."""
        return {TYPE_NAME: self.diff.unmanaged} if self.diff.unmanaged else {}

    def summary_lines(self) -> list[str]:
        """One line with the counts and the kept LIFs; empty when there is nothing to say."""
        if self.diff.is_empty and not self.diff.unmanaged:
            return []
        text = (
            f"{TYPE_NAME}: {self.diff.count(CREATE)} to create, {self.diff.count(UPDATE)} to "
            f"update, {self.diff.count(DELETE)} to delete"
        )
        if self.diff.unmanaged:
            text += f", {len(self.diff.unmanaged)} unmanaged (kept)"
        return [text]


@dataclass
class OntapApplyResult:
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


def build_steps(changes: list[Change]) -> list[Step]:
    """Turn changes into write steps: deletes, then updates, then creates.

    An update becomes up to three PATCHes: ``settings`` (``auto_revert`` and the service
    policy), ``address`` (address with its netmask) and ``home`` (home node and port, the
    port sent with its node).
    """
    steps: list[Step] = []
    for change in sorted(changes, key=lambda c: _KIND_ORDER[c.kind]):
        if change.kind == DELETE:
            steps.append(Step(DELETE, change.resource_name, change.key, "interface", change.uuid))
        elif change.kind == CREATE:
            fields = to_api_kwargs({"svm": change.key[0], "name": change.key[1], **change.after})
            steps.append(Step(CREATE, change.resource_name, change.key, "interface", None, fields))
        else:
            steps.extend(_update_steps(change))
    return steps


def _update_steps(change: Change) -> list[Step]:
    after, before, changed = change.after, change.before, set(change.changed)
    groups: list[tuple[str, dict[str, Any]]] = []
    settings: dict[str, Any] = {
        n: after[n] for n in ("auto_revert", "service_policy") if n in changed
    }
    if settings:
        groups.append(("settings", to_api_kwargs(settings)))
    if changed & {"address", "netmask"}:
        address = {
            "address": after.get("address", before["address"]),
            "netmask": after.get("netmask", before["netmask"]),
        }
        groups.append(("address", to_api_kwargs(address)))
    if changed & {"home_node", "home_port"}:
        home = {
            "home_node": after.get("home_node", before["home_node"]),
            "home_port": after.get("home_port", before["home_port"]),
        }
        groups.append(("home", to_api_kwargs(home)))
    return [
        Step(UPDATE, change.resource_name, change.key, part, change.uuid, fields)
        for part, fields in groups
    ]


def _failure_message(steps: list[Step], completed: list[Step], failed: Step, error: str) -> str:
    """Name the failed step, ONTAP's message and the steps that already ran."""
    lines = [
        f"ontap apply failed at step {len(completed) + 1} of {len(steps)} "
        f"({failed.kind} {TYPE_NAME} '{label(failed.key)}', {failed.part}): {error}"
    ]
    if completed:
        lines.append(f"{len(completed)} step(s) completed before it:")
        lines.extend(f"- {s.kind} {TYPE_NAME} '{label(s.key)}' ({s.part})" for s in completed)
    else:
        lines.append("No step completed before it.")
    return "\n".join(lines)


def _outcomes(steps: list[Step], names: dict[tuple[str, str], str]) -> list[ResourceOutcome]:
    """One outcome per LIF: create beats delete beats update."""
    best: dict[tuple[str, str], Step] = {}
    for step in steps:
        current = best.get(step.key)
        if current is None or _ACTION_RANK[step.kind] < _ACTION_RANK[current.kind]:
            best[step.key] = step
    outcomes: list[ResourceOutcome] = []
    for key, step in best.items():
        name = step.resource_name
        if step.kind == DELETE and name == label(key):
            name = names.get(key, name)
        outcomes.append(
            ResourceOutcome(address=f"ontap_{SLUG}.{name}", action=step.kind, resource_name=name)
        )
    return outcomes


class OntapManager:
    """Plans, applies and destroys data LIF changes for one ONTAP cluster."""

    def __init__(
        self,
        config_dir: Path,
        service_factory: ServiceFactory | None = None,
        host_resolver: HostResolver | None = None,
    ) -> None:
        """Initialize the manager.

        Args:
            config_dir: Configuration directory (for the settings).
            service_factory: Builds the service from settings; replaced in tests.
            host_resolver: Resolves the ``host`` setting to an IP; replaced in tests.
        """
        self.config_dir = config_dir
        self._factory: ServiceFactory = service_factory or default_service_factory
        self._resolver: HostResolver = host_resolver or resolve_host
        self._settings: dict[str, OntapSettings] = {}
        self._services: dict[str, OntapService] = {}

    def _service(self, env_name: str) -> tuple[OntapSettings, OntapService]:
        """Return the settings and the one service of this manager for the environment."""
        if env_name not in self._services:
            settings = load_settings(self.config_dir, env_name)
            self._settings[env_name] = settings
            self._services[env_name] = self._factory(settings)
        return self._settings[env_name], self._services[env_name]

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: Mapping[str, list[ResourceConfig]] | None = None,
        target_resources: list[str] | None = None,
    ) -> OntapPlan:
        """Diff the declared LIFs against the cluster and order the writes.

        Args:
            env_name: Environment name (for the settings).
            resources: The provider's resources.
            add_only: Suppress deletes (drift runs).
            managed_resources: Managed rows by type; only these are deleted when undeclared.
            target_resources: Restrict to these resource names; implies add-only.

        Returns:
            The plan. ``refusals`` is non-empty when a change could cut the connection.
        """
        desired = desired_from_resources(resources)
        if target_resources:
            wanted = set(target_resources)
            desired = [d for d in desired if d.resource_name in wanted]
            add_only = True
        managed = managed_resources.get(TYPE_NAME, []) if managed_resources is not None else None
        index = managed_index(managed)
        plan = OntapPlan(
            resources=list(resources),
            add_only=add_only,
            managed_resources=managed_resources,
            names=index.names,
        )
        report_svms = {d.svm for d in desired}
        svms = sorted(report_svms | ({k[0] for k in index.names} if managed else set()))
        if not svms:
            return plan
        settings, service = self._service(env_name)
        plan.diff = compute_interface_diff(
            desired,
            service.list_interfaces(svms),
            add_only=add_only,
            managed_keys=set(index.names) if managed_resources is not None else None,
            report_svms=report_svms,
            host=settings.host,
            resolve_management=lambda: self._resolver(settings.host),
        )
        return self._finish(plan)

    @staticmethod
    def _finish(plan: OntapPlan) -> OntapPlan:
        """Order the changes into steps and carry the diff's warnings and refusals."""
        plan.steps = build_steps(plan.diff.changes)
        plan.warnings.extend(plan.diff.warnings)
        plan.refusals.extend(plan.diff.refusals)
        return plan

    def plan_destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        target_resources: list[str] | None = None,
    ) -> OntapPlan:
        """Plan the deletion of the declared LIFs that exist on the cluster.

        ``absent: true`` entries and undeclared LIFs are never touched. The same lock-out
        refusal as ``plan`` applies.

        Args:
            env_name: Environment name (for the settings).
            resources: The provider's resources.
            target_resources: Restrict to these resource names.
        """
        desired = [d for d in desired_from_resources(resources) if not d.absent]
        if target_resources:
            wanted = set(target_resources)
            desired = [d for d in desired if d.resource_name in wanted]
        plan = OntapPlan(resources=list(resources), add_only=True)
        svms = sorted({d.svm for d in desired})
        if not svms:
            return plan
        settings, service = self._service(env_name)
        live = _live_by_key(service.list_interfaces(svms))
        for obj in desired:
            found = live.get(obj.key)
            if found is not None:
                plan.diff.changes.append(
                    Change(DELETE, obj.key, obj.resource_name, found["uuid"], found)
                )
        if plan.diff.changes:
            plan.diff.refusals.extend(
                lockout_refusals(plan.diff.changes, settings.host, self._resolver(settings.host))
            )
        return self._finish(plan)

    def apply(self, env_name: str, plan: OntapPlan) -> OntapApplyResult:
        """Run a plan's steps, stopping at the first error.

        A plan with refusals is never written: the refusals come back and nothing is sent.

        Args:
            env_name: Environment name (for the settings).
            plan: A plan built against the cluster in this run.

        Returns:
            What ran, what failed, the per-resource outcomes and the released managed rows.
        """
        result = OntapApplyResult(refusals=list(plan.refusals), warnings=list(plan.warnings))
        if plan.refusals:
            return result
        if plan.steps:
            _, service = self._service(env_name)
            self._run(service, plan.steps, result)
        result.outcomes = _outcomes(result.completed, plan.names)
        result.counts = {
            kind: sum(1 for o in result.outcomes if o.action == kind)
            for kind in (CREATE, UPDATE, DELETE)
        }
        if result.failed is None:
            result.released = self._released(plan)
        return result

    @staticmethod
    def _run(service: OntapService, steps: list[Step], result: OntapApplyResult) -> None:
        """Send each step; record the first failure and stop."""
        for step in steps:
            try:
                if step.kind == CREATE:
                    service.create_interface(**step.fields)
                elif step.uuid is None:
                    raise OntapError(f"{step.kind} step has no interface uuid")
                elif step.kind == UPDATE:
                    service.update_interface(step.uuid, **step.fields)
                else:
                    service.delete_interface(step.uuid)
            except OntapError as exc:
                result.failed = step
                result.error = _failure_message(steps, result.completed, step, str(exc))
                logger.error("ontap apply failed at '%s' (%s)", label(step.key), step.part)
                return
            result.completed.append(step)

    @staticmethod
    def _released(plan: OntapPlan) -> list[ReleasedResource]:
        """List managed rows that left the YAML (ADR-0018), after a full-mode apply."""
        if plan.add_only or plan.managed_resources is None:
            return []
        rows = plan.managed_resources.get(TYPE_NAME, [])
        yaml_names = {r.name for r in plan.resources if r.type == TYPE_NAME}
        unparsed = managed_index(rows).unparsed
        released: list[ReleasedResource] = []
        seen: set[str] = set()
        for row in rows:
            if row.name in yaml_names or row.name in unparsed or row.name in seen:
                continue
            seen.add(row.name)
            released.append({"resource_type": TYPE_NAME, "name": row.name})
        return released

    def destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        target_resources: list[str] | None = None,
    ) -> OntapApplyResult:
        """Delete the declared LIFs that exist on the cluster.

        Args:
            env_name: Environment name (for the settings).
            resources: The provider's resources.
            target_resources: Restrict to these resource names.
        """
        return self.apply(
            env_name, self.plan_destroy(env_name, resources, target_resources=target_resources)
        )

    def resource_ids(self, env_name: str, resources: list[ResourceConfig]) -> dict[str, str]:
        """Return ``{resource_name: uuid}`` for the declared LIFs that exist live.

        Args:
            env_name: Environment name (for the settings).
            resources: The provider's resources.
        """
        desired: list[DesiredInterface] = [
            d for d in desired_from_resources(resources) if not d.absent
        ]
        svms = sorted({d.svm for d in desired})
        if not svms:
            return {}
        _, service = self._service(env_name)
        live = _live_by_key(service.list_interfaces(svms))
        return {
            d.resource_name: str(live[d.key]["uuid"])
            for d in desired
            if d.key in live and live[d.key]["uuid"]
        }


def _live_by_key(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Index the SVM-scoped live records by identity, as comparison views."""
    from ..schema import live_view

    views: dict[tuple[str, str], dict[str, Any]] = {}
    for record in rows:
        view = live_view(record)
        if view["scope"] == "svm" and view["svm"] and view["name"]:
            views.setdefault((view["svm"], view["name"]), view)
    return views
