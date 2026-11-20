"""A two-cluster plan generates files for both clusters end to end (#1539)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import yaml

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.runners.terraform_runner import TerraformRunner
from infrafoundry.core.secrets import SecretManager
from infrafoundry.providers.kubernetes import KubernetesProvider

TWO_CLUSTERS: dict[str, Any] = {
    "name": "dev",
    "providers": ["kubernetes"],
    "provider_settings": {
        "kubernetes": {
            "primary": "edge",
            "clusters": {
                "edge": {"kubeconfig_path": "/k/edge.yaml"},
                "cloud": {"kubeconfig_path": "/k/cloud.yaml", "context": "cloud-admin"},
            },
        }
    },
}
FLAT: dict[str, Any] = {
    "name": "dev",
    "providers": ["kubernetes"],
    "provider_settings": {"kubernetes": {"kubeconfig_path": "/k/flat.yaml"}},
}


def _plan(tmp_path: Path, settings: dict[str, Any], files: dict[str, str]) -> tuple[Path, Mock]:
    envs = tmp_path / "envs"
    env = envs / "dev"
    (env / "kubernetes").mkdir(parents=True)
    (env / "settings.yaml").write_text(yaml.safe_dump(settings))
    for name, content in files.items():
        (env / "kubernetes" / name).write_text(content)
    output = tmp_path / "generated"
    orchestrator = Orchestrator(config_manager=ConfigManager(envs), output_dir=output)
    secrets = Mock(spec=SecretManager)
    secrets.decrypt_file = Mock(return_value={})
    secrets.get_secret = Mock(return_value=None)
    orchestrator.plan_orchestrator._secret_manager_factory = Mock(return_value=secrets)
    orchestrator.register_provider(KubernetesProvider(config_dir=envs, output_dir=output))
    with patch.object(TerraformRunner, "plan", return_value={"success": True}) as tf_plan:
        orchestrator.plan("dev")
    return output / "dev" / "terraform", tf_plan


def test_plan_generates_terraform_for_every_cluster(tmp_path: Path) -> None:
    terraform, tf_plan = _plan(
        tmp_path,
        TWO_CLUSTERS,
        {
            "namespaces-edge.yaml": "namespaces:\n  - {name: app-edge}\n",
            "namespaces-cloud.yaml": "cluster: cloud\nnamespaces:\n  - {name: app-cloud}\n",
        },
    )
    assert (terraform / "kubernetes" / "provider.tf").exists()
    assert (terraform / "kubernetes@cloud" / "provider.tf").exists()
    assert "app-cloud" in (terraform / "kubernetes@cloud" / "namespaces.tf").read_text()
    assert "app-edge" in (terraform / "kubernetes" / "namespaces.tf").read_text()
    planned = {call.args[0].terraform_dir for call in tf_plan.call_args_list}
    assert planned == {terraform / "kubernetes", terraform / "kubernetes@cloud"}
    assert tf_plan.call_count == 2


def test_flat_configuration_generates_only_the_plain_directory(tmp_path: Path) -> None:
    terraform, tf_plan = _plan(
        tmp_path, FLAT, {"namespaces.yaml": "namespaces:\n  - {name: app}\n"}
    )
    assert sorted(p.name for p in terraform.iterdir()) == ["kubernetes"]
    assert tf_plan.call_count == 1
