"""Tests for the Proxmox SDN dry-run in plan (#1374). No live calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import APIError, AuthenticationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.proxmox import ProxmoxProvider
from infrafoundry.providers.proxmox.sdn_dry_run import (
    NodeSdnDiff,
    SdnDryRunReport,
    format_sdn_dry_run_report,
    parse_pve_version,
    run_sdn_dry_run,
)

NODES = [
    {"node": "pve3", "status": "online"},
    {"node": "pve1", "status": "online"},
    {"node": "pve2", "status": "online"},
]
IFACES = "+ vxlan-local-tunnelip 192.0.2.11\n"
FRR = "+ router bgp 65000\n"


def _client(
    *,
    version: str = "9.2.26",
    nodes: list[dict[str, str]] | None = None,
    diffs: dict[str, Any] | None = None,
    dry_run_error: APIError | None = None,
) -> MagicMock:
    """A client whose ``get_json`` answers by endpoint, keyed by ``params['node']``."""
    diffs = diffs or {}
    calls: list[str] = []

    def get_json(endpoint: str, **kwargs: Any) -> dict[str, Any]:
        if endpoint == "version":
            return {"data": {"version": version}}
        if endpoint == "nodes":
            return {"data": NODES if nodes is None else nodes}
        assert endpoint == "cluster/sdn/dry-run"
        node = kwargs["params"]["node"]
        calls.append(node)
        if dry_run_error is not None:
            raise dry_run_error
        result = diffs.get(node, {"interfaces-diff": "", "frr-diff": ""})
        if isinstance(result, Exception):
            raise result
        return {"data": result}

    client = MagicMock()
    client.get_json = MagicMock(side_effect=get_json)
    client.dry_run_calls = calls
    return client


@pytest.mark.parametrize(
    ("text", "expected"),
    [("9.2.26", (9, 2)), ("9.1.7", (9, 1)), ("10.0", (10, 0)), ("", None), ("garbage", None)],
)
def test_parse_pve_version(text: str, expected: tuple[int, int] | None) -> None:
    assert parse_pve_version(text) == expected


def test_non_empty_diffs_are_reported() -> None:
    client = _client(diffs={"pve1": {"interfaces-diff": IFACES, "frr-diff": FRR}})
    report = run_sdn_dry_run(client)
    assert [n.node for n in report.nodes] == ["pve1", "pve2", "pve3"]
    lines = format_sdn_dry_run_report(report)
    text = "\n".join(lines)
    assert "pending before this run" in lines[0]
    assert "Terraform plan" in lines[1]
    assert "pve1: pending SDN changes" in text
    assert "    interfaces-diff:" in lines
    assert "    frr-diff:" in lines
    assert "      + vxlan-local-tunnelip 192.0.2.11" in lines
    assert "pve2: no pending SDN changes" in text


def test_empty_diffs_report_no_changes() -> None:
    lines = format_sdn_dry_run_report(run_sdn_dry_run(_client()))
    for node in ("pve1", "pve2", "pve3"):
        assert f"  {node}: no pending SDN changes" in lines
    assert not any("interfaces-diff" in line or "frr-diff" in line for line in lines)


def test_pre_92_is_skipped_without_calling_dry_run() -> None:
    client = _client(version="9.1.7")
    report = run_sdn_dry_run(client)
    assert report.skipped_reason is not None
    assert "9.2" in report.skipped_reason
    assert client.dry_run_calls == []
    assert format_sdn_dry_run_report(report) == [report.skipped_reason]


@pytest.mark.parametrize("status", [404, 501])
def test_unparseable_version_with_missing_endpoint_is_skipped(status: int) -> None:
    client = _client(version="garbage", dry_run_error=APIError("nope", status_code=status))
    report = run_sdn_dry_run(client)
    assert report.skipped_reason is not None
    assert "no SDN dry-run" in report.skipped_reason
    assert client.dry_run_calls == ["pve1"]


def test_missing_endpoint_after_an_offline_node_is_still_skipped() -> None:
    """The unsupported check applies to the first dry-run call, not the first node."""
    nodes = [{"node": "pve1", "status": "offline"}, {"node": "pve2", "status": "online"}]
    client = _client(
        version="garbage", nodes=nodes, dry_run_error=APIError("nope", status_code=501)
    )
    report = run_sdn_dry_run(client)
    assert report.skipped_reason is not None
    assert "no SDN dry-run" in report.skipped_reason


def test_offline_node_is_skipped_without_dry_run_call() -> None:
    client = _client(nodes=[{"node": "pve1", "status": "offline"}, NODES[2]])
    report = run_sdn_dry_run(client)
    assert client.dry_run_calls == ["pve2"]
    assert "  pve1: skipped (node offline)" in format_sdn_dry_run_report(report)


def test_per_node_error_does_not_stop_other_nodes() -> None:
    client = _client(diffs={"pve2": APIError("boom", status_code=500)})
    lines = format_sdn_dry_run_report(run_sdn_dry_run(client))
    assert "  pve2: dry-run failed: boom" in lines
    assert "  pve3: no pending SDN changes" in lines


def test_node_diff_has_changes() -> None:
    assert not NodeSdnDiff(node="pve1", frr_diff="  \n").has_changes
    assert NodeSdnDiff(node="pve1", frr_diff="+ x").has_changes
    assert format_sdn_dry_run_report(SdnDryRunReport(version="9.2.0")) != []


# ---- ProxmoxProvider.get_plan_notes -----------------------------------------


@pytest.fixture
def provider(tmp_path: Path) -> ProxmoxProvider:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    p = ProxmoxProvider(config_dir, output_dir)
    p.set_environment("test")
    return p


def _res(rtype: str) -> ResourceConfig:
    return ResourceConfig(name="x", type=rtype, provider="proxmox", config={})


def test_plan_notes_empty_without_sdn_resources(provider: ProxmoxProvider) -> None:
    with patch.object(ProxmoxProvider, "_sdn_dry_run_client") as build:
        assert provider.get_plan_notes([_res("vm")]) == []
    build.assert_not_called()


def test_plan_notes_skip_line_without_credentials(provider: ProxmoxProvider) -> None:
    with patch.object(ProxmoxProvider, "_sdn_dry_run_client", return_value=None):
        notes = provider.get_plan_notes([_res("sdn_zone")])
    assert len(notes) == 1
    assert notes[0].startswith("SDN dry-run skipped")


def test_plan_notes_authentication_error_is_a_skip_line(provider: ProxmoxProvider) -> None:
    client = MagicMock()
    client.get_json.side_effect = AuthenticationError("bad token")
    with patch.object(ProxmoxProvider, "_sdn_dry_run_client", return_value=client):
        notes = provider.get_plan_notes([_res("sdn_vnet")])
    assert notes == ["SDN dry-run skipped: bad token"]


def test_plan_notes_return_formatted_report(provider: ProxmoxProvider) -> None:
    client = _client(diffs={"pve1": {"interfaces-diff": IFACES, "frr-diff": ""}})
    with patch.object(ProxmoxProvider, "_sdn_dry_run_client", return_value=client):
        notes = provider.get_plan_notes([_res("sdn_zone")])
    assert "      + vxlan-local-tunnelip 192.0.2.11" in notes
