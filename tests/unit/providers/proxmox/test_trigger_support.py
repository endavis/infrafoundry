"""Unit tests for Proxmox trigger resource type.

Tests template rendering for terraform_data trigger resources used
to fire lifecycle events in packages without real infrastructure.
"""

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.proxmox import ProxmoxProvider


@pytest.fixture
def provider(tmp_path):
    """Create a ProxmoxProvider for template testing."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    p = ProxmoxProvider(config_dir, output_dir)
    p.set_environment("test")
    return p


def _make_trigger(name: str = "test-trigger", **config_overrides) -> ResourceConfig:
    """Helper to create a trigger ResourceConfig."""
    config: dict = {**config_overrides}
    return ResourceConfig(name=name, type="trigger", provider="proxmox", config=config)


def _render_triggers(provider: ProxmoxProvider, triggers: list[ResourceConfig]) -> str:
    """Render trigger resources through the template."""
    return provider.render_template("proxmox/triggers.tf.j2", {"triggers": triggers})


class TestTriggerRendering:
    """Tests for trigger resource template rendering."""

    def test_trigger_basic(self, provider):
        """Basic trigger should render a terraform_data resource."""
        triggers = [_make_trigger()]
        content = _render_triggers(provider, triggers)
        assert 'resource "terraform_data" "test_trigger"' in content

    def test_trigger_with_inputs(self, provider):
        """Trigger with inputs should render input block."""
        triggers = [_make_trigger(inputs={"deployment": "minio", "version": "1.0"})]
        content = _render_triggers(provider, triggers)
        assert 'resource "terraform_data" "test_trigger"' in content
        assert "input = {" in content
        assert 'deployment = "minio"' in content
        assert 'version = "1.0"' in content

    def test_trigger_without_inputs(self, provider):
        """Trigger without inputs should not render input block."""
        triggers = [_make_trigger()]
        content = _render_triggers(provider, triggers)
        assert "input" not in content

    def test_trigger_name_with_hyphens(self, provider):
        """Hyphens in trigger name should be converted to underscores."""
        triggers = [_make_trigger(name="minio-deploy-trigger")]
        content = _render_triggers(provider, triggers)
        assert 'resource "terraform_data" "minio_deploy_trigger"' in content

    def test_multiple_triggers(self, provider):
        """Multiple triggers should render multiple terraform_data resources."""
        triggers = [
            _make_trigger(name="trigger-1", inputs={"app": "minio"}),
            _make_trigger(name="trigger-2", inputs={"app": "redis"}),
        ]
        content = _render_triggers(provider, triggers)
        assert 'resource "terraform_data" "trigger_1"' in content
        assert 'resource "terraform_data" "trigger_2"' in content
        assert 'app = "minio"' in content
        assert 'app = "redis"' in content


class TestTriggerProviderIntegration:
    """Tests for trigger type registration in the Proxmox provider."""

    def test_trigger_in_resource_types(self, provider):
        """Trigger should be a supported resource type."""
        assert "trigger" in provider.get_resource_types()

    def test_trigger_terraform_type(self, provider):
        """Trigger should map to terraform_data."""
        tf_types = provider.get_terraform_resource_types()
        assert "trigger" in tf_types
        assert "terraform_data" in tf_types["trigger"]

    def test_trigger_has_no_dependencies(self, provider):
        """Trigger should have no dependencies."""
        deps = provider.get_dependencies()
        assert "trigger" in deps
        assert deps["trigger"] == []
