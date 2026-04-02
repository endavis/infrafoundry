"""Unit tests for OCI image validator."""

from __future__ import annotations

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.oci.validators.image_validator import ImageValidator


@pytest.fixture
def report():
    """Create a validation report."""
    return ValidationReport()


@pytest.fixture
def validator(report):
    """Create an ImageValidator instance."""
    return ImageValidator(report)


def _instance(name: str, image_ocid: str = "") -> ResourceConfig:
    """Helper to create an instance resource config."""
    config: dict = {"shape": "VM.Standard.A1.Flex", "subnet": "my-subnet"}
    if image_ocid:
        config["image_ocid"] = image_ocid
    return ResourceConfig(name=name, type="instance", provider="oci", config=config)


class TestImageValidator:
    """Tests for ImageValidator.validate method."""

    def test_image_found(self, validator, report):
        """Image OCID found produces SUCCESS with display name."""
        resources = [_instance("my-instance", "ocid1.image.oc1..aaa")]
        images = [
            {"id": "ocid1.image.oc1..aaa", "displayName": "Oracle-Linux-8"},
            {"id": "ocid1.image.oc1..bbb", "displayName": "Ubuntu-22.04"},
        ]

        validator.validate(resources, images)

        assert len(report.results) == 1
        result = report.results[0]
        assert result.passed is True
        assert "Oracle-Linux-8" in result.message
        assert "my-instance" in result.message

    def test_image_not_found(self, validator, report):
        """Image OCID not found produces ERROR with instance names."""
        resources = [_instance("my-instance", "ocid1.image.oc1..missing")]
        images = [{"id": "ocid1.image.oc1..aaa", "displayName": "Oracle-Linux-8"}]

        validator.validate(resources, images)

        assert len(report.results) == 1
        result = report.results[0]
        assert result.passed is False
        assert result.level == ValidationLevel.ERROR
        assert "not found" in result.message
        assert "my-instance" in result.message

    def test_none_images_skips(self, validator, report):
        """None images (API failure) produces no checks."""
        resources = [_instance("my-instance", "ocid1.image.oc1..aaa")]

        validator.validate(resources, None)

        assert len(report.results) == 0

    def test_no_instances_skips(self, validator, report):
        """No instance resources produces no checks."""
        resources = [
            ResourceConfig(
                name="my-vcn",
                type="vcn",
                provider="oci",
                config={"cidr_block": "10.0.0.0/16"},
            )
        ]
        images = [{"id": "ocid1.image.oc1..aaa", "displayName": "Oracle-Linux-8"}]

        validator.validate(resources, images)

        assert len(report.results) == 0

    def test_no_image_ocid_skips(self, validator, report):
        """Instance without image_ocid produces no checks."""
        resources = [_instance("my-instance")]
        images = [{"id": "ocid1.image.oc1..aaa", "displayName": "Oracle-Linux-8"}]

        validator.validate(resources, images)

        assert len(report.results) == 0

    def test_multiple_instances_same_image(self, validator, report):
        """Multiple instances referencing same image produce one check."""
        resources = [
            _instance("instance-1", "ocid1.image.oc1..aaa"),
            _instance("instance-2", "ocid1.image.oc1..aaa"),
        ]
        images = [{"id": "ocid1.image.oc1..aaa", "displayName": "Oracle-Linux-8"}]

        validator.validate(resources, images)

        assert len(report.results) == 1
        result = report.results[0]
        assert result.passed is True
        assert "instance-1" in result.message
        assert "instance-2" in result.message

    def test_empty_image_list(self, validator, report):
        """Empty image list with references produces errors."""
        resources = [_instance("my-instance", "ocid1.image.oc1..aaa")]

        validator.validate(resources, [])

        assert len(report.results) == 1
        assert report.results[0].passed is False
