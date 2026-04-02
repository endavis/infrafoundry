"""Unit tests for OCI network validator."""

from __future__ import annotations

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.oci.validators.network_validator import NetworkValidator


@pytest.fixture
def report():
    """Create a validation report."""
    return ValidationReport()


@pytest.fixture
def validator(report):
    """Create a NetworkValidator instance."""
    return NetworkValidator(report)


def _vcn(name: str, display_name: str | None = None) -> ResourceConfig:
    """Helper to create a VCN resource config."""
    config: dict = {"cidr_block": "10.0.0.0/16"}
    if display_name:
        config["display_name"] = display_name
    return ResourceConfig(name=name, type="vcn", provider="oci", config=config)


def _subnet(name: str, vcn: str, display_name: str | None = None) -> ResourceConfig:
    """Helper to create a subnet resource config."""
    config: dict = {"vcn": vcn, "cidr_block": "10.0.1.0/24"}
    if display_name:
        config["display_name"] = display_name
    return ResourceConfig(name=name, type="subnet", provider="oci", config=config)


class TestVCNCollisions:
    """Tests for VCN name collision detection."""

    def test_vcn_name_collision(self, validator, report):
        """VCN name collision with existing resource produces WARNING."""
        resources = [_vcn("my-vcn")]
        existing_vcns = [{"displayName": "my-vcn", "id": "ocid1.vcn.oc1..aaa"}]

        validator.validate(resources, existing_vcns, None)

        vcn_checks = [r for r in report.results if "vcn_collision" in r.check_name]
        assert len(vcn_checks) == 1
        assert vcn_checks[0].level == ValidationLevel.WARNING
        assert "already exists" in vcn_checks[0].message

    def test_no_vcn_collision(self, validator, report):
        """Clean config with no collisions produces no warnings."""
        resources = [_vcn("new-vcn")]
        existing_vcns = [{"displayName": "other-vcn", "id": "ocid1.vcn.oc1..aaa"}]

        validator.validate(resources, existing_vcns, None)

        vcn_checks = [r for r in report.results if "vcn_collision" in r.check_name]
        assert len(vcn_checks) == 1
        assert "does not conflict" in vcn_checks[0].message

    def test_vcn_with_display_name(self, validator, report):
        """VCN with explicit display_name uses it for collision check."""
        resources = [_vcn("my-vcn", display_name="Custom VCN Name")]
        existing_vcns = [{"displayName": "Custom VCN Name", "id": "ocid1.vcn.oc1..aaa"}]

        validator.validate(resources, existing_vcns, None)

        vcn_checks = [r for r in report.results if "vcn_collision" in r.check_name]
        assert len(vcn_checks) == 1
        assert vcn_checks[0].level == ValidationLevel.WARNING

    def test_none_vcns_skips(self, validator, report):
        """None VCN data skips collision checks."""
        resources = [_vcn("my-vcn")]

        validator.validate(resources, None, None)

        vcn_checks = [r for r in report.results if "vcn_collision" in r.check_name]
        assert len(vcn_checks) == 0


class TestSubnetCollisions:
    """Tests for subnet name collision detection."""

    def test_subnet_name_collision(self, validator, report):
        """Subnet name collision produces WARNING."""
        resources = [_subnet("my-subnet", "my-vcn")]
        existing_subnets = [{"displayName": "my-subnet", "id": "ocid1.subnet.oc1..aaa"}]

        validator.validate(resources, None, existing_subnets)

        subnet_checks = [r for r in report.results if "subnet_collision" in r.check_name]
        assert len(subnet_checks) == 1
        assert subnet_checks[0].level == ValidationLevel.WARNING

    def test_no_subnet_collision(self, validator, report):
        """No collision produces clean message."""
        resources = [_subnet("new-subnet", "my-vcn")]
        existing_subnets = [{"displayName": "other-subnet", "id": "ocid1.subnet.oc1..aaa"}]

        validator.validate(resources, None, existing_subnets)

        subnet_checks = [r for r in report.results if "subnet_collision" in r.check_name]
        assert len(subnet_checks) == 1
        assert "does not conflict" in subnet_checks[0].message

    def test_none_subnets_skips(self, validator, report):
        """None subnet data skips collision checks."""
        resources = [_subnet("my-subnet", "my-vcn")]

        validator.validate(resources, None, None)

        subnet_checks = [r for r in report.results if "subnet_collision" in r.check_name]
        assert len(subnet_checks) == 0
