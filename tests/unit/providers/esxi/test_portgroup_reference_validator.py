"""Unit tests for ESXi PortgroupReferenceValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.esxi.validators.portgroup_reference_validator import (
    PortgroupReferenceValidator,
)


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(report):
    """Create a PortgroupReferenceValidator instance."""
    return PortgroupReferenceValidator(report)


def _make_portgroup(name: str, host: str = "esxi-01") -> ResourceConfig:
    """Create a portgroup resource."""
    return ResourceConfig(
        name=name,
        type="portgroup",
        provider="esxi",
        config={"host": host, "vswitch": "vSwitch1"},
    )


def _make_vm(
    name: str, network: list | dict | None = None, host: str = "esxi-01"
) -> ResourceConfig:
    """Create a VM resource."""
    config: dict = {"host": host, "name": name}
    if network is not None:
        config["network"] = network
    return ResourceConfig(name=name, type="vm", provider="esxi", config=config)


def test_valid_reference(validator, report):
    """Test VM referencing existing portgroup on same host."""
    resources = [
        _make_portgroup("VM Network", "esxi-01"),
        _make_vm("vm1", network=[{"portgroup": "VM Network"}], host="esxi-01"),
    ]
    validator.validate(resources)

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True
    assert "VM Network" in call_args["message"]


def test_invalid_reference_wrong_host(validator, report):
    """Test VM referencing portgroup on different host."""
    resources = [
        _make_portgroup("VM Network", "esxi-01"),
        _make_vm("vm1", network=[{"portgroup": "VM Network"}], host="esxi-02"),
    ]
    validator.validate(resources)

    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "does not exist" in call_args["message"]


def test_invalid_reference_missing_portgroup(validator, report):
    """Test VM referencing non-existent portgroup."""
    resources = [
        _make_vm("vm1", network=[{"portgroup": "ghost-pg"}], host="esxi-01"),
    ]
    validator.validate(resources)

    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "ghost-pg" in call_args["message"]


def test_vm_with_no_network(validator, report):
    """Test VM without network config produces no checks."""
    resources = [
        _make_portgroup("VM Network", "esxi-01"),
        _make_vm("vm1", network=None, host="esxi-01"),
    ]
    validator.validate(resources)
    report.add_check.assert_not_called()


def test_vm_with_dict_network(validator, report):
    """Test VM with single dict network config."""
    resources = [
        _make_portgroup("VM Network", "esxi-01"),
        _make_vm("vm1", network={"portgroup": "VM Network"}, host="esxi-01"),
    ]
    validator.validate(resources)

    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True


def test_vm_with_multiple_nics(validator, report):
    """Test VM with multiple NICs referencing different portgroups."""
    resources = [
        _make_portgroup("pg-mgmt", "esxi-01"),
        _make_portgroup("pg-storage", "esxi-01"),
        _make_vm(
            "vm1",
            network=[
                {"portgroup": "pg-mgmt"},
                {"portgroup": "pg-storage"},
            ],
            host="esxi-01",
        ),
    ]
    validator.validate(resources)
    assert report.add_check.call_count == 2
    for call in report.add_check.call_args_list:
        assert call[1]["passed"] is True


def test_vm_nic_without_portgroup_ref(validator, report):
    """Test VM NIC without portgroup reference is skipped."""
    resources = [
        _make_vm("vm1", network=[{"virtual_network": "VM Network"}], host="esxi-01"),
    ]
    validator.validate(resources)
    report.add_check.assert_not_called()


def test_no_vms(validator, report):
    """Test with no VM resources."""
    resources = [_make_portgroup("VM Network")]
    validator.validate(resources)
    report.add_check.assert_not_called()


def test_no_resources(validator, report):
    """Test with empty resource list."""
    validator.validate([])
    report.add_check.assert_not_called()
