"""Tests for compartment rendering and compartment-aware generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.exceptions import ConfigurationError
from infrafoundry.core.provider import ResourceConfig
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


def _comp(name: str, **config: Any) -> ResourceConfig:
    config.setdefault("description", "A compartment")
    return _res(name, "compartment", **config)


class TestCompartmentTemplate:
    """Tests for compartments.tf.j2."""

    def test_renders_defaults(self, provider: OCIProvider) -> None:
        """A compartment defaults to the tenancy parent and enable_delete false."""
        provider.generate_terraform([_comp("workload-comp")])
        content = _tf(provider, "compartments.tf")
        assert 'resource "oci_identity_compartment" "workload_comp"' in content
        assert "compartment_id = var.oci_tenancy_ocid" in content
        assert 'name           = "workload-comp"' in content
        assert "enable_delete  = false" in content

    def test_enable_delete_and_escaped_description(self, provider: OCIProvider) -> None:
        """enable_delete renders true and the description is escaped."""
        provider.generate_terraform([_comp("c", enable_delete=True, description='say "hi"')])
        content = _tf(provider, "compartments.tf")
        assert "enable_delete  = true" in content
        assert 'description    = "say \\"hi\\""' in content

    def test_nested_parent_and_ocid_parent(self, provider: OCIProvider) -> None:
        """A parent name is a reference and a parent OCID is a literal."""
        provider.generate_terraform([_comp("top", parent=OCID), _comp("child-comp", parent="top")])
        content = _tf(provider, "compartments.tf")
        assert f'compartment_id = "{OCID}"' in content
        assert "compartment_id = oci_identity_compartment.top.id" in content

    def test_output_guarded(self, provider: OCIProvider) -> None:
        """compartment_ids output exists only with compartments."""
        provider.generate_terraform([_comp("c")])
        assert 'output "compartment_ids"' in _tf(provider, "outputs.tf")
        provider.generate_terraform([_res("v", "vcn", cidr_block="192.0.2.0/24")])
        assert "compartment_ids" not in _tf(provider, "outputs.tf")


class TestCompartmentReferences:
    """VCN, subnet and instance honour the compartment field."""

    def test_by_name(self, provider: OCIProvider) -> None:
        """A compartment name renders as a resource reference on every resource."""
        provider.generate_terraform(
            [
                _comp("workload-comp"),
                _res(
                    "v",
                    "vcn",
                    cidr_block="192.0.2.0/24",
                    compartment="workload-comp",
                    internet_gateway=True,
                    nat_gateway=True,
                    security_list={"ingress_rules": []},
                ),
                _res(
                    "s",
                    "subnet",
                    vcn="v",
                    cidr_block="192.0.2.0/25",
                    compartment="workload-comp",
                ),
                _res(
                    "i",
                    "instance",
                    subnet="s",
                    shape="VM.Standard.A1.Flex",
                    image="img",
                    compartment="workload-comp",
                ),
            ]
        )
        ref = "compartment_id = oci_identity_compartment.workload_comp.id"
        assert _tf(provider, "vcn.tf").count(ref) == 7
        assert "compartment_id      = oci_identity_compartment.workload_comp.id" in _tf(
            provider, "instances.tf"
        )
        assert "var.oci_compartment_ocid" not in _tf(provider, "vcn.tf")

    def test_by_ocid(self, provider: OCIProvider) -> None:
        """An OCID renders as a quoted literal."""
        provider.generate_terraform([_res("v", "vcn", cidr_block="192.0.2.0/24", compartment=OCID)])
        assert f'compartment_id = "{OCID}"' in _tf(provider, "vcn.tf")

    def test_no_compartments_unchanged(self, provider: OCIProvider) -> None:
        """Without compartments the fallback variable is used and no file is written."""
        provider.generate_terraform([_res("v", "vcn", cidr_block="192.0.2.0/24")])
        assert "compartment_id = var.oci_compartment_ocid" in _tf(provider, "vcn.tf")
        tf_dir = provider.output_dir / "terraform" / "oci"
        assert not (tf_dir / "compartments.tf").exists()

    def test_unknown_name_raises(self, provider: OCIProvider) -> None:
        """An undefined compartment name raises ConfigurationError."""
        with pytest.raises(ConfigurationError):
            provider.generate_terraform(
                [_res("v", "vcn", cidr_block="192.0.2.0/24", compartment="ghost")]
            )

    def test_input_resources_not_mutated(self, provider: OCIProvider) -> None:
        """Resolution works on copies."""
        vcn = _res("v", "vcn", cidr_block="192.0.2.0/24", compartment=OCID)
        provider.generate_terraform([vcn])
        assert "compartment_id_expr" not in vcn.config


def test_variable_default(provider: OCIProvider) -> None:
    """oci_compartment_ocid has an empty default."""
    provider.generate_terraform([_comp("c")])
    content = _tf(provider, "variables.tf")
    block = content.split('variable "oci_compartment_ocid"')[1].split("}")[0]
    assert 'default     = ""' in block


def test_type_registration(provider: OCIProvider) -> None:
    """The compartment type is registered."""
    assert "compartment" in provider.get_resource_types()
    assert provider.get_terraform_resource_types()["compartment"] == ["oci_identity_compartment"]
    assert provider.get_dependencies()["compartment"] == []


def test_validate_offline_passes_reference_resources(provider: OCIProvider) -> None:
    """validate_offline hands reference_resources to the validator."""
    from unittest.mock import MagicMock, patch

    resources = [_res("v", "vcn", cidr_block="192.0.2.0/24")]
    refs = [_comp("c")]
    with patch("infrafoundry.providers.oci.OCIValidator") as validator_cls:
        provider.validate_offline(resources, refs, MagicMock(), MagicMock())
    validator_cls.return_value.validate_offline.assert_called_once_with(resources, refs)
