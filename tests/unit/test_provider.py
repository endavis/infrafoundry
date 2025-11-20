"""Unit tests for ProviderBase."""

from pathlib import Path

import pytest

from infrafoundry.core.provider import ProviderBase, ResourceConfig


class TestProviderImplementation(ProviderBase):
    """Test implementation of ProviderBase for testing."""

    def __init__(self, name: str, config_dir: Path, output_dir: Path) -> None:
        """Initialize test provider."""
        super().__init__(name, config_dir, output_dir)

    def validate_config(self, config: dict) -> bool:
        """Validate configuration."""
        return True

    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform files."""
        pass

    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Generate Ansible files."""
        pass

    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return ["test_resource"]


@pytest.mark.unit
class TestProviderBase:
    """Tests for ProviderBase abstract class."""

    def test_init(self, temp_dir):
        """Test ProviderBase initialization."""
        config_dir = temp_dir / "config"
        output_dir = temp_dir / "output"
        provider = TestProviderImplementation("test", config_dir, output_dir)
        assert provider.name == "test"
        assert provider.terraform_dir == output_dir / "terraform" / "test"
        assert provider.ansible_dir == output_dir / "ansible" / "test"

    def test_ensure_directories(self, temp_dir):
        """Test ensure_directories creates output directories."""
        config_dir = temp_dir / "config"
        output_dir = temp_dir / "output"
        provider = TestProviderImplementation("test", config_dir, output_dir)
        provider.ensure_directories()

        assert provider.terraform_dir.exists()
        assert provider.ansible_dir.exists()

    def test_get_dependencies_default(self, temp_dir):
        """Test get_dependencies returns empty dict by default."""
        config_dir = temp_dir / "config"
        output_dir = temp_dir / "output"
        provider = TestProviderImplementation("test", config_dir, output_dir)
        deps = provider.get_dependencies()
        assert deps == {}

    def test_resource_config_creation(self):
        """Test ResourceConfig dataclass."""
        resource = ResourceConfig(
            provider="test",
            type="vm",
            name="test-vm",
            config={"cores": 4, "memory": 8192},
        )
        assert resource.provider == "test"
        assert resource.type == "vm"
        assert resource.name == "test-vm"
        assert resource.config["cores"] == 4
