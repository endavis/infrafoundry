"""Unit tests for OPNsense OPNsenseValidator orchestration."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator
from infrafoundry.providers.opnsense.validator import OPNsenseValidator
from infrafoundry.providers.opnsense.validators import (
    FirewallRuleValidator,
    InterfaceAssignmentValidator,
    ResourceNameValidator,
    UnboundValidator,
    VLANValidator,
)
from tests.helpers.env import make_env_config


@pytest.fixture
def env_config():
    """Create a valid environment config."""
    return make_env_config(
        provider_settings={
            "opnsense": {
                "api_url": "https://opnsense.example.com",
                "api_key": "test-key",
                "api_secret": "test-secret",
            }
        },
    )


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(env_config, report):
    """Create an OPNsenseValidator instance."""
    return OPNsenseValidator(env_config, report)


class TestComposition:
    """Tests for validator composition."""

    def test_api_validator_initialized(self, validator):
        """BaseAPIValidator is composed during init."""
        assert isinstance(validator.api_validator, BaseAPIValidator)

    def test_specialized_validators_initialized(self, validator):
        """All specialized validators are created."""
        assert isinstance(validator.firewall_rule_validator, FirewallRuleValidator)
        assert isinstance(validator.vlan_validator, VLANValidator)
        assert isinstance(validator.unbound_validator, UnboundValidator)
        assert isinstance(validator.resource_name_validator, ResourceNameValidator)
        assert isinstance(validator.interface_assignment_validator, InterfaceAssignmentValidator)


class TestValidateConnectivity:
    """Tests for validate_connectivity."""

    def test_missing_credentials_returns_early(self, validator):
        """Returns early when credentials are missing."""
        validator.api_validator.get_credentials = MagicMock(return_value=None)

        validator.validate_connectivity()

        validator.api_validator.get_credentials.assert_called_once()

    def test_api_200_reports_success(self, validator):
        """Reports success on 200 response."""
        validator.api_validator.get_credentials = MagicMock(
            return_value={
                "api_url": "https://opnsense.example.com",
                "api_key": "key",
                "api_secret": "secret",
            }
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"product_version": "24.7"}
        validator.api_validator.api_request = MagicMock(return_value=mock_response)
        validator.api_validator.add_success = MagicMock()

        validator.validate_connectivity()

        assert validator.api_validator.add_success.call_count == 2  # connection + version

    def test_api_200_without_version(self, validator):
        """Reports success without version when not in response."""
        validator.api_validator.get_credentials = MagicMock(
            return_value={
                "api_url": "https://opnsense.example.com",
                "api_key": "key",
                "api_secret": "secret",
            }
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        validator.api_validator.api_request = MagicMock(return_value=mock_response)
        validator.api_validator.add_success = MagicMock()

        validator.validate_connectivity()

        assert validator.api_validator.add_success.call_count == 1  # connection only

    def test_api_401_reports_auth_error(self, validator):
        """Reports authentication error on 401."""
        validator.api_validator.get_credentials = MagicMock(
            return_value={
                "api_url": "https://opnsense.example.com",
                "api_key": "key",
                "api_secret": "secret",
            }
        )
        mock_response = MagicMock()
        mock_response.status_code = 401
        validator.api_validator.api_request = MagicMock(return_value=mock_response)
        validator.api_validator.add_error = MagicMock()

        validator.validate_connectivity()

        validator.api_validator.add_error.assert_called_once()
        assert "401" in validator.api_validator.add_error.call_args[1]["message"]

    def test_api_500_reports_warning(self, validator):
        """Reports warning on 500 response."""
        validator.api_validator.get_credentials = MagicMock(
            return_value={
                "api_url": "https://opnsense.example.com",
                "api_key": "key",
                "api_secret": "secret",
            }
        )
        mock_response = MagicMock()
        mock_response.status_code = 500
        validator.api_validator.api_request = MagicMock(return_value=mock_response)
        validator.api_validator.add_error = MagicMock()

        validator.validate_connectivity()

        validator.api_validator.add_error.assert_called_once()
        assert "500" in validator.api_validator.add_error.call_args[1]["message"]

    def test_request_failure_returns_early(self, validator):
        """Returns early when API request fails entirely."""
        validator.api_validator.get_credentials = MagicMock(
            return_value={
                "api_url": "https://opnsense.example.com",
                "api_key": "key",
                "api_secret": "secret",
            }
        )
        validator.api_validator.api_request = MagicMock(return_value=None)
        validator.api_validator.add_success = MagicMock()
        validator.api_validator.add_error = MagicMock()

        validator.validate_connectivity()

        validator.api_validator.add_success.assert_not_called()
        validator.api_validator.add_error.assert_not_called()


class TestValidateReferences:
    """Tests for validate_references."""

    def test_missing_credentials_returns_early(self, validator):
        """Returns early when credentials are missing."""
        validator.api_validator.get_credentials = MagicMock(return_value=None)

        validator.validate_references([])

    def test_delegates_to_specialized_validators(self, validator):
        """Delegates to all specialized validators."""
        validator.api_validator.get_credentials = MagicMock(
            return_value={
                "api_url": "https://opnsense.example.com",
                "api_key": "key",
                "api_secret": "secret",
            }
        )
        validator.api_validator.fetch_json = MagicMock(return_value=None)
        validator.firewall_rule_validator = MagicMock()
        validator.vlan_validator = MagicMock()
        validator.unbound_validator = MagicMock()
        validator.resource_name_validator = MagicMock()
        validator.interface_assignment_validator = MagicMock()

        resources = [
            ResourceConfig(name="alias1", type="aliases", provider="opnsense", config={}),
        ]

        validator.validate_references(resources)

        validator.firewall_rule_validator.validate.assert_called_once()
        validator.vlan_validator.validate.assert_called_once()
        validator.unbound_validator.validate.assert_called_once()
        validator.resource_name_validator.validate.assert_called_once()
        validator.interface_assignment_validator.validate.assert_called_once()

    def test_exception_caught_gracefully(self, validator):
        """Exceptions during validation are caught and reported."""
        validator.api_validator.get_credentials = MagicMock(
            return_value={
                "api_url": "https://opnsense.example.com",
                "api_key": "key",
                "api_secret": "secret",
            }
        )
        validator.api_validator.fetch_json = MagicMock(side_effect=RuntimeError("unexpected"))
        validator.api_validator.handle_validation_exception = MagicMock()

        validator.validate_references(
            [
                ResourceConfig(name="alias1", type="aliases", provider="opnsense", config={}),
            ]
        )

        validator.api_validator.handle_validation_exception.assert_called_once()


class TestCollectResourceReferences:
    """Tests for _collect_resource_references."""

    def test_collects_aliases(self, validator):
        """Collects alias resources."""
        resources = [
            ResourceConfig(name="my-alias", type="aliases", provider="opnsense", config={}),
        ]

        refs = validator._collect_resource_references(resources)

        assert "my-alias" in refs["alias_names"]
        assert len(refs["aliases"]) == 1

    def test_collects_vlans(self, validator):
        """Collects VLAN resources."""
        resources = [
            ResourceConfig(name="vlan10", type="vlans", provider="opnsense", config={}),
        ]

        refs = validator._collect_resource_references(resources)

        assert "vlan10" in refs["vlan_names"]
        assert len(refs["vlans"]) == 1

    def test_collects_firewall_rules(self, validator):
        """Collects firewall rule resources."""
        resources = [
            ResourceConfig(name="rule1", type="firewall_rules", provider="opnsense", config={}),
        ]

        refs = validator._collect_resource_references(resources)

        assert len(refs["firewall_rules"]) == 1

    def test_collects_unbound_host_overrides(self, validator):
        """Collects unbound host override resources."""
        resources = [
            ResourceConfig(
                name="host1", type="unbound_host_override", provider="opnsense", config={}
            ),
        ]

        refs = validator._collect_resource_references(resources)

        assert len(refs["unbound_host_overrides"]) == 1

    def test_collects_interface_assignments(self, validator):
        """Collects interface_assignment resources."""
        resources = [
            ResourceConfig(
                name="lan",
                type="interface_assignments",
                provider="opnsense",
                config={"device": "ixl1"},
            ),
        ]

        refs = validator._collect_resource_references(resources)

        assert len(refs["interface_assignments"]) == 1
        assert "lan" in refs["interface_assignment_names"]

    def test_empty_resources(self, validator):
        """Returns empty collections for empty resources."""
        refs = validator._collect_resource_references([])

        assert len(refs["aliases"]) == 0
        assert len(refs["alias_names"]) == 0
        assert len(refs["vlans"]) == 0
        assert len(refs["interface_assignments"]) == 0
        assert len(refs["interface_assignment_names"]) == 0


class TestGetExistingAliases:
    """Tests for _get_existing_aliases."""

    def test_success_returns_aliases(self, validator):
        """Returns alias dict on successful API call."""
        validator.api_validator.fetch_json = MagicMock(
            return_value={
                "rows": [
                    {"name": "alias1", "type": "host"},
                    {"name": "alias2", "type": "network"},
                ]
            }
        )

        result = validator._get_existing_aliases("https://opn.example.com", "key", "secret")

        assert "alias1" in result
        assert "alias2" in result

    def test_api_failure_returns_empty(self, validator):
        """Returns empty dict on API failure."""
        validator.api_validator.fetch_json = MagicMock(return_value=None)

        result = validator._get_existing_aliases("https://opn.example.com", "key", "secret")

        assert result == {}

    def test_skips_rows_without_name(self, validator):
        """Skips rows that don't have a name field."""
        validator.api_validator.fetch_json = MagicMock(
            return_value={"rows": [{"name": "alias1"}, {"type": "host"}]}
        )

        result = validator._get_existing_aliases("https://opn.example.com", "key", "secret")

        assert len(result) == 1
        assert "alias1" in result


class TestGetExistingInterfaces:
    """Tests for _get_existing_interfaces."""

    def test_success_with_dict_format(self, validator):
        """Returns interfaces from dict format."""
        validator.api_validator.fetch_json = MagicMock(
            return_value={
                "lan": {"device": "igc0", "if_type": "ethernet"},
                "wan": {"device": "igc1", "if_type": "ethernet"},
            }
        )

        result = validator._get_existing_interfaces("https://opn.example.com", "key", "secret")

        assert "lan" in result
        assert "wan" in result

    def test_success_with_list_format(self, validator):
        """Returns interfaces from list format."""
        validator.api_validator.fetch_json = MagicMock(
            return_value=[
                {"name": "lan", "device": "igc0"},
                {"name": "wan", "device": "igc1"},
            ]
        )

        result = validator._get_existing_interfaces("https://opn.example.com", "key", "secret")

        assert "lan" in result
        assert "wan" in result

    def test_api_failure_returns_empty(self, validator):
        """Returns empty dict on API failure."""
        validator.api_validator.fetch_json = MagicMock(return_value=None)

        result = validator._get_existing_interfaces("https://opn.example.com", "key", "secret")

        assert result == {}


class TestNormalizeInterfaceData:
    """Tests for _normalize_interface_data."""

    def test_dict_format(self, validator):
        """Normalizes dict format to list."""
        data = {"lan": {"device": "igc0"}, "wan": {"device": "igc1"}}

        result = validator._normalize_interface_data(data)

        assert len(result) == 2
        names = [item["name"] for item in result]
        assert "lan" in names
        assert "wan" in names

    def test_list_format(self, validator):
        """Passes through list format."""
        data = [{"name": "lan"}, {"name": "wan"}]

        result = validator._normalize_interface_data(data)

        assert len(result) == 2

    def test_non_dict_values_skipped(self, validator):
        """Skips non-dict values in dict format."""
        data = {"lan": {"device": "igc0"}, "count": 42}

        result = validator._normalize_interface_data(data)

        assert len(result) == 1

    def test_non_dict_items_skipped_in_list(self, validator):
        """Skips non-dict items in list format."""
        data = [{"name": "lan"}, "not-a-dict", 42]

        result = validator._normalize_interface_data(data)

        assert len(result) == 1

    def test_unknown_type_returns_empty(self, validator):
        """Returns empty list for unknown data types."""
        result = validator._normalize_interface_data("unexpected")

        assert result == []


class TestExtractInterfaceName:
    """Tests for _extract_interface_name."""

    def test_name_field(self, validator):
        """Extracts from 'name' field."""
        assert validator._extract_interface_name({"name": "lan"}) == "lan"

    def test_device_field(self, validator):
        """Falls back to 'device' field."""
        assert validator._extract_interface_name({"device": "igc0"}) == "igc0"

    def test_if_field(self, validator):
        """Falls back to 'if' field."""
        assert validator._extract_interface_name({"if": "em0"}) == "em0"

    def test_interface_field(self, validator):
        """Falls back to 'interface' field."""
        assert validator._extract_interface_name({"interface": "eth0"}) == "eth0"

    def test_priority_order(self, validator):
        """Returns 'name' over 'device' when both present."""
        assert validator._extract_interface_name({"name": "lan", "device": "igc0"}) == "lan"

    def test_no_fields_returns_none(self, validator):
        """Returns None when no recognized fields."""
        assert validator._extract_interface_name({"type": "ethernet"}) is None
