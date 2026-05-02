"""Unit tests for ``InterfaceAssignmentValidator``.

Coverage:
    - ``device:`` references a physical NIC → pass.
    - ``device:`` references a managed VLAN by name → pass.
    - ``device:`` is ``<nic>_vlan<tag>`` and both parts valid → pass.
    - ``device:`` references unknown things → ERROR.
    - Forward-compat field type checks (``description``, ``enabled``,
      ``lock``, ``ipv4``, ``ipv6``).
"""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.interface_assignment_validator import (
    InterfaceAssignmentValidator,
)


def _resource(
    name: str,
    *,
    device: Any = "ixl1",
    description: Any = None,
    enabled: Any = None,
    lock: Any = None,
    ipv4: Any = None,
    ipv6: Any = None,
) -> ResourceConfig:
    config: dict[str, Any] = {}
    if device is not None:
        config["device"] = device
    if description is not None:
        config["description"] = description
    if enabled is not None:
        config["enabled"] = enabled
    if lock is not None:
        config["lock"] = lock
    if ipv4 is not None:
        config["ipv4"] = ipv4
    if ipv6 is not None:
        config["ipv6"] = ipv6
    return ResourceConfig(
        name=name, type="interface_assignments", provider="opnsense", config=config
    )


@pytest.fixture
def report() -> ValidationReport:
    return ValidationReport()


@pytest.fixture
def validator(report: ValidationReport) -> InterfaceAssignmentValidator:
    return InterfaceAssignmentValidator(report)


# ---------------------------------------------------------------------------
# device — happy paths
# ---------------------------------------------------------------------------


class TestDeviceResolution:
    def test_physical_nic_passes(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate(
            [_resource("lan", device="ixl1")],
            vlan_names=set(),
            existing_interfaces={"ixl0": {}, "ixl1": {}},
        )
        assert all(c.passed for c in report.results)

    def test_managed_vlan_name_passes(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate(
            [_resource("storage", device="vlan-storage")],
            vlan_names={"vlan-storage"},
            existing_interfaces={"ixl0": {}, "ixl1": {}},
        )
        assert all(c.passed for c in report.results)

    def test_vlan_child_notation_passes(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        # The OPNsense convention: <nic>_vlan<tag>
        validator.validate(
            [_resource("wan-vlan", device="ixl0_vlan4000")],
            vlan_names=set(),
            existing_interfaces={"ixl0": {}},
        )
        assert all(c.passed for c in report.results)

    def test_vlan_child_with_underscored_nic_passes(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        # NIC names sometimes contain underscores (less common but possible).
        validator.validate(
            [_resource("foo", device="igb_0_vlan100")],
            vlan_names=set(),
            existing_interfaces={"igb_0": {}},
        )
        assert all(c.passed for c in report.results)


# ---------------------------------------------------------------------------
# device — error paths
# ---------------------------------------------------------------------------


class TestDeviceErrors:
    def test_unknown_nic_fails(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate(
            [_resource("lan", device="igc0")],
            vlan_names=set(),
            existing_interfaces={"ixl0": {}, "ixl1": {}},
        )
        device_checks = [
            c for c in report.results if c.check_name == "interface_assignment_lan_device"
        ]
        assert any(not c.passed for c in device_checks)
        assert any(c.level == ValidationLevel.ERROR for c in device_checks)

    def test_vlan_child_with_unknown_nic_fails(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate(
            [_resource("wan-vlan", device="igc0_vlan100")],
            vlan_names=set(),
            existing_interfaces={"ixl0": {}},
        )
        device_checks = [
            c for c in report.results if c.check_name == "interface_assignment_wan-vlan_device"
        ]
        assert any(not c.passed for c in device_checks)

    def test_vlan_child_with_out_of_range_tag_fails(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate(
            [_resource("bad", device="ixl0_vlan5000")],
            vlan_names=set(),
            existing_interfaces={"ixl0": {}},
        )
        device_checks = [
            c for c in report.results if c.check_name == "interface_assignment_bad_device"
        ]
        assert any(not c.passed for c in device_checks)

    def test_empty_string_device_fails(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate(
            [_resource("lan", device="")],
            vlan_names=set(),
            existing_interfaces={"ixl0": {}},
        )
        assert any(
            not c.passed and c.check_name == "interface_assignment_lan_device"
            for c in report.results
        )

    def test_non_string_device_fails(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate(
            [_resource("lan", device=123)],
            vlan_names=set(),
            existing_interfaces={"ixl0": {}},
        )
        assert any(
            not c.passed and c.check_name == "interface_assignment_lan_device"
            for c in report.results
        )

    def test_missing_device_skipped(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        # Missing device is the load-time required-field check's job —
        # this validator should not error here.
        validator.validate(
            [_resource("lan", device=None)],
            vlan_names=set(),
            existing_interfaces={"ixl0": {}},
        )
        device_checks = [
            c for c in report.results if c.check_name == "interface_assignment_lan_device"
        ]
        assert device_checks == []


# ---------------------------------------------------------------------------
# Forward-compat field types
# ---------------------------------------------------------------------------


class TestFieldTypes:
    def test_non_string_description_fails(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate(
            [_resource("lan", description=123)],
            vlan_names=set(),
            existing_interfaces={"ixl1": {}},
        )
        assert any(
            not c.passed and c.check_name == "interface_assignment_lan_description"
            for c in report.results
        )

    def test_non_bool_enabled_fails(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate(
            [_resource("lan", enabled="yes")],
            vlan_names=set(),
            existing_interfaces={"ixl1": {}},
        )
        assert any(
            not c.passed and c.check_name == "interface_assignment_lan_enabled"
            for c in report.results
        )

    def test_non_bool_lock_fails(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate(
            [_resource("lan", lock="yes")],
            vlan_names=set(),
            existing_interfaces={"ixl1": {}},
        )
        assert any(
            not c.passed and c.check_name == "interface_assignment_lan_lock" for c in report.results
        )

    def test_non_dict_ipv4_fails(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate(
            [_resource("lan", ipv4="static")],
            vlan_names=set(),
            existing_interfaces={"ixl1": {}},
        )
        assert any(
            not c.passed and c.check_name == "interface_assignment_lan_ipv4" for c in report.results
        )

    def test_non_dict_ipv6_fails(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate(
            [_resource("lan", ipv6=["track6"])],
            vlan_names=set(),
            existing_interfaces={"ixl1": {}},
        )
        assert any(
            not c.passed and c.check_name == "interface_assignment_lan_ipv6" for c in report.results
        )

    def test_dict_ipv4_passes(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate(
            [_resource("lan", ipv4={"mode": "static", "address": "10.0.0.1/24"})],
            vlan_names=set(),
            existing_interfaces={"ixl1": {}},
        )
        # No ipv4 check failure — the only check should be the device pass.
        ipv4_failures = [
            c
            for c in report.results
            if c.check_name == "interface_assignment_lan_ipv4" and not c.passed
        ]
        assert ipv4_failures == []

    def test_none_ipv4_skipped(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        # YAML "ipv4:" with no value parses to None — validator must not error.
        validator.validate(
            [_resource("lan", ipv4=None)],
            vlan_names=set(),
            existing_interfaces={"ixl1": {}},
        )
        ipv4_failures = [
            c
            for c in report.results
            if c.check_name == "interface_assignment_lan_ipv4" and not c.passed
        ]
        assert ipv4_failures == []

    def test_string_description_passes_silently(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate(
            [_resource("lan", description="The LAN interface")],
            vlan_names=set(),
            existing_interfaces={"ixl1": {}},
        )
        # Only the device-pass check should be present; no description failure.
        description_failures = [
            c
            for c in report.results
            if c.check_name == "interface_assignment_lan_description" and not c.passed
        ]
        assert description_failures == []

    def test_bool_enabled_passes_silently(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate(
            [_resource("lan", enabled=False)],
            vlan_names=set(),
            existing_interfaces={"ixl1": {}},
        )
        enabled_failures = [
            c
            for c in report.results
            if c.check_name == "interface_assignment_lan_enabled" and not c.passed
        ]
        assert enabled_failures == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_assignments_list(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate([], vlan_names=set(), existing_interfaces={})
        assert report.results == []

    def test_multiple_assignments_all_validated(
        self,
        validator: InterfaceAssignmentValidator,
        report: ValidationReport,
    ) -> None:
        validator.validate(
            [
                _resource("lan", device="ixl1"),
                _resource("wan", device="ixl0"),
                _resource("opt1", device="ixl0_vlan4000"),
            ],
            vlan_names=set(),
            existing_interfaces={"ixl0": {}, "ixl1": {}},
        )
        # Each assignment yields a device check; all should pass.
        device_checks = [c for c in report.results if c.check_name.endswith("_device")]
        assert len(device_checks) == 3
        assert all(c.passed for c in device_checks)
