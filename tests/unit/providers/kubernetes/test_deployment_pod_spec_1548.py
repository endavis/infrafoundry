"""Tests for deployment volumes, secret env and update strategy (#1548)."""

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.kubernetes import KubernetesProvider
from infrafoundry.providers.kubernetes.validator import KubernetesValidator
from tests.helpers.env import make_env_config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Never read a real kubeconfig."""
    monkeypatch.delenv("KUBECONFIG", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))


@pytest.fixture
def provider(tmp_path: Path) -> KubernetesProvider:
    """Create a KubernetesProvider for template testing."""
    (tmp_path / "config").mkdir()
    (tmp_path / "output").mkdir()
    p = KubernetesProvider(tmp_path / "config", tmp_path / "output")
    p.set_environment("test")
    return p


def _res(type_: str, rname: str, **config: Any) -> ResourceConfig:
    return ResourceConfig(provider="kubernetes", type=type_, name=rname, config=config)


def _render(provider: KubernetesProvider, refs: list[str] | None = None, **config: Any) -> str:
    config.setdefault("name", "app")
    config.setdefault("containers", [{"name": "app", "image": "alpine:3"}])
    return provider.render_template(
        "kubernetes/deployments.tf.j2",
        {"deployments": [_res("deployments", "app", **config)], "dependency_refs": refs or []},
    )


def _errors(*resources: ResourceConfig) -> list[str]:
    report = ValidationReport()
    env = make_env_config(name="t", provider_settings={"kubernetes": {}})
    KubernetesValidator(env, report)._validate_local_references(list(resources))
    return [r.message for r in report.results if not r.passed and r.level == ValidationLevel.ERROR]


class TestGolden:
    def test_existing_deployment_output_is_unchanged(self, provider: KubernetesProvider) -> None:
        full: dict[str, Any] = {
            "name": "web-app",
            "namespace": "apps",
            "replicas": 3,
            "labels": {"tier": "frontend", "team": "platform"},
            "depends_on": ["kubernetes_secret.extra"],
            "containers": [
                {
                    "name": "web",
                    "image": "nginx:1.27",
                    "ports": [
                        {"containerPort": 80, "name": "http", "protocol": "TCP"},
                        {"containerPort": 8443},
                    ],
                    "env": [
                        {"name": "MODE", "value": "prod"},
                        {"name": "LEVEL", "value": "info"},
                    ],
                    "resources": {
                        "limits": {"cpu": "500m", "memory": "256Mi"},
                        "requests": {"cpu": "100m", "memory": "128Mi"},
                    },
                },
                {"name": "sidecar", "image": "busybox:1.36"},
            ],
        }
        minimal: dict[str, Any] = {
            "name": "bare-app",
            "containers": [{"name": "app", "image": "alpine:3"}],
        }
        content = provider.render_template(
            "kubernetes/deployments.tf.j2",
            {
                "deployments": [
                    _res("deployments", "web-app", **full),
                    _res("deployments", "bare-app", **minimal),
                ],
                "dependency_refs": ["kubernetes_namespace.apps", "kubernetes_config_map.settings"],
            },
        )
        # The template ends each resource with a blank line; the end-of-file-fixer
        # pre-commit hook strips the trailing one from the stored golden file.
        golden = (FIXTURES / "deployment_existing_1548.tf").read_text()
        assert content == golden + "\n"


class TestRendering:
    def test_command_and_args(self, provider: KubernetesProvider) -> None:
        content = _render(
            provider,
            containers=[
                {"name": "a", "image": "x", "command": ["sh", "-c"], "args": ["run", "--now"]}
            ],
        )
        assert 'command = ["sh", "-c"]' in content
        assert 'args = ["run", "--now"]' in content

    def test_env_value_from_secret_and_config_map(self, provider: KubernetesProvider) -> None:
        content = _render(
            provider,
            containers=[
                {
                    "name": "a",
                    "image": "x",
                    "env": [
                        {
                            "name": "TOKEN",
                            "value_from": {"secret_key_ref": {"name": "creds", "key": "token"}},
                        },
                        {
                            "name": "MODE",
                            "value_from": {"config_map_key_ref": {"name": "cfg", "key": "mode"}},
                        },
                    ],
                }
            ],
        )
        assert "secret_key_ref {" in content
        assert 'name = "creds"' in content
        assert "config_map_key_ref {" in content
        assert 'key  = "mode"' in content
        assert "value =" not in content

    def test_volume_mounts(self, provider: KubernetesProvider) -> None:
        content = _render(
            provider,
            containers=[
                {
                    "name": "a",
                    "image": "x",
                    "volume_mounts": [
                        {"name": "data", "mount_path": "/data", "sub_path": "db", "read_only": True}
                    ],
                }
            ],
        )
        assert 'name       = "data"' in content
        assert 'mount_path = "/data"' in content
        assert 'sub_path = "db"' in content
        assert "read_only = true" in content

    def test_volume_kinds_sit_in_pod_spec(self, provider: KubernetesProvider) -> None:
        content = _render(
            provider,
            volumes=[
                {"name": "data", "persistent_volume_claim": {"claim_name": "data-pvc"}},
                {"name": "sec", "secret": {"secret_name": "creds"}},
                {"name": "plain", "config_map": {"name": "cfg"}},
                {
                    "name": "items",
                    "config_map": {"name": "cfg", "items": [{"key": "k", "path": "p"}]},
                },
                {"name": "tmp", "empty_dir": {}},
            ],
        )
        assert 'claim_name = "data-pvc"' in content
        assert 'secret_name = "creds"' in content
        assert content.count("config_map {") == 2
        assert content.count("items {") == 1
        assert "empty_dir {}" in content
        assert content.index("volume {") > content.index("container {")
        # volumes follow the container block closing
        assert content.index("volume {") > content.index('image = "alpine:3"')

    def test_strategy_rendered_only_when_set(self, provider: KubernetesProvider) -> None:
        assert 'type = "Recreate"' in _render(provider, strategy={"type": "Recreate"})
        assert "strategy" not in _render(provider)


class TestDependencyEdge:
    def test_pvc_ref_in_deployments_depends_on(
        self, provider: KubernetesProvider, tmp_path: Path
    ) -> None:
        pvc = _res("persistentvolumeclaims", "data", name="data")
        dep = _res("deployments", "app", name="app", containers=[{"name": "a", "image": "x"}])
        refs = provider._build_dependency_refs(
            {"persistentvolumeclaims": [pvc], "deployments": [dep]}
        )
        assert any(r.startswith("kubernetes_persistent_volume_claim.") for r in refs["deployments"])
        provider.generate_terraform([pvc, dep])
        content = (provider.output_dir / "terraform" / "kubernetes" / "deployments.tf").read_text()
        assert "depends_on" in content
        assert "kubernetes_persistent_volume_claim." in content


class TestValidation:
    def _dep(self, **config: Any) -> ResourceConfig:
        config.setdefault("name", "app")
        return _res("deployments", "app", **config)

    def test_valid_config_passes(self) -> None:
        dep = self._dep(
            strategy={"type": "Recreate"},
            volumes=[{"name": "data", "empty_dir": {}}],
            containers=[
                {
                    "name": "a",
                    "image": "x",
                    "volume_mounts": [{"name": "data", "mount_path": "/d"}],
                    "env": [
                        {"name": "A", "value": "1"},
                        {"name": "B", "value_from": {"secret_key_ref": {"name": "s", "key": "k"}}},
                    ],
                }
            ],
        )
        assert _errors(dep) == []

    def test_undeclared_mount_is_error(self) -> None:
        dep = self._dep(
            containers=[
                {"name": "a", "image": "x", "volume_mounts": [{"name": "nope", "mount_path": "/"}]}
            ]
        )
        errors = _errors(dep)
        assert len(errors) == 1
        assert "nope" in errors[0]

    def test_env_both_or_neither_is_error(self) -> None:
        dep = self._dep(
            containers=[
                {
                    "name": "a",
                    "image": "x",
                    "env": [
                        {"name": "BOTH", "value": "1", "value_from": {}},
                        {"name": "NONE"},
                    ],
                }
            ]
        )
        assert len(_errors(dep)) == 2

    def test_invalid_strategy_is_error(self) -> None:
        assert len(_errors(self._dep(strategy={"type": "Blue"}))) == 1

    def test_malformed_shapes_do_not_raise(self) -> None:
        dep = self._dep(volumes="x", strategy=None, containers=["bad", {"volume_mounts": 3}])
        assert _errors(dep) == []
        dep2 = self._dep(containers=[{"name": "a", "env": ["x"], "volume_mounts": ["y"]}])
        assert _errors(dep2) == []
        assert len(_errors(self._dep(strategy="Recreate"))) == 1

    def test_jobs_are_not_checked(self) -> None:
        job = _res(
            "jobs",
            "j",
            name="j",
            containers=[{"name": "a", "image": "x", "volume_mounts": [{"name": "z"}]}],
        )
        assert _errors(job) == []
