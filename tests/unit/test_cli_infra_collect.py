"""Unit tests for the 'infra collect' CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

from click.testing import CliRunner, Result

from infrafoundry.cli.main import main
from infrafoundry.collectors.runner import CollectionReport, DeviceResult
from infrafoundry.collectors.store import ArtifactChange

P = "infrafoundry.cli.commands.infra.collect.collect_environment"


def _invoke(report: CollectionReport, *args: str) -> tuple[Result, Mock]:
    with (
        patch("infrafoundry.cli.main._get_orchestrator", return_value=Mock()),
        patch(P, return_value=report) as fn,
    ):
        result = CliRunner().invoke(main, ["infra", "collect", "--env", "dev", *args])
    return result, fn


def test_no_changes() -> None:
    change = ArtifactChange("ont-isp", Path("x/config.xml.sops.json"), "unchanged")
    result, _ = _invoke(CollectionReport([DeviceResult("ont-isp", [change])]))
    assert result.exit_code == 0 and "No changes." in result.output


def test_changed_file_reported() -> None:
    change = ArtifactChange("ont-isp", Path("x/config.xml.sops.json"), "changed")
    result, _ = _invoke(CollectionReport([DeviceResult("ont-isp", [change])]))
    assert result.exit_code == 0
    assert "changed: ont-isp/config.xml.sops.json" in result.output


def test_failure_exits_nonzero_with_summary() -> None:
    change = ArtifactChange("switch-core", Path("x/export.rsc.sops.json"), "new")
    report = CollectionReport(
        [DeviceResult("ont-isp", error="down"), DeviceResult("switch-core", [change])]
    )
    result, _ = _invoke(report)
    assert result.exit_code != 0
    assert "new: switch-core/export.rsc.sops.json" in result.output
    assert "ont-isp: down" in result.output and "1 device(s) failed" in result.output


def test_device_passed_through() -> None:
    _, fn = _invoke(CollectionReport([]), "-d", "ont-isp", "-d", "switch-core")
    assert fn.call_args.args[2] == ("ont-isp", "switch-core")


def test_listed_in_help() -> None:
    result = CliRunner().invoke(main, ["infra", "--help"])
    assert "collect" in result.output
