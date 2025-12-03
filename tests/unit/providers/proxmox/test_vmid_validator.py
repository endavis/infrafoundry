"""Unit tests for Proxmox VMIDValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.proxmox.validators.vmid_validator import VMIDValidator


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(report):
    """Create a VMIDValidator instance."""
    return VMIDValidator(report)


def test_validate_vmid_available(validator, report):
    """Test validation of available VMID."""
    cluster_vms = [
        {"vmid": 100, "name": "existing-vm"},
    ]

    validator.validate(cluster_vms, {200: "new-vm"})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True
    assert "200" in call_args["message"]
    assert "available" in call_args["message"]


def test_validate_vmid_conflict_different_name(validator, report):
    """Test validation of VMID conflict with different VM name."""
    cluster_vms = [
        {"vmid": 100, "name": "existing-vm"},
    ]

    validator.validate(cluster_vms, {100: "new-vm"})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "100" in call_args["message"]
    assert "already in use" in call_args["message"]
    assert "existing-vm" in call_args["message"]


def test_validate_vmid_exists_same_name(validator, report):
    """Test validation of VMID that already exists with same name (update scenario)."""
    cluster_vms = [
        {"vmid": 100, "name": "my-vm"},
    ]

    validator.validate(cluster_vms, {100: "my-vm"})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True
    assert "100" in call_args["message"]
    assert "already exists" in call_args["message"]
    assert "update" in call_args["message"].lower() or "recreation" in call_args["message"].lower()


def test_validate_empty_vmids(validator, report):
    """Test validation with no VMIDs."""
    cluster_vms = [
        {"vmid": 100, "name": "existing-vm"},
    ]

    validator.validate(cluster_vms, {})

    report.add_check.assert_not_called()


def test_validate_cluster_vms_none(validator, report):
    """Test validation when cluster VMs fetch failed."""
    validator.validate(None, {200: "new-vm"})

    report.add_check.assert_not_called()


def test_validate_multiple_vmids(validator, report):
    """Test validation of multiple VMIDs."""
    cluster_vms = [
        {"vmid": 100, "name": "existing-vm"},
    ]

    validator.validate(
        cluster_vms,
        {
            100: "existing-vm",  # Update
            200: "new-vm1",  # Available
            300: "new-vm2",  # Available
        },
    )

    assert report.add_check.call_count == 3


def test_validate_vm_without_name(validator, report):
    """Test validation with VM that has no name field."""
    cluster_vms = [
        {"vmid": 100},  # No name field
    ]

    validator.validate(cluster_vms, {100: "new-vm"})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "N/A" in call_args["message"]  # Falls back to N/A


def test_validate_all_vmids_available(validator, report):
    """Test validation when all VMIDs are available."""
    cluster_vms = [
        {"vmid": 100, "name": "existing-vm"},
    ]

    validator.validate(
        cluster_vms,
        {
            200: "new-vm1",
            300: "new-vm2",
            400: "new-vm3",
        },
    )

    assert report.add_check.call_count == 3
    # All should pass
    for call in report.add_check.call_args_list:
        assert call[1]["passed"] is True


def test_validate_all_vmids_conflicts(validator, report):
    """Test validation when all VMIDs have conflicts."""
    cluster_vms = [
        {"vmid": 100, "name": "vm1"},
        {"vmid": 200, "name": "vm2"},
    ]

    validator.validate(
        cluster_vms,
        {
            100: "different-name1",
            200: "different-name2",
        },
    )

    assert report.add_check.call_count == 2
    # All should fail
    for call in report.add_check.call_args_list:
        assert call[1]["passed"] is False
