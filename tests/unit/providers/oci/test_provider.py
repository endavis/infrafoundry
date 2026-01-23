"""Unit tests for OCI provider."""

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.oci import OCIProvider


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
    """Create an OCIProvider instance."""
    config_dir, output_dir = tmp_dirs
    return OCIProvider(config_dir, output_dir)


def test_provider_init(provider):
    """Test provider initializes with correct name."""
    assert provider.name == "oci"


def test_get_resource_types(provider):
    """Test supported resource types."""
    types = provider.get_resource_types()
    assert "vcn" in types
    assert "subnet" in types
    assert "instance" in types


def test_get_dependencies(provider):
    """Test resource dependency graph."""
    deps = provider.get_dependencies()
    assert deps["vcn"] == []
    assert deps["subnet"] == ["vcn"]
    assert "vcn" in deps["instance"]
    assert "subnet" in deps["instance"]


def test_validate_config_valid(provider):
    """Test config validation with required fields."""
    assert provider.validate_config({"name": "test"}) is True


def test_validate_config_invalid(provider):
    """Test config validation with missing fields."""
    assert provider.validate_config({}) is False


def test_generate_terraform_creates_files(provider, tmp_dirs):
    """Test that generate_terraform creates expected files."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="test-vcn",
            type="vcn",
            provider="oci",
            config={
                "cidr_block": "10.0.0.0/16",
                "dns_label": "testvcn",
                "internet_gateway": True,
            },
        ),
        ResourceConfig(
            name="public-subnet",
            type="subnet",
            provider="oci",
            config={
                "vcn": "test-vcn",
                "cidr_block": "10.0.0.0/24",
                "dns_label": "public",
                "public": True,
            },
        ),
        ResourceConfig(
            name="test-instance",
            type="instance",
            provider="oci",
            config={
                "shape": "VM.Standard.A1.Flex",
                "shape_config": {"ocpus": 1, "memory_in_gbs": 6},
                "subnet": "public-subnet",
                "image": "ocid1.image.oc1.iad.example",
                "ssh_authorized_keys": ["ssh-rsa AAAA..."],
            },
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "oci"
    assert (terraform_dir / "provider.tf").exists()
    assert (terraform_dir / "variables.tf").exists()
    assert (terraform_dir / "vcn.tf").exists()
    assert (terraform_dir / "instances.tf").exists()
    assert (terraform_dir / "outputs.tf").exists()


def test_generate_terraform_vcn_content(provider, tmp_dirs):
    """Test VCN terraform content."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="my-vcn",
            type="vcn",
            provider="oci",
            config={
                "cidr_block": "10.0.0.0/16",
                "dns_label": "myvcn",
            },
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "oci"
    vcn_content = (terraform_dir / "vcn.tf").read_text()
    assert "oci_core_vcn" in vcn_content
    assert "10.0.0.0/16" in vcn_content
    assert "myvcn" in vcn_content


def test_generate_terraform_instance_with_shape_config(provider, tmp_dirs):
    """Test instance terraform with flex shape config."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="public-subnet",
            type="subnet",
            provider="oci",
            config={
                "vcn": "test-vcn",
                "cidr_block": "10.0.0.0/24",
                "public": True,
            },
        ),
        ResourceConfig(
            name="flex-instance",
            type="instance",
            provider="oci",
            config={
                "shape": "VM.Standard.A1.Flex",
                "shape_config": {"ocpus": 2, "memory_in_gbs": 12},
                "subnet": "public-subnet",
                "image": "ocid1.image.oc1.iad.example",
            },
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "oci"
    content = (terraform_dir / "instances.tf").read_text()
    assert "VM.Standard.A1.Flex" in content
    assert "ocpus" in content
    assert "memory_in_gbs" in content


def test_generate_ansible_creates_files(provider, tmp_dirs):
    """Test that generate_ansible creates playbook and inventory."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="test-instance",
            type="instance",
            provider="oci",
            config={
                "shape": "VM.Standard.A1.Flex",
                "subnet": "public-subnet",
                "image": "ocid1.image.oc1.iad.example",
                "ansible_roles": ["common", "docker"],
            },
        ),
    ]

    provider.generate_ansible(resources)

    ansible_dir = output_dir / "test" / "ansible" / "oci"
    assert (ansible_dir / "playbook.yml").exists()
    assert (ansible_dir / "inventory.yml").exists()


def test_generate_ansible_playbook_content(provider, tmp_dirs):
    """Test playbook includes ansible_roles."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="web-server",
            type="instance",
            provider="oci",
            config={
                "shape": "VM.Standard.A1.Flex",
                "subnet": "public-subnet",
                "image": "ocid1.image.oc1.iad.example",
                "ansible_roles": ["nginx"],
            },
        ),
    ]

    provider.generate_ansible(resources)

    ansible_dir = output_dir / "test" / "ansible" / "oci"
    content = (ansible_dir / "playbook.yml").read_text()
    assert "nginx" in content
    assert "web-server" in content


def test_generate_ansible_inventory_content(provider, tmp_dirs):
    """Test inventory contains instance entries."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="my-instance",
            type="instance",
            provider="oci",
            config={
                "shape": "VM.Standard.A1.Flex",
                "subnet": "public-subnet",
                "image": "ocid1.image.oc1.iad.example",
                "ssh_user": "opc",
            },
        ),
    ]

    provider.generate_ansible(resources)

    ansible_dir = output_dir / "test" / "ansible" / "oci"
    content = (ansible_dir / "inventory.yml").read_text()
    assert "my-instance" in content
    assert "opc" in content


def test_cloud_init_snippets_missing_file(provider, tmp_dirs):
    """Test cloud-init snippets with missing file does not raise."""
    _config_dir, _output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="test-instance",
            type="instance",
            provider="oci",
            config={
                "shape": "VM.Standard.A1.Flex",
                "subnet": "public-subnet",
                "image": "ocid1.image.oc1.iad.example",
                "cloud_init_snippets": ["nonexistent"],
            },
        ),
    ]

    # Should not raise with fail_on_missing_snippets=False (default)
    provider.generate_terraform(resources)


def test_cloud_init_snippets_fail_on_missing(provider, tmp_dirs):
    """Test cloud-init snippets raises when configured to fail."""
    _config_dir, _output_dir = tmp_dirs
    provider.set_environment("test")
    provider.fail_on_missing_snippets = True

    resources = [
        ResourceConfig(
            name="test-instance",
            type="instance",
            provider="oci",
            config={
                "shape": "VM.Standard.A1.Flex",
                "subnet": "public-subnet",
                "image": "ocid1.image.oc1.iad.example",
                "cloud_init_snippets": ["nonexistent"],
            },
        ),
    ]

    with pytest.raises(FileNotFoundError):
        provider.generate_terraform(resources)


def test_cloud_init_snippets_merge(provider, tmp_dirs):
    """Test cloud-init snippets are merged into config."""
    config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    # Create snippet file
    snippets_dir = config_dir / "test" / "files" / "cloud-init-snippets"
    snippets_dir.mkdir(parents=True)
    (snippets_dir / "base.yaml").write_text(
        "packages:\n  - curl\n  - wget\nruncmd:\n  - echo hello\n"
    )

    resources = [
        ResourceConfig(
            name="test-instance",
            type="instance",
            provider="oci",
            config={
                "shape": "VM.Standard.A1.Flex",
                "subnet": "public-subnet",
                "image": "ocid1.image.oc1.iad.example",
                "cloud_init_snippets": ["base"],
            },
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "oci"
    content = (terraform_dir / "instances.tf").read_text()
    assert "user_data" in content


def test_provider_terraform_provider_content(provider, tmp_dirs):
    """Test provider.tf content."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="test-vcn",
            type="vcn",
            provider="oci",
            config={"cidr_block": "10.0.0.0/16"},
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "oci"
    content = (terraform_dir / "provider.tf").read_text()
    assert "oracle/oci" in content
    assert "var.oci_tenancy_ocid" in content
    assert "var.oci_region" in content


def test_generate_terraform_only_instances(provider, tmp_dirs):
    """Test generating terraform with only instances."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="standalone",
            type="instance",
            provider="oci",
            config={
                "shape": "VM.Standard.E4.Flex",
                "subnet": "existing-subnet",
                "image": "ocid1.image.oc1.iad.example",
            },
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "oci"
    assert (terraform_dir / "instances.tf").exists()
    assert not (terraform_dir / "vcn.tf").exists()


def test_generate_ansible_with_ansible_host_override(provider, tmp_dirs):
    """Test ansible inventory uses ansible_host override when set."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    custom_host = "custom-ansible-host-override"
    resources = [
        ResourceConfig(
            name="ts-node",
            type="instance",
            provider="oci",
            config={
                "shape": "VM.Standard.A1.Flex",
                "subnet": "public-subnet",
                "image": "ocid1.image.oc1.iad.example",
                "ansible_host": custom_host,
            },
        ),
    ]

    provider.generate_ansible(resources)

    ansible_dir = output_dir / "test" / "ansible" / "oci"
    content = (ansible_dir / "inventory.yml").read_text()
    assert custom_host in content
    assert "oci_core_instance" not in content


def test_generate_ansible_filters_non_instances(provider, tmp_dirs):
    """Test that generate_ansible only includes instance resources."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="my-vcn",
            type="vcn",
            provider="oci",
            config={"cidr_block": "10.0.0.0/16"},
        ),
        ResourceConfig(
            name="my-instance",
            type="instance",
            provider="oci",
            config={
                "shape": "VM.Standard.A1.Flex",
                "subnet": "public-subnet",
                "image": "ocid1.image.oc1.iad.example",
            },
        ),
    ]

    provider.generate_ansible(resources)

    ansible_dir = output_dir / "test" / "ansible" / "oci"
    content = (ansible_dir / "inventory.yml").read_text()
    assert "my-instance" in content
    assert "my-vcn" not in content
