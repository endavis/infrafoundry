"""Unit tests for Proxmox TemplateValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.proxmox.validator import ClusterVM
from infrafoundry.providers.proxmox.validators.template_validator import TemplateValidator


@pytest.fixture
def report() -> MagicMock:
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(report: MagicMock) -> TemplateValidator:
    """Create a TemplateValidator instance."""
    return TemplateValidator(report)


def test_validate_template_by_vmid_found(validator: TemplateValidator, report: MagicMock) -> None:
    """Test validation of template found by VMID."""
    cluster_vms: list[ClusterVM] = [
        {"vmid": 100, "name": "ubuntu-22.04", "template": 1},
        {"vmid": 101, "name": "debian-12", "template": 1},
    ]

    validator.validate(cluster_vms, {"100": ["vm1"]})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True
    assert "100" in call_args["message"]
    assert "ubuntu-22.04" in call_args["message"]


def test_validate_template_by_vmid_not_found(
    validator: TemplateValidator, report: MagicMock
) -> None:
    """Test validation of template not found by VMID."""
    cluster_vms: list[ClusterVM] = [
        {"vmid": 100, "name": "ubuntu-22.04", "template": 1},
    ]

    validator.validate(cluster_vms, {"999": ["vm1", "vm2"]})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "999" in call_args["message"]
    assert "not found" in call_args["message"]
    assert "vm1" in call_args["message"]


def test_validate_template_by_name_found(validator: TemplateValidator, report: MagicMock) -> None:
    """Test validation of template found by name."""
    cluster_vms: list[ClusterVM] = [
        {"vmid": 100, "name": "ubuntu-22.04", "template": 1},
    ]

    validator.validate(cluster_vms, {"ubuntu-22.04": ["vm1"]})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True
    assert "ubuntu-22.04" in call_args["message"]
    assert "100" in str(call_args["message"])  # Shows VMID


def test_validate_template_by_name_not_found(
    validator: TemplateValidator, report: MagicMock
) -> None:
    """Test validation of template not found by name."""
    cluster_vms: list[ClusterVM] = [
        {"vmid": 100, "name": "ubuntu-22.04", "template": 1},
    ]

    validator.validate(cluster_vms, {"missing-template": ["vm1"]})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "not found" in call_args["message"]
    assert "missing-template" in call_args["message"]


def test_validate_ignores_non_templates(validator: TemplateValidator, report: MagicMock) -> None:
    """Test that non-template VMs are ignored."""
    cluster_vms: list[ClusterVM] = [
        {"vmid": 100, "name": "ubuntu-22.04", "template": 1},
        {"vmid": 200, "name": "regular-vm", "template": 0},
    ]

    validator.validate(cluster_vms, {"ubuntu-22.04": ["vm1"]})

    # Should find the template, not the regular VM
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True


def test_validate_empty_template_refs(validator: TemplateValidator, report: MagicMock) -> None:
    """Test validation with no template references."""
    cluster_vms: list[ClusterVM] = [
        {"vmid": 100, "name": "ubuntu-22.04", "template": 1},
    ]

    validator.validate(cluster_vms, {})

    report.add_check.assert_not_called()


def test_validate_cluster_vms_none(validator: TemplateValidator, report: MagicMock) -> None:
    """Test validation when cluster VMs fetch failed."""
    validator.validate(None, {"100": ["vm1"]})

    report.add_check.assert_not_called()


def test_validate_multiple_templates(validator: TemplateValidator, report: MagicMock) -> None:
    """Test validation of multiple template references."""
    cluster_vms: list[ClusterVM] = [
        {"vmid": 100, "name": "ubuntu-22.04", "template": 1},
        {"vmid": 101, "name": "debian-12", "template": 1},
    ]

    validator.validate(
        cluster_vms,
        {
            "100": ["vm1"],
            "debian-12": ["vm2", "vm3"],
        },
    )

    assert report.add_check.call_count == 2


def test_validate_template_used_by_multiple_resources(
    validator: TemplateValidator, report: MagicMock
) -> None:
    """Test template referenced by multiple resources."""
    cluster_vms: list[ClusterVM] = [
        {"vmid": 100, "name": "ubuntu-22.04", "template": 1},
    ]

    validator.validate(cluster_vms, {"100": ["vm1", "vm2", "vm3"]})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True


def test_validate_skips_templates_missing_a_key(
    validator: TemplateValidator, report: MagicMock
) -> None:
    """A template entry without ``vmid`` or ``name`` is skipped, not a ``KeyError`` (#1121)."""
    cluster_vms: list[ClusterVM] = [
        {"name": "no-vmid", "template": 1},
        {"vmid": 101, "template": 1},
        {"vmid": 100, "name": "ubuntu-22.04", "template": 1},
    ]

    validator.validate(cluster_vms, {"100": ["vm1"], "101": ["vm2"], "ubuntu-22.04": ["vm3"]})

    passed = {c.kwargs["check_name"]: c.kwargs["passed"] for c in report.add_check.call_args_list}
    assert passed["proxmox_template_vmid_100"] is True
    assert passed["proxmox_template_vmid_101"] is True
    assert all(passed.values())
