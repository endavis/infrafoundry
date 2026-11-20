"""An explicit ``config.name`` survives the resource-centric loader (#1544)."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrafoundry.core.config.resource_centric_loader import ResourceCentricLoader
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.kubernetes import KubernetesProvider

_YAML = """\
resources:
  - provider: kubernetes
    type: deployments
    name: web
    config:
      name: web
      containers:
        - name: web
          image: nginx:1.27
  - provider: kubernetes
    type: services
    name: web-svc
    config:
      name: web
      ports:
        - port: 80
  - provider: kubernetes
    type: configmaps
    name: settings
    config:
      data:
        key: value
"""


def _load(tmp_path: Path) -> dict[str, ResourceConfig]:
    path = tmp_path / "dev" / "resources"
    path.mkdir(parents=True)
    (path / "k8s.yaml").write_text(_YAML)
    return {r.name: r for r in ResourceCentricLoader(tmp_path).load_resources("dev")}


@pytest.mark.unit
class TestConfigNameKept:
    """Top-level ``name`` only fills ``config.name`` when it is unset."""

    def test_explicit_config_name_wins(self, tmp_path: Path) -> None:
        loaded = _load(tmp_path)
        assert loaded["web"].config["name"] == "web"
        assert loaded["web-svc"].name == "web-svc"
        assert loaded["web-svc"].config["name"] == "web"

    def test_missing_config_name_uses_top_level_name(self, tmp_path: Path) -> None:
        assert _load(tmp_path)["settings"].config["name"] == "settings"

    def test_service_and_deployment_share_one_object_name(self, tmp_path: Path) -> None:
        loaded = _load(tmp_path)
        (tmp_path / "config").mkdir()
        (tmp_path / "output").mkdir()
        prov = KubernetesProvider(tmp_path / "config", tmp_path / "output")
        prov.set_environment("dev")
        prov.generate_terraform([loaded["web"], loaded["web-svc"]])
        text = "\n".join(p.read_text() for p in prov.terraform_dir.glob("*.tf"))
        assert 'resource "kubernetes_service" "web"' in text
        assert 'resource "kubernetes_deployment" "web"' in text
        assert "web-svc" not in text
        assert 'app = "web"' in text
