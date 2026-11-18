"""Read-only planner for a MikroTik device (apply lands in #1483).

``MikroTikManager.plan`` reads each needed REST path once, diffs the declared
objects against the live rows, orders the writes into phases and refuses a plan whose
end state would cut the management connection.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from infrafoundry.core.provider import ResourceConfig

from ..client import RouterOSClient, RouterOSReader
from ..schema import (
    DEPENDENCY_ORDER,
    SPECS,
    DesiredObject,
    desired_from_resources,
)
from ..settings import MikroTikSettings, load_settings, management_host
from ._managed import managed_keys
from .diff import CREATE, DELETE, UPDATE, TypeDiff, compute_type_diff
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

ClientFactory = Callable[[MikroTikSettings], RouterOSReader]
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
        """One line per type with changes or kept objects, then the phase order."""
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
        for phase, title in PHASE_TITLES.items():
            count = sum(1 for s in self.steps if s.phase == phase)
            if count:
                lines.append(f"phase {phase} ({title}): {count} step(s)")
        return lines


class MikroTikManager:
    """Plans changes for one RouterOS device."""

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

        plan = MikroTikPlan()
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
