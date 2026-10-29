"""Unit tests for OPNsense OPNsenseValidator orchestration."""

from typing import Any
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
from infrafoundry.providers.opnsense.validators.gateway_validator import GatewayValidator
from infrafoundry.providers.opnsense.validators.nat_rule_validator import NATRuleValidator
from tests.helpers.env import make_env_config


@pytest.fixture
def env_config() -> Any:
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
def report() -> MagicMock:
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(env_config: Any, report: MagicMock) -> OPNsenseValidator:
    """Create an OPNsenseValidator instance."""
    return OPNsenseValidator(env_config, report)


class TestComposition:
    """Tests for validator composition."""

    def test_api_validator_initialized(self, validator: OPNsenseValidator) -> None:
        """BaseAPIValidator is composed during init."""
        assert isinstance(validator.api_validator, BaseAPIValidator)

    def test_specialized_validators_initialized(self, validator: OPNsenseValidator) -> None:
        """All specialized validators are created."""
        assert isinstance(validator.firewall_rule_validator, FirewallRuleValidator)
        assert isinstance(validator.vlan_validator, VLANValidator)
        assert isinstance(validator.unbound_validator, UnboundValidator)
        assert isinstance(validator.resource_name_validator, ResourceNameValidator)
        assert isinstance(validator.interface_assignment_validator, InterfaceAssignmentValidator)


class TestValidateConnectivity:
    """Tests for validate_connectivity."""

    def test_missing_credentials_returns_early(self, validator: OPNsenseValidator) -> None:
        """Returns early when credentials are missing."""
        validator.api_validator.get_credentials = MagicMock(return_value=None)  # type: ignore[method-assign]

        validator.validate_connectivity()

        validator.api_validator.get_credentials.assert_called_once()

    def test_api_200_reports_success(self, validator: OPNsenseValidator) -> None:
        """Reports success on 200 response."""
        validator.api_validator.get_credentials = MagicMock(  # type: ignore[method-assign]
            return_value={
                "api_url": "https://opnsense.example.com",
                "api_key": "key",
                "api_secret": "secret",
            }
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"product_version": "24.7"}
        validator.api_validator.api_request = MagicMock(return_value=mock_response)  # type: ignore[method-assign]
        validator.api_validator.add_success = MagicMock()  # type: ignore[method-assign]

        validator.validate_connectivity()

        assert validator.api_validator.add_success.call_count == 2  # connection + version

    def test_api_200_without_version(self, validator: OPNsenseValidator) -> None:
        """Reports success without version when not in response."""
        validator.api_validator.get_credentials = MagicMock(  # type: ignore[method-assign]
            return_value={
                "api_url": "https://opnsense.example.com",
                "api_key": "key",
                "api_secret": "secret",
            }
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        validator.api_validator.api_request = MagicMock(return_value=mock_response)  # type: ignore[method-assign]
        validator.api_validator.add_success = MagicMock()  # type: ignore[method-assign]

        validator.validate_connectivity()

        assert validator.api_validator.add_success.call_count == 1  # connection only

    def test_api_401_reports_auth_error(self, validator: OPNsenseValidator) -> None:
        """Reports authentication error on 401."""
        validator.api_validator.get_credentials = MagicMock(  # type: ignore[method-assign]
            return_value={
                "api_url": "https://opnsense.example.com",
                "api_key": "key",
                "api_secret": "secret",
            }
        )
        mock_response = MagicMock()
        mock_response.status_code = 401
        validator.api_validator.api_request = MagicMock(return_value=mock_response)  # type: ignore[method-assign]
        validator.api_validator.add_error = MagicMock()  # type: ignore[method-assign]

        validator.validate_connectivity()

        validator.api_validator.add_error.assert_called_once()
        assert "401" in validator.api_validator.add_error.call_args[1]["message"]

    def test_api_500_reports_warning(self, validator: OPNsenseValidator) -> None:
        """Reports warning on 500 response."""
        validator.api_validator.get_credentials = MagicMock(  # type: ignore[method-assign]
            return_value={
                "api_url": "https://opnsense.example.com",
                "api_key": "key",
                "api_secret": "secret",
            }
        )
        mock_response = MagicMock()
        mock_response.status_code = 500
        validator.api_validator.api_request = MagicMock(return_value=mock_response)  # type: ignore[method-assign]
        validator.api_validator.add_error = MagicMock()  # type: ignore[method-assign]

        validator.validate_connectivity()

        validator.api_validator.add_error.assert_called_once()
        assert "500" in validator.api_validator.add_error.call_args[1]["message"]

    def test_request_failure_returns_early(self, validator: OPNsenseValidator) -> None:
        """Returns early when API request fails entirely."""
        validator.api_validator.get_credentials = MagicMock(  # type: ignore[method-assign]
            return_value={
                "api_url": "https://opnsense.example.com",
                "api_key": "key",
                "api_secret": "secret",
            }
        )
        validator.api_validator.api_request = MagicMock(return_value=None)  # type: ignore[method-assign]
        validator.api_validator.add_success = MagicMock()  # type: ignore[method-assign]
        validator.api_validator.add_error = MagicMock()  # type: ignore[method-assign]

        validator.validate_connectivity()

        validator.api_validator.add_success.assert_not_called()
        validator.api_validator.add_error.assert_not_called()


class TestValidateReferences:
    """Tests for validate_references."""

    def test_missing_credentials_returns_early(self, validator: OPNsenseValidator) -> None:
        """Returns early when credentials are missing."""
        validator.api_validator.get_credentials = MagicMock(return_value=None)  # type: ignore[method-assign]

        validator.validate_references([])

    def test_delegates_to_specialized_validators(self, validator: OPNsenseValidator) -> None:
        """Delegates to all specialized validators."""
        validator.api_validator.get_credentials = MagicMock(  # type: ignore[method-assign]
            return_value={
                "api_url": "https://opnsense.example.com",
                "api_key": "key",
                "api_secret": "secret",
            }
        )
        validator.api_validator.fetch_json = MagicMock(return_value=None)  # type: ignore[method-assign]
        validator.firewall_rule_validator = MagicMock()
        validator.vlan_validator = MagicMock()
        validator.unbound_validator = MagicMock()
        validator.resource_name_validator = MagicMock()
        validator.interface_assignment_validator = MagicMock()

        resources = [
            ResourceConfig(name="alias1", type="firewall.aliases", provider="opnsense", config={}),
        ]

        validator.validate_references(resources)

        validator.firewall_rule_validator.validate.assert_called_once()
        validator.vlan_validator.validate.assert_called_once()
        validator.unbound_validator.validate.assert_called_once()
        validator.resource_name_validator.validate.assert_called_once()
        validator.interface_assignment_validator.validate.assert_called_once()

    def test_exception_caught_gracefully(self, validator: OPNsenseValidator) -> None:
        """Exceptions during validation are caught and reported."""
        validator.api_validator.get_credentials = MagicMock(  # type: ignore[method-assign]
            return_value={
                "api_url": "https://opnsense.example.com",
                "api_key": "key",
                "api_secret": "secret",
            }
        )
        validator.api_validator.fetch_json = MagicMock(side_effect=RuntimeError("unexpected"))  # type: ignore[method-assign]
        validator.api_validator.handle_validation_exception = MagicMock()  # type: ignore[method-assign]

        validator.validate_references(
            [
                ResourceConfig(
                    name="alias1", type="firewall.aliases", provider="opnsense", config={}
                ),
            ]
        )

        validator.api_validator.handle_validation_exception.assert_called_once()


def _reservation(name: str, subnet_ref: str) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="kea.dhcp4.reservations",
        provider="opnsense",
        config={
            "hw_address": "aa:bb:cc:dd:ee:01",
            "ip_address": "10.0.10.50",
            "hostname": name,
            "subnet_ref": subnet_ref,
        },
    )


def _subnet(name: str) -> ResourceConfig:
    return ResourceConfig(
        name=name, type="kea.dhcp4.subnets", provider="opnsense", config={"subnet": "10.0.10.0/24"}
    )


class TestReferenceResources:
    """A filtered run checks its resources but resolves names against all of them (#1133)."""

    @pytest.fixture
    def real_validator(self, env_config: Any) -> tuple[OPNsenseValidator, ValidationReport]:
        report = ValidationReport()
        validator = OPNsenseValidator(env_config, report)
        validator.api_validator.fetch_json = MagicMock(return_value=None)  # type: ignore[method-assign]
        return validator, report

    @staticmethod
    def _errors(report: ValidationReport) -> list[str]:
        return [r.message for r in report.results if not r.passed and r.level.value == "error"]

    def test_reference_outside_the_filter_resolves(
        self, real_validator: tuple[OPNsenseValidator, ValidationReport]
    ) -> None:
        validator, report = real_validator
        reservation = _reservation("k3s-server-dhcp", "opt1-infrastructure")

        validator.validate_references([reservation], [reservation, _subnet("opt1-infrastructure")])

        assert self._errors(report) == []

    def test_without_reference_resources_the_filtered_list_is_used(
        self, real_validator: tuple[OPNsenseValidator, ValidationReport]
    ) -> None:
        validator, report = real_validator

        validator.validate_references([_reservation("k3s-server-dhcp", "opt1-infrastructure")])

        assert any("unknown subnet_ref" in m for m in self._errors(report))

    def test_unknown_reference_still_errors(
        self, real_validator: tuple[OPNsenseValidator, ValidationReport]
    ) -> None:
        validator, report = real_validator
        reservation = _reservation("k3s-server-dhcp", "no-such-subnet")

        validator.validate_references([reservation], [reservation, _subnet("other")])

        assert any("'no-such-subnet'" in m for m in self._errors(report))

    def test_reference_resources_are_not_themselves_checked(
        self, real_validator: tuple[OPNsenseValidator, ValidationReport]
    ) -> None:
        """A broken resource outside the filter is not reported."""
        validator, report = real_validator
        in_scope = _reservation("in-scope", "lan")
        broken = _reservation("out-of-scope", "no-such-subnet")

        validator.validate_references([in_scope], [in_scope, broken, _subnet("lan")])

        assert self._errors(report) == []


class TestCollectResourceReferences:
    """Tests for _collect_resource_references."""

    def test_collects_aliases(self, validator: OPNsenseValidator) -> None:
        """Collects alias resources."""
        resources = [
            ResourceConfig(
                name="my-alias", type="firewall.aliases", provider="opnsense", config={}
            ),
        ]

        refs = validator._collect_resource_references(resources)

        assert "my-alias" in refs["alias_names"]
        assert len(refs["aliases"]) == 1

    def test_collects_vlans(self, validator: OPNsenseValidator) -> None:
        """Collects VLAN resources."""
        resources = [
            ResourceConfig(name="vlan10", type="interfaces.vlans", provider="opnsense", config={}),
        ]

        refs = validator._collect_resource_references(resources)

        assert "vlan10" in refs["vlan_names"]
        assert len(refs["vlans"]) == 1

    def test_collects_firewall_rules(self, validator: OPNsenseValidator) -> None:
        """Collects firewall rule resources."""
        resources = [
            ResourceConfig(name="rule1", type="firewall.rules", provider="opnsense", config={}),
        ]

        refs = validator._collect_resource_references(resources)

        assert len(refs["firewall_rules"]) == 1

    def test_collects_unbound_host_overrides(self, validator: OPNsenseValidator) -> None:
        """Collects unbound host override resources."""
        resources = [
            ResourceConfig(
                name="host1", type="unbound.host_overrides", provider="opnsense", config={}
            ),
        ]

        refs = validator._collect_resource_references(resources)

        assert len(refs["unbound_host_overrides"]) == 1

    def test_collects_interface_assignments(self, validator: OPNsenseValidator) -> None:
        """Collects interface_assignment resources."""
        resources = [
            ResourceConfig(
                name="lan",
                type="interfaces.assignments",
                provider="opnsense",
                config={"device": "ixl1"},
            ),
        ]

        refs = validator._collect_resource_references(resources)

        assert len(refs["interface_assignments"]) == 1
        assert "lan" in refs["interface_assignment_names"]

    def test_empty_resources(self, validator: OPNsenseValidator) -> None:
        """Returns empty collections for empty resources."""
        refs = validator._collect_resource_references([])

        assert len(refs["aliases"]) == 0
        assert len(refs["alias_names"]) == 0
        assert len(refs["vlans"]) == 0
        assert len(refs["interface_assignments"]) == 0
        assert len(refs["interface_assignment_names"]) == 0


class TestGetExistingAliases:
    """Tests for _get_existing_aliases."""

    def test_success_returns_aliases(self, validator: OPNsenseValidator) -> None:
        """Returns alias dict on successful API call."""
        validator.api_validator.fetch_json = MagicMock(  # type: ignore[method-assign]
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

    def test_api_failure_returns_empty(self, validator: OPNsenseValidator) -> None:
        """Returns empty dict on API failure."""
        validator.api_validator.fetch_json = MagicMock(return_value=None)  # type: ignore[method-assign]

        result = validator._get_existing_aliases("https://opn.example.com", "key", "secret")

        assert result == {}

    def test_skips_rows_without_name(self, validator: OPNsenseValidator) -> None:
        """Skips rows that don't have a name field."""
        validator.api_validator.fetch_json = MagicMock(  # type: ignore[method-assign]
            return_value={"rows": [{"name": "alias1"}, {"type": "host"}]}
        )

        result = validator._get_existing_aliases("https://opn.example.com", "key", "secret")

        assert len(result) == 1
        assert "alias1" in result


class TestGetExistingInterfaces:
    """Tests for _get_existing_interfaces."""

    def test_success_with_dict_format(self, validator: OPNsenseValidator) -> None:
        """Returns interfaces from dict format."""
        validator.api_validator.fetch_json = MagicMock(  # type: ignore[method-assign]
            return_value={
                "lan": {"device": "igc0", "if_type": "ethernet"},
                "wan": {"device": "igc1", "if_type": "ethernet"},
            }
        )

        result = validator._get_existing_interfaces("https://opn.example.com", "key", "secret")

        assert "lan" in result
        assert "wan" in result

    def test_success_with_list_format(self, validator: OPNsenseValidator) -> None:
        """Returns interfaces from list format."""
        validator.api_validator.fetch_json = MagicMock(  # type: ignore[method-assign]
            return_value=[
                {"name": "lan", "device": "igc0"},
                {"name": "wan", "device": "igc1"},
            ]
        )

        result = validator._get_existing_interfaces("https://opn.example.com", "key", "secret")

        assert "lan" in result
        assert "wan" in result

    def test_26_1_rows_resolve_identifier_and_device(self, validator: OPNsenseValidator) -> None:
        """26.1 rows (identifier/device, no name) resolve by both; empty identifier skipped."""
        validator.api_validator.fetch_json = MagicMock(  # type: ignore[method-assign]
            return_value=[
                {"identifier": "wan", "device": "em1", "description": "WAN"},
                {"identifier": "", "device": "enc0", "description": "Unassigned Interface"},
            ]
        )

        result = validator._get_existing_interfaces("https://opn.example.com", "key", "secret")

        assert set(result) == {"wan", "em1", "enc0"}
        assert "" not in result

    def test_legacy_name_row_still_resolves(self, validator: OPNsenseValidator) -> None:
        """Older name-shaped rows keep working and register device too."""
        validator.api_validator.fetch_json = MagicMock(  # type: ignore[method-assign]
            return_value=[{"name": "lan", "device": "igc0"}]
        )

        result = validator._get_existing_interfaces("https://opn.example.com", "key", "secret")

        assert set(result) == {"lan", "igc0"}

    def test_26_1_wan_reference_passes_rule_validators(self, validator: OPNsenseValidator) -> None:
        """Firewall rule, NAT rule and gateway referencing wan raise no unknown-interface error."""
        validator.api_validator.fetch_json = MagicMock(  # type: ignore[method-assign]
            return_value=[{"identifier": "wan", "device": "em1", "description": "WAN"}]
        )
        existing = validator._get_existing_interfaces("https://opn.example.com", "key", "secret")
        report = ValidationReport()

        fw = ResourceConfig(
            name="fw1",
            type="firewall.rules",
            provider="opnsense",
            config={"interface": "wan", "action": "pass", "direction": "in"},
        )
        FirewallRuleValidator(report).validate([fw], set(), set(), set(), existing, {}, set())
        nat = ResourceConfig(
            name="nat1",
            type="firewall.nat_rules",
            provider="opnsense",
            config={"interface": "wan"},
        )
        NATRuleValidator(report).validate([nat], set(), set(), existing, {})
        gw = ResourceConfig(
            name="WAN_GW",
            type="routing.gateways",
            provider="opnsense",
            config={"interface": "wan", "protocol": "inet", "gateway": "192.0.2.1"},
        )
        GatewayValidator(report).validate([gw], set(), existing)

        bad = [r for r in report.results if "unknown interface" in r.message]
        assert not bad
        resolved = [r for r in report.results if "wan" in r.message and r.passed]
        assert len(resolved) >= 3

    def test_api_failure_returns_empty(self, validator: OPNsenseValidator) -> None:
        """Returns empty dict on API failure."""
        validator.api_validator.fetch_json = MagicMock(return_value=None)  # type: ignore[method-assign]

        result = validator._get_existing_interfaces("https://opn.example.com", "key", "secret")

        assert result == {}


class TestNormalizeInterfaceData:
    """Tests for _normalize_interface_data."""

    def test_dict_format(self, validator: OPNsenseValidator) -> None:
        """Normalizes dict format to list."""
        data = {"lan": {"device": "igc0"}, "wan": {"device": "igc1"}}

        result = validator._normalize_interface_data(data)

        assert len(result) == 2
        names = [item["name"] for item in result]
        assert "lan" in names
        assert "wan" in names

    def test_list_format(self, validator: OPNsenseValidator) -> None:
        """Passes through list format."""
        data = [{"name": "lan"}, {"name": "wan"}]

        result = validator._normalize_interface_data(data)

        assert len(result) == 2

    def test_non_dict_values_skipped(self, validator: OPNsenseValidator) -> None:
        """Skips non-dict values in dict format."""
        data = {"lan": {"device": "igc0"}, "count": 42}

        result = validator._normalize_interface_data(data)

        assert len(result) == 1

    def test_non_dict_items_skipped_in_list(self, validator: OPNsenseValidator) -> None:
        """Skips non-dict items in list format."""
        data = [{"name": "lan"}, "not-a-dict", 42]

        result = validator._normalize_interface_data(data)

        assert len(result) == 1

    def test_unknown_type_returns_empty(self, validator: OPNsenseValidator) -> None:
        """Returns empty list for unknown data types."""
        result = validator._normalize_interface_data("unexpected")

        assert result == []


class TestExtractInterfaceName:
    """Tests for _extract_interface_name."""

    def test_name_field(self, validator: OPNsenseValidator) -> None:
        """Extracts from 'name' field."""
        assert validator._extract_interface_name({"name": "lan"}) == "lan"

    def test_device_field(self, validator: OPNsenseValidator) -> None:
        """Falls back to 'device' field."""
        assert validator._extract_interface_name({"device": "igc0"}) == "igc0"

    def test_if_field(self, validator: OPNsenseValidator) -> None:
        """Falls back to 'if' field."""
        assert validator._extract_interface_name({"if": "em0"}) == "em0"

    def test_interface_field(self, validator: OPNsenseValidator) -> None:
        """Falls back to 'interface' field."""
        assert validator._extract_interface_name({"interface": "eth0"}) == "eth0"

    def test_priority_order(self, validator: OPNsenseValidator) -> None:
        """Returns 'name' over 'device' when both present."""
        assert validator._extract_interface_name({"name": "lan", "device": "igc0"}) == "lan"

    def test_no_fields_returns_none(self, validator: OPNsenseValidator) -> None:
        """Returns None when no recognized fields."""
        assert validator._extract_interface_name({"type": "ethernet"}) is None
