"""Unit tests for the OPNsense ``VLANValidator`` (ADR-0014 §7).

Coverage:
    - ``device`` reference checking against the live NIC list.
    - ``tag`` range (1-4094).
    - ``priority`` range (0-7).
    - ``lock`` must be a boolean if present.
    - The pre-existing ``parent`` field bug is fixed: validator now reads
      ``device`` (which is what the YAML/template surface uses).
"""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.vlan_validator import VLANValidator


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(report):
    """Create a VLANValidator instance."""
    return VLANValidator(report)


def _vlan(name: str, **config_overrides) -> ResourceConfig:
    base = {
        "device": "em0",
        "tag": 100,
        "description": "test",
        "priority": 0,
    }
    base.update(config_overrides)
    return ResourceConfig(name=name, type="interfaces.vlans", provider="opnsense", config=base)


# ---------------------------------------------------------------------------
# device validation
# ---------------------------------------------------------------------------


def test_validate_device_found(validator, report):
    """VLAN with existing parent NIC passes the device check."""
    validator.validate([_vlan("vlan100", device="em0")], {"em0": {"device": "em0"}})

    # First call should be the device check (passed=True at INFO level).
    device_calls = [
        call
        for call in report.add_check.call_args_list
        if call[1]["check_name"] == "vlan_vlan100_device"
    ]
    assert len(device_calls) == 1
    assert device_calls[0][1]["passed"] is True
    assert "em0" in device_calls[0][1]["message"]
    assert device_calls[0][1]["level"] == ValidationLevel.INFO


def test_validate_device_not_found(validator, report):
    """Bad device reference is reported as ERROR."""
    validator.validate([_vlan("vlan100", device="missing")], {"em0": {}})

    device_calls = [
        call
        for call in report.add_check.call_args_list
        if call[1]["check_name"] == "vlan_vlan100_device"
    ]
    assert len(device_calls) == 1
    assert device_calls[0][1]["passed"] is False
    assert "missing" in device_calls[0][1]["message"]
    assert device_calls[0][1]["level"] == ValidationLevel.ERROR


def test_validate_no_device_skipped(validator, report):
    """Absence of ``device`` is not a validator concern (caught by config loader)."""
    vlan = ResourceConfig(
        name="v",
        type="interfaces.vlans",
        provider="opnsense",
        config={},
    )
    validator.validate([vlan], {"em0": {}})
    device_calls = [
        call for call in report.add_check.call_args_list if call[1]["check_name"] == "vlan_v_device"
    ]
    assert device_calls == []


def test_validate_empty_vlans(validator, report):
    """Empty VLAN list yields no checks."""
    validator.validate([], {"em0": {}})
    report.add_check.assert_not_called()


def test_validate_multiple_vlans(validator, report):
    """Each VLAN is validated independently."""
    vlans = [
        _vlan("vlan100", device="em0"),
        _vlan("vlan200", device="em1"),
    ]
    validator.validate(vlans, {"em0": {}, "em1": {}})

    device_calls = [
        call
        for call in report.add_check.call_args_list
        if call[1]["check_name"].endswith("_device")
    ]
    assert len(device_calls) == 2
    for call in device_calls:
        assert call[1]["passed"] is True


def test_validate_mixed_results(validator, report):
    """Pass + fail in the same batch."""
    vlans = [
        _vlan("vlan100", device="em0"),
        _vlan("vlan200", device="missing"),
    ]
    validator.validate(vlans, {"em0": {}})
    device_calls = sorted(
        (
            call
            for call in report.add_check.call_args_list
            if call[1]["check_name"].endswith("_device")
        ),
        key=lambda c: c[1]["check_name"],
    )
    assert device_calls[0][1]["passed"] is True  # vlan100
    assert device_calls[1][1]["passed"] is False  # vlan200


# ---------------------------------------------------------------------------
# tag validation
# ---------------------------------------------------------------------------


def test_validate_tag_in_range_emits_no_error(validator, report):
    validator.validate([_vlan("v1", tag=100)], {"em0": {}})
    tag_errors = [c for c in report.add_check.call_args_list if c[1]["check_name"] == "vlan_v1_tag"]
    assert tag_errors == []


def test_validate_tag_out_of_range_high(validator, report):
    validator.validate([_vlan("v1", tag=5000)], {"em0": {}})
    tag_calls = [c for c in report.add_check.call_args_list if c[1]["check_name"] == "vlan_v1_tag"]
    assert len(tag_calls) == 1
    assert tag_calls[0][1]["passed"] is False


def test_validate_tag_out_of_range_low(validator, report):
    validator.validate([_vlan("v1", tag=0)], {"em0": {}})
    tag_calls = [c for c in report.add_check.call_args_list if c[1]["check_name"] == "vlan_v1_tag"]
    assert len(tag_calls) == 1
    assert tag_calls[0][1]["passed"] is False


def test_validate_tag_non_integer(validator, report):
    validator.validate([_vlan("v1", tag="not-int")], {"em0": {}})
    tag_calls = [c for c in report.add_check.call_args_list if c[1]["check_name"] == "vlan_v1_tag"]
    assert len(tag_calls) == 1
    assert tag_calls[0][1]["passed"] is False


# ---------------------------------------------------------------------------
# priority validation
# ---------------------------------------------------------------------------


def test_validate_priority_in_range_emits_no_error(validator, report):
    validator.validate([_vlan("v1", priority=3)], {"em0": {}})
    priority_calls = [
        c for c in report.add_check.call_args_list if c[1]["check_name"] == "vlan_v1_priority"
    ]
    assert priority_calls == []


def test_validate_priority_out_of_range(validator, report):
    validator.validate([_vlan("v1", priority=9)], {"em0": {}})
    priority_calls = [
        c for c in report.add_check.call_args_list if c[1]["check_name"] == "vlan_v1_priority"
    ]
    assert len(priority_calls) == 1
    assert priority_calls[0][1]["passed"] is False


def test_validate_priority_non_integer(validator, report):
    validator.validate([_vlan("v1", priority="x")], {"em0": {}})
    priority_calls = [
        c for c in report.add_check.call_args_list if c[1]["check_name"] == "vlan_v1_priority"
    ]
    assert len(priority_calls) == 1
    assert priority_calls[0][1]["passed"] is False


# ---------------------------------------------------------------------------
# lock validation (ADR-0014 §6)
# ---------------------------------------------------------------------------


def test_validate_lock_boolean_true_passes(validator, report):
    validator.validate([_vlan("v1", lock=True)], {"em0": {}})
    lock_calls = [
        c for c in report.add_check.call_args_list if c[1]["check_name"] == "vlan_v1_lock"
    ]
    # No error is emitted for a valid bool — only the failure path adds.
    assert lock_calls == []


def test_validate_lock_boolean_false_passes(validator, report):
    validator.validate([_vlan("v1", lock=False)], {"em0": {}})
    lock_calls = [
        c for c in report.add_check.call_args_list if c[1]["check_name"] == "vlan_v1_lock"
    ]
    assert lock_calls == []


def test_validate_lock_must_be_boolean(validator, report):
    validator.validate([_vlan("v1", lock="yes")], {"em0": {}})
    lock_calls = [
        c for c in report.add_check.call_args_list if c[1]["check_name"] == "vlan_v1_lock"
    ]
    assert len(lock_calls) == 1
    assert lock_calls[0][1]["passed"] is False
    assert "boolean" in lock_calls[0][1]["message"]


def test_validate_lock_absent_skipped(validator, report):
    validator.validate([_vlan("v1")], {"em0": {}})
    lock_calls = [
        c for c in report.add_check.call_args_list if c[1]["check_name"] == "vlan_v1_lock"
    ]
    assert lock_calls == []
