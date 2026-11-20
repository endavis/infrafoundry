"""Tests for OCI bucket and IAM generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.exceptions import ConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.terraform_outputs import parse_output_ref
from infrafoundry.providers.oci import OCIProvider

OCID = "ocid1.compartment.oc1..aaaaaaaexample"


@pytest.fixture
def provider(tmp_path: Path) -> OCIProvider:
    """Create an OCIProvider writing under tmp_path."""
    (tmp_path / "config").mkdir()
    (tmp_path / "output").mkdir()
    p = OCIProvider(tmp_path / "config", tmp_path / "output")
    p.set_environment("test")
    return p


def _tf(provider: OCIProvider, name: str) -> str:
    return (provider.output_dir / "terraform" / "oci" / name).read_text()


def _res(name: str, type_: str, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type=type_, provider="oci", config=config)


class TestRegistration:
    """Types, terraform map and dependencies."""

    def test_types(self, provider: OCIProvider) -> None:
        """The five new types are registered next to the existing ones."""
        types = provider.get_resource_types()
        for t in ("bucket", "iam_user", "iam_group", "iam_policy", "customer_secret_key"):
            assert t in types
        for t in ("compartment", "vcn", "subnet", "instance"):
            assert t in types

    def test_terraform_map_and_deps(self, provider: OCIProvider) -> None:
        """Primary types map and policies depend on groups."""
        tf = provider.get_terraform_resource_types()
        assert tf["bucket"] == ["oci_objectstorage_bucket"]
        assert tf["customer_secret_key"] == ["oci_identity_customer_secret_key"]
        assert tf["instance"] == ["oci_core_instance"]
        assert provider.get_dependencies()["iam_policy"] == ["iam_group"]
        assert provider.get_dependencies()["instance"] == ["vcn", "subnet"]


class TestBucket:
    """Bucket rendering."""

    def test_defaults(self, provider: OCIProvider) -> None:
        """A bare bucket gets the defaults and the namespace data source."""
        provider.generate_terraform([_res("data-bucket", "bucket")])
        content = _tf(provider, "object_storage.tf")
        assert 'data "oci_objectstorage_namespace" "this"' in content
        assert 'resource "oci_objectstorage_bucket" "data_bucket"' in content
        assert "compartment_id = var.oci_compartment_ocid" in content
        assert '"Standard"' in content
        assert '"Disabled"' in content
        assert '"NoPublicAccess"' in content
        assert "oci_objectstorage_object_lifecycle_policy" not in content

    def test_compartment_by_ocid(self, provider: OCIProvider) -> None:
        """The bucket compartment resolves like a vcn."""
        provider.generate_terraform([_res("b", "bucket", compartment=OCID)])
        assert f'compartment_id = "{OCID}"' in _tf(provider, "object_storage.tf")

    def test_lifecycle(self, provider: OCIProvider) -> None:
        """Lifecycle rules render a policy resource."""
        rule = {
            "name": "expire",
            "action": "DELETE",
            "time_amount": 30,
            "time_unit": "DAYS",
            "prefix": "logs/",
            "enabled": False,
            "target": "objects",
        }
        provider.generate_terraform([_res("b", "bucket", lifecycle=[rule])])
        content = _tf(provider, "object_storage.tf")
        assert 'resource "oci_objectstorage_object_lifecycle_policy" "b"' in content
        assert 'name        = "expire"' in content
        assert "is_enabled  = false" in content
        assert "time_amount = 30" in content
        assert 'inclusion_prefixes = ["logs/"]' in content
        assert 'target      = "objects"' in content

    def test_namespace_output_only_with_buckets(self, provider: OCIProvider) -> None:
        """The namespace output exists only when a bucket is defined."""
        provider.generate_terraform([_res("b", "bucket")])
        assert 'output "objectstorage_namespace"' in _tf(provider, "outputs.tf")
        provider.generate_terraform([_res("u", "iam_user")])
        assert "objectstorage_namespace" not in _tf(provider, "outputs.tf")
        assert not (provider.output_dir / "terraform" / "oci" / "object_storage.tf").exists()


class TestIam:
    """User, group, policy and key rendering."""

    def test_users_groups_memberships(self, provider: OCIProvider) -> None:
        """Users and groups use the tenancy; members become memberships."""
        provider.generate_terraform(
            [
                _res("app-user", "iam_user", compartment=OCID),
                _res("app-group", "iam_group", members=["app-user"]),
            ]
        )
        content = _tf(provider, "iam.tf")
        assert 'resource "oci_identity_user" "app_user"' in content
        assert 'resource "oci_identity_group" "app_group"' in content
        assert content.count("compartment_id = var.oci_tenancy_ocid") == 2
        assert OCID not in content
        assert "Managed by InfraFoundry" in content
        assert 'resource "oci_identity_user_group_membership" "app_group_app_user"' in content
        assert "user_id  = oci_identity_user.app_user.id" in content

    def test_unknown_member_raises(self, provider: OCIProvider) -> None:
        """An undefined member raises ConfigurationError."""
        with pytest.raises(ConfigurationError):
            provider.generate_terraform([_res("g", "iam_group", members=["ghost"])])

    def test_policy(self, provider: OCIProvider) -> None:
        """Statements are verbatim, groups are dependencies, compartment defaults to tenancy."""
        stmt = "Allow group app-group to manage objects in tenancy where target.bucket.name='b'"
        provider.generate_terraform(
            [_res("g", "iam_group"), _res("p", "iam_policy", statements=[stmt])]
        )
        content = _tf(provider, "iam.tf")
        # tojson writes the quote as \u0027, which HCL decodes back to the same string.
        assert f'"{stmt}",'.replace("'", "\\u0027") in content
        assert "oci_identity_group.g," in content
        assert "compartment_id = var.oci_tenancy_ocid" in content

    def test_policy_in_named_compartment(self, provider: OCIProvider) -> None:
        """A policy compartment resolves to a compartment resource."""
        provider.generate_terraform(
            [
                _res("c", "compartment", description="d"),
                _res("p", "iam_policy", statements=["Allow x"], compartment="c"),
            ]
        )
        assert "compartment_id = oci_identity_compartment.c.id" in _tf(provider, "iam.tf")

    def test_key_and_outputs(self, provider: OCIProvider) -> None:
        """A key renders with sensitive outputs that parse as output references."""
        provider.generate_terraform(
            [_res("u", "iam_user"), _res("s3-key", "customer_secret_key", user="u")]
        )
        content = _tf(provider, "iam.tf")
        assert 'resource "oci_identity_customer_secret_key" "s3_key"' in content
        assert "user_id      = oci_identity_user.u.id" in content
        out = _tf(provider, "outputs.tf")
        for suffix in ("id", "secret"):
            block = out.split(f'output "customer_secret_key_s3_key_{suffix}"')[1].split("}")[0]
            assert "sensitive   = true" in block
            assert parse_output_ref(f"outputs.oci.customer_secret_key_s3_key_{suffix}")
        assert "oci_identity_customer_secret_key.s3_key.key" in out

    def test_unknown_key_user_raises(self, provider: OCIProvider) -> None:
        """An undefined user raises ConfigurationError."""
        with pytest.raises(ConfigurationError):
            provider.generate_terraform([_res("k", "customer_secret_key", user="ghost")])

    def test_no_literal_secret(self, provider: OCIProvider) -> None:
        """No generated file holds a literal secret value."""
        provider.generate_terraform(
            [_res("u", "iam_user"), _res("k", "customer_secret_key", user="u")]
        )
        tf_dir = provider.output_dir / "terraform" / "oci"
        for path in tf_dir.glob("*.tf"):
            assert "secret_key_value" not in path.read_text()
