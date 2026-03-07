"""Unit tests for OPNsense Unbound DNS host override template generation."""

from pathlib import Path

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense import OPNsenseProvider


class TestUnboundHostOverrideTemplates:
    """Test Unbound DNS host override Terraform template generation."""

    @pytest.fixture
    def provider(self, tmp_path: Path) -> OPNsenseProvider:
        """Create OPNsense provider instance."""
        config_dir = tmp_path / "config"
        output_dir = tmp_path / "output"
        return OPNsenseProvider(config_dir, output_dir)

    @pytest.fixture
    def basic_override(self) -> ResourceConfig:
        """Create a basic host override resource."""
        return ResourceConfig(
            provider="opnsense",
            type="unbound_host_override",
            name="web-server",
            config={
                "hostname": "web",
                "domain": "example.com",
                "server": "192.168.1.10",
            },
        )

    @pytest.fixture
    def override_with_description(self) -> ResourceConfig:
        """Create a host override resource with description."""
        return ResourceConfig(
            provider="opnsense",
            type="unbound_host_override",
            name="mail-server",
            config={
                "hostname": "mail",
                "domain": "example.com",
                "server": "192.168.1.20",
                "description": "Mail server override",
            },
        )

    def test_generate_basic_host_override(
        self, provider: OPNsenseProvider, basic_override: ResourceConfig
    ) -> None:
        """Test basic host override Terraform generation."""
        provider.generate_terraform([basic_override])

        override_tf = provider.terraform_dir / "unbound_host_override.tf"
        assert override_tf.exists()

        content = override_tf.read_text()
        assert 'resource "opnsense_unbound_host_override"' in content
        assert "web_server" in content  # name normalized
        assert 'hostname = "web"' in content
        assert 'domain   = "example.com"' in content
        assert 'server = "192.168.1.10"' in content

    def test_generate_override_with_description(
        self, provider: OPNsenseProvider, override_with_description: ResourceConfig
    ) -> None:
        """Test host override with description renders correctly."""
        provider.generate_terraform([override_with_description])

        content = (provider.terraform_dir / "unbound_host_override.tf").read_text()
        assert 'description = "Mail server override"' in content

    def test_generate_override_without_optional_fields(self, provider: OPNsenseProvider) -> None:
        """Test host override without optional fields omits them."""
        override = ResourceConfig(
            provider="opnsense",
            type="unbound_host_override",
            name="minimal",
            config={
                "hostname": "app",
                "domain": "internal.local",
            },
        )

        provider.generate_terraform([override])

        content = (provider.terraform_dir / "unbound_host_override.tf").read_text()
        assert 'hostname = "app"' in content
        assert 'domain   = "internal.local"' in content
        assert "server" not in content
        assert "description" not in content

    def test_generate_multiple_overrides(self, provider: OPNsenseProvider) -> None:
        """Test generating multiple host overrides."""
        overrides = [
            ResourceConfig(
                provider="opnsense",
                type="unbound_host_override",
                name=f"host-{i}",
                config={
                    "hostname": f"host{i}",
                    "domain": "example.com",
                    "server": f"192.168.1.{10 + i}",
                },
            )
            for i in range(3)
        ]

        provider.generate_terraform(overrides)

        content = (provider.terraform_dir / "unbound_host_override.tf").read_text()
        assert "host_0" in content
        assert "host_1" in content
        assert "host_2" in content

    def test_name_normalization(self, provider: OPNsenseProvider) -> None:
        """Test that resource names with dashes are converted to underscores."""
        override = ResourceConfig(
            provider="opnsense",
            type="unbound_host_override",
            name="my-web-server",
            config={
                "hostname": "web",
                "domain": "example.com",
            },
        )

        provider.generate_terraform([override])

        content = (provider.terraform_dir / "unbound_host_override.tf").read_text()
        assert "my_web_server" in content
        assert (
            "my-web-server"
            not in content.split('"opnsense_unbound_host_override"')[1].split('"')[1]
        )

    def test_outputs_include_overrides(
        self, provider: OPNsenseProvider, basic_override: ResourceConfig
    ) -> None:
        """Test that outputs.tf includes unbound host overrides."""
        provider.generate_terraform([basic_override])

        outputs_tf = provider.terraform_dir / "outputs.tf"
        assert outputs_tf.exists()

        content = outputs_tf.read_text()
        assert "unbound_host_overrides" in content
        assert "web.example.com" in content


class TestUnboundHostOverrideProvider:
    """Test OPNsense provider integration for unbound_host_override."""

    def test_resource_type_registered(self) -> None:
        """Test that unbound_host_override is in get_resource_types."""
        provider = OPNsenseProvider(config_dir=Path("."), output_dir=Path("."))
        assert "unbound_host_override" in provider.get_resource_types()

    def test_dependencies_registered(self) -> None:
        """Test that unbound_host_override has no dependencies."""
        provider = OPNsenseProvider(config_dir=Path("."), output_dir=Path("."))
        deps = provider.get_dependencies()
        assert "unbound_host_override" in deps
        assert deps["unbound_host_override"] == []
