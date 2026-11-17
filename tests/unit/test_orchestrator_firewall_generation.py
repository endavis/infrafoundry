"""A two-firewall plan generates files for both firewalls end to end (#1462)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.runners.opnsense_direct_runner import OPNsenseDirectRunner
from infrafoundry.core.runners.terraform_runner import TerraformRunner
from infrafoundry.core.secrets import SecretManager
from infrafoundry.providers.opnsense import OPNsenseProvider

SETTINGS = {
    "name": "dev",
    "providers": ["opnsense"],
    "provider_settings": {
        "opnsense": {
            "primary": "fw-a",
            "firewalls": {
                "fw-a": {"api_url": "https://fw-a.example.com", "api_key": "k", "api_secret": "s"},
                "fw-b": {"api_url": "https://fw-b.example.com", "api_key": "k", "api_secret": "s"},
            },
        }
    },
}


def _gateways(firewall: str, address: str) -> dict[str, object]:
    return {
        "firewall": firewall,
        "opnsense": {
            "routing": {
                "gateways": [
                    {
                        "name": f"gw-{firewall}",
                        "config": {"interface": "wan", "gateway": address},
                    }
                ]
            }
        },
    }


def test_plan_generates_terraform_for_every_firewall(tmp_path: Path) -> None:
    envs = tmp_path / "envs"
    env = envs / "dev"
    (env / "opnsense").mkdir(parents=True)
    (env / "settings.yaml").write_text(yaml.safe_dump(SETTINGS))
    (env / "opnsense" / "gw-a.yaml").write_text(yaml.safe_dump(_gateways("fw-a", "192.0.2.1")))
    (env / "opnsense" / "gw-b.yaml").write_text(yaml.safe_dump(_gateways("fw-b", "198.51.100.1")))

    output = tmp_path / "generated"
    orchestrator = Orchestrator(config_manager=ConfigManager(envs), output_dir=output)
    secrets = Mock(spec=SecretManager)
    secrets.decrypt_file = Mock(return_value={})
    secrets.get_secret = Mock(return_value=None)
    orchestrator.plan_orchestrator._secret_manager_factory = Mock(return_value=secrets)
    orchestrator.register_provider(OPNsenseProvider(config_dir=envs, output_dir=output))

    with (
        patch.object(TerraformRunner, "plan", return_value={"success": True}) as tf_plan,
        patch.object(OPNsenseDirectRunner, "plan", return_value={"success": True}),
        patch.object(OPNsenseProvider, "check_endpoint_support", return_value=None),
    ):
        orchestrator.plan("dev")

    terraform = output / "dev" / "terraform"
    assert (terraform / "opnsense" / "provider.tf").exists()
    assert (terraform / "opnsense@fw-b" / "provider.tf").exists()
    planned = {call.args[0].terraform_dir for call in tf_plan.call_args_list}
    assert planned == {terraform / "opnsense", terraform / "opnsense@fw-b"}
    assert tf_plan.call_count == 2
