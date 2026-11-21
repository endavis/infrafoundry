"""Proxmox node ssh connections check host keys against the operator's known_hosts (#1588)."""

from pathlib import Path

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.proxmox import ProxmoxProvider


def test_generated_ssh_command_is_strict(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    provider = ProxmoxProvider(config_dir, output_dir)
    provider.set_environment("test")
    vm = ResourceConfig(
        name="vm-01",
        type="vm",
        provider="proxmox",
        config={"name": "vm-01", "target_node": "node1", "vmid": 200},
    )

    provider.generate_terraform([vm])

    variables = (output_dir / "test" / "terraform" / "proxmox" / "variables.tf").read_text()
    assert "-o StrictHostKeyChecking=yes" in variables
    assert "UserKnownHostsFile" not in variables
