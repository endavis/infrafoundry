"""Tests for pyinfra generation in ProxmoxProvider."""

from pathlib import Path

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.proxmox import ProxmoxProvider


@pytest.fixture
def provider(tmp_path: Path) -> ProxmoxProvider:
    """Create a ProxmoxProvider instance."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    return ProxmoxProvider(config_dir, output_dir)


def test_generate_pyinfra(provider: ProxmoxProvider) -> None:
    """Test generating pyinfra files."""
    provider.set_environment("dev")

    resources = [
        ResourceConfig(
            name="web01",
            type="vm",
            provider="proxmox",
            config={
                "name": "web01",
                "ssh_user": "admin",
                "ipconfig": "ip=192.168.1.10/24,gw=192.168.1.1",
                "pyinfra_ops": [
                    {
                        "name": "Install nginx",
                        "operation": "apt.packages",
                        "params": {"packages": ["nginx"]},
                    },
                    {
                        "name": "Start service",
                        "operation": "systemd.service",
                        "params": {"service": "nginx", "running": True},
                    },
                ],
            },
        )
    ]

    provider.generate_pyinfra(resources)

    pyinfra_dir = provider.pyinfra_dir
    assert pyinfra_dir.exists()
    assert (pyinfra_dir / "inventory.py").exists()
    assert (pyinfra_dir / "deploy.py").exists()

    inventory_content = (pyinfra_dir / "inventory.py").read_text()
    # snake_case conversion check
    assert "web01" in inventory_content
    assert "192.168.1.10" in inventory_content
    assert "admin" in inventory_content

    deploy_content = (pyinfra_dir / "deploy.py").read_text()
    assert "apt.packages" in deploy_content
    assert "Install nginx" in deploy_content
    assert "systemd.service" in deploy_content
    assert "Start service" in deploy_content
