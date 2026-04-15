"""Unit tests for OCI validator."""

from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import APIError, ConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.oci.validator import OCIValidator
from infrafoundry.providers.oci.validators import (
    CompartmentValidator,
    ImageValidator,
    NetworkValidator,
)
from tests.helpers.env import make_env_config


@pytest.fixture
def env_config():
    """Create a mock environment config."""
    return make_env_config(
        provider_settings={
            "oci": {
                "tenancy_ocid": "ocid1.tenancy.oc1..example",
                "user_ocid": "ocid1.user.oc1..example",
                "fingerprint": "aa:bb:cc:dd:ee:ff:00:11",
                "private_key_path": "/tmp/test_key.pem",
                "region": "us-ashburn-1",
                "compartment_ocid": "ocid1.compartment.oc1..example",
            }
        },
    )


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(env_config, report):
    """Create an OCIValidator instance."""
    return OCIValidator(env_config, report)


class TestComposition:
    """Tests for validator composition."""

    def test_specialized_validators_initialized(self, validator):
        """Specialized validators are created during init."""
        assert isinstance(validator.compartment_validator, CompartmentValidator)
        assert isinstance(validator.network_validator, NetworkValidator)
        assert isinstance(validator.image_validator, ImageValidator)


class TestValidateReferences:
    """Tests for validate_references method."""

    def test_valid_subnet_vcn_reference(self, validator, report):
        """Test valid subnet -> VCN reference."""
        resources = [
            ResourceConfig(
                name="my-vcn",
                type="vcn",
                provider="oci",
                config={"cidr_block": "10.0.0.0/16"},
            ),
            ResourceConfig(
                name="my-subnet",
                type="subnet",
                provider="oci",
                config={"vcn": "my-vcn", "cidr_block": "10.0.0.0/24"},
            ),
        ]

        # Mock _validate_api_references to isolate local checks
        validator._validate_api_references = MagicMock()
        validator.validate_references(resources)

        # Should have passed checks
        calls = report.add_check.call_args_list
        subnet_check = [c for c in calls if "subnet_my-subnet_vcn" in str(c)]
        assert len(subnet_check) == 1
        assert subnet_check[0][1]["passed"] is True

    def test_invalid_subnet_vcn_reference(self, validator, report):
        """Test invalid subnet -> VCN reference."""
        resources = [
            ResourceConfig(
                name="my-subnet",
                type="subnet",
                provider="oci",
                config={"vcn": "nonexistent-vcn", "cidr_block": "10.0.0.0/24"},
            ),
        ]

        validator._validate_api_references = MagicMock()
        validator.validate_references(resources)

        calls = report.add_check.call_args_list
        subnet_check = [c for c in calls if "subnet_my-subnet_vcn" in str(c)]
        assert len(subnet_check) == 1
        assert subnet_check[0][1]["passed"] is False
        assert "nonexistent-vcn" in subnet_check[0][1]["message"]

    def test_valid_instance_subnet_reference(self, validator, report):
        """Test valid instance -> subnet reference."""
        resources = [
            ResourceConfig(
                name="my-subnet",
                type="subnet",
                provider="oci",
                config={"vcn": "my-vcn", "cidr_block": "10.0.0.0/24"},
            ),
            ResourceConfig(
                name="my-instance",
                type="instance",
                provider="oci",
                config={"subnet": "my-subnet", "shape": "VM.Standard.A1.Flex", "image": "img1"},
            ),
        ]

        validator._validate_api_references = MagicMock()
        validator.validate_references(resources)

        calls = report.add_check.call_args_list
        instance_check = [c for c in calls if "instance_my-instance_subnet" in str(c)]
        assert len(instance_check) == 1
        assert instance_check[0][1]["passed"] is True

    def test_invalid_instance_subnet_reference(self, validator, report):
        """Test invalid instance -> subnet reference."""
        resources = [
            ResourceConfig(
                name="my-instance",
                type="instance",
                provider="oci",
                config={
                    "subnet": "missing-subnet",
                    "shape": "VM.Standard.A1.Flex",
                    "image": "img1",
                },
            ),
        ]

        validator._validate_api_references = MagicMock()
        validator.validate_references(resources)

        calls = report.add_check.call_args_list
        instance_check = [c for c in calls if "instance_my-instance_subnet" in str(c)]
        assert len(instance_check) == 1
        assert instance_check[0][1]["passed"] is False
        assert "missing-subnet" in instance_check[0][1]["message"]

    def test_no_references_to_validate(self, validator, report):
        """Test resources with no cross-references."""
        resources = [
            ResourceConfig(
                name="my-vcn",
                type="vcn",
                provider="oci",
                config={"cidr_block": "10.0.0.0/16"},
            ),
        ]

        validator._validate_api_references = MagicMock()
        validator.validate_references(resources)

        # No checks for VCN-only resources
        report.add_check.assert_not_called()

    def test_instance_without_subnet_field(self, validator, report):
        """Test instance without subnet field does not fail."""
        resources = [
            ResourceConfig(
                name="my-instance",
                type="instance",
                provider="oci",
                config={"shape": "VM.Standard.A1.Flex", "image": "img1"},
            ),
        ]

        validator._validate_api_references = MagicMock()
        validator.validate_references(resources)

        # No subnet reference, should pass silently
        calls = report.add_check.call_args_list
        instance_checks = [c for c in calls if "instance_my-instance_subnet" in str(c)]
        # With no subnet field, the check should still pass (empty subnet_ref is falsy)
        assert len(instance_checks) == 1
        assert instance_checks[0][1]["passed"] is True

    def test_multiple_resources_validation(self, validator, report):
        """Test validation with multiple resources."""
        resources = [
            ResourceConfig(
                name="vcn-1",
                type="vcn",
                provider="oci",
                config={"cidr_block": "10.0.0.0/16"},
            ),
            ResourceConfig(
                name="subnet-1",
                type="subnet",
                provider="oci",
                config={"vcn": "vcn-1", "cidr_block": "10.0.1.0/24"},
            ),
            ResourceConfig(
                name="subnet-2",
                type="subnet",
                provider="oci",
                config={"vcn": "vcn-1", "cidr_block": "10.0.2.0/24"},
            ),
            ResourceConfig(
                name="instance-1",
                type="instance",
                provider="oci",
                config={"subnet": "subnet-1", "shape": "VM.Standard.A1.Flex", "image": "img1"},
            ),
            ResourceConfig(
                name="instance-2",
                type="instance",
                provider="oci",
                config={"subnet": "subnet-2", "shape": "VM.Standard.A1.Flex", "image": "img1"},
            ),
        ]

        validator._validate_api_references = MagicMock()
        validator.validate_references(resources)

        calls = report.add_check.call_args_list
        # 2 subnet checks + 2 instance checks = 4
        assert len(calls) == 4
        assert all(c[1]["passed"] is True for c in calls)


class TestValidateAPIReferences:
    """Tests for _validate_api_references method."""

    def test_skipped_when_no_compartment_ocid(self, report):
        """API validation skipped when compartment_ocid is missing."""
        env_config = make_env_config(
            provider_settings={
                "oci": {
                    "tenancy_ocid": "ocid1.tenancy.oc1..example",
                    "user_ocid": "ocid1.user.oc1..example",
                    "fingerprint": "aa:bb:cc:dd:ee:ff:00:11",
                    "private_key_path": "/tmp/test_key.pem",
                    "region": "us-ashburn-1",
                    # No compartment_ocid
                }
            },
        )
        validator = OCIValidator(env_config, report)

        # Should not attempt to create client
        with patch.object(validator, "_create_client") as mock_create:
            validator._validate_api_references([])
            mock_create.assert_not_called()

    def test_skipped_when_no_region(self, report):
        """API validation skipped when region is missing."""
        env_config = make_env_config(
            provider_settings={
                "oci": {
                    "tenancy_ocid": "ocid1.tenancy.oc1..example",
                    "user_ocid": "ocid1.user.oc1..example",
                    "fingerprint": "aa:bb:cc:dd:ee:ff:00:11",
                    "private_key_path": "/tmp/test_key.pem",
                    "compartment_ocid": "ocid1.compartment.oc1..example",
                    # No region
                }
            },
        )
        validator = OCIValidator(env_config, report)

        with patch.object(validator, "_create_client") as mock_create:
            validator._validate_api_references([])
            mock_create.assert_not_called()

    def test_skipped_when_client_creation_fails(self, validator):
        """API validation skips gracefully when client creation fails."""
        validator._create_client = MagicMock(return_value=None)

        resources = [
            ResourceConfig(
                name="my-vcn",
                type="vcn",
                provider="oci",
                config={"cidr_block": "10.0.0.0/16"},
            ),
        ]

        # Should not raise
        validator._validate_api_references(resources)

    def test_fetches_and_delegates_to_validators(self, validator):
        """API references fetches data and delegates to specialized validators."""
        mock_client = MagicMock()
        mock_client.identity_url.return_value = "https://identity.us-ashburn-1.oraclecloud.com"
        mock_client.iaas_url.return_value = "https://iaas.us-ashburn-1.oraclecloud.com"

        compartments = [{"id": "ocid1.compartment.oc1..example", "name": "root"}]
        vcns = [{"displayName": "existing-vcn", "id": "ocid1.vcn.oc1..aaa"}]
        subnets = [{"displayName": "existing-subnet", "id": "ocid1.subnet.oc1..aaa"}]
        images = [{"id": "ocid1.image.oc1..aaa", "displayName": "Oracle-Linux-8"}]

        def mock_list(base_url, path):
            if "compartments" in path:
                return compartments
            elif "vcns" in path:
                return vcns
            elif "subnets" in path:
                return subnets
            elif "images" in path:
                return images
            return []

        mock_client.list_resources.side_effect = mock_list
        validator._create_client = MagicMock(return_value=mock_client)
        validator.compartment_validator.validate = MagicMock()
        validator.network_validator.validate = MagicMock()
        validator.image_validator.validate = MagicMock()

        resources = [
            ResourceConfig(
                name="my-vcn",
                type="vcn",
                provider="oci",
                config={"cidr_block": "10.0.0.0/16"},
            ),
        ]

        validator._validate_api_references(resources)

        # All four list endpoints should be called
        assert mock_client.list_resources.call_count == 4

        # Specialized validators should be called with pre-fetched data
        validator.compartment_validator.validate.assert_called_once_with(
            "ocid1.compartment.oc1..example", compartments
        )
        validator.network_validator.validate.assert_called_once_with(resources, vcns, subnets)
        validator.image_validator.validate.assert_called_once_with(resources, images)


class TestSafeList:
    """Tests for _safe_list helper."""

    def test_returns_list_on_success(self, validator):
        """Returns list when client succeeds."""
        mock_client = MagicMock()
        mock_client.list_resources.return_value = [{"id": "test"}]

        result = validator._safe_list(mock_client, "https://example.com", "/path")

        assert result == [{"id": "test"}]

    def test_returns_none_on_api_error(self, validator):
        """Returns None when client raises APIError."""
        mock_client = MagicMock()
        mock_client.list_resources.side_effect = APIError("failed", provider="oci")

        result = validator._safe_list(mock_client, "https://example.com", "/path")

        assert result is None


class TestValidateConnectivity:
    """Tests for validate_connectivity method."""

    def test_missing_credentials(self, report):
        """Test connectivity validation with missing credentials."""
        env_config = make_env_config(provider_settings={"oci": {}})
        validator = OCIValidator(env_config, report)

        validator.validate_connectivity()

        # Should not crash, credentials check should fail gracefully

    def test_connectivity_with_valid_credentials(self, validator, report):
        """Test that connectivity creates a client and calls list_resources."""
        validator.api_validator.get_credentials = MagicMock(
            return_value={
                "tenancy_ocid": "ocid1.tenancy.oc1..example",
                "user_ocid": "ocid1.user.oc1..example",
                "fingerprint": "aa:bb:cc:dd:ee:ff:00:11",
                "private_key_path": "/tmp/test_key.pem",
                "region": "us-ashburn-1",
            }
        )
        mock_client = MagicMock()
        mock_client.identity_url.return_value = "https://identity.us-ashburn-1.oraclecloud.com"
        mock_client.list_resources.return_value = [{"name": "AD-1"}]
        validator._create_client = MagicMock(return_value=mock_client)
        validator.api_validator.add_success = MagicMock()

        validator.validate_connectivity()

        mock_client.list_resources.assert_called_once()
        validator.api_validator.add_success.assert_called()

    def test_connectivity_client_creation_fails(self, validator, report):
        """Test connectivity when client creation fails."""
        validator.api_validator.get_credentials = MagicMock(
            return_value={
                "tenancy_ocid": "t",
                "user_ocid": "u",
                "fingerprint": "f",
                "private_key_path": "/nonexistent",
                "region": "us-ashburn-1",
            }
        )
        validator._create_client = MagicMock(return_value=None)

        validator.validate_connectivity()

        # Should not crash


class TestCreateClient:
    """Tests for _create_client helper."""

    def test_returns_none_on_configuration_error(self, validator):
        """Returns None and reports warning when client creation fails."""
        validator.api_validator.add_error = MagicMock()
        with patch(
            "infrafoundry.providers.oci.validator.OCIClient.from_provider_settings",
            side_effect=ConfigurationError("key not found"),
        ):
            result = validator._create_client()

        assert result is None
        validator.api_validator.add_error.assert_called_once()

    def test_returns_client_on_success(self, validator, tmp_path):
        """Returns OCIClient when creation succeeds."""
        mock_client = MagicMock()
        with patch(
            "infrafoundry.providers.oci.validator.OCIClient.from_provider_settings",
            return_value=mock_client,
        ):
            result = validator._create_client()

        assert result is mock_client
