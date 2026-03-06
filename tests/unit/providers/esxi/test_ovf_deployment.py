"""Unit tests for ESXi OVF deployment template rendering."""

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.esxi import EsxiProvider


@pytest.fixture
def provider(tmp_path):
    """Create an EsxiProvider for template testing."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    p = EsxiProvider(config_dir, output_dir)
    p.set_environment("test")
    return p


def _make_ovf_deployment(name: str = "ontap-node-01", **config_overrides) -> ResourceConfig:
    """Helper to create an ovf_deployment ResourceConfig."""
    config: dict = {
        "host": "esxi-01",
        "ovf_source": "/path/to/vsim.ovf",
        "disk_store": "datastore1",
        "vm_name": "ontap-node-01",
        "network_map": {
            "hostonly": "PG-Cluster-esx-01",
            "nat": "PG-Management-esx-01",
        },
        **config_overrides,
    }
    return ResourceConfig(name=name, type="ovf_deployment", provider="esxi", config=config)


class TestOvfDeploymentTemplate:
    """Tests for ovf_deployment.tf.j2 template."""

    def test_basic_ovf_deployment(self, provider):
        """Basic OVF deployment should render terraform_data resource."""
        deployments = [_make_ovf_deployment()]
        content = provider.render_template(
            "esxi/ovf_deployment.tf.j2",
            {"ovf_deployments": deployments, "host_alias": EsxiProvider._host_alias},
        )
        assert 'resource "terraform_data" "ovf_ontap_node_01"' in content
        assert "ovftool" in content
        assert "triggers_replace" in content

    def test_network_map_renders_net_flags(self, provider):
        """Network map should render --net: flags for each OVF network."""
        deployments = [_make_ovf_deployment()]
        content = provider.render_template(
            "esxi/ovf_deployment.tf.j2",
            {"ovf_deployments": deployments, "host_alias": EsxiProvider._host_alias},
        )
        assert '--net:"hostonly"="PG-Cluster-esx-01"' in content
        assert '--net:"nat"="PG-Management-esx-01"' in content

    def test_host_alias_in_variables(self, provider):
        """Host alias should be used in variable references."""
        deployments = [_make_ovf_deployment()]
        content = provider.render_template(
            "esxi/ovf_deployment.tf.j2",
            {"ovf_deployments": deployments, "host_alias": EsxiProvider._host_alias},
        )
        assert "var.esxi_hostname_esxi_01" in content
        assert "var.esxi_username_esxi_01" in content
        assert "var.esxi_password_esxi_01" in content

    def test_multiple_deployments(self, provider):
        """Multiple deployments should render multiple resources."""
        deployments = [
            _make_ovf_deployment("node-01", vm_name="ontap-01"),
            _make_ovf_deployment("node-02", vm_name="ontap-02", host="esxi-02"),
        ]
        content = provider.render_template(
            "esxi/ovf_deployment.tf.j2",
            {"ovf_deployments": deployments, "host_alias": EsxiProvider._host_alias},
        )
        assert 'resource "terraform_data" "ovf_node_01"' in content
        assert 'resource "terraform_data" "ovf_node_02"' in content
        assert "var.esxi_hostname_esxi_02" in content

    def test_name_normalization(self, provider):
        """Dashes in resource names should be converted to underscores."""
        deployments = [_make_ovf_deployment("my-ovf-vm")]
        content = provider.render_template(
            "esxi/ovf_deployment.tf.j2",
            {"ovf_deployments": deployments, "host_alias": EsxiProvider._host_alias},
        )
        assert '"ovf_my_ovf_vm"' in content

    def test_default_disk_mode_thin(self, provider):
        """Default disk mode should be thin."""
        deployments = [_make_ovf_deployment()]
        content = provider.render_template(
            "esxi/ovf_deployment.tf.j2",
            {"ovf_deployments": deployments, "host_alias": EsxiProvider._host_alias},
        )
        assert "-dm=thin" in content

    def test_custom_disk_mode(self, provider):
        """Custom disk mode should be rendered."""
        deployments = [_make_ovf_deployment(disk_mode="thick")]
        content = provider.render_template(
            "esxi/ovf_deployment.tf.j2",
            {"ovf_deployments": deployments, "host_alias": EsxiProvider._host_alias},
        )
        assert "-dm=thick" in content

    def test_power_on_default(self, provider):
        """Default power=on should render --powerOn flag."""
        deployments = [_make_ovf_deployment()]
        content = provider.render_template(
            "esxi/ovf_deployment.tf.j2",
            {"ovf_deployments": deployments, "host_alias": EsxiProvider._host_alias},
        )
        assert "--powerOn" in content

    def test_power_off(self, provider):
        """Power=off should not render --powerOn flag."""
        deployments = [_make_ovf_deployment(power="off")]
        content = provider.render_template(
            "esxi/ovf_deployment.tf.j2",
            {"ovf_deployments": deployments, "host_alias": EsxiProvider._host_alias},
        )
        assert "--powerOn" not in content

    def test_notes_rendered(self, provider):
        """Notes should be rendered as --annotation flag."""
        deployments = [_make_ovf_deployment(notes="ONTAP 9.17.1")]
        content = provider.render_template(
            "esxi/ovf_deployment.tf.j2",
            {"ovf_deployments": deployments, "host_alias": EsxiProvider._host_alias},
        )
        assert '--annotation="ONTAP 9.17.1"' in content

    def test_no_notes(self, provider):
        """Without notes, --annotation should not appear."""
        deployments = [_make_ovf_deployment()]
        content = provider.render_template(
            "esxi/ovf_deployment.tf.j2",
            {"ovf_deployments": deployments, "host_alias": EsxiProvider._host_alias},
        )
        assert "--annotation" not in content

    def test_destroy_provisioner(self, provider):
        """Destroy provisioner should include SSH command with VM name."""
        deployments = [_make_ovf_deployment(vm_name="ontap-node-01")]
        content = provider.render_template(
            "esxi/ovf_deployment.tf.j2",
            {"ovf_deployments": deployments, "host_alias": EsxiProvider._host_alias},
        )
        assert "when    = destroy" in content
        assert "vim-cmd vmsvc/power.off" in content
        assert "vim-cmd vmsvc/destroy" in content
        assert "ontap-node-01" in content
        assert "sshpass" in content

    def test_vm_name_defaults_to_resource_name(self, provider):
        """When vm_name is not set, resource name should be used."""
        deployment = _make_ovf_deployment("my-vm")
        del deployment.config["vm_name"]
        content = provider.render_template(
            "esxi/ovf_deployment.tf.j2",
            {"ovf_deployments": [deployment], "host_alias": EsxiProvider._host_alias},
        )
        assert '--name="my-vm"' in content

    def test_triggers_replace_block(self, provider):
        """Triggers replace block should contain vm_name, ovf_source, host."""
        deployments = [_make_ovf_deployment()]
        content = provider.render_template(
            "esxi/ovf_deployment.tf.j2",
            {"ovf_deployments": deployments, "host_alias": EsxiProvider._host_alias},
        )
        assert 'vm_name    = "ontap-node-01"' in content
        assert 'ovf_source = "/path/to/vsim.ovf"' in content
        assert 'host       = "esxi-01"' in content

    def test_overwrite_flag(self, provider):
        """Overwrite=true should render --overwrite flag."""
        deployments = [_make_ovf_deployment(overwrite=True)]
        content = provider.render_template(
            "esxi/ovf_deployment.tf.j2",
            {"ovf_deployments": deployments, "host_alias": EsxiProvider._host_alias},
        )
        assert "--overwrite" in content

    def test_no_overwrite_by_default(self, provider):
        """By default --overwrite should not appear."""
        deployments = [_make_ovf_deployment()]
        content = provider.render_template(
            "esxi/ovf_deployment.tf.j2",
            {"ovf_deployments": deployments, "host_alias": EsxiProvider._host_alias},
        )
        assert "--overwrite" not in content
