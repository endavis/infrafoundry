"""Unit tests for OPNsense DHCPv6 change detection logic.

Tests the static helper methods that extract and normalize fields from OPNsense
API responses and desired configuration, as well as the integration behaviour of
``_generate_kea_dhcp6_resources`` — verifying that updates and reconfigure calls
are skipped when no changes are detected.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense import OPNsenseProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def provider(tmp_path: Path) -> OPNsenseProvider:
    """Create OPNsense provider instance."""
    config_dir = tmp_path / "config"
    output_dir = tmp_path / "output"
    return OPNsenseProvider(config_dir, output_dir)


# ---------------------------------------------------------------------------
# _extract_subnet_fields
# ---------------------------------------------------------------------------


class TestExtractSubnetFields:
    """Tests for _extract_subnet_fields static method."""

    def test_simple_string_fields(self) -> None:
        """Extract flat string fields from a subnet GET response."""
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "pools": "::10-::ff",
                "valid_lifetime": "3600",
                "description": "VLAN 10",
                "interface": "opt1",
            }
        }
        result = OPNsenseProvider._extract_subnet_fields(api_response)
        assert result["subnet"] == "fd00:1::/64"
        assert result["pools"] == "::10-::ff"
        assert result["valid_lifetime"] == "3600"
        assert result["description"] == "VLAN 10"
        assert result["interface"] == "opt1"

    def test_interface_as_dict_with_selected(self) -> None:
        """Interface returned as a dict with selected indicators."""
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "interface": {
                    "opt1": {"value": "OPT1", "selected": 1},
                    "opt2": {"value": "OPT2", "selected": 0},
                },
            }
        }
        result = OPNsenseProvider._extract_subnet_fields(api_response)
        assert result["interface"] == "opt1"

    def test_interface_as_dict_multiple_selected(self) -> None:
        """Multiple interfaces selected — returned sorted and comma-joined."""
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "interface": {
                    "opt2": {"value": "OPT2", "selected": 1},
                    "opt1": {"value": "OPT1", "selected": 1},
                },
            }
        }
        result = OPNsenseProvider._extract_subnet_fields(api_response)
        assert result["interface"] == "opt1,opt2"

    def test_option_data_extracted(self) -> None:
        """DNS settings from option_data are extracted with dotted keys."""
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "option_data": {
                    "dns_servers": "fd00::1,fd00::2",
                    "domain_search": "example.com",
                },
            }
        }
        result = OPNsenseProvider._extract_subnet_fields(api_response)
        assert result["option_data.dns_servers"] == "fd00::1,fd00::2"
        assert result["option_data.domain_search"] == "example.com"

    def test_missing_fields_default_to_empty(self) -> None:
        """Missing or None fields default to empty strings."""
        api_response: dict[str, Any] = {"subnet6": {}}
        result = OPNsenseProvider._extract_subnet_fields(api_response)
        assert result["subnet"] == ""
        assert result["pools"] == ""
        assert result["valid_lifetime"] == ""
        assert result["description"] == ""
        assert result["interface"] == ""
        assert result["option_data.dns_servers"] == ""
        assert result["option_data.domain_search"] == ""

    def test_none_values_normalized(self) -> None:
        """None field values are normalized to empty strings."""
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": None,
                "interface": None,
                "pools": None,
            }
        }
        result = OPNsenseProvider._extract_subnet_fields(api_response)
        assert result["subnet"] == ""
        assert result["interface"] == ""
        assert result["pools"] == ""

    def test_missing_wrapper_key(self) -> None:
        """Response without the 'subnet6' wrapper key returns empty fields."""
        api_response: dict[str, Any] = {}
        result = OPNsenseProvider._extract_subnet_fields(api_response)
        assert result["subnet"] == ""
        assert result["interface"] == ""


# ---------------------------------------------------------------------------
# _extract_reservation_fields
# ---------------------------------------------------------------------------


class TestExtractReservationFields:
    """Tests for _extract_reservation_fields static method."""

    def test_simple_string_fields(self) -> None:
        """Extract flat string fields from a reservation GET response."""
        api_response: dict[str, Any] = {
            "reservation": {
                "ip_address": "fd00:1::10",
                "duid": "00:01:00:01:2c:3d:00:01",
                "hostname": "server1",
                "description": "Main server",
                "subnet": "uuid-1234",
            }
        }
        result = OPNsenseProvider._extract_reservation_fields(api_response)
        assert result["ip_address"] == "fd00:1::10"
        assert result["duid"] == "00:01:00:01:2c:3d:00:01"
        assert result["hostname"] == "server1"
        assert result["description"] == "Main server"
        assert result["subnet"] == "uuid-1234"

    def test_subnet_as_dict_with_selected(self) -> None:
        """Subnet returned as a dict with selected UUID."""
        api_response: dict[str, Any] = {
            "reservation": {
                "ip_address": "fd00:1::10",
                "duid": "00:01:00:01:2c:3d:00:01",
                "hostname": "server1",
                "description": "",
                "subnet": {
                    "uuid-1234": {"value": "fd00:1::/64", "selected": 1},
                    "uuid-5678": {"value": "fd00:2::/64", "selected": 0},
                },
            }
        }
        result = OPNsenseProvider._extract_reservation_fields(api_response)
        assert result["subnet"] == "uuid-1234"

    def test_missing_fields_default_to_empty(self) -> None:
        """Missing fields default to empty strings."""
        api_response: dict[str, Any] = {"reservation": {}}
        result = OPNsenseProvider._extract_reservation_fields(api_response)
        assert result["ip_address"] == ""
        assert result["duid"] == ""
        assert result["hostname"] == ""
        assert result["description"] == ""
        assert result["subnet"] == ""

    def test_missing_wrapper_key(self) -> None:
        """Response without the 'reservation' wrapper key returns empty fields."""
        api_response: dict[str, Any] = {}
        result = OPNsenseProvider._extract_reservation_fields(api_response)
        assert result["subnet"] == ""
        assert result["ip_address"] == ""


# ---------------------------------------------------------------------------
# _build_desired_subnet_fields
# ---------------------------------------------------------------------------


class TestBuildDesiredSubnetFields:
    """Tests for _build_desired_subnet_fields static method."""

    def test_basic_subnet_data(self) -> None:
        """Build normalized fields from basic subnet data."""
        subnet_data: dict[str, Any] = {
            "subnet": "fd00:1::/64",
            "interface": "opt1",
            "pools": "::10-::ff",
            "valid_lifetime": "3600",
            "description": "VLAN 10",
        }
        result = OPNsenseProvider._build_desired_subnet_fields(subnet_data)
        assert result["subnet"] == "fd00:1::/64"
        assert result["interface"] == "opt1"
        assert result["pools"] == "::10-::ff"
        assert result["valid_lifetime"] == "3600"
        assert result["description"] == "VLAN 10"
        assert result["option_data.dns_servers"] == ""
        assert result["option_data.domain_search"] == ""

    def test_with_option_data(self) -> None:
        """Build normalized fields including option_data."""
        subnet_data: dict[str, Any] = {
            "subnet": "fd00:1::/64",
            "interface": "opt1",
            "option_data": {
                "dns_servers": "fd00::1,fd00::2",
                "domain_search": "example.com",
            },
        }
        result = OPNsenseProvider._build_desired_subnet_fields(subnet_data)
        assert result["option_data.dns_servers"] == "fd00::1,fd00::2"
        assert result["option_data.domain_search"] == "example.com"

    def test_missing_fields_default_to_empty(self) -> None:
        """Missing fields default to empty strings."""
        result = OPNsenseProvider._build_desired_subnet_fields({})
        assert result["subnet"] == ""
        assert result["interface"] == ""
        assert result["pools"] == ""
        assert result["valid_lifetime"] == ""
        assert result["description"] == ""


# ---------------------------------------------------------------------------
# _build_desired_reservation_fields
# ---------------------------------------------------------------------------


class TestBuildDesiredReservationFields:
    """Tests for _build_desired_reservation_fields static method."""

    def test_basic_reservation_data(self) -> None:
        """Build normalized fields from basic reservation data."""
        reservation_data: dict[str, Any] = {
            "subnet": "uuid-1234",
            "ip_address": "fd00:1::10",
            "duid": "00:01:00:01:2c:3d:00:01",
            "hostname": "server1",
            "description": "Main server",
        }
        result = OPNsenseProvider._build_desired_reservation_fields(reservation_data)
        assert result["subnet"] == "uuid-1234"
        assert result["ip_address"] == "fd00:1::10"
        assert result["duid"] == "00:01:00:01:2c:3d:00:01"
        assert result["hostname"] == "server1"
        assert result["description"] == "Main server"

    def test_missing_fields_default_to_empty(self) -> None:
        """Missing fields default to empty strings."""
        result = OPNsenseProvider._build_desired_reservation_fields({})
        assert all(v == "" for v in result.values())


# ---------------------------------------------------------------------------
# Field comparison round-trip (extract vs build produce matching results)
# ---------------------------------------------------------------------------


class TestFieldComparisonRoundTrip:
    """Verify that extract and build produce matching dicts for unchanged config."""

    def test_subnet_unchanged(self) -> None:
        """Subnet fields match when API returns identical values."""
        desired: dict[str, Any] = {
            "subnet": "fd00:1::/64",
            "interface": "opt1",
            "pools": "::10-::ff",
            "valid_lifetime": "3600",
            "description": "VLAN 10",
            "option_data": {
                "dns_servers": "fd00::1",
                "domain_search": "example.com",
            },
        }
        # Simulate what the API returns for the same config
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "interface": "opt1",
                "pools": "::10-::ff",
                "valid_lifetime": "3600",
                "description": "VLAN 10",
                "option_data": {
                    "dns_servers": "fd00::1",
                    "domain_search": "example.com",
                },
            }
        }
        assert OPNsenseProvider._extract_subnet_fields(
            api_response
        ) == OPNsenseProvider._build_desired_subnet_fields(desired)

    def test_subnet_changed_description(self) -> None:
        """Subnet fields differ when description changes."""
        desired: dict[str, Any] = {
            "subnet": "fd00:1::/64",
            "interface": "opt1",
            "description": "Updated VLAN 10",
        }
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "interface": "opt1",
                "description": "VLAN 10",
            }
        }
        assert OPNsenseProvider._extract_subnet_fields(
            api_response
        ) != OPNsenseProvider._build_desired_subnet_fields(desired)

    def test_reservation_unchanged(self) -> None:
        """Reservation fields match when API returns identical values."""
        desired: dict[str, Any] = {
            "subnet": "uuid-1234",
            "ip_address": "fd00:1::10",
            "duid": "00:01:00:01:2c:3d:00:01",
            "hostname": "server1",
            "description": "",
        }
        api_response: dict[str, Any] = {
            "reservation": {
                "subnet": "uuid-1234",
                "ip_address": "fd00:1::10",
                "duid": "00:01:00:01:2c:3d:00:01",
                "hostname": "server1",
                "description": "",
            }
        }
        assert OPNsenseProvider._extract_reservation_fields(
            api_response
        ) == OPNsenseProvider._build_desired_reservation_fields(desired)

    def test_reservation_changed_ip(self) -> None:
        """Reservation fields differ when IP changes."""
        desired: dict[str, Any] = {
            "subnet": "uuid-1234",
            "ip_address": "fd00:1::20",
            "duid": "00:01:00:01:2c:3d:00:01",
            "hostname": "server1",
            "description": "",
        }
        api_response: dict[str, Any] = {
            "reservation": {
                "subnet": "uuid-1234",
                "ip_address": "fd00:1::10",
                "duid": "00:01:00:01:2c:3d:00:01",
                "hostname": "server1",
                "description": "",
            }
        }
        assert OPNsenseProvider._extract_reservation_fields(
            api_response
        ) != OPNsenseProvider._build_desired_reservation_fields(desired)


# ---------------------------------------------------------------------------
# Type normalization
# ---------------------------------------------------------------------------


class TestTypeNormalization:
    """Ensure integer/string type mismatches are handled correctly."""

    def test_valid_lifetime_int_vs_string(self) -> None:
        """Integer valid_lifetime in desired matches string in API response."""
        # The provider code already converts to str via str(config["valid_lifetime"])
        # but the build helper also normalizes via str()
        desired: dict[str, Any] = {"valid_lifetime": 3600}
        api_response: dict[str, Any] = {"subnet6": {"valid_lifetime": "3600"}}
        assert (
            OPNsenseProvider._extract_subnet_fields(api_response)["valid_lifetime"]
            == OPNsenseProvider._build_desired_subnet_fields(desired)["valid_lifetime"]
        )


# ---------------------------------------------------------------------------
# Integration: _generate_kea_dhcp6_resources with mocked API
# ---------------------------------------------------------------------------


def _make_kea_mock(
    existing_subnets: list[dict[str, Any]] | None = None,
    existing_reservations: list[dict[str, Any]] | None = None,
    get_subnet_responses: dict[str, dict[str, Any]] | None = None,
    get_reservation_responses: dict[str, dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mock KeaClient with preconfigured responses."""
    kea = MagicMock()
    kea.search_dhcp6_subnets.return_value = existing_subnets or []
    kea.search_dhcp6_reservations.return_value = existing_reservations or []

    def _get_subnet(uuid: str) -> dict[str, Any]:
        return (get_subnet_responses or {}).get(uuid, {"subnet6": {}})

    def _get_reservation(uuid: str) -> dict[str, Any]:
        return (get_reservation_responses or {}).get(uuid, {"reservation": {}})

    kea.get_dhcp6_subnet.side_effect = _get_subnet
    kea.get_dhcp6_reservation.side_effect = _get_reservation
    kea.add_dhcp6_subnet.return_value = {"result": "saved"}
    kea.add_dhcp6_reservation.return_value = {"result": "saved"}
    kea.update_dhcp6_subnet.return_value = {"result": "saved"}
    kea.update_dhcp6_reservation.return_value = {"result": "saved"}
    kea.reconfigure_service.return_value = {"status": "ok"}

    return kea


def _patch_env_and_client(
    provider: OPNsenseProvider,
    kea_mock: MagicMock,
) -> tuple[Any, Any]:
    """Return context managers that patch environment loading and KeaClient."""
    provider._current_environment = "test"  # type: ignore[attr-defined]

    config_mgr_patch = patch("infrafoundry.providers.opnsense.ConfigManager")
    client_patch = patch("infrafoundry.providers.opnsense.OPNsenseClient")
    kea_patch = patch("infrafoundry.providers.opnsense.KeaClient", return_value=kea_mock)

    return config_mgr_patch, client_patch, kea_patch


class TestGenerateKeaDhcp6ResourcesNoChanges:
    """When existing resources match desired state, skip updates and reconfigure."""

    def test_subnet_unchanged_skips_update_and_reconfigure(
        self, provider: OPNsenseProvider
    ) -> None:
        """No update or reconfigure when subnet config matches."""
        subnet = ResourceConfig(
            provider="opnsense",
            type="kea_dhcp6_subnet",
            name="vlan10-v6",
            config={
                "subnet": "fd00:1::/64",
                "interface": "opt1",
                "pools": [{"range": "::10-::ff"}],
                "valid_lifetime": 3600,
                "description": "VLAN 10",
            },
        )

        kea = _make_kea_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "sub-uuid-1"}],
            get_subnet_responses={
                "sub-uuid-1": {
                    "subnet6": {
                        "subnet": "fd00:1::/64",
                        "interface": "opt1",
                        "pools": "::10-::ff",
                        "valid_lifetime": "3600",
                        "description": "VLAN 10",
                    }
                }
            },
        )

        provider._current_environment = "test"  # type: ignore[attr-defined]
        with (
            patch("infrafoundry.core.config.ConfigManager") as cfg_cls,
            patch(
                "infrafoundry.providers.opnsense.api_client.OPNsenseClient",
            ),
            patch(
                "infrafoundry.providers.opnsense.api_client.KeaClient",
                return_value=kea,
            ),
        ):
            env_config = MagicMock()
            env_config.get_provider_settings.return_value = {
                "api_key": "k",
                "api_secret": "s",
                "api_url": "https://fw",
            }
            cfg_cls.return_value.load_environment.return_value = env_config

            provider._generate_kea_dhcp6_resources([subnet], [])

        kea.update_dhcp6_subnet.assert_not_called()
        kea.reconfigure_service.assert_not_called()

    def test_reservation_unchanged_skips_update_and_reconfigure(
        self, provider: OPNsenseProvider
    ) -> None:
        """No update or reconfigure when reservation config matches."""
        reservation = ResourceConfig(
            provider="opnsense",
            type="kea_dhcp6_reservation",
            name="server1-v6",
            config={
                "subnet": "fd00:1::/64",
                "ip_address": "fd00:1::10",
                "duid": "00:01:00:01:2c:3d:00:01",
                "hostname": "server1",
                "description": "",
            },
        )

        kea = _make_kea_mock(
            existing_reservations=[
                {
                    "duid": "00:01:00:01:2c:3d:00:01",
                    "subnet": "sub-uuid-1",
                    "uuid": "res-uuid-1",
                }
            ],
            get_reservation_responses={
                "res-uuid-1": {
                    "reservation": {
                        "subnet": "sub-uuid-1",
                        "ip_address": "fd00:1::10",
                        "duid": "00:01:00:01:2c:3d:00:01",
                        "hostname": "server1",
                        "description": "",
                    }
                }
            },
        )

        # Provide the subnet map so the reservation can resolve its subnet UUID
        kea.search_dhcp6_subnets.return_value = [{"subnet": "fd00:1::/64", "uuid": "sub-uuid-1"}]

        provider._current_environment = "test"  # type: ignore[attr-defined]
        with (
            patch("infrafoundry.core.config.ConfigManager") as cfg_cls,
            patch(
                "infrafoundry.providers.opnsense.api_client.OPNsenseClient",
            ),
            patch(
                "infrafoundry.providers.opnsense.api_client.KeaClient",
                return_value=kea,
            ),
        ):
            env_config = MagicMock()
            env_config.get_provider_settings.return_value = {
                "api_key": "k",
                "api_secret": "s",
                "api_url": "https://fw",
            }
            cfg_cls.return_value.load_environment.return_value = env_config

            # Pass empty subnets list but provide the subnet in search results
            # so the reservation can resolve its subnet_id
            provider._generate_kea_dhcp6_resources([], [reservation])

        kea.update_dhcp6_reservation.assert_not_called()
        kea.reconfigure_service.assert_not_called()


class TestGenerateKeaDhcp6ResourcesWithChanges:
    """When existing resources differ from desired state, update and reconfigure."""

    def test_subnet_changed_triggers_update_and_reconfigure(
        self, provider: OPNsenseProvider
    ) -> None:
        """Update and reconfigure when subnet description changes."""
        subnet = ResourceConfig(
            provider="opnsense",
            type="kea_dhcp6_subnet",
            name="vlan10-v6",
            config={
                "subnet": "fd00:1::/64",
                "interface": "opt1",
                "description": "Updated VLAN 10",
            },
        )

        kea = _make_kea_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "sub-uuid-1"}],
            get_subnet_responses={
                "sub-uuid-1": {
                    "subnet6": {
                        "subnet": "fd00:1::/64",
                        "interface": "opt1",
                        "description": "VLAN 10",
                    }
                }
            },
        )

        provider._current_environment = "test"  # type: ignore[attr-defined]
        with (
            patch("infrafoundry.core.config.ConfigManager") as cfg_cls,
            patch("infrafoundry.providers.opnsense.api_client.OPNsenseClient"),
            patch("infrafoundry.providers.opnsense.api_client.KeaClient", return_value=kea),
        ):
            env_config = MagicMock()
            env_config.get_provider_settings.return_value = {
                "api_key": "k",
                "api_secret": "s",
                "api_url": "https://fw",
            }
            cfg_cls.return_value.load_environment.return_value = env_config

            provider._generate_kea_dhcp6_resources([subnet], [])

        kea.update_dhcp6_subnet.assert_called_once()
        kea.reconfigure_service.assert_called_once()

    def test_reservation_changed_triggers_update_and_reconfigure(
        self, provider: OPNsenseProvider
    ) -> None:
        """Update and reconfigure when reservation IP changes."""
        # A subnet resource is needed so existing_subnets_map gets populated
        subnet = ResourceConfig(
            provider="opnsense",
            type="kea_dhcp6_subnet",
            name="vlan10-v6",
            config={
                "subnet": "fd00:1::/64",
                "interface": "opt1",
            },
        )
        reservation = ResourceConfig(
            provider="opnsense",
            type="kea_dhcp6_reservation",
            name="server1-v6",
            config={
                "subnet": "fd00:1::/64",
                "ip_address": "fd00:1::20",
                "duid": "00:01:00:01:2c:3d:00:01",
                "hostname": "server1",
                "description": "",
            },
        )

        kea = _make_kea_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "sub-uuid-1"}],
            existing_reservations=[
                {
                    "duid": "00:01:00:01:2c:3d:00:01",
                    "subnet": "sub-uuid-1",
                    "uuid": "res-uuid-1",
                }
            ],
            get_subnet_responses={
                "sub-uuid-1": {
                    "subnet6": {
                        "subnet": "fd00:1::/64",
                        "interface": "opt1",
                    }
                }
            },
            get_reservation_responses={
                "res-uuid-1": {
                    "reservation": {
                        "subnet": "sub-uuid-1",
                        "ip_address": "fd00:1::10",
                        "duid": "00:01:00:01:2c:3d:00:01",
                        "hostname": "server1",
                        "description": "",
                    }
                }
            },
        )

        provider._current_environment = "test"  # type: ignore[attr-defined]
        with (
            patch("infrafoundry.core.config.ConfigManager") as cfg_cls,
            patch("infrafoundry.providers.opnsense.api_client.OPNsenseClient"),
            patch("infrafoundry.providers.opnsense.api_client.KeaClient", return_value=kea),
        ):
            env_config = MagicMock()
            env_config.get_provider_settings.return_value = {
                "api_key": "k",
                "api_secret": "s",
                "api_url": "https://fw",
            }
            cfg_cls.return_value.load_environment.return_value = env_config

            provider._generate_kea_dhcp6_resources([subnet], [reservation])

        kea.update_dhcp6_reservation.assert_called_once()
        kea.reconfigure_service.assert_called_once()

    def test_new_subnet_triggers_create_and_reconfigure(self, provider: OPNsenseProvider) -> None:
        """Create and reconfigure when subnet does not exist yet."""
        subnet = ResourceConfig(
            provider="opnsense",
            type="kea_dhcp6_subnet",
            name="vlan10-v6",
            config={
                "subnet": "fd00:1::/64",
                "interface": "opt1",
            },
        )

        kea = _make_kea_mock(existing_subnets=[])
        # First call returns [] (initial search), second returns created subnet
        kea.search_dhcp6_subnets.side_effect = [
            [],
            [{"subnet": "fd00:1::/64", "uuid": "new-uuid"}],
        ]

        provider._current_environment = "test"  # type: ignore[attr-defined]
        with (
            patch("infrafoundry.core.config.ConfigManager") as cfg_cls,
            patch("infrafoundry.providers.opnsense.api_client.OPNsenseClient"),
            patch("infrafoundry.providers.opnsense.api_client.KeaClient", return_value=kea),
        ):
            env_config = MagicMock()
            env_config.get_provider_settings.return_value = {
                "api_key": "k",
                "api_secret": "s",
                "api_url": "https://fw",
            }
            cfg_cls.return_value.load_environment.return_value = env_config

            provider._generate_kea_dhcp6_resources([subnet], [])

        kea.add_dhcp6_subnet.assert_called_once()
        kea.reconfigure_service.assert_called_once()

    def test_new_reservation_triggers_create_and_reconfigure(
        self, provider: OPNsenseProvider
    ) -> None:
        """Create and reconfigure when reservation does not exist yet."""
        # A subnet resource is needed so existing_subnets_map gets populated
        subnet = ResourceConfig(
            provider="opnsense",
            type="kea_dhcp6_subnet",
            name="vlan10-v6",
            config={
                "subnet": "fd00:1::/64",
                "interface": "opt1",
            },
        )
        reservation = ResourceConfig(
            provider="opnsense",
            type="kea_dhcp6_reservation",
            name="server1-v6",
            config={
                "subnet": "fd00:1::/64",
                "ip_address": "fd00:1::10",
                "duid": "00:01:00:01:2c:3d:00:01",
                "hostname": "server1",
                "description": "",
            },
        )

        kea = _make_kea_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "sub-uuid-1"}],
            existing_reservations=[],
            get_subnet_responses={
                "sub-uuid-1": {
                    "subnet6": {
                        "subnet": "fd00:1::/64",
                        "interface": "opt1",
                    }
                }
            },
        )

        provider._current_environment = "test"  # type: ignore[attr-defined]
        with (
            patch("infrafoundry.core.config.ConfigManager") as cfg_cls,
            patch("infrafoundry.providers.opnsense.api_client.OPNsenseClient"),
            patch("infrafoundry.providers.opnsense.api_client.KeaClient", return_value=kea),
        ):
            env_config = MagicMock()
            env_config.get_provider_settings.return_value = {
                "api_key": "k",
                "api_secret": "s",
                "api_url": "https://fw",
            }
            cfg_cls.return_value.load_environment.return_value = env_config

            provider._generate_kea_dhcp6_resources([subnet], [reservation])

        kea.add_dhcp6_reservation.assert_called_once()
        kea.reconfigure_service.assert_called_once()


class TestGenerateKeaDhcp6ResourcesMixedChanges:
    """Mixed scenarios: some resources changed, some not."""

    def test_mixed_subnets_only_updates_changed(self, provider: OPNsenseProvider) -> None:
        """Only the changed subnet is updated; reconfigure still called."""
        subnet_unchanged = ResourceConfig(
            provider="opnsense",
            type="kea_dhcp6_subnet",
            name="vlan10-v6",
            config={
                "subnet": "fd00:1::/64",
                "interface": "opt1",
                "description": "VLAN 10",
            },
        )
        subnet_changed = ResourceConfig(
            provider="opnsense",
            type="kea_dhcp6_subnet",
            name="vlan20-v6",
            config={
                "subnet": "fd00:2::/64",
                "interface": "opt2",
                "description": "Updated VLAN 20",
            },
        )

        kea = _make_kea_mock(
            existing_subnets=[
                {"subnet": "fd00:1::/64", "uuid": "sub-uuid-1"},
                {"subnet": "fd00:2::/64", "uuid": "sub-uuid-2"},
            ],
            get_subnet_responses={
                "sub-uuid-1": {
                    "subnet6": {
                        "subnet": "fd00:1::/64",
                        "interface": "opt1",
                        "description": "VLAN 10",
                    }
                },
                "sub-uuid-2": {
                    "subnet6": {
                        "subnet": "fd00:2::/64",
                        "interface": "opt2",
                        "description": "VLAN 20",
                    }
                },
            },
        )

        provider._current_environment = "test"  # type: ignore[attr-defined]
        with (
            patch("infrafoundry.core.config.ConfigManager") as cfg_cls,
            patch("infrafoundry.providers.opnsense.api_client.OPNsenseClient"),
            patch("infrafoundry.providers.opnsense.api_client.KeaClient", return_value=kea),
        ):
            env_config = MagicMock()
            env_config.get_provider_settings.return_value = {
                "api_key": "k",
                "api_secret": "s",
                "api_url": "https://fw",
            }
            cfg_cls.return_value.load_environment.return_value = env_config

            provider._generate_kea_dhcp6_resources([subnet_unchanged, subnet_changed], [])

        # Only subnet-2 should be updated
        kea.update_dhcp6_subnet.assert_called_once()
        call_args = kea.update_dhcp6_subnet.call_args
        assert call_args[0][0] == "sub-uuid-2"  # UUID of changed subnet
        kea.reconfigure_service.assert_called_once()


class TestSubnetWithInterfaceDict:
    """Handle OPNsense API returning interface as a dict with selected flags."""

    def test_interface_dict_matching_skips_update(self, provider: OPNsenseProvider) -> None:
        """Skip update when interface dict's selected value matches desired."""
        subnet = ResourceConfig(
            provider="opnsense",
            type="kea_dhcp6_subnet",
            name="vlan10-v6",
            config={
                "subnet": "fd00:1::/64",
                "interface": "opt1",
            },
        )

        kea = _make_kea_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "sub-uuid-1"}],
            get_subnet_responses={
                "sub-uuid-1": {
                    "subnet6": {
                        "subnet": "fd00:1::/64",
                        "interface": {
                            "opt1": {"value": "OPT1", "selected": 1},
                            "opt2": {"value": "OPT2", "selected": 0},
                        },
                    }
                }
            },
        )

        provider._current_environment = "test"  # type: ignore[attr-defined]
        with (
            patch("infrafoundry.core.config.ConfigManager") as cfg_cls,
            patch("infrafoundry.providers.opnsense.api_client.OPNsenseClient"),
            patch("infrafoundry.providers.opnsense.api_client.KeaClient", return_value=kea),
        ):
            env_config = MagicMock()
            env_config.get_provider_settings.return_value = {
                "api_key": "k",
                "api_secret": "s",
                "api_url": "https://fw",
            }
            cfg_cls.return_value.load_environment.return_value = env_config

            provider._generate_kea_dhcp6_resources([subnet], [])

        kea.update_dhcp6_subnet.assert_not_called()
        kea.reconfigure_service.assert_not_called()


class TestReservationWithSubnetDict:
    """Handle OPNsense API returning subnet as a dict with selected flags."""

    def test_subnet_dict_matching_skips_update(self, provider: OPNsenseProvider) -> None:
        """Skip update when subnet dict's selected UUID matches desired."""
        reservation = ResourceConfig(
            provider="opnsense",
            type="kea_dhcp6_reservation",
            name="server1-v6",
            config={
                "subnet": "fd00:1::/64",
                "ip_address": "fd00:1::10",
                "duid": "00:01:00:01:2c:3d:00:01",
                "hostname": "server1",
                "description": "",
            },
        )

        kea = _make_kea_mock(
            existing_reservations=[
                {
                    "duid": "00:01:00:01:2c:3d:00:01",
                    "subnet": "sub-uuid-1",
                    "uuid": "res-uuid-1",
                }
            ],
            get_reservation_responses={
                "res-uuid-1": {
                    "reservation": {
                        "subnet": {
                            "sub-uuid-1": {"value": "fd00:1::/64", "selected": 1},
                            "sub-uuid-2": {"value": "fd00:2::/64", "selected": 0},
                        },
                        "ip_address": "fd00:1::10",
                        "duid": "00:01:00:01:2c:3d:00:01",
                        "hostname": "server1",
                        "description": "",
                    }
                }
            },
        )

        kea.search_dhcp6_subnets.return_value = [{"subnet": "fd00:1::/64", "uuid": "sub-uuid-1"}]

        provider._current_environment = "test"  # type: ignore[attr-defined]
        with (
            patch("infrafoundry.core.config.ConfigManager") as cfg_cls,
            patch("infrafoundry.providers.opnsense.api_client.OPNsenseClient"),
            patch("infrafoundry.providers.opnsense.api_client.KeaClient", return_value=kea),
        ):
            env_config = MagicMock()
            env_config.get_provider_settings.return_value = {
                "api_key": "k",
                "api_secret": "s",
                "api_url": "https://fw",
            }
            cfg_cls.return_value.load_environment.return_value = env_config

            provider._generate_kea_dhcp6_resources([], [reservation])

        kea.update_dhcp6_reservation.assert_not_called()
        kea.reconfigure_service.assert_not_called()
