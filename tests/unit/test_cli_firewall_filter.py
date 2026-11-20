"""``--firewall`` and ``-P opnsense`` expansion on infra plan/apply/destroy/doctor (#1450)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from infrafoundry.cli.commands.infra._firewall import expand_provider_filter
from infrafoundry.cli.main import main
from infrafoundry.core.provider import ResourceConfig

MULTI: dict[str, Any] = {
    "opnsense": {
        "primary": "fw-a",
        "firewalls": {"fw-a": {}, "fw-b": {}, "fw-c": {}},
    }
}


def _orchestrator(settings: dict[str, Any] | None, providers: list[str]) -> MagicMock:
    orchestrator = MagicMock()
    orchestrator.config_manager.load_environment.return_value.provider_settings = settings or {}
    orchestrator.config_manager.get_all_resources_all_providers.return_value = [
        ResourceConfig(name=f"r{i}", type="t", provider=p, config={})
        for i, p in enumerate(providers)
    ]
    return orchestrator


PRESENT = ["opnsense", "opnsense@fw-b", "proxmox"]


class TestExpandProviderFilter:
    def test_nothing_selected_is_none(self) -> None:
        assert expand_provider_filter(_orchestrator(MULTI, PRESENT), "e", (), ()) is None

    def test_other_providers_pass_through(self) -> None:
        assert expand_provider_filter(_orchestrator(MULTI, PRESENT), "e", ("proxmox",), ()) == [
            "proxmox"
        ]

    def test_provider_opnsense_expands_to_firewalls_with_resources(self) -> None:
        result = expand_provider_filter(_orchestrator(MULTI, PRESENT), "e", ("opnsense",), ())
        assert result == ["opnsense", "opnsense@fw-b"]

    def test_provider_opnsense_keeps_other_providers(self) -> None:
        result = expand_provider_filter(
            _orchestrator(MULTI, PRESENT), "e", ("proxmox", "opnsense"), ()
        )
        assert result == ["proxmox", "opnsense", "opnsense@fw-b"]

    def test_legacy_environment_keeps_the_exact_filter(self) -> None:
        legacy = {"opnsense": {"api_url": "https://fw.example.com"}}
        assert expand_provider_filter(
            _orchestrator(legacy, ["opnsense"]), "e", ("opnsense",), ()
        ) == ["opnsense"]

    def test_firewall_maps_to_exact_ids(self) -> None:
        orchestrator = _orchestrator(MULTI, PRESENT)
        assert expand_provider_filter(orchestrator, "e", (), ("fw-b",)) == ["opnsense@fw-b"]
        assert expand_provider_filter(orchestrator, "e", (), ("fw-a",)) == ["opnsense"]
        assert expand_provider_filter(orchestrator, "e", (), ("fw-b", "fw-a", "fw-b")) == [
            "opnsense@fw-b",
            "opnsense",
        ]

    def test_firewall_narrows_provider_opnsense(self) -> None:
        orchestrator = _orchestrator(MULTI, PRESENT)
        assert expand_provider_filter(orchestrator, "e", ("opnsense",), ("fw-b",)) == [
            "opnsense@fw-b"
        ]

    def test_unknown_firewall_lists_the_declared_ones(self) -> None:
        with pytest.raises(click.UsageError, match=r"Unknown firewall\(s\) fw-z; declared: fw-a"):
            expand_provider_filter(_orchestrator(MULTI, PRESENT), "e", (), ("fw-z",))

    def test_firewall_without_a_firewalls_map_is_an_error(self) -> None:
        legacy = {"opnsense": {"api_url": "https://fw.example.com"}}
        with pytest.raises(click.UsageError, match=r"needs provider_settings\.opnsense\.firewalls"):
            expand_provider_filter(_orchestrator(legacy, ["opnsense"]), "e", (), ("fw-a",))

    def test_firewall_with_another_provider_only_is_an_error(self) -> None:
        with pytest.raises(click.UsageError, match=r"add '-P opnsense' or drop -P"):
            expand_provider_filter(_orchestrator(MULTI, PRESENT), "e", ("proxmox",), ("fw-b",))


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _invoke(runner: CliRunner, orchestrator: MagicMock, *args: str) -> Any:
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=orchestrator):
        return runner.invoke(main, ["infra", *args])


class TestCommands:
    @pytest.mark.parametrize("command", ["plan", "apply", "destroy"])
    def test_firewall_becomes_an_exact_provider_filter(
        self, runner: CliRunner, command: str
    ) -> None:
        orchestrator = _orchestrator(MULTI, PRESENT)
        result = (
            _invoke(
                runner, orchestrator, command, "--env", "e", "--firewall", "fw-b", "--auto-approve"
            )
            if command != "plan"
            else _invoke(runner, orchestrator, command, "--env", "e", "--firewall", "fw-b")
        )
        assert result.exit_code == 0, result.output
        method = getattr(orchestrator, command)
        assert method.call_args.kwargs["provider_filter"] == ["opnsense@fw-b"]

    def test_doctor_passes_the_expanded_filter(self, runner: CliRunner) -> None:
        orchestrator = _orchestrator(MULTI, PRESENT)
        orchestrator.validate.return_value = {"opnsense@fw-b": {"errors": 0, "warnings": 0}}
        with patch(
            "infrafoundry.cli.commands.infra.doctor._jumphost_preflight", return_value=False
        ):
            result = _invoke(runner, orchestrator, "doctor", "--env", "e", "--firewall", "fw-b")
        assert result.exit_code == 0, result.output
        assert orchestrator.validate.call_args.kwargs["provider_filter"] == ["opnsense@fw-b"]

    @pytest.mark.parametrize("flag", [["-r", "x"], ["-p", "pkg"]])
    @pytest.mark.parametrize("command", ["plan", "apply", "destroy", "doctor"])
    def test_firewall_excludes_package_and_resource(
        self, runner: CliRunner, command: str, flag: list[str]
    ) -> None:
        result = _invoke(
            runner,
            _orchestrator(MULTI, PRESENT),
            command,
            "--env",
            "e",
            "--firewall",
            "fw-b",
            *flag,
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output

    def test_provider_and_firewall_may_be_combined(self, runner: CliRunner) -> None:
        orchestrator = _orchestrator(MULTI, PRESENT)
        result = _invoke(
            runner, orchestrator, "plan", "--env", "e", "-P", "opnsense", "--firewall", "fw-b"
        )
        assert result.exit_code == 0, result.output
        assert orchestrator.plan.call_args.kwargs["provider_filter"] == ["opnsense@fw-b"]

    def test_unknown_firewall_is_a_usage_error(self, runner: CliRunner) -> None:
        orchestrator = _orchestrator(MULTI, PRESENT)
        result = _invoke(runner, orchestrator, "plan", "--env", "e", "--firewall", "fw-z")
        assert result.exit_code != 0
        assert "Unknown firewall" in result.output
        orchestrator.plan.assert_not_called()

    def test_legacy_provider_filter_is_unchanged(self, runner: CliRunner) -> None:
        legacy = {"opnsense": {"api_url": "https://fw.example.com"}}
        orchestrator = _orchestrator(legacy, ["opnsense"])
        result = _invoke(runner, orchestrator, "plan", "--env", "e", "-P", "opnsense")
        assert result.exit_code == 0, result.output
        assert orchestrator.plan.call_args.kwargs["provider_filter"] == ["opnsense"]


# --- kubernetes clusters (#1539) -----------------------------------------------

CLUSTERS: dict[str, Any] = {
    "kubernetes": {"primary": "edge", "clusters": {"edge": {}, "cloud": {}, "extra": {}}}
}
K_PRESENT = ["kubernetes", "kubernetes@cloud", "proxmox"]


class TestExpandClusters:
    def test_provider_kubernetes_expands_to_clusters_with_resources(self) -> None:
        orchestrator = _orchestrator(CLUSTERS, K_PRESENT)
        result = expand_provider_filter(orchestrator, "e", ("kubernetes",), ())
        assert result == ["kubernetes", "kubernetes@cloud"]

    def test_cluster_maps_to_exact_ids(self) -> None:
        orchestrator = _orchestrator(CLUSTERS, K_PRESENT)
        assert expand_provider_filter(orchestrator, "e", (), (), clusters=("cloud",)) == [
            "kubernetes@cloud"
        ]
        assert expand_provider_filter(orchestrator, "e", (), (), clusters=("edge",)) == [
            "kubernetes"
        ]

    def test_unknown_cluster_is_a_usage_error(self) -> None:
        orchestrator = _orchestrator(CLUSTERS, K_PRESENT)
        with pytest.raises(click.UsageError, match=r"Unknown cluster\(s\) nope; declared: edge"):
            expand_provider_filter(orchestrator, "e", (), (), clusters=("nope",))

    def test_cluster_without_a_clusters_map_is_a_usage_error(self) -> None:
        flat = {"kubernetes": {"kubeconfig_path": "/k/flat.yaml"}}
        orchestrator = _orchestrator(flat, ["kubernetes"])
        with pytest.raises(
            click.UsageError, match=r"needs provider_settings\.kubernetes\.clusters"
        ):
            expand_provider_filter(orchestrator, "e", (), (), clusters=("cloud",))

    def test_cluster_with_another_provider_only_is_a_usage_error(self) -> None:
        orchestrator = _orchestrator(CLUSTERS, K_PRESENT)
        with pytest.raises(click.UsageError, match=r"add '-P kubernetes' or drop -P"):
            expand_provider_filter(orchestrator, "e", ("proxmox",), (), clusters=("cloud",))

    def test_firewall_and_cluster_combine(self) -> None:
        orchestrator = _orchestrator({**MULTI, **CLUSTERS}, [*PRESENT, *K_PRESENT])
        result = expand_provider_filter(orchestrator, "e", (), ("fw-b",), clusters=("cloud",))
        assert result == ["opnsense@fw-b", "kubernetes@cloud"]

    def test_provider_list_may_name_both_families(self) -> None:
        orchestrator = _orchestrator({**MULTI, **CLUSTERS}, [*PRESENT, *K_PRESENT])
        result = expand_provider_filter(
            orchestrator, "e", ("opnsense", "kubernetes"), ("fw-b",), clusters=("cloud",)
        )
        assert result == ["opnsense@fw-b", "kubernetes@cloud"]


class TestClusterCommands:
    @pytest.mark.parametrize("command", ["plan", "apply", "destroy"])
    def test_cluster_becomes_an_exact_provider_filter(
        self, runner: CliRunner, command: str
    ) -> None:
        orchestrator = _orchestrator(CLUSTERS, K_PRESENT)
        args = [command, "--env", "e", "--cluster", "cloud"]
        if command != "plan":
            args.append("--auto-approve")
        result = _invoke(runner, orchestrator, *args)
        assert result.exit_code == 0, result.output
        assert getattr(orchestrator, command).call_args.kwargs["provider_filter"] == [
            "kubernetes@cloud"
        ]

    def test_doctor_passes_the_expanded_filter(self, runner: CliRunner) -> None:
        orchestrator = _orchestrator(CLUSTERS, K_PRESENT)
        orchestrator.validate.return_value = {"kubernetes@cloud": {"errors": 0, "warnings": 0}}
        with patch(
            "infrafoundry.cli.commands.infra.doctor._jumphost_preflight", return_value=False
        ):
            result = _invoke(runner, orchestrator, "doctor", "--env", "e", "--cluster", "cloud")
        assert result.exit_code == 0, result.output
        assert orchestrator.validate.call_args.kwargs["provider_filter"] == ["kubernetes@cloud"]

    @pytest.mark.parametrize("flag", [["-r", "x"], ["-p", "pkg"]])
    @pytest.mark.parametrize("command", ["plan", "apply", "destroy", "doctor"])
    def test_cluster_excludes_package_and_resource(
        self, runner: CliRunner, command: str, flag: list[str]
    ) -> None:
        result = _invoke(
            runner,
            _orchestrator(CLUSTERS, K_PRESENT),
            command,
            "--env",
            "e",
            "--cluster",
            "cloud",
            *flag,
        )
        assert result.exit_code != 0
