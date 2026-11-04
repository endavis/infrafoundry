"""Unit tests for ProviderBase."""

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.provider import ProviderBase, ResourceConfig


class StubProviderImplementation(ProviderBase):
    """Test implementation of ProviderBase for testing."""

    def __init__(self, name: str, config_dir: Path, output_dir: Path) -> None:
        """Initialize test provider."""
        super().__init__(name, config_dir, output_dir)

    def validate_config(self, config: dict[str, Any]) -> bool:
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

    def get_terraform_resource_types(self) -> dict[str, list[str]]:
        """Map InfraFoundry resource types to terraform resource types."""
        return {"test_resource": ["test_terraform_resource"]}


@pytest.mark.unit
class TestProviderBase:
    """Tests for ProviderBase abstract class."""

    def test_init(self, temp_dir: Path) -> None:
        """Test ProviderBase initialization."""
        config_dir = temp_dir / "config"
        output_dir = temp_dir / "output"
        provider = StubProviderImplementation("test", config_dir, output_dir)
        assert provider.name == "test"
        assert provider.terraform_dir == output_dir / "terraform" / "test"
        assert provider.ansible_dir == output_dir / "ansible" / "test"

    def test_ensure_directories(self, temp_dir: Path) -> None:
        """Test ensure_directories creates output directories."""
        config_dir = temp_dir / "config"
        output_dir = temp_dir / "output"
        provider = StubProviderImplementation("test", config_dir, output_dir)
        provider.ensure_directories()

        assert provider.terraform_dir.exists()
        assert provider.ansible_dir.exists()

    def test_get_dependencies_default(self, temp_dir: Path) -> None:
        """Test get_dependencies returns empty dict by default."""
        config_dir = temp_dir / "config"
        output_dir = temp_dir / "output"
        provider = StubProviderImplementation("test", config_dir, output_dir)
        deps = provider.get_dependencies()
        assert deps == {}

    def test_terraform_parallelism_defaults_to_none(self, temp_dir: Path) -> None:
        """Test terraform_parallelism defaults to None (terraform default of 10)."""
        provider = StubProviderImplementation("test", temp_dir / "cfg", temp_dir / "out")
        assert provider.terraform_parallelism is None

    def test_resource_config_creation(self) -> None:
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


class TestUnsupportedResourceReason:
    """Optional get_unsupported_resource_types hook and its guarded lookup (#1149)."""

    def test_base_default_is_empty(self, tmp_path: Path) -> None:
        provider = StubProviderImplementation("stub", tmp_path, tmp_path)

        assert provider.get_unsupported_resource_types() == {}

    def test_none_for_plain_object_and_mock_spec(self, tmp_path: Path) -> None:
        from unittest.mock import Mock

        from infrafoundry.core.provider import unsupported_resource_reason

        assert unsupported_resource_reason(object(), "x") is None
        assert unsupported_resource_reason(Mock(spec=ProviderBase), "x") is None

    def test_none_for_absent_type_and_reason_for_present(self) -> None:
        from infrafoundry.core.provider import unsupported_resource_reason

        class _P:
            def get_unsupported_resource_types(self) -> dict[str, str]:
                return {"a": "because"}

        assert unsupported_resource_reason(_P(), "b") is None
        assert unsupported_resource_reason(_P(), "a") == "because"

    def test_message_names_resource_type_provider_and_reason(self) -> None:
        from infrafoundry.core.provider import unsupported_resource_message

        message = unsupported_resource_message("opn", "res", "t.y", "why")

        assert (
            message == "Resource 'res' has type 't.y', which provider 'opn' does not support: why"
        )
