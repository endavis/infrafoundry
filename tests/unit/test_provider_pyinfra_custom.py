"""Tests for pyinfra custom function support."""

from pathlib import Path

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.proxmox import ProxmoxProvider


@pytest.fixture
def provider(tmp_path: Path) -> ProxmoxProvider:
    """Create a ProxmoxProvider instance."""
    # Mock structure:
    # /config_repo/
    #   envs/
    #     dev/
    #   pyinfra/
    #     my_module.py

    config_root = tmp_path / "config_repo"
    config_root.mkdir()

    envs_dir = config_root / "envs"
    envs_dir.mkdir()

    dev_env_dir = envs_dir / "dev"
    dev_env_dir.mkdir()

    # Create custom pyinfra module
    pyinfra_dir = config_root / "pyinfra"
    pyinfra_dir.mkdir()
    (pyinfra_dir / "my_module.py").write_text("""
from pyinfra.api import deploy

@deploy("My Custom Deploy")
def my_deploy():
    pass
""")

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Provider is initialized with config_dir pointing to envs/dev usually?
    # Or envs/?
    # In CLI main.py: config_manager = ConfigManager(base_dir=config_repo / "envs")
    # And provider config_dir = config_manager.base_dir (which is envs/)

    return ProxmoxProvider(envs_dir, output_dir)


def test_generate_pyinfra_with_custom_funcs(provider: ProxmoxProvider) -> None:
    """Test generating pyinfra with custom function references."""
    provider.set_environment("dev")

    resources = [
        ResourceConfig(
            name="web01",
            type="vm",
            provider="proxmox",
            config={"name": "web01", "pyinfra_deploy_funcs": ["my_module.my_deploy"]},
        )
    ]

    provider.generate_pyinfra(resources)

    pyinfra_dir = provider.pyinfra_dir

    # Check if module was copied
    assert (pyinfra_dir / "my_module.py").exists()
    assert "My Custom Deploy" in (pyinfra_dir / "my_module.py").read_text()

    # Check deploy.py content
    deploy_content = (pyinfra_dir / "deploy.py").read_text()
    assert "from my_module import my_deploy" in deploy_content
    assert "my_deploy()" in deploy_content
