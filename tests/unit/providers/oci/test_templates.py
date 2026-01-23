"""Unit tests for OCI template rendering."""

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.oci import OCIProvider


@pytest.fixture
def provider(tmp_path):
    """Create an OCIProvider for template testing."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    p = OCIProvider(config_dir, output_dir)
    p.set_environment("test")
    return p


class TestProviderTemplate:
    """Tests for provider.tf.j2 template."""

    def test_renders_oci_provider_block(self, provider):
        """Test provider template renders OCI provider configuration."""
        content = provider.render_template("oci/provider.tf.j2", {})
        assert 'provider "oci"' in content
        assert "oracle/oci" in content
        assert "~> 6.0" in content

    def test_includes_all_auth_variables(self, provider):
        """Test provider template references all auth variables."""
        content = provider.render_template("oci/provider.tf.j2", {})
        assert "var.oci_tenancy_ocid" in content
        assert "var.oci_user_ocid" in content
        assert "var.oci_fingerprint" in content
        assert "var.oci_private_key_path" in content
        assert "var.oci_region" in content


class TestVariablesTemplate:
    """Tests for variables.tf.j2 template."""

    def test_declares_all_variables(self, provider):
        """Test variables template declares all required variables."""
        content = provider.render_template("oci/variables.tf.j2", {})
        assert 'variable "oci_tenancy_ocid"' in content
        assert 'variable "oci_user_ocid"' in content
        assert 'variable "oci_fingerprint"' in content
        assert 'variable "oci_private_key_path"' in content
        assert 'variable "oci_region"' in content
        assert 'variable "oci_compartment_ocid"' in content

    def test_variables_have_descriptions(self, provider):
        """Test all variables have descriptions."""
        content = provider.render_template("oci/variables.tf.j2", {})
        # Each variable block should have a description
        assert content.count("description") == 6


class TestVCNTemplate:
    """Tests for vcn.tf.j2 template."""

    def test_renders_vcn_resource(self, provider):
        """Test VCN template renders oci_core_vcn resource."""
        vcns = [
            ResourceConfig(
                name="test-vcn",
                type="vcn",
                provider="oci",
                config={"cidr_block": "10.0.0.0/16", "dns_label": "testvcn"},
            )
        ]
        content = provider.render_template("oci/vcn.tf.j2", {"vcns": vcns, "subnets": []})
        assert 'resource "oci_core_vcn" "test_vcn"' in content
        assert "10.0.0.0/16" in content
        assert "testvcn" in content

    def test_renders_internet_gateway(self, provider):
        """Test VCN with internet_gateway creates IGW and route table."""
        vcns = [
            ResourceConfig(
                name="public-vcn",
                type="vcn",
                provider="oci",
                config={
                    "cidr_block": "10.0.0.0/16",
                    "internet_gateway": True,
                },
            )
        ]
        content = provider.render_template("oci/vcn.tf.j2", {"vcns": vcns, "subnets": []})
        assert "oci_core_internet_gateway" in content
        assert "oci_core_route_table" in content
        assert "0.0.0.0/0" in content

    def test_renders_subnet(self, provider):
        """Test subnet rendering."""
        subnets = [
            ResourceConfig(
                name="my-subnet",
                type="subnet",
                provider="oci",
                config={
                    "vcn": "my-vcn",
                    "cidr_block": "10.0.1.0/24",
                    "dns_label": "mysub",
                    "public": True,
                },
            )
        ]
        content = provider.render_template("oci/vcn.tf.j2", {"vcns": [], "subnets": subnets})
        assert 'resource "oci_core_subnet" "my_subnet"' in content
        assert "10.0.1.0/24" in content
        assert "mysub" in content
        assert "prohibit_public_ip_on_vnic = false" in content

    def test_private_subnet(self, provider):
        """Test private subnet prohibits public IP."""
        subnets = [
            ResourceConfig(
                name="private-sub",
                type="subnet",
                provider="oci",
                config={
                    "vcn": "my-vcn",
                    "cidr_block": "10.0.2.0/24",
                    "public": False,
                },
            )
        ]
        content = provider.render_template("oci/vcn.tf.j2", {"vcns": [], "subnets": subnets})
        assert "prohibit_public_ip_on_vnic = true" in content

    def test_renders_nat_gateway(self, provider):
        """Test VCN with nat_gateway creates NAT gateway and private route table."""
        vcns = [
            ResourceConfig(
                name="nat-vcn",
                type="vcn",
                provider="oci",
                config={
                    "cidr_block": "10.0.0.0/16",
                    "nat_gateway": True,
                },
            )
        ]
        content = provider.render_template("oci/vcn.tf.j2", {"vcns": vcns, "subnets": []})
        assert "oci_core_nat_gateway" in content
        assert 'display_name   = "nat-vcn-nat-gw"' in content
        assert "nat_vcn_private_rt" in content
        assert "oci_core_nat_gateway.nat_vcn_nat.id" in content

    def test_private_subnet_with_nat_gets_private_rt(self, provider):
        """Test private subnet gets private_rt when VCN has NAT gateway."""
        vcns = [
            ResourceConfig(
                name="my-vcn",
                type="vcn",
                provider="oci",
                config={
                    "cidr_block": "10.0.0.0/16",
                    "internet_gateway": True,
                    "nat_gateway": True,
                },
            )
        ]
        subnets = [
            ResourceConfig(
                name="private-sub",
                type="subnet",
                provider="oci",
                config={
                    "vcn": "my-vcn",
                    "cidr_block": "10.0.1.0/24",
                    "public": False,
                },
            )
        ]
        content = provider.render_template("oci/vcn.tf.j2", {"vcns": vcns, "subnets": subnets})
        assert "oci_core_route_table.my_vcn_private_rt.id" in content

    def test_private_subnet_without_nat_no_route_table(self, provider):
        """Test private subnet without NAT gateway gets no route table."""
        vcns = [
            ResourceConfig(
                name="my-vcn",
                type="vcn",
                provider="oci",
                config={
                    "cidr_block": "10.0.0.0/16",
                    "internet_gateway": True,
                },
            )
        ]
        subnets = [
            ResourceConfig(
                name="private-sub",
                type="subnet",
                provider="oci",
                config={
                    "vcn": "my-vcn",
                    "cidr_block": "10.0.1.0/24",
                    "public": False,
                },
            )
        ]
        content = provider.render_template("oci/vcn.tf.j2", {"vcns": vcns, "subnets": subnets})
        assert "private_rt" not in content

    def test_vcn_with_security_list(self, provider):
        """Test VCN with security list configuration."""
        vcns = [
            ResourceConfig(
                name="secure-vcn",
                type="vcn",
                provider="oci",
                config={
                    "cidr_block": "10.0.0.0/16",
                    "security_list": {
                        "ingress_rules": [
                            {
                                "source": "0.0.0.0/0",
                                "protocol": "6",
                                "tcp_options": {"min": 22, "max": 22},
                            },
                        ],
                    },
                },
            )
        ]
        content = provider.render_template("oci/vcn.tf.j2", {"vcns": vcns, "subnets": []})
        assert "oci_core_security_list" in content
        assert "ingress_security_rules" in content
        assert "tcp_options" in content


class TestInstancesTemplate:
    """Tests for instances.tf.j2 template."""

    def test_renders_instance(self, provider):
        """Test basic instance rendering."""
        instances = [
            ResourceConfig(
                name="my-server",
                type="instance",
                provider="oci",
                config={
                    "shape": "VM.Standard.A1.Flex",
                    "subnet": "my-subnet",
                    "image": "ocid1.image.oc1.iad.example",
                },
            )
        ]
        content = provider.render_template("oci/instances.tf.j2", {"instances": instances})
        assert 'resource "oci_core_instance" "my_server"' in content
        assert "VM.Standard.A1.Flex" in content
        assert "ocid1.image.oc1.iad.example" in content

    def test_renders_shape_config(self, provider):
        """Test flex shape configuration."""
        instances = [
            ResourceConfig(
                name="flex-vm",
                type="instance",
                provider="oci",
                config={
                    "shape": "VM.Standard.A1.Flex",
                    "shape_config": {"ocpus": 4, "memory_in_gbs": 24},
                    "subnet": "my-subnet",
                    "image": "ocid1.image.oc1.iad.example",
                },
            )
        ]
        content = provider.render_template("oci/instances.tf.j2", {"instances": instances})
        assert "shape_config" in content
        assert "ocpus         = 4" in content
        assert "memory_in_gbs = 24" in content

    def test_renders_ssh_keys(self, provider):
        """Test SSH authorized keys in metadata."""
        instances = [
            ResourceConfig(
                name="ssh-vm",
                type="instance",
                provider="oci",
                config={
                    "shape": "VM.Standard.A1.Flex",
                    "subnet": "my-subnet",
                    "image": "ocid1.image.oc1.iad.example",
                    "ssh_authorized_keys": ["ssh-rsa AAAA1", "ssh-rsa AAAA2"],
                },
            )
        ]
        content = provider.render_template("oci/instances.tf.j2", {"instances": instances})
        assert "ssh_authorized_keys" in content

    def test_renders_boot_volume_size(self, provider):
        """Test custom boot volume size."""
        instances = [
            ResourceConfig(
                name="big-disk",
                type="instance",
                provider="oci",
                config={
                    "shape": "VM.Standard.A1.Flex",
                    "subnet": "my-subnet",
                    "image": "ocid1.image.oc1.iad.example",
                    "boot_volume_size_in_gbs": 100,
                },
            )
        ]
        content = provider.render_template("oci/instances.tf.j2", {"instances": instances})
        assert "boot_volume_size_in_gbs = 100" in content

    def test_renders_freeform_tags(self, provider):
        """Test freeform tags rendering."""
        instances = [
            ResourceConfig(
                name="tagged-vm",
                type="instance",
                provider="oci",
                config={
                    "shape": "VM.Standard.A1.Flex",
                    "subnet": "my-subnet",
                    "image": "ocid1.image.oc1.iad.example",
                    "freeform_tags": {"env": "dev", "team": "infra"},
                },
            )
        ]
        content = provider.render_template("oci/instances.tf.j2", {"instances": instances})
        assert "freeform_tags" in content
        assert '"env"' in content
        assert '"dev"' in content

    def test_renders_availability_domains_data(self, provider):
        """Test availability domains data source is included."""
        instances = [
            ResourceConfig(
                name="test-vm",
                type="instance",
                provider="oci",
                config={
                    "shape": "VM.Standard.A1.Flex",
                    "subnet": "my-subnet",
                    "image": "ocid1.image.oc1.iad.example",
                },
            )
        ]
        content = provider.render_template("oci/instances.tf.j2", {"instances": instances})
        assert "oci_identity_availability_domains" in content

    def test_renders_cloud_init_merged(self, provider):
        """Test cloud-init merged data in metadata."""
        instances = [
            ResourceConfig(
                name="ci-vm",
                type="instance",
                provider="oci",
                config={
                    "shape": "VM.Standard.A1.Flex",
                    "subnet": "my-subnet",
                    "image": "ocid1.image.oc1.iad.example",
                    "cloud_init_merged": {"packages": ["curl", "wget"]},
                },
            )
        ]
        content = provider.render_template("oci/instances.tf.j2", {"instances": instances})
        assert "user_data" in content
        assert "base64encode" in content


class TestOutputsTemplate:
    """Tests for outputs.tf.j2 template."""

    def test_renders_vcn_outputs(self, provider):
        """Test VCN outputs."""
        resources_by_type = {
            "vcn": [
                ResourceConfig(
                    name="my-vcn",
                    type="vcn",
                    provider="oci",
                    config={"cidr_block": "10.0.0.0/16"},
                )
            ]
        }
        content = provider.render_template(
            "oci/outputs.tf.j2", {"resources_by_type": resources_by_type}
        )
        assert "vcn_ids" in content
        assert "oci_core_vcn.my_vcn.id" in content

    def test_renders_subnet_outputs(self, provider):
        """Test subnet outputs."""
        resources_by_type = {
            "subnet": [
                ResourceConfig(
                    name="pub-subnet",
                    type="subnet",
                    provider="oci",
                    config={"vcn": "my-vcn", "cidr_block": "10.0.0.0/24"},
                )
            ]
        }
        content = provider.render_template(
            "oci/outputs.tf.j2", {"resources_by_type": resources_by_type}
        )
        assert "subnet_ids" in content
        assert "oci_core_subnet.pub_subnet.id" in content

    def test_renders_instance_outputs(self, provider):
        """Test instance outputs include public and private IPs."""
        resources_by_type = {
            "instance": [
                ResourceConfig(
                    name="web-server",
                    type="instance",
                    provider="oci",
                    config={"shape": "VM.Standard.A1.Flex", "subnet": "s", "image": "img"},
                )
            ]
        }
        content = provider.render_template(
            "oci/outputs.tf.j2", {"resources_by_type": resources_by_type}
        )
        assert "instance_ips" in content
        assert "instance_private_ips" in content
        assert "oci_core_instance.web_server.public_ip" in content
        assert "oci_core_instance.web_server.private_ip" in content

    def test_empty_resources_no_outputs(self, provider):
        """Test empty resources produce no output blocks."""
        content = provider.render_template("oci/outputs.tf.j2", {"resources_by_type": {}})
        assert "output" not in content


class TestPlaybookTemplate:
    """Tests for playbook.yml.j2 template."""

    def test_renders_playbook_with_roles(self, provider):
        """Test playbook includes ansible roles."""
        instances = [
            ResourceConfig(
                name="app-server",
                type="instance",
                provider="oci",
                config={
                    "shape": "VM.Standard.A1.Flex",
                    "subnet": "s",
                    "image": "img",
                    "ansible_roles": ["docker", "app"],
                },
            )
        ]
        content = provider.render_template("oci/playbook.yml.j2", {"instances": instances})
        assert "docker" in content
        assert "app" in content
        assert "app-server" in content

    def test_renders_playbook_without_roles(self, provider):
        """Test playbook renders without roles."""
        instances = [
            ResourceConfig(
                name="plain-server",
                type="instance",
                provider="oci",
                config={"shape": "VM.Standard.A1.Flex", "subnet": "s", "image": "img"},
            )
        ]
        content = provider.render_template("oci/playbook.yml.j2", {"instances": instances})
        assert "Configure OCI Instances" in content


class TestInventoryTemplate:
    """Tests for inventory.yml.j2 template."""

    def test_renders_inventory_with_instances(self, provider):
        """Test inventory lists instances with host info."""
        instances = [
            ResourceConfig(
                name="web-1",
                type="instance",
                provider="oci",
                config={
                    "shape": "VM.Standard.A1.Flex",
                    "subnet": "s",
                    "image": "img",
                    "ssh_user": "opc",
                },
            )
        ]
        content = provider.render_template("oci/inventory.yml.j2", {"instances": instances})
        assert "web-1" in content
        assert "opc" in content
        assert "oci_instances" in content

    def test_ansible_host_override(self, provider):
        """Test ansible_host config override takes priority over Terraform output."""
        custom_host = "custom-ansible-host-override"
        instances = [
            ResourceConfig(
                name="ts-host",
                type="instance",
                provider="oci",
                config={
                    "shape": "VM.Standard.A1.Flex",
                    "subnet": "s",
                    "image": "img",
                    "ansible_host": custom_host,
                },
            )
        ]
        content = provider.render_template("oci/inventory.yml.j2", {"instances": instances})
        assert custom_host in content
        assert "oci_core_instance" not in content

    def test_ansible_host_default(self, provider):
        """Test ansible_host falls back to Terraform output when not set."""
        instances = [
            ResourceConfig(
                name="pub-host",
                type="instance",
                provider="oci",
                config={
                    "shape": "VM.Standard.A1.Flex",
                    "subnet": "s",
                    "image": "img",
                },
            )
        ]
        content = provider.render_template("oci/inventory.yml.j2", {"instances": instances})
        assert "oci_core_instance.pub_host.public_ip" in content

    def test_default_ssh_user(self, provider):
        """Test inventory uses ubuntu as default ssh user."""
        instances = [
            ResourceConfig(
                name="default-user",
                type="instance",
                provider="oci",
                config={"shape": "VM.Standard.A1.Flex", "subnet": "s", "image": "img"},
            )
        ]
        content = provider.render_template("oci/inventory.yml.j2", {"instances": instances})
        assert "ubuntu" in content
