"""Regression tests for templates reading dict keys that shadow dict methods (#1559)."""

from pathlib import Path

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.kubernetes import KubernetesProvider


@pytest.fixture
def provider(tmp_path: Path) -> KubernetesProvider:
    """Create a KubernetesProvider for template testing."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    p = KubernetesProvider(config_dir, output_dir)
    p.set_environment("test")
    return p


def _render_job(provider: KubernetesProvider, config_map: dict[str, object]) -> str:
    jobs = [
        ResourceConfig(
            name="migrate",
            type="jobs",
            provider="kubernetes",
            config={
                "containers": [{"name": "app", "image": "registry.example.com/app:1"}],
                "volumes": [{"name": "settings", "config_map": config_map}],
            },
        )
    ]
    return provider.render_template("kubernetes/jobs.tf.j2", {"jobs": jobs, "dependency_refs": []})


def _render_pvc(provider: KubernetesProvider, expressions: list[dict[str, object]]) -> str:
    pvcs = [
        ResourceConfig(
            name="data",
            type="persistentvolumeclaims",
            provider="kubernetes",
            config={
                "storage": "5Gi",
                "access_modes": ["ReadWriteOnce"],
                "selector": {"match_expressions": expressions},
            },
        )
    ]
    return provider.render_template("kubernetes/pvc.tf.j2", {"pvcs": pvcs, "dependency_refs": []})


class TestJobConfigMapItems:
    """jobs.tf.j2 config_map volume with and without items."""

    def test_without_items(self, provider: KubernetesProvider) -> None:
        """A config_map volume without items renders no items block."""
        content = _render_job(provider, {"name": "settings"})
        assert "config_map {" in content
        assert 'name = "settings"' in content
        assert "items {" not in content

    def test_with_items(self, provider: KubernetesProvider) -> None:
        """A config_map volume with items renders each key/path pair."""
        content = _render_job(
            provider,
            {"name": "settings", "items": [{"key": "app.conf", "path": "conf/app.conf"}]},
        )
        assert "items {" in content
        assert 'key  = "app.conf"' in content
        assert 'path = "conf/app.conf"' in content


class TestPVCMatchExpressionValues:
    """pvc.tf.j2 selector match_expressions with and without values."""

    def test_with_values(self, provider: KubernetesProvider) -> None:
        """An expression with values renders the values list."""
        content = _render_pvc(
            provider,
            [{"key": "tier", "operator": "In", "values": ["fast", "slow"]}],
        )
        assert "match_expressions {" in content
        assert 'values   = ["fast", "slow"]' in content

    def test_without_values(self, provider: KubernetesProvider) -> None:
        """An operator taking no values renders no values line."""
        content = _render_pvc(provider, [{"key": "tier", "operator": "Exists"}])
        assert 'operator = "Exists"' in content
        assert "values" not in content
