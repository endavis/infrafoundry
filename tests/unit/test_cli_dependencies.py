"""Unit tests for the 'dependencies' CLI command."""

import importlib
from typing import Any

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main

cli_main = importlib.import_module("infrafoundry.cli.main")


def test_dependencies_mermaid_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dependencies command emits mermaid when requested."""
    runner = CliRunner()

    class FakeGraph:
        def export_to_mermaid(self) -> str:
            return "graph TD; A-->B"

        def get_execution_batches(self) -> list[Any]:
            return [["proxmox:vm1"]]

    class FakeOrchestrator:
        def build_dependency_graph(self, env: Any) -> Any:
            return FakeGraph()

    def fake_load_orchestrator(*args: Any, **kwargs: Any) -> Any:
        return FakeOrchestrator()

    monkeypatch.setattr(cli_main, "_get_orchestrator", fake_load_orchestrator)

    result = runner.invoke(
        main, ["infra", "analyze", "dependencies", "--env", "dev", "--format", "mermaid"]
    )

    assert result.exit_code == 0
    assert "graph TD" in result.output


def test_dependencies_list_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dependencies command lists batches by default."""
    runner = CliRunner()

    class FakeGraph:
        def get_execution_batches(self) -> list[Any]:
            return [["proxmox:net"], ["proxmox:vm1", "proxmox:vm2"]]

    class FakeOrchestrator:
        def build_dependency_graph(self, env: Any) -> Any:
            return FakeGraph()

    def fake_load_orchestrator(*args: Any, **kwargs: Any) -> Any:
        return FakeOrchestrator()

    monkeypatch.setattr(cli_main, "_get_orchestrator", fake_load_orchestrator)

    result = runner.invoke(main, ["infra", "analyze", "dependencies", "--env", "dev"])

    assert result.exit_code == 0
    assert "Batch 1" in result.output
    assert "proxmox:vm1" in result.output


def test_dependencies_with_resource_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dependencies command with --resource shows specific resource analysis."""
    runner = CliRunner()

    class FakeGraph:
        def get_all_dependencies(self, resource: Any) -> list[Any]:
            if resource == "proxmox:vm1":
                return ["proxmox:net", "proxmox:storage"]
            return []

        def get_all_dependents(self, resource: Any) -> list[Any]:
            if resource == "proxmox:vm1":
                return ["proxmox:vm2"]
            return []

    class FakeOrchestrator:
        def build_dependency_graph(self, env: Any) -> Any:
            return FakeGraph()

    def fake_load_orchestrator(*args: Any, **kwargs: Any) -> Any:
        return FakeOrchestrator()

    monkeypatch.setattr(cli_main, "_get_orchestrator", fake_load_orchestrator)

    result = runner.invoke(
        main, ["infra", "analyze", "dependencies", "--env", "dev", "--resource", "proxmox:vm1"]
    )

    assert result.exit_code == 0
    assert "Dependency analysis for proxmox:vm1" in result.output
    assert "proxmox:net" in result.output
    assert "proxmox:storage" in result.output
    assert "proxmox:vm2" in result.output
    assert "Depends on:" in result.output
    assert "Required by:" in result.output
