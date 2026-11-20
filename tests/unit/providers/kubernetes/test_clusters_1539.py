"""Several Kubernetes clusters per environment (#1539, ADR-0030)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.execution_planner import ExecutionPlanner
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.terraform_outputs import output_ref_dependencies
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.kubernetes import KubernetesProvider, clusters
from infrafoundry.providers.kubernetes.clusters import (
    cluster_settings,
    kubeconfig_env_override,
    validate_clusters_settings,
)
from infrafoundry.providers.kubernetes.validator import KubernetesValidator
from tests.helpers.env import make_env_config

FLAT: dict[str, Any] = {"kubeconfig_path": "/k/flat.yaml", "context": "flat-ctx"}
MULTI: dict[str, Any] = {
    "primary": "edge",
    "clusters": {
        "edge": {"kubeconfig_path": "/k/edge.yaml"},
        "cloud": {"kubeconfig_path": "/k/cloud.yaml", "context": "cloud-admin"},
    },
}


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("KUBECONFIG", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.setattr(clusters, "_WARNED", set())


def _env(settings: dict[str, Any], **extra: Any) -> Any:
    return make_env_config(name="test", provider_settings={"kubernetes": settings}, **extra)


def _provider(tmp_path: Path, cluster: str | None = None) -> KubernetesProvider:
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "output").mkdir(exist_ok=True)
    prov = KubernetesProvider(tmp_path / "config", tmp_path / "output", cluster=cluster)
    prov.set_environment("test")
    return prov


def _ns(provider: str = "kubernetes") -> ResourceConfig:
    return ResourceConfig(provider=provider, type="namespaces", name="app", config={})


class TestClusterSettings:
    def test_flat_shape_is_returned_unchanged(self) -> None:
        assert cluster_settings(FLAT, "kubernetes") is FLAT
        assert cluster_settings(None, "kubernetes") is None

    def test_per_cluster_settings(self) -> None:
        assert cluster_settings(MULTI, "kubernetes") == {"kubeconfig_path": "/k/edge.yaml"}
        assert cluster_settings(MULTI, "kubernetes@cloud") == {
            "kubeconfig_path": "/k/cloud.yaml",
            "context": "cloud-admin",
        }
        assert cluster_settings(MULTI, "kubernetes@nope") == {}

    def test_reads_an_environment_config(self) -> None:
        assert cluster_settings(_env(MULTI), "kubernetes@cloud") == MULTI["clusters"]["cloud"]

    def test_valid_and_flat_shapes_have_no_errors(self) -> None:
        assert validate_clusters_settings(None) == []
        assert validate_clusters_settings(FLAT) == []
        assert validate_clusters_settings(MULTI) == []

    def test_shape_errors(self) -> None:
        errors = validate_clusters_settings(
            {"kubeconfig_path": "/x", "clusters": {"a": {}, "B_1": {}, "c": "no"}}
        )
        assert any("cannot combine 'clusters' with top-level kubeconfig_path" in e for e in errors)
        assert any("cluster name 'B_1' is invalid" in e for e in errors)
        assert any("cluster 'c' must be a mapping" in e for e in errors)
        assert any("'primary' is required" in e for e in errors)
        assert validate_clusters_settings({"primary": "z", "clusters": {"a": {}}}) == [
            "primary 'z' is not declared under clusters"
        ]


class TestKubeconfigEnv:
    def test_flat_shape_lets_kubeconfig_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KUBECONFIG", "/env/a.yaml:/env/b.yaml")
        assert kubeconfig_env_override(FLAT) == "/env/a.yaml"
        assert kubeconfig_env_override(None) == "/env/a.yaml"

    def test_clusters_shape_ignores_kubeconfig_and_warns_once(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("KUBECONFIG", "/env/a.yaml")
        with caplog.at_level(logging.WARNING):
            assert kubeconfig_env_override(MULTI) is None
            assert kubeconfig_env_override(MULTI) is None
        warnings = [r for r in caplog.records if "KUBECONFIG is set but ignored" in r.message]
        assert len(warnings) == 1

    def test_unset_kubeconfig_is_none(self) -> None:
        assert kubeconfig_env_override(MULTI) is None
        assert kubeconfig_env_override(FLAT) is None


class TestProvider:
    def test_instance_name_and_spawn(self, tmp_path: Path) -> None:
        base = _provider(tmp_path)
        assert base.name == "kubernetes"
        spawned = base.spawn_instance("cloud")
        assert spawned.name == "kubernetes@cloud"
        assert spawned.terraform_dir == base.terraform_dir.parent / "kubernetes@cloud"
        assert spawned.base_output_dir == base.base_output_dir

    def test_each_cluster_gets_its_own_tf_vars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = _env(MULTI)
        base = _provider(tmp_path)
        cloud = base.spawn_instance("cloud")
        for prov in (base, cloud):
            monkeypatch.setattr(prov, "_load_environment_config", lambda: env)
        primary_vars = base.get_terraform_env_vars()
        cloud_vars = cloud.get_terraform_env_vars()
        assert primary_vars["TF_VAR_kubeconfig_path"] == "/k/edge.yaml"
        assert "TF_VAR_kubeconfig_context" not in primary_vars
        assert cloud_vars["TF_VAR_kubeconfig_path"] == "/k/cloud.yaml"
        assert cloud_vars["TF_VAR_kubeconfig_context"] == "cloud-admin"

    def test_flat_shape_kubeconfig_still_overrides(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        prov = _provider(tmp_path)
        env = _env(FLAT)
        monkeypatch.setattr(prov, "_load_environment_config", lambda: env)
        monkeypatch.setenv("KUBECONFIG", "/env/a.yaml")
        result = prov.get_terraform_env_vars()
        assert result["TF_VAR_kubeconfig_path"] == "/env/a.yaml"
        assert result["TF_VAR_kubeconfig_context"] == "flat-ctx"

    def test_clusters_shape_ignores_kubeconfig_for_every_cluster(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        env = _env(MULTI)
        base = _provider(tmp_path)
        cloud = base.spawn_instance("cloud")
        for prov in (base, cloud):
            monkeypatch.setattr(prov, "_load_environment_config", lambda: env)
        monkeypatch.setenv("KUBECONFIG", "/env/a.yaml")
        with caplog.at_level(logging.WARNING):
            assert base.get_terraform_env_vars()["TF_VAR_kubeconfig_path"] == "/k/edge.yaml"
            assert cloud.get_terraform_env_vars()["TF_VAR_kubeconfig_path"] == "/k/cloud.yaml"
        assert any("KUBECONFIG is set but ignored" in r.message for r in caplog.records)

    def test_generated_files_declare_config_context(self, tmp_path: Path) -> None:
        prov = _provider(tmp_path).spawn_instance("cloud")
        helm = ResourceConfig(
            provider="kubernetes@cloud",
            type="helm_releases",
            name="rel",
            config={"chart": "c", "repository": "https://charts.example.com"},
        )
        prov.generate_terraform([_ns("kubernetes@cloud"), helm])
        provider_tf = (prov.terraform_dir / "provider.tf").read_text()
        assert provider_tf.count("config_context = var.kubeconfig_context") == 2
        assert 'variable "kubeconfig_context"' in (prov.terraform_dir / "variables.tf").read_text()
        assert prov.terraform_dir.name == "kubernetes@cloud"


class TestValidator:
    def test_context_comes_from_the_cluster_and_ignores_kubeconfig(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("KUBECONFIG", "/env/a.yaml")
        validator = KubernetesValidator(
            _env(MULTI), ValidationReport(), provider_name="kubernetes@cloud"
        )
        context = validator._kubeconfig_context()
        assert context.kubeconfig_path == "/k/cloud.yaml"
        assert context.context_override == "cloud-admin"

    def test_flat_context_still_honours_kubeconfig(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KUBECONFIG", "/env/a.yaml")
        context = KubernetesValidator(_env(FLAT), ValidationReport())._kubeconfig_context()
        assert context.kubeconfig_path == "/env/a.yaml"
        assert context.context_override == "flat-ctx"

    def test_shape_errors_reported_for_the_primary_only(self) -> None:
        bad: dict[str, Any] = {"clusters": {"a": {}, "b": {}}}
        for name, expected in (("kubernetes", 1), ("kubernetes@b", 0)):
            report = ValidationReport()
            KubernetesValidator(_env(bad), report, provider_name=name).validate_offline([])
            errors = [
                r
                for r in report.results
                if r.check_name == "kubernetes_clusters_settings" and not r.passed
            ]
            assert len(errors) == expected

    @staticmethod
    def _output_ref_errors(provider_name: str, ref: str) -> list[str]:
        res = ResourceConfig(
            provider=provider_name,
            type="secrets",
            name="creds",
            config={"string_data_secrets": {"k": ref}},
        )
        report = ValidationReport()
        KubernetesValidator(_env(MULTI), report, provider_name=provider_name).validate_offline(
            [res]
        )
        return [
            r.message
            for r in report.results
            if not r.passed and r.level == ValidationLevel.ERROR and "outputs." in r.message
        ]

    def test_instance_may_read_primary_outputs(self) -> None:
        assert self._output_ref_errors("kubernetes@cloud", "outputs.kubernetes.token") == []
        assert self._output_ref_errors("kubernetes@cloud", "outputs.tailscale.key") == []

    def test_primary_may_not_read_its_own_outputs(self) -> None:
        errors = self._output_ref_errors("kubernetes", "outputs.kubernetes.token")
        assert any("own outputs" in e for e in errors)


class TestOutputOrdering:
    def test_instance_consumer_depends_on_producer(self, tmp_path: Path) -> None:
        prov = _provider(tmp_path).spawn_instance("cloud")
        secret = ResourceConfig(
            provider="kubernetes@cloud",
            type="secrets",
            name="creds",
            config={"string_data_secrets": {"k": "outputs.tailscale.key"}},
        )
        deps = output_ref_dependencies({"kubernetes@cloud": prov}, {"kubernetes@cloud": [secret]})
        assert deps == {"kubernetes@cloud": {"tailscale"}}
        planner = ExecutionPlanner(provider_dependencies=deps)
        assert planner.sort_providers(["kubernetes@cloud", "kubernetes", "tailscale"]) == [
            "kubernetes",
            "tailscale",
            "kubernetes@cloud",
        ]
