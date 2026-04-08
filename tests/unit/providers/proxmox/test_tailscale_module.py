"""Tests for the Proxmox provider's Tailscale cloud-init module integration.

Phase 2 of issue #212. Verifies that VMs with a ``tailscale:`` block produce
a ``module "tailscale_<name>"`` block in the generated terraform, that the
``proxmox_virtual_environment_file.cloud_init_user_data_<vm>`` resource
sources its ``data`` from the module's ``rendered`` output (with
``base64_encode = false``), and that the existing ``cloud_init_snippets``
path is unchanged for VMs without a tailscale block.
"""

from __future__ import annotations

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.proxmox import ProxmoxProvider


@pytest.fixture
def tmp_dirs(tmp_path):
    """Create temporary config and output directories."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return config_dir, output_dir


@pytest.fixture
def provider(tmp_dirs):
    """ProxmoxProvider with the test environment set."""
    config_dir, output_dir = tmp_dirs
    p = ProxmoxProvider(config_dir, output_dir)
    p.set_environment("test")
    return p


def _vm(name: str, *, tailscale: dict | None = None, **extra_config) -> ResourceConfig:
    """Build a minimal Proxmox VM ResourceConfig with optional tailscale block."""
    config = {
        "name": name,
        "target_node": "pve1",
        "vmid": 200,
        "ssh_user": "ubuntu",
        **extra_config,
    }
    if tailscale is not None:
        config["tailscale"] = tailscale
    return ResourceConfig(name=name, type="vm", provider="proxmox", config=config)


def _read_tf(output_dir, filename: str) -> str:
    return (output_dir / "test" / "terraform" / "proxmox" / filename).read_text()


class TestProxmoxTailscaleAuthKey:
    """Cover the static auth_key auth mode."""

    def test_module_block_emitted(self, provider, tmp_dirs):
        _, output_dir = tmp_dirs
        vm = _vm(
            "ts-control",
            tailscale={
                "enable_ssh": True,
                "advertise_tags": ["tag:k3s"],
                "auth": {"auth_key_secret": "tailscale.auth_key"},
            },
        )
        provider.generate_terraform([vm])
        vms_tf = _read_tf(output_dir, "vms.tf")

        assert 'module "tailscale_ts_control"' in vms_tf
        assert 'source  = "tailscale/cloudinit/tailscale"' in vms_tf
        assert 'version = "0.0.11"' in vms_tf
        assert "auth_key = var.tailscale_auth_key" in vms_tf

    def test_base64_encode_is_false(self, provider, tmp_dirs):
        _, output_dir = tmp_dirs
        vm = _vm(
            "ts-control",
            tailscale={"auth": {"auth_key_secret": "tailscale.auth_key"}},
        )
        provider.generate_terraform([vm])
        vms_tf = _read_tf(output_dir, "vms.tf")

        # Proxmox stores the file raw via source_raw; the module must NOT
        # base64-encode its output or Proxmox would store gibberish.
        assert "base64_encode = false" in vms_tf

    def test_file_resource_uses_module_rendered(self, provider, tmp_dirs):
        _, output_dir = tmp_dirs
        vm = _vm(
            "ts-control",
            tailscale={"auth": {"auth_key_secret": "tailscale.auth_key"}},
        )
        provider.generate_terraform([vm])
        vms_tf = _read_tf(output_dir, "vms.tf")

        # The file resource sources its data from the module
        assert "data      = module.tailscale_ts_control.rendered" in vms_tf
        # The VM still references the file resource via user_data_file_id
        assert (
            "user_data_file_id = proxmox_virtual_environment_file."
            "cloud_init_user_data_ts_control.id"
        ) in vms_tf

    def test_variables_tf_declares_sensitive_var(self, provider, tmp_dirs):
        _, output_dir = tmp_dirs
        vm = _vm(
            "ts-control",
            tailscale={"auth": {"auth_key_secret": "tailscale.auth_key"}},
        )
        provider.generate_terraform([vm])
        variables_tf = _read_tf(output_dir, "variables.tf")

        assert 'variable "tailscale_auth_key"' in variables_tf
        assert "sensitive   = true" in variables_tf

    def test_advertise_tags_rendered(self, provider, tmp_dirs):
        _, output_dir = tmp_dirs
        vm = _vm(
            "ts-control",
            tailscale={
                "advertise_tags": ["tag:ociinfrastructure", "tag:k3s"],
                "auth": {"auth_key_secret": "tailscale.auth_key"},
            },
        )
        provider.generate_terraform([vm])
        vms_tf = _read_tf(output_dir, "vms.tf")

        assert "advertise_tags" in vms_tf
        assert "tag:ociinfrastructure" in vms_tf
        assert "tag:k3s" in vms_tf


class TestProxmoxTailscaleOAuth:
    """Cover the OAuth client credentials auth mode."""

    def test_oauth_module_block_emitted(self, provider, tmp_dirs):
        _, output_dir = tmp_dirs
        vm = _vm(
            "ts-control",
            tailscale={
                "auth": {
                    "oauth": {
                        "client_id_secret": "tailscale.oauth_client_id",
                        "client_secret_secret": "tailscale.oauth_client_secret",
                    },
                },
            },
        )
        provider.generate_terraform([vm])
        vms_tf = _read_tf(output_dir, "vms.tf")

        assert 'module "tailscale_ts_control"' in vms_tf
        assert "client_id     = var.tailscale_oauth_client_id" in vms_tf
        assert "client_secret = var.tailscale_oauth_client_secret" in vms_tf
        assert "auth_key" not in vms_tf

    def test_oauth_variables_tf_has_both_secrets(self, provider, tmp_dirs):
        _, output_dir = tmp_dirs
        vm = _vm(
            "ts-control",
            tailscale={
                "auth": {
                    "oauth": {
                        "client_id_secret": "tailscale.oauth_client_id",
                        "client_secret_secret": "tailscale.oauth_client_secret",
                    },
                },
            },
        )
        provider.generate_terraform([vm])
        variables_tf = _read_tf(output_dir, "variables.tf")

        assert 'variable "tailscale_oauth_client_id"' in variables_tf
        assert 'variable "tailscale_oauth_client_secret"' in variables_tf


class TestProxmoxTailscaleAdditionalParts:
    """Cover the ``additional_parts`` escape hatch."""

    def test_additional_parts_rendered(self, provider, tmp_dirs):
        _, output_dir = tmp_dirs
        vm = _vm(
            "ts-control",
            tailscale={
                "auth": {"auth_key_secret": "tailscale.auth_key"},
                "additional_parts": [
                    {
                        "filename": "99-extras.cfg",
                        "content_type": "text/cloud-config",
                        "content": "bootcmd:\n  - ssh-keygen -A\n",
                    },
                ],
            },
        )
        provider.generate_terraform([vm])
        vms_tf = _read_tf(output_dir, "vms.tf")

        assert "additional_parts" in vms_tf
        assert "99-extras.cfg" in vms_tf
        assert "ssh-keygen -A" in vms_tf


class TestProxmoxTailscaleValidation:
    """Cover schema enforcement (mutual exclusion, both auth modes)."""

    def test_both_auth_modes_rejected(self, provider, tmp_dirs):
        from infrafoundry.core.tailscale import TailscaleSchemaError

        vm = _vm(
            "ts-control",
            tailscale={
                "auth": {
                    "auth_key_secret": "tailscale.auth_key",
                    "oauth": {
                        "client_id_secret": "tailscale.oauth_client_id",
                        "client_secret_secret": "tailscale.oauth_client_secret",
                    },
                },
            },
        )

        with pytest.raises(TailscaleSchemaError, match="exactly one"):
            provider.generate_terraform([vm])

    def test_no_auth_mode_rejected(self, provider, tmp_dirs):
        from infrafoundry.core.tailscale import TailscaleSchemaError

        vm = _vm("ts-control", tailscale={"auth": {}})

        with pytest.raises(TailscaleSchemaError, match="exactly one"):
            provider.generate_terraform([vm])

    def test_tailscale_and_cloud_init_snippets_rejected(self, provider, tmp_dirs):
        from infrafoundry.core.tailscale import TailscaleSchemaError

        vm = _vm(
            "ts-control",
            tailscale={"auth": {"auth_key_secret": "tailscale.auth_key"}},
            cloud_init_snippets=["base"],
        )

        with pytest.raises(TailscaleSchemaError, match="mutually exclusive"):
            provider.generate_terraform([vm])

    def test_invalid_tag_format_rejected(self, provider, tmp_dirs):
        from infrafoundry.core.tailscale import TailscaleSchemaError

        vm = _vm(
            "ts-control",
            tailscale={
                "advertise_tags": ["k3s"],  # Missing 'tag:' prefix
                "auth": {"auth_key_secret": "tailscale.auth_key"},
            },
        )

        with pytest.raises(TailscaleSchemaError, match="must start with 'tag:'"):
            provider.generate_terraform([vm])


class TestProxmoxTailscaleMultipleVMs:
    """Cover deduplication when multiple VMs share the same auth secret."""

    def test_multiple_vms_one_var_declaration(self, provider, tmp_dirs):
        _, output_dir = tmp_dirs
        vms = [
            _vm(
                "ts-a",
                vmid=200,
                tailscale={"auth": {"auth_key_secret": "tailscale.auth_key"}},
            ),
            _vm(
                "ts-b",
                vmid=201,
                tailscale={"auth": {"auth_key_secret": "tailscale.auth_key"}},
            ),
        ]
        provider.generate_terraform(vms)

        vms_tf = _read_tf(output_dir, "vms.tf")
        variables_tf = _read_tf(output_dir, "variables.tf")

        assert 'module "tailscale_ts_a"' in vms_tf
        assert 'module "tailscale_ts_b"' in vms_tf
        assert variables_tf.count('variable "tailscale_auth_key"') == 1


class TestProxmoxTailscaleRegression:
    """Cover that the existing cloud_init_snippets path still works."""

    def test_vm_without_tailscale_uses_existing_path(self, provider, tmp_dirs):
        config_dir, output_dir = tmp_dirs
        snippets_dir = config_dir / "test" / "files" / "cloud-init-snippets"
        snippets_dir.mkdir(parents=True)
        (snippets_dir / "base.yaml").write_text("packages:\n  - curl\n")

        vm = _vm("plain", cloud_init_snippets=["base"])
        provider.generate_terraform([vm])
        vms_tf = _read_tf(output_dir, "vms.tf")

        # Existing path: heredoc with #cloud-config + literal yaml
        assert "#cloud-config" in vms_tf
        # Should NOT have a module block
        assert 'module "tailscale_' not in vms_tf

    def test_provider_tf_declares_cloudinit_provider_unconditionally(self, provider, tmp_dirs):
        _, output_dir = tmp_dirs
        vm = _vm("plain")
        provider.generate_terraform([vm])
        provider_tf = _read_tf(output_dir, "provider.tf")

        assert 'source  = "hashicorp/cloudinit"' in provider_tf
