"""Unit tests for EsxiProvider."""

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.esxi import EsxiProvider


@pytest.mark.unit
class TestEsxiProvider:
    """Tests for EsxiProvider."""

    def test_init(self, temp_dir):
        """Test EsxiProvider initialization."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        output_dir = temp_dir / "output"

        provider = EsxiProvider(
            config_dir=config_dir,
            output_dir=output_dir,
        )
        assert provider.name == "esxi"

    def test_get_resource_types(self, temp_dir):
        """Test getting supported resource types."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()

        provider = EsxiProvider(
            config_dir=config_dir,
            output_dir=temp_dir / "output",
        )
        types = provider.get_resource_types()
        assert "vswitch" in types
        assert "portgroup" in types
        assert "vm" in types

    def test_get_dependencies(self, temp_dir):
        """Test dependency resolution."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()

        provider = EsxiProvider(
            config_dir=config_dir,
            output_dir=temp_dir / "output",
        )
        deps = provider.get_dependencies()
        assert "vm" in deps
        assert "vswitch" in deps["vm"]
        assert "portgroup" in deps["vm"]
        assert "vswitch" in deps["portgroup"]
        assert deps["vswitch"] == []

    def test_validate_config_valid(self, temp_dir):
        """Test validate_config with valid config."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()

        provider = EsxiProvider(
            config_dir=config_dir,
            output_dir=temp_dir / "output",
        )
        assert provider.validate_config({"name": "test-vswitch"}) is True

    def test_validate_config_missing_name(self, temp_dir):
        """Test validate_config with missing name."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()

        provider = EsxiProvider(
            config_dir=config_dir,
            output_dir=temp_dir / "output",
        )
        assert provider.validate_config({"host": "esxi-01"}) is False

    def test_host_alias(self):
        """Test host name to Terraform alias conversion."""
        assert EsxiProvider._host_alias("esxi-ontap-01") == "esxi_ontap_01"
        assert EsxiProvider._host_alias("esxi.local") == "esxi_local"
        assert EsxiProvider._host_alias("simple") == "simple"
        assert EsxiProvider._host_alias("host-with.mixed-chars") == "host_with_mixed_chars"

    def test_collect_hosts(self, temp_dir):
        """Test host collection from resources."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()

        provider = EsxiProvider(
            config_dir=config_dir,
            output_dir=temp_dir / "output",
        )

        resources = [
            ResourceConfig(
                name="vSwitch1",
                type="vswitch",
                provider="esxi",
                config={"host": "esxi-01"},
            ),
            ResourceConfig(
                name="pg1",
                type="portgroup",
                provider="esxi",
                config={"host": "esxi-01", "vswitch": "vSwitch1"},
            ),
            ResourceConfig(
                name="vm1",
                type="vm",
                provider="esxi",
                config={"host": "esxi-02", "name": "vm1"},
            ),
        ]

        hosts = provider._collect_hosts(resources)
        assert len(hosts) == 2
        assert hosts[0]["name"] == "esxi-01"
        assert hosts[0]["alias"] == "esxi_01"
        assert hosts[1]["name"] == "esxi-02"
        assert hosts[1]["alias"] == "esxi_02"

    def test_normalize_vm_config_dict_to_list(self, temp_dir):
        """Test that single dict network is wrapped in a list."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()

        provider = EsxiProvider(
            config_dir=config_dir,
            output_dir=temp_dir / "output",
        )

        vm = ResourceConfig(
            name="test-vm",
            type="vm",
            provider="esxi",
            config={"host": "esxi-01", "name": "test-vm", "network": {"portgroup": "pg1"}},
        )
        result = provider._normalize_vm_config(vm)
        assert isinstance(result.config["network"], list)
        assert len(result.config["network"]) == 1

    def test_normalize_vm_config_list_unchanged(self, temp_dir):
        """Test that list network remains unchanged."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()

        provider = EsxiProvider(
            config_dir=config_dir,
            output_dir=temp_dir / "output",
        )

        nics = [{"portgroup": "pg1"}, {"portgroup": "pg2"}]
        vm = ResourceConfig(
            name="test-vm",
            type="vm",
            provider="esxi",
            config={"host": "esxi-01", "name": "test-vm", "network": nics},
        )
        result = provider._normalize_vm_config(vm)
        assert isinstance(result.config["network"], list)
        assert len(result.config["network"]) == 2

    def test_normalize_vm_config_no_network(self, temp_dir):
        """Test that no network key remains absent."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()

        provider = EsxiProvider(
            config_dir=config_dir,
            output_dir=temp_dir / "output",
        )

        vm = ResourceConfig(
            name="test-vm",
            type="vm",
            provider="esxi",
            config={"host": "esxi-01", "name": "test-vm"},
        )
        result = provider._normalize_vm_config(vm)
        assert "network" not in result.config

    def test_normalize_does_not_mutate_original(self, temp_dir):
        """Test that original VM config is not modified."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()

        provider = EsxiProvider(
            config_dir=config_dir,
            output_dir=temp_dir / "output",
        )

        vm = ResourceConfig(
            name="test-vm",
            type="vm",
            provider="esxi",
            config={"host": "esxi-01", "name": "test-vm", "network": {"portgroup": "pg1"}},
        )
        provider._normalize_vm_config(vm)
        assert isinstance(vm.config["network"], dict)
