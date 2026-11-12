"""Proxmox VE 9.2 SDN dry-run: show what the next SDN apply would change.

Service layer for ``infra plan`` (#1374). It calls ``GET cluster/sdn/dry-run``
once per node and returns a report; it prints nothing itself.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.exceptions import APIError
from infrafoundry.providers.proxmox.api_client import ProxmoxClient

logger = logging.getLogger(__name__)

MIN_DRY_RUN_VERSION: tuple[int, int] = (9, 2)
_UNSUPPORTED_STATUS_CODES = (404, 501)
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)")


def parse_pve_version(version: str) -> tuple[int, int] | None:
    """Parse the major and minor parts of a PVE version string.

    Args:
        version: Version string such as ``9.2.26``

    Returns:
        ``(major, minor)``, or ``None`` when the string is not a version
    """
    match = _VERSION_RE.match(version.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


@dataclass
class NodeSdnDiff:
    """The SDN dry-run result for one node."""

    node: str
    interfaces_diff: str = ""
    frr_diff: str = ""
    skipped: str | None = None
    error: str | None = None

    @property
    def has_changes(self) -> bool:
        """Whether either diff is non-empty."""
        return bool(self.interfaces_diff.strip() or self.frr_diff.strip())


@dataclass
class SdnDryRunReport:
    """The SDN dry-run result for a cluster."""

    version: str = ""
    skipped_reason: str | None = None
    nodes: list[NodeSdnDiff] = field(default_factory=list)


def _node_entries(data: Any) -> list[tuple[str, str]]:
    """Return ``(name, status)`` pairs from the ``nodes`` payload, sorted by name."""
    if not isinstance(data, list):
        return []
    entries: list[tuple[str, str]] = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("node"), str):
            status = item.get("status")
            entries.append((item["node"], status if isinstance(status, str) else "unknown"))
    return sorted(entries)


def _unsupported_reason(version: str) -> str:
    shown = version or "unknown version"
    return (
        f"SDN dry-run skipped: Proxmox VE {shown} has no SDN dry-run "
        f"(needs {MIN_DRY_RUN_VERSION[0]}.{MIN_DRY_RUN_VERSION[1]} or later)"
    )


def run_sdn_dry_run(client: ProxmoxClient) -> SdnDryRunReport:
    """Run the SDN dry-run on every online node.

    Args:
        client: Authenticated Proxmox API client

    Returns:
        A report; per-node failures are recorded in it rather than raised

    Raises:
        APIError: When the ``version`` or ``nodes`` lookups fail
    """
    version_data = client.get_json("version").get("data", {})
    version = str(version_data.get("version", "")) if isinstance(version_data, dict) else ""
    parsed = parse_pve_version(version)
    report = SdnDryRunReport(version=version)
    if parsed is not None and parsed < MIN_DRY_RUN_VERSION:
        report.skipped_reason = _unsupported_reason(version)
        return report

    attempted = False
    for node, status in _node_entries(client.get_json("nodes").get("data")):
        if status != "online":
            report.nodes.append(NodeSdnDiff(node=node, skipped=f"node {status}"))
            continue
        first_call, attempted = not attempted, True
        try:
            payload = client.get_json("cluster/sdn/dry-run", params={"node": node})
        except APIError as exc:
            if first_call and exc.status_code in _UNSUPPORTED_STATUS_CODES:
                report.skipped_reason = _unsupported_reason(version)
                return report
            logger.warning("SDN dry-run failed on node %s: %s", node, exc.message)
            report.nodes.append(NodeSdnDiff(node=node, error=exc.message))
            continue
        data = payload.get("data")
        data = data if isinstance(data, dict) else {}
        report.nodes.append(
            NodeSdnDiff(
                node=node,
                interfaces_diff=str(data.get("interfaces-diff") or ""),
                frr_diff=str(data.get("frr-diff") or ""),
            )
        )
    return report


def format_sdn_dry_run_report(report: SdnDryRunReport) -> list[str]:
    """Render a report as plain console lines.

    Args:
        report: Result of :func:`run_sdn_dry_run`

    Returns:
        Lines to print, without markup
    """
    if report.skipped_reason:
        return [report.skipped_reason]
    lines = [
        "Proxmox SDN dry-run (pending before this run; the next SDN apply, from any "
        "source, will also push these):",
        "  SDN objects this run would stage are not included; see the Terraform plan.",
    ]
    for node in report.nodes:
        if node.skipped:
            lines.append(f"  {node.node}: skipped ({node.skipped})")
        elif node.error:
            lines.append(f"  {node.node}: dry-run failed: {node.error}")
        elif not node.has_changes:
            lines.append(f"  {node.node}: no pending SDN changes")
        else:
            lines.append(f"  {node.node}: pending SDN changes")
            for header, diff in (
                ("interfaces-diff", node.interfaces_diff),
                ("frr-diff", node.frr_diff),
            ):
                if not diff.strip():
                    continue
                lines.append(f"    {header}:")
                lines.extend(f"      {row}" for row in diff.rstrip("\n").splitlines())
    return lines
