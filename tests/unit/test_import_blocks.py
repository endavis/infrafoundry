"""Tests for Terraform import block generation."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_mixins import _RESOURCE_DECL_RE, TerraformGeneratorMixin


class TestResourceConfigImportId:
    """Test that ResourceConfig accepts and defaults import_id."""

    def test_import_id_defaults_to_none(self) -> None:
        rc = ResourceConfig(name="test", type="vm", provider="proxmox", config={})
        assert rc.import_id is None

    def test_import_id_stores_value(self) -> None:
        rc = ResourceConfig(
            name="test", type="vm", provider="proxmox", config={}, import_id="abc-123"
        )
        assert rc.import_id == "abc-123"


class TestResourceDeclRegex:
    """Test the module-level _RESOURCE_DECL_RE pattern."""

    def test_matches_standard_resource_declaration(self) -> None:
        match = _RESOURCE_DECL_RE.match('resource "aws_instance" "my_server"')
        assert match is not None
        assert match.group(1) == "aws_instance"
        assert match.group(2) == "my_server"

    def test_matches_with_opening_brace(self) -> None:
        match = _RESOURCE_DECL_RE.match('resource "opnsense_dhcpv4_static_map" "server1" {')
        assert match is not None
        assert match.group(1) == "opnsense_dhcpv4_static_map"
        assert match.group(2) == "server1"

    def test_does_not_match_non_resource_lines(self) -> None:
        assert _RESOURCE_DECL_RE.match('variable "name" {') is None
        assert _RESOURCE_DECL_RE.match("# resource comment") is None
        assert _RESOURCE_DECL_RE.match("") is None


class _MixinHarness(TerraformGeneratorMixin):
    """Minimal harness to test TerraformGeneratorMixin methods in isolation."""

    def __init__(self) -> None:
        self.terraform_dir = Path("/tmp/tf")
        self.config_dir = Path("/tmp/cfg")
        self._written_files: dict[str, str] = {}

    def render_template(self, template_name: str, context: dict[str, Any]) -> str:
        raise NotImplementedError("must be mocked")

    def _write_terraform_file(self, filename: str, content: str) -> None:
        self._written_files[filename] = content


class TestGenerateImportBlocks:
    """Test _generate_import_blocks method."""

    def setup_method(self) -> None:
        self.mixin = _MixinHarness()

    def test_no_import_id_returns_empty(self) -> None:
        rc = ResourceConfig(name="srv", type="vm", provider="p", config={})
        rendered = 'resource "proxmox_vm" "srv" {\n}'
        result = self.mixin._generate_import_blocks(rendered, {"vms": [rc]})
        assert result == ""

    def test_single_resource_with_import_id(self) -> None:
        rc = ResourceConfig(
            name="server-1",
            type="dhcp_static_maps",
            provider="opnsense",
            config={},
            import_id="uuid-1234",
        )
        rendered = (
            'resource "opnsense_dhcpv4_static_map" "server_1" {\n  ip_address = "192.168.1.50"\n}'
        )
        result = self.mixin._generate_import_blocks(rendered, {"static_maps": [rc]})
        assert "import {" in result
        assert "to = opnsense_dhcpv4_static_map.server_1" in result
        assert 'id = "uuid-1234"' in result

    def test_hyphen_to_underscore_matching(self) -> None:
        rc = ResourceConfig(
            name="my-server",
            type="vm",
            provider="proxmox",
            config={},
            import_id="id-99",
        )
        rendered = 'resource "proxmox_vm" "my_server" {\n}'
        result = self.mixin._generate_import_blocks(rendered, {"vms": [rc]})
        assert "to = proxmox_vm.my_server" in result
        assert 'id = "id-99"' in result

    def test_multiple_resources_mixed(self) -> None:
        rc_with = ResourceConfig(
            name="a",
            type="t",
            provider="p",
            config={},
            import_id="id-a",
        )
        rc_without = ResourceConfig(name="b", type="t", provider="p", config={})
        rendered = 'resource "p_t" "a" {\n}\n\nresource "p_t" "b" {\n}'
        result = self.mixin._generate_import_blocks(rendered, {"items": [rc_with, rc_without]})
        assert "to = p_t.a" in result
        assert 'id = "id-a"' in result
        assert "b" not in result

    def test_empty_context(self) -> None:
        rendered = 'resource "aws_s3" "bucket" {\n}'
        result = self.mixin._generate_import_blocks(rendered, {})
        assert result == ""

    def test_non_list_context_values_ignored(self) -> None:
        rendered = 'resource "aws_s3" "bucket" {\n}'
        result = self.mixin._generate_import_blocks(rendered, {"scalar": "value", "num": 42})
        assert result == ""

    def test_import_blocks_appear_before_resource_blocks(self) -> None:
        rc = ResourceConfig(
            name="srv",
            type="vm",
            provider="p",
            config={},
            import_id="id-1",
        )
        rendered = 'resource "p_vm" "srv" {\n  name = "srv"\n}'
        result = self.mixin._generate_import_blocks(rendered, {"vms": [rc]})
        assert result.startswith("import {")


class TestRenderAndWriteTerraformWithImport:
    """Test that render_and_write_terraform integrates import blocks."""

    def setup_method(self) -> None:
        self.mixin = _MixinHarness()

    def test_import_blocks_prepended_to_output(self) -> None:
        rc = ResourceConfig(
            name="server-1",
            type="dhcp_static_maps",
            provider="opnsense",
            config={},
            import_id="uuid-abc",
        )
        rendered_tf = (
            'resource "opnsense_dhcpv4_static_map" "server_1" {\n  ip_address = "192.168.1.50"\n}'
        )
        context = {"static_maps": [rc]}

        with patch.object(self.mixin, "render_template", return_value=rendered_tf):
            self.mixin.render_and_write_terraform(
                "test.tf.j2", context=context, output_name="dhcp_static_maps.tf"
            )

        written = self.mixin._written_files["dhcp_static_maps.tf"]
        # Import block comes first
        assert written.startswith("import {")
        assert "to = opnsense_dhcpv4_static_map.server_1" in written
        assert 'id = "uuid-abc"' in written
        # Original resource block follows
        assert 'resource "opnsense_dhcpv4_static_map" "server_1"' in written

    def test_no_import_id_leaves_output_unchanged(self) -> None:
        rc = ResourceConfig(name="srv", type="vm", provider="p", config={})
        rendered_tf = 'resource "p_vm" "srv" {\n}'
        context = {"vms": [rc]}

        with patch.object(self.mixin, "render_template", return_value=rendered_tf):
            self.mixin.render_and_write_terraform(
                "test.tf.j2", context=context, output_name="vm.tf"
            )

        written = self.mixin._written_files["vm.tf"]
        assert written == rendered_tf


class TestLoaderImportId:
    """Test that config loaders pass import_id through to ResourceConfig."""

    def test_provider_centric_loader(self, tmp_path: Path) -> None:
        from infrafoundry.core.config.provider_centric_loader import ProviderCentricLoader

        env_dir = tmp_path / "prod" / "opnsense"
        env_dir.mkdir(parents=True)
        config_file = env_dir / "kea_subnet.yaml"
        config_file.write_text(
            "kea_subnet:\n"
            "  - name: subnet-mgmt\n"
            "    import_id: uuid-123\n"
            "    subnet: '10.0.0.0/24'\n"
        )
        loader = ProviderCentricLoader(tmp_path)
        resources = loader.load_resources("prod", "opnsense", "kea_subnet")
        assert len(resources) == 1
        assert resources[0].import_id == "uuid-123"

    def test_provider_centric_loader_no_import_id(self, tmp_path: Path) -> None:
        from infrafoundry.core.config.provider_centric_loader import ProviderCentricLoader

        env_dir = tmp_path / "prod" / "opnsense"
        env_dir.mkdir(parents=True)
        config_file = env_dir / "kea_subnet.yaml"
        config_file.write_text("kea_subnet:\n  - name: subnet-mgmt\n    subnet: '10.0.0.0/24'\n")
        loader = ProviderCentricLoader(tmp_path)
        resources = loader.load_resources("prod", "opnsense", "kea_subnet")
        assert len(resources) == 1
        assert resources[0].import_id is None

    def test_resource_centric_loader(self, tmp_path: Path) -> None:
        from infrafoundry.core.config.resource_centric_loader import ResourceCentricLoader

        env_dir = tmp_path / "prod" / "resources"
        env_dir.mkdir(parents=True)
        config_file = env_dir / "infra.yaml"
        config_file.write_text(
            "resources:\n"
            "  - provider: opnsense\n"
            "    type: kea_subnet\n"
            "    name: subnet-mgmt\n"
            "    import_id: uuid-456\n"
            "    config:\n"
            "      subnet: '10.0.0.0/24'\n"
        )
        loader = ResourceCentricLoader(tmp_path)
        resources = loader.load_resources("prod")
        assert len(resources) == 1
        assert resources[0].import_id == "uuid-456"
