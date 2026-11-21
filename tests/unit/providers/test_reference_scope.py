"""Scoped doctor runs resolve names against the whole environment (#1568).

A run limited to a package reports only on the selected resources, but a name they
reference (a compartment, a VCN, a vswitch) may be defined in another package.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.protocols import ValidatesReferencesInContext
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationContext, ValidationLevel, ValidationReport
from infrafoundry.providers.aws import AWSProvider
from infrafoundry.providers.aws.validator import AWSValidator
from infrafoundry.providers.aws.validators.context import AWSConfigContext
from infrafoundry.providers.esxi.validator import EsxiValidator
from infrafoundry.providers.mikrotik import MikroTikProvider
from infrafoundry.providers.oci import OCIProvider
from infrafoundry.providers.oci.validator import OCIValidator
from infrafoundry.providers.proxmox import ProxmoxProvider
from infrafoundry.providers.proxmox.validator import ProxmoxValidator
from infrafoundry.providers.tailscale import TailscaleProvider
from tests.helpers.env import make_env_config

OCI_SETTINGS = {
    "tenancy_ocid": "ocid1.tenancy.oc1..example",
    "user_ocid": "ocid1.user.oc1..example",
    "fingerprint": "aa:bb",
    "private_key_path": "/tmp/k.pem",
    "region": "us-phoenix-1",
    "compartment_ocid": "ocid1.compartment.oc1..example",
}


def _errors(report: ValidationReport) -> list[str]:
    return [
        r.check_name for r in report.results if r.level == ValidationLevel.ERROR and not r.passed
    ]


def _oci(name: str, type_: str, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type=type_, provider="oci", config=config)


def _oci_validate(
    resources: list[ResourceConfig], refs: list[ResourceConfig] | None = None
) -> list[str]:
    report = ValidationReport()
    env = make_env_config(provider_settings={"oci": OCI_SETTINGS})
    validator = OCIValidator(env, report)
    with patch.object(validator, "_validate_api_references"):
        validator.validate_references(resources, refs)
    return _errors(report)


class TestOciScoped:
    """OCIValidator.validate_references with reference_resources."""

    def test_compartment_defined_in_another_package(self) -> None:
        """A bucket's compartment defined only in the reference set passes."""
        comp = _oci("example-compartment", "compartment", description="d")
        bucket = _oci("example-bucket", "bucket", compartment="example-compartment")
        assert _oci_validate([bucket], [comp, bucket]) == []

    def test_compartment_defined_nowhere_still_fails(self) -> None:
        """An undefined compartment is still reported on a scoped run."""
        bucket = _oci("example-bucket", "bucket", compartment="missing")
        assert "oci_compartment_ref_bucket_example-bucket" in _oci_validate([bucket], [bucket])

    def test_unscoped_behaviour_unchanged(self) -> None:
        """Without reference_resources the selected set is the whole lookup pool."""
        bucket = _oci("example-bucket", "bucket", compartment="example-compartment")
        assert _oci_validate([bucket]) == ["oci_compartment_ref_bucket_example-bucket"]

    def test_subnet_vcn_and_instance_subnet_cross_package(self) -> None:
        """Subnet to VCN and instance to subnet resolve against the reference set."""
        vcn = _oci("example-vcn", "vcn", cidr_block="10.0.0.0/16")
        subnet = _oci("example-subnet", "subnet", vcn="example-vcn", cidr_block="10.0.1.0/24")
        inst = _oci("example-vm", "instance", subnet="example-subnet")
        refs = [vcn, subnet, inst]
        assert _oci_validate([subnet], refs) == []
        assert _oci_validate([inst], refs) == []
        assert _oci_validate([subnet]) == ["oci_ref_subnet_example-subnet_vcn"]
        assert _oci_validate([inst]) == ["oci_ref_instance_example-vm_subnet"]

    def test_subnet_cidr_checks_use_reference_vcn(self) -> None:
        """A subnet outside a VCN defined elsewhere is reported."""
        vcn = _oci("example-vcn", "vcn", cidr_block="10.0.0.0/16")
        subnet = _oci("example-subnet", "subnet", vcn="example-vcn", cidr_block="192.0.2.0/24")
        assert _oci_validate([subnet], [vcn, subnet]) == [
            "oci_subnet_example-subnet_cidr_outside_vcn"
        ]

    def test_overlap_reported_only_when_a_selected_subnet_is_involved(self) -> None:
        """An overlap between two unselected subnets is not this run's finding."""
        vcn = _oci("example-vcn", "vcn", cidr_block="10.0.0.0/16")
        a = _oci("sub-a", "subnet", vcn="example-vcn", cidr_block="10.0.1.0/24")
        b = _oci("sub-b", "subnet", vcn="example-vcn", cidr_block="10.0.1.0/25")
        c = _oci("sub-c", "subnet", vcn="example-vcn", cidr_block="10.0.9.0/24")
        refs = [vcn, a, b, c]
        assert _oci_validate([c], refs) == []
        assert len(_oci_validate([a], refs)) == 1


class TestProviderDelegation:
    """validate_references_in_context hands reference_resources to the validator."""

    @pytest.mark.parametrize(
        ("provider_cls", "module", "validator"),
        [
            (OCIProvider, "infrafoundry.providers.oci", "OCIValidator"),
            (ProxmoxProvider, "infrafoundry.providers.proxmox", "ProxmoxValidator"),
            (TailscaleProvider, "infrafoundry.providers.tailscale", "TailscaleValidator"),
            (AWSProvider, "infrafoundry.providers.aws", "AWSValidator"),
        ],
    )
    def test_delegates(
        self, provider_cls: Any, module: str, validator: str, tmp_path: Path
    ) -> None:
        """The provider is context-aware and passes the reference list through."""
        provider = provider_cls(tmp_path, tmp_path)
        assert isinstance(provider, ValidatesReferencesInContext)
        res = [ResourceConfig(name="a", type="x", provider="p", config={})]
        ref = [*res]
        with patch(f"{module}.{validator}") as cls:
            provider.validate_references_in_context(res, ref, make_env_config(), ValidationReport())
            cls.return_value.validate_references.assert_called_once_with(res, ref)

    def test_mikrotik_delegates(self, tmp_path: Path) -> None:
        """MikroTik passes the reference list through."""
        provider = MikroTikProvider(tmp_path, tmp_path)
        assert isinstance(provider, ValidatesReferencesInContext)
        res = [ResourceConfig(name="a", type="x", provider="mikrotik", config={})]
        with patch("infrafoundry.providers.mikrotik.MikroTikValidator") as cls:
            provider.validate_references_in_context(
                res, [*res], make_env_config(), ValidationReport()
            )
            cls.return_value.validate_references.assert_called_once_with(res, [*res])


def test_proxmox_declared_vnets_include_reference_resources() -> None:
    """A vnet declared in another package counts as declared for a scoped run."""
    vnet = ResourceConfig(name="example-vnet", type="sdn_vnet", provider="proxmox", config={})
    vm = ResourceConfig(name="vm", type="vm", provider="proxmox", config={})
    validator = ProxmoxValidator(make_env_config(), ValidationReport())
    with (
        patch("infrafoundry.providers.proxmox.validator.ProxmoxClient") as client,
        patch("infrafoundry.providers.proxmox.validator.run_validators") as run,
        patch.object(validator, "validate_offline"),
        patch.object(validator, "_collect_resource_references", return_value=MagicMock()),
        patch.object(validator, "_get_cluster_vms", return_value=[]),
    ):
        client.from_provider_settings.return_value = MagicMock()
        validator.validate_references([vm], [vnet, vm])
        validator.validate_references([vm])
    scoped, unscoped = (c.args[1].declared_vnets for c in run.call_args_list[::2])
    assert scoped == frozenset({"example-vnet"})
    assert unscoped == frozenset()


def test_esxi_vswitch_and_portgroup_resolve_in_reference_set() -> None:
    """Portgroup to vswitch and VM to portgroup resolve across packages."""
    host = {"host": "esxi-01"}
    vswitch = ResourceConfig(name="vs", type="vswitch", provider="esxi", config=dict(host))
    pg = ResourceConfig(
        name="pg", type="portgroup", provider="esxi", config={**host, "vswitch": "vs"}
    )
    vm = ResourceConfig(
        name="vm",
        type="vm",
        provider="esxi",
        config={**host, "network": {"portgroup": "pg"}},
    )
    refs = [vswitch, pg, vm]
    for selected in ([pg], [vm]):
        report = ValidationReport()
        EsxiValidator(make_env_config(), report).validate_references(selected, refs)
        assert _errors(report) == []
    report = ValidationReport()
    EsxiValidator(make_env_config(), report).validate_references([pg])
    assert _errors(report) == ["esxi_portgroup_vswitch_pg"]


def test_esxi_provider_in_context_passes_references(tmp_path: Path) -> None:
    """The ESXi provider is context-aware and delegates."""
    from infrafoundry.providers.esxi import EsxiProvider

    provider = EsxiProvider(tmp_path, tmp_path)
    assert isinstance(provider, ValidatesReferencesInContext)
    res = [ResourceConfig(name="a", type="vswitch", provider="esxi", config={})]
    with patch("infrafoundry.providers.esxi.EsxiValidator") as cls:
        provider.validate_references_in_context(res, [*res], make_env_config(), ValidationReport())
        cls.return_value.validate_references.assert_called_once_with(res, [*res])


def test_aws_context_indexes_include_reference_resources() -> None:
    """Security group and instance names resolve against the reference set."""
    sg = ResourceConfig(name="example-sg", type="security_group", provider="aws", config={})
    inst = ResourceConfig(name="example-vm", type="instance", provider="aws", config={})
    vol = ResourceConfig(name="vol", type="ebs_volume", provider="aws", config={})
    ctx = AWSConfigContext.from_resources([vol], [sg, inst, vol])
    assert ctx.security_group_names == {"example-sg"}
    assert set(ctx.instances_by_name) == {"example-vm"}
    assert ctx.resources == [vol]
    assert AWSConfigContext.from_resources([vol]).security_group_names == frozenset()
    with patch("infrafoundry.providers.aws.validator.run_validators") as run:
        AWSValidator(make_env_config(), ValidationReport()).validate_references([vol], [sg, vol])
    assert run.call_args.args[1].security_group_names == {"example-sg"}


def test_base_context_reference_resources_default_empty() -> None:
    """The base context's reference list defaults to empty."""
    assert ValidationContext().reference_resources == []
