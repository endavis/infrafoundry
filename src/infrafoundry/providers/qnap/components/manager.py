"""Planner, applier and destroyer for a QNAP switch's VLANs, LACP groups and ports (ADR-0039).

``QnapConfigManager.plan`` reads the switch once, diffs the declared objects against it,
orders the writes into phases and refuses a plan whose end state could cut the management
connection. ``apply`` runs a plan's steps and stops at the first error. Afterwards, whether
the steps succeeded or not, it waits for the switch to answer and reads the written
objects back; a switch that does not answer or a re-read that differs fails the apply.
``destroy`` deletes the declared VLANs and LACP groups that exist on the switch; a ``port``
is never deleted, so destroy and a row that leaves the YAML only release it.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from infrafoundry.core.managed_set import ReleasedResource
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..client import QnapClient, QnapError, QnapWriter
from ..schema import (
    CONFIG_TYPES,
    DEFAULT_VLAN_ID,
    DELETABLE_TYPES,
    LACP_ADDRESS_PREFIX,
    LACP_TYPE,
    PORT_ADDRESS_PREFIX,
    PORT_TYPE,
    VLAN_ADDRESS_PREFIX,
    VLAN_TYPE,
    DesiredLag,
    DesiredPort,
    DesiredVlan,
    LacpInfo,
    LiveLag,
    LivePort,
    LiveVlan,
    count_ports,
    desired_lags,
    desired_ports,
    desired_vlans,
    member_style,
    parse_lacp_info,
    parse_lags,
    parse_ports,
    parse_vlans,
    port_matches,
    resolve_port,
)
from ..settings import QnapSettings, load_settings
from ._managed import managed_index, managed_keys
from .diff import (
    CREATE,
    DELETE,
    UPDATE,
    Change,
    LagEnd,
    TypeDiff,
    check_end_state,
    check_port_fec,
    diff_lags,
    diff_ports,
    diff_vlans,
    end_state,
    label,
    untag_warnings,
)
from .executor import execute_steps
from .lockout import check_lockout, check_port_lockout, management_vlan, watched_ports
from .ordering import PHASE_TITLES, Step, order_changes

logger = logging.getLogger(__name__)

ClientFactory = Callable[[QnapSettings], QnapWriter]
_PREFIX = {
    VLAN_TYPE: VLAN_ADDRESS_PREFIX,
    LACP_TYPE: LACP_ADDRESS_PREFIX,
    PORT_TYPE: PORT_ADDRESS_PREFIX,
}
_LIVE_POLL_SECONDS = 2.0
_BACKUP_HINT = (
    "Restore from the 'infra collect' backup of this switch, or use physical access if the "
    "management connection is gone."
)


@dataclass
class QnapPlan:
    """The outcome of planning one environment against one switch."""

    diffs: dict[str, TypeDiff] = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    resources: list[ResourceConfig] = field(default_factory=list)
    """The YAML resources the plan was built from (apply derives the released names)."""
    add_only: bool = False
    managed_resources: Mapping[str, list[ResourceConfig]] | None = None
    end_vlans: dict[int, dict[int, bool]] = field(default_factory=dict)
    end_lags: dict[int, LagEnd] = field(default_factory=dict)
    end_ports: dict[int, DesiredPort] = field(default_factory=dict)
    """The declared settings of the ports the plan changes (the read-back compares them)."""
    live_mtus: dict[int, int] = field(default_factory=dict)
    """Physical port number to its MTU before the writes (to spot a switch-wide MTU)."""

    @property
    def counts(self) -> dict[str, int]:
        """Number of creates, updates and deletes across all types."""
        return {
            kind: sum(d.count(kind) for d in self.diffs.values())
            for kind in (CREATE, UPDATE, DELETE)
        }

    @property
    def has_changes(self) -> bool:
        """True when any type has a change."""
        return any(not d.is_empty for d in self.diffs.values())

    @property
    def unmanaged(self) -> dict[str, list[str]]:
        """Undeclared live objects that stay, per type."""
        return {t: d.unmanaged for t, d in self.diffs.items() if d.unmanaged}

    def summary_lines(self) -> list[str]:
        """One line per type with changes or kept objects, the notes, then the phases."""
        lines: list[str] = []
        for type_name, diff in self.diffs.items():
            if diff.is_empty and not diff.unmanaged:
                continue
            text = (
                f"{type_name}: {diff.count(CREATE)} to create, {diff.count(UPDATE)} to update, "
                f"{diff.count(DELETE)} to delete"
            )
            if diff.unmanaged:
                text += f", {len(diff.unmanaged)} unmanaged (kept)"
            lines.append(text)
            for change in diff.changes:
                suffix = " (unmanaged)" if change.incidental else ""
                lines.extend(
                    f"{type_name} {label(change.key)}{suffix}: {note}" for note in change.notes
                )
        for phase, title in PHASE_TITLES.items():
            count = sum(1 for s in self.steps if s.phase == phase)
            if count:
                lines.append(f"phase {phase} ({title}): {count} step(s)")
        return lines


@dataclass
class QnapApplyResult:
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
        """True when nothing was refused and every step ran and was read back."""
        return not self.refusals and self.failed is None and self.error is None


def _failure_message(steps: list[Step], completed: list[Step], failed: Step, error: str) -> str:
    """Name the failed step, the switch's message and the steps that already ran."""
    lines = [
        f"qnap apply failed at step {len(completed) + 1} of {len(steps)} "
        f"(phase {failed.phase}: {failed.kind} {failed.type_name} '{failed.resource_name}'): "
        f"{error}"
    ]
    if completed:
        lines.append(f"{len(completed)} step(s) completed before it:")
        lines.extend(f"- {s.kind} {s.type_name} '{s.resource_name}'" for s in completed)
    else:
        lines.append("No step completed before it.")
    return "\n".join(lines)


_ACTION_RANK = {CREATE: 0, DELETE: 1, UPDATE: 2}


def _outcomes(
    steps: list[Step], names: dict[str, dict[tuple[Any, ...], str]]
) -> list[ResourceOutcome]:
    """One outcome per managed resource: create beats delete beats update."""
    best: dict[tuple[str, tuple[Any, ...]], Step] = {}
    for step in steps:
        if step.incidental:
            continue
        ident = (step.type_name, step.key)
        current = best.get(ident)
        if current is None or _ACTION_RANK[step.kind] < _ACTION_RANK[current.kind]:
            best[ident] = step
    outcomes: list[ResourceOutcome] = []
    for (type_name, key), step in best.items():
        name = step.resource_name
        if step.kind == DELETE and name == label(key):
            name = names.get(type_name, {}).get(key, name)
        address = f"{_PREFIX[type_name]}.{name}"
        outcomes.append(ResourceOutcome(address=address, action=step.kind, resource_name=name))
    return outcomes


@dataclass
class _Live:
    """Everything one read of the switch gave."""

    vlans: list[LiveVlan]
    lags: list[LiveLag]
    info: LacpInfo
    ports_raw: Any = None
    """The ``GET ports`` reply, when it was read."""
    ports: list[LivePort] = field(default_factory=list)

    @property
    def vlan_members(self) -> dict[int, dict[int, bool]]:
        return {v.id: dict(v.members) for v in self.vlans}

    @property
    def lag_ends(self) -> dict[int, LagEnd]:
        return {g.group: LagEnd(g.mode, g.members) for g in self.lags}


def _read(client: QnapWriter, *, ports: bool = False) -> _Live:
    """Read the VLANs, LACP groups and limits; ``ports`` also reads ``GET ports``."""
    live = _Live(
        parse_vlans(client.get("vlan")),
        parse_lags(client.get("lacp/group")),
        parse_lacp_info(client.get("lacp/info")),
    )
    if ports:
        live.ports_raw = client.get("ports")
        live.ports = parse_ports(live.ports_raw)
    return live


class QnapConfigManager:
    """Plans, applies and destroys VLAN, LACP and port changes for one QNAP switch."""

    def __init__(
        self,
        config_dir: Path,
        client_factory: ClientFactory | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize the manager.

        Args:
            config_dir: Configuration directory (for the settings).
            client_factory: Builds the client from settings; replaced in tests.
            sleep: Sleeps between liveness polls; replaced in tests.
            clock: Monotonic clock for the liveness deadline; replaced in tests.
        """
        self.config_dir = config_dir
        self._client_factory: ClientFactory = client_factory or QnapClient
        self._sleep = sleep
        self._clock = clock

    # -- plan

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: Mapping[str, list[ResourceConfig]] | None = None,
        target_resources: list[str] | None = None,
    ) -> QnapPlan:
        """Diff the declared objects against the switch and order the writes.

        Args:
            env_name: Environment name (for the settings).
            resources: The provider's resources.
            add_only: Suppress deletes (drift runs).
            managed_resources: Managed rows by type; only these are deleted when undeclared.
            target_resources: Restrict to these resource names; implies add-only.

        Returns:
            The plan. ``refusals`` is non-empty when the end state is unsafe. A run that
            declares no config object and has nothing to delete makes no device call.

        Raises:
            QnapPlanError: If the declared end state cannot exist on this switch.
        """
        vlans, lags = desired_vlans(resources), desired_lags(resources)
        ports = desired_ports(resources)
        if target_resources:
            wanted = set(target_resources)
            vlans = [d for d in vlans if d.resource_name in wanted]
            lags = [d for d in lags if d.resource_name in wanted]
            ports = [d for d in ports if d.resource_name in wanted]
            add_only = True
        plan = QnapPlan(
            resources=list(resources), add_only=add_only, managed_resources=managed_resources
        )
        managed = {t: (managed_resources or {}).get(t) for t in CONFIG_TYPES}
        removable = not add_only and any(managed[t] for t in DELETABLE_TYPES)
        if not vlans and not lags and not ports and not removable:
            return plan
        settings = load_settings(self.config_dir, env_name)
        client = self._client_factory(settings)
        with client.session():
            live = _read(client, ports=bool(ports))
            plan.diffs[VLAN_TYPE] = diff_vlans(
                vlans,
                live.vlans,
                live.info.start_index,
                add_only=add_only,
                managed_keys=managed_keys(managed[VLAN_TYPE], VLAN_TYPE),
            )
            plan.diffs[LACP_TYPE] = diff_lags(
                lags,
                live.lags,
                live.info.start_index,
                add_only=add_only,
                managed_keys=managed_keys(managed[LACP_TYPE], LACP_TYPE),
            )
            if ports:
                port_diff = diff_ports(ports, live.ports)
                plan.diffs[PORT_TYPE] = port_diff
                changed = {c.key[0] for c in port_diff.changes}
                plan.end_ports = {p.port: p for p in ports if p.port in changed}
            if plan.has_changes:
                self._finish(plan, client, settings, live, verify_references=True)
        return plan

    def _finish(
        self,
        plan: QnapPlan,
        client: QnapWriter,
        settings: QnapSettings,
        live: _Live,
        *,
        verify_references: bool,
    ) -> None:
        """Check the end state, run the lock-out rules and order the steps."""
        start = live.info.start_index
        live_vlans, live_lags = live.vlan_members, live.lag_ends
        plan.end_vlans, plan.end_lags = end_state(plan.diffs, live_vlans, live_lags)
        if verify_references:
            ports_raw = live.ports_raw if live.ports_raw is not None else client.get("ports")
            check_end_state(
                plan.diffs,
                plan.end_vlans,
                plan.end_lags,
                port_count=count_ports(ports_raw),
                info=live.info,
            )
        port_diff = plan.diffs.get(PORT_TYPE)
        check_port_fec(port_diff, live.ports)
        if port_diff is not None and any("mtu" in c.fields for c in port_diff.changes):
            plan.live_mtus = {row.key: row.mtu for row in live.ports if not row.is_lag}
        for diff in plan.diffs.values():
            plan.warnings.extend(diff.warnings)
        plan.warnings.extend(untag_warnings(plan.end_vlans, live_vlans, start))
        if settings.allow_lockout_risk:
            plan.warnings.append(
                "allow_lockout_risk is set: lock-out refusals are downgraded to warnings"
            )
        watched: frozenset[int] = frozenset()
        mgmt, notes = management_vlan(settings, client.get("ip/ipv4/interface"))
        plan.warnings.extend(notes)
        if mgmt is None:
            plan.refusals.append(
                "cannot determine the management VLAN, so the plan cannot prove it keeps the "
                "management connection; set provider_settings.qnap.management_vlan"
            )
        else:
            protected = {resolve_port(p, start) for p in settings.protected_ports}
            check = check_lockout(
                plan.end_vlans,
                {g: lag.members for g, lag in plan.end_lags.items()},
                live_vlans,
                {g: lag.members for g, lag in live_lags.items()},
                mgmt,
                protected,
                start,
                settings.allow_lockout_risk,
            )
            plan.refusals.extend(check.refusals)
            plan.warnings.extend(check.warnings)
            if port_diff is not None and port_diff.changes:
                lag_members = {
                    g: set(lag.members) | set(live_lags[g].members if g in live_lags else ())
                    for g, lag in plan.end_lags.items()
                } | {g: set(lag.members) for g, lag in live_lags.items() if g not in plan.end_lags}
                mgmt_members = set(live_vlans.get(mgmt, {})) | set(plan.end_vlans.get(mgmt, {}))
                watched = watched_ports(protected, mgmt_members, lag_members, start)
                port_check = check_port_lockout(
                    port_diff.changes, watched, settings.allow_lockout_risk
                )
                plan.refusals.extend(port_check.refusals)
                plan.warnings.extend(port_check.warnings)
        plan.steps = order_changes(
            plan.diffs.get(VLAN_TYPE),
            plan.diffs.get(LACP_TYPE),
            live_vlans,
            plan.end_vlans,
            mgmt,
            member_as_str=member_style(live.lags),
            port_diff=port_diff,
            last_ports=watched,
        )

    def plan_destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        target_resources: list[str] | None = None,
    ) -> QnapPlan:
        """Plan the deletion of the declared objects that exist on the switch.

        Only declared objects that exist are removed, never VLAN 1, ``absent: true``
        entries or undeclared objects. The end state goes through the same lock-out rules.

        Args:
            env_name: Environment name (for the settings).
            resources: The provider's resources.
            target_resources: Restrict to these resource names.
        """
        vlans = [d for d in desired_vlans(resources) if not d.absent]
        lags = [d for d in desired_lags(resources) if not d.absent]
        if target_resources:
            wanted = set(target_resources)
            vlans = [d for d in vlans if d.resource_name in wanted]
            lags = [d for d in lags if d.resource_name in wanted]
        plan = QnapPlan(resources=list(resources), add_only=True)
        if not vlans and not lags:
            return plan
        settings = load_settings(self.config_dir, env_name)
        client = self._client_factory(settings)
        with client.session():
            live = _read(client)
            live_vlans = {v.id: v for v in live.vlans}
            live_lags = {g.group: g for g in live.lags}
            vlan_diff = TypeDiff(VLAN_TYPE)
            for obj in vlans:
                found = live_vlans.get(obj.id)
                if found is not None and obj.id != DEFAULT_VLAN_ID:
                    vlan_diff.changes.append(
                        Change(DELETE, VLAN_TYPE, obj.key, obj.resource_name, before=found.members)
                    )
            lag_diff = TypeDiff(LACP_TYPE)
            for lag in lags:
                lag_found = live_lags.get(lag.group)
                if lag_found is not None:
                    lag_diff.changes.append(
                        Change(
                            DELETE,
                            LACP_TYPE,
                            lag.key,
                            lag.resource_name,
                            before=LagEnd(lag_found.mode, lag_found.members),
                        )
                    )
            plan.diffs = {VLAN_TYPE: vlan_diff, LACP_TYPE: lag_diff}
            if plan.has_changes:
                self._finish(plan, client, settings, live, verify_references=False)
        return plan

    # -- apply

    def apply(self, env_name: str, plan: QnapPlan) -> QnapApplyResult:
        """Run a plan's steps, stopping at the first error, then read the result back.

        A plan with refusals is never written: the refusals come back and nothing is sent.

        Args:
            env_name: Environment name (for the settings).
            plan: A plan built against the switch in this run.

        Returns:
            What ran, what failed, the per-resource outcomes and the released managed rows.
        """
        result = QnapApplyResult(refusals=list(plan.refusals), warnings=list(plan.warnings))
        if plan.refusals:
            return result
        if not plan.steps:
            result.released = self._released(plan)
            return result
        settings = load_settings(self.config_dir, env_name)
        client = self._client_factory(settings)
        with client.session():
            executed = execute_steps(client, plan.steps)
        result.completed = executed.completed
        result.outcomes = _outcomes(executed.completed, self._managed_names(plan))
        result.counts = {
            kind: sum(1 for o in result.outcomes if o.action == kind)
            for kind in (CREATE, UPDATE, DELETE)
        }
        messages: list[str] = []
        if executed.failed is not None:
            result.failed = executed.failed
            messages.append(
                _failure_message(
                    plan.steps,
                    executed.completed,
                    executed.failed,
                    executed.error or "unknown error",
                )
            )
            logger.error(
                "qnap apply failed at %s '%s'",
                executed.failed.type_name,
                executed.failed.resource_name,
            )
        messages.extend(
            self._verify_after_apply(client, settings, plan, executed.completed, result.warnings)
        )
        if messages:
            result.error = "\n".join(messages)
            return result
        result.released = self._released(plan)
        return result

    def _verify_after_apply(
        self,
        client: QnapWriter,
        settings: QnapSettings,
        plan: QnapPlan,
        completed: list[Step],
        warnings: list[str],
    ) -> list[str]:
        """Wait for the switch, read it back and return the problems found.

        Observations that are not failures (a switch-wide MTU) are appended to ``warnings``.
        """
        if not self._wait_live(client, settings.liveness_timeout):
            return [
                f"the switch stopped answering on {settings.api_url} after "
                f"{len(completed)} completed step(s). {_BACKUP_HINT}"
            ]
        if not completed:
            return []
        try:
            with client.session():
                live = _read(client, ports=any(s.type_name == PORT_TYPE for s in completed))
        except QnapError as exc:
            return [f"could not read the switch back after the writes: {exc}"]
        warnings.extend(self._mtu_warnings(plan, completed, live))
        return [
            f"after the writes the switch differs from the plan for {name}"
            for name in self._mismatches(plan, completed, live)
        ]

    @staticmethod
    def _mtu_warnings(plan: QnapPlan, completed: list[Step], live: _Live) -> list[str]:
        """Warn when an MTU write also changed ports the YAML does not declare."""
        changed = {
            s.key[0]: plan.end_ports[s.key[0]].mtu
            for s in completed
            if s.type_name == PORT_TYPE and s.key[0] in plan.end_ports and plan.live_mtus
        }
        wanted = {m for m in changed.values() if m is not None}
        if not wanted:
            return []
        declared = {p.port for p in desired_ports(plan.resources)}
        spread = [
            row.key
            for row in live.ports
            if not row.is_lag
            and row.key not in declared
            and row.mtu in wanted
            and plan.live_mtus.get(row.key) not in (None, row.mtu)
        ]
        if not spread:
            return []
        return [
            "the MTU is switch-wide: undeclared port(s) "
            + ", ".join(str(k) for k in sorted(spread))
            + " now show the new MTU too"
        ]

    def _wait_live(self, client: QnapWriter, timeout: int) -> bool:
        """Poll ``/api/live`` until it answers or ``timeout`` seconds have passed."""
        deadline = self._clock() + timeout
        while True:
            if client.live():
                return True
            if self._clock() >= deadline:
                return False
            self._sleep(_LIVE_POLL_SECONDS)

    @staticmethod
    def _mismatches(plan: QnapPlan, completed: list[Step], live: _Live) -> list[str]:
        """Name the fully written objects whose live state differs from the plan's end state."""
        done = {(s.type_name, s.key) for s in completed}
        pending = {(s.type_name, s.key) for s in plan.steps if s not in completed}
        names: dict[tuple[str, tuple[Any, ...]], str] = {}
        for step in plan.steps:
            names.setdefault((step.type_name, step.key), step.resource_name)
        live_vlans = live.vlan_members
        live_lags = live.lag_ends
        bad: list[str] = []
        for ident in sorted(done - pending, key=str):
            type_name, key = ident
            group = key[0]
            if type_name == PORT_TYPE:
                desired = plan.end_ports.get(group)
                row = next((p for p in live.ports if p.key == group), None)
                ok = desired is not None and row is not None and port_matches(row, desired)
            elif type_name == VLAN_TYPE:
                want = plan.end_vlans.get(group)
                ok = live_vlans.get(group) == want
            else:
                end = plan.end_lags.get(group)
                have = live_lags.get(group)
                ok = (have is None and end is None) or (
                    have is not None
                    and end is not None
                    and have.members == end.members
                    and str(have.mode) == str(end.mode)
                )
            if not ok:
                bad.append(f"{type_name} '{names[ident]}'")
        return bad

    @staticmethod
    def _managed_names(plan: QnapPlan) -> dict[str, dict[tuple[Any, ...], str]]:
        """Map each managed type's keys to the managed row names."""
        if plan.managed_resources is None:
            return {}
        return {
            type_name: managed_index(rows, type_name).names
            for type_name, rows in plan.managed_resources.items()
            if type_name in CONFIG_TYPES
        }

    @staticmethod
    def _released(plan: QnapPlan) -> list[ReleasedResource]:
        """List managed rows that left the YAML (ADR-0018), after a full-mode apply."""
        if plan.add_only or plan.managed_resources is None:
            return []
        released: list[ReleasedResource] = []
        for type_name, rows in plan.managed_resources.items():
            if type_name not in CONFIG_TYPES:
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
    ) -> QnapApplyResult:
        """Delete the declared objects that exist on the switch.

        Args:
            env_name: Environment name (for the settings).
            resources: The provider's resources.
            target_resources: Restrict to these resource names.
        """
        return self.apply(
            env_name, self.plan_destroy(env_name, resources, target_resources=target_resources)
        )

    def resource_ids(self, env_name: str, resources: list[ResourceConfig]) -> dict[str, str]:
        """Return ``{resource_name: id}`` for the declared objects that exist live.

        Args:
            env_name: Environment name (for the settings).
            resources: The provider's resources.
        """
        desired: list[DesiredVlan | DesiredLag | DesiredPort] = [
            *(d for d in desired_vlans(resources) if not d.absent),
            *(d for d in desired_lags(resources) if not d.absent),
            *desired_ports(resources),
        ]
        if not desired:
            return {}
        has_ports = any(d.type_name == PORT_TYPE for d in desired)
        client = self._client_factory(load_settings(self.config_dir, env_name))
        with client.session():
            live = _read(client, ports=has_ports)
        present = (
            {(VLAN_TYPE, v.id) for v in live.vlans}
            | {(LACP_TYPE, g.group) for g in live.lags}
            | {(PORT_TYPE, p.key) for p in live.ports if not p.is_lag}
        )
        return {
            d.resource_name: str(d.key[0]) for d in desired if (d.type_name, d.key[0]) in present
        }
