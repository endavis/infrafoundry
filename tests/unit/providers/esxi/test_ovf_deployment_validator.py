"""Unit tests for ESXi OvfDeploymentValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.esxi.validators.ovf_deployment_validator import (
    OvfDeploymentValidator,
)


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(report):
    """Create an OvfDeploymentValidator instance."""
    return OvfDeploymentValidator(report)


def _make_ovf_deployment(name: str = "ontap-node-01", **config_overrides) -> ResourceConfig:
    """Create an ovf_deployment resource."""
    config: dict = {
        "host": "esxi-01",
        "ovf_source": "/path/to/vsim.ovf",
        "disk_store": "datastore1",
        "vm_name": "ontap-node-01",
        "network_map": {
            "hostonly": "PG-Cluster-esx-01",
            "nat": "PG-Management-esx-01",
        },
        **config_overrides,
    }
    return ResourceConfig(name=name, type="ovf_deployment", provider="esxi", config=config)


class TestOvfDeploymentValidatorRequired:
    """Tests for required field validation."""

    def test_valid_config_passes(self, validator, report):
        """Valid OVF deployment config should pass all checks."""
        validator.validate([_make_ovf_deployment()])

        calls = [c[1] for c in report.add_check.call_args_list]
        failed = [c for c in calls if not c["passed"]]
        # Only the ovf_source file warning might appear, but all required checks pass
        error_fails = [c for c in failed if c.get("level") == ValidationLevel.ERROR]
        assert len(error_fails) == 0

    def test_missing_host_error(self, validator, report):
        """Missing host should produce an error."""
        validator.validate([_make_ovf_deployment(host="")])

        calls = [c[1] for c in report.add_check.call_args_list]
        host_check = [
            c
            for c in calls
            if "host" in c["check_name"]
            and "ovf_source" not in c["check_name"]
            and "disk_store" not in c["check_name"]
            and "network_map" not in c["check_name"]
            and "exists" not in c["check_name"]
        ]
        assert len(host_check) == 1
        assert host_check[0]["passed"] is False
        assert host_check[0]["level"] == ValidationLevel.ERROR
        assert "missing required field 'host'" in host_check[0]["message"]

    def test_missing_ovf_source_error(self, validator, report):
        """Missing ovf_source should produce an error."""
        validator.validate([_make_ovf_deployment(ovf_source="")])

        calls = [c[1] for c in report.add_check.call_args_list]
        source_check = [
            c for c in calls if "ovf_source" in c["check_name"] and "exists" not in c["check_name"]
        ]
        assert len(source_check) == 1
        assert source_check[0]["passed"] is False
        assert source_check[0]["level"] == ValidationLevel.ERROR

    def test_missing_disk_store_error(self, validator, report):
        """Missing disk_store should produce an error."""
        validator.validate([_make_ovf_deployment(disk_store="")])

        calls = [c[1] for c in report.add_check.call_args_list]
        store_check = [c for c in calls if "disk_store" in c["check_name"]]
        assert len(store_check) == 1
        assert store_check[0]["passed"] is False
        assert store_check[0]["level"] == ValidationLevel.ERROR

    def test_missing_network_map_error(self, validator, report):
        """Missing network_map should produce an error."""
        resource = _make_ovf_deployment()
        del resource.config["network_map"]
        validator.validate([resource])

        calls = [c[1] for c in report.add_check.call_args_list]
        map_check = [c for c in calls if "network_map" in c["check_name"]]
        assert len(map_check) == 1
        assert map_check[0]["passed"] is False
        assert map_check[0]["level"] == ValidationLevel.ERROR

    def test_empty_network_map_error(self, validator, report):
        """Empty network_map dict should produce an error."""
        validator.validate([_make_ovf_deployment(network_map={})])

        calls = [c[1] for c in report.add_check.call_args_list]
        map_check = [c for c in calls if "network_map" in c["check_name"]]
        assert len(map_check) == 1
        assert map_check[0]["passed"] is False

    def test_network_map_empty_values_error(self, validator, report):
        """Network map with empty port group names should produce an error."""
        validator.validate([_make_ovf_deployment(network_map={"hostonly": "", "nat": "PG-Mgmt"})])

        calls = [c[1] for c in report.add_check.call_args_list]
        map_check = [c for c in calls if "network_map" in c["check_name"]]
        assert len(map_check) == 1
        assert map_check[0]["passed"] is False
        assert "empty port group names" in map_check[0]["message"]


class TestOvfDeploymentValidatorWarnings:
    """Tests for warning-level validation."""

    def test_ovf_source_not_found_warning(self, validator, report):
        """Non-existent ovf_source file should produce a warning."""
        validator.validate([_make_ovf_deployment(ovf_source="/nonexistent/path.ovf")])

        calls = [c[1] for c in report.add_check.call_args_list]
        exists_check = [c for c in calls if "exists" in c["check_name"]]
        assert len(exists_check) == 1
        assert exists_check[0]["level"] == ValidationLevel.WARNING
        assert "not found locally" in exists_check[0]["message"]

    def test_ovf_source_exists_no_warning(self, validator, report, tmp_path):
        """Existing ovf_source file should not produce a warning."""
        ovf_file = tmp_path / "test.ovf"
        ovf_file.touch()
        validator.validate([_make_ovf_deployment(ovf_source=str(ovf_file))])

        calls = [c[1] for c in report.add_check.call_args_list]
        exists_check = [c for c in calls if "exists" in c["check_name"]]
        assert len(exists_check) == 0


class TestOvfDeploymentValidatorEdgeCases:
    """Tests for edge cases."""

    def test_non_ovf_deployment_ignored(self, validator, report):
        """Non-ovf_deployment resources should be ignored."""
        vm = ResourceConfig(
            name="test-vm",
            type="vm",
            provider="esxi",
            config={"host": "esxi-01"},
        )
        validator.validate([vm])
        report.add_check.assert_not_called()

    def test_empty_resources(self, validator, report):
        """Empty resource list should produce no checks."""
        validator.validate([])
        report.add_check.assert_not_called()

    def test_multiple_deployments(self, validator, report):
        """Multiple OVF deployments should all be validated."""
        resources = [
            _make_ovf_deployment("node-01"),
            _make_ovf_deployment("node-02"),
        ]
        validator.validate(resources)

        calls = [c[1] for c in report.add_check.call_args_list]
        node01_checks = [
            c for c in calls if "node_01" in c["check_name"] or "node-01" in c.get("message", "")
        ]
        node02_checks = [
            c for c in calls if "node_02" in c["check_name"] or "node-02" in c.get("message", "")
        ]
        assert len(node01_checks) > 0
        assert len(node02_checks) > 0


class TestOvfDeploymentValidatorMacMap:
    """Tests for mac_map validation."""

    def test_mac_map_valid(self, validator, report):
        """Valid mac_map with ethernet names and correct format should pass."""
        validator.validate([_make_ovf_deployment(mac_map={"ethernet0": "BC:24:11:0A:01:01"})])

        calls = [c[1] for c in report.add_check.call_args_list]
        mac_checks = [c for c in calls if "mac_map" in c["check_name"]]
        assert len(mac_checks) == 1
        assert mac_checks[0]["passed"] is True
        assert mac_checks[0]["level"] == ValidationLevel.INFO

    def test_mac_map_invalid_ethernet_name(self, validator, report):
        """mac_map keys not matching ethernetN format should produce an error."""
        validator.validate([_make_ovf_deployment(mac_map={"not_ethernet": "BC:24:11:0A:01:01"})])

        calls = [c[1] for c in report.add_check.call_args_list]
        key_checks = [c for c in calls if "mac_map_keys" in c["check_name"]]
        assert len(key_checks) == 1
        assert key_checks[0]["passed"] is False
        assert key_checks[0]["level"] == ValidationLevel.ERROR
        assert "not_ethernet" in key_checks[0]["message"]

    def test_mac_map_invalid_format(self, validator, report):
        """Invalid MAC address format should produce an error."""
        validator.validate([_make_ovf_deployment(mac_map={"ethernet0": "not-a-mac"})])

        calls = [c[1] for c in report.add_check.call_args_list]
        format_checks = [c for c in calls if "mac_map_format" in c["check_name"]]
        assert len(format_checks) == 1
        assert format_checks[0]["passed"] is False
        assert format_checks[0]["level"] == ValidationLevel.ERROR
        assert "not-a-mac" in format_checks[0]["message"]

    def test_mac_map_empty_dict(self, validator, report):
        """Empty mac_map dict should be treated as no mac_map (no validation)."""
        validator.validate([_make_ovf_deployment(mac_map={})])

        calls = [c[1] for c in report.add_check.call_args_list]
        mac_checks = [c for c in calls if "mac_map" in c["check_name"]]
        assert len(mac_checks) == 0

    def test_no_mac_map(self, validator, report):
        """Omitting mac_map should pass without mac_map validation."""
        validator.validate([_make_ovf_deployment()])

        calls = [c[1] for c in report.add_check.call_args_list]
        mac_checks = [c for c in calls if "mac_map" in c["check_name"]]
        assert len(mac_checks) == 0

    def test_mac_map_multiple_valid_entries(self, validator, report):
        """Multiple valid mac_map entries should all pass."""
        validator.validate(
            [
                _make_ovf_deployment(
                    mac_map={
                        "ethernet0": "BC:24:11:0A:01:01",
                        "ethernet1": "BC:24:11:0A:01:02",
                        "ethernet2": "BC:24:11:0A:01:03",
                        "ethernet3": "BC:24:11:0A:01:04",
                    }
                )
            ]
        )

        calls = [c[1] for c in report.add_check.call_args_list]
        mac_checks = [c for c in calls if "mac_map" in c["check_name"]]
        assert len(mac_checks) == 1
        assert mac_checks[0]["passed"] is True
        assert "4 mapping(s)" in mac_checks[0]["message"]

    def test_mac_map_lowercase_mac_valid(self, validator, report):
        """Lowercase MAC addresses should be accepted."""
        validator.validate([_make_ovf_deployment(mac_map={"ethernet0": "bc:24:11:0a:01:01"})])

        calls = [c[1] for c in report.add_check.call_args_list]
        format_checks = [c for c in calls if "mac_map_format" in c["check_name"]]
        assert len(format_checks) == 0
        mac_checks = [c for c in calls if "mac_map" in c["check_name"]]
        assert len(mac_checks) == 1
        assert mac_checks[0]["passed"] is True
