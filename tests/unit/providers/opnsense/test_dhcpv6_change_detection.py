"""Unit tests for OPNsense DHCPv6 change detection logic.

Tests the static helper methods that extract and normalize fields from OPNsense
API responses and desired configuration, as well as the integration behaviour of
``_generate_kea_dhcp6_resources`` — verifying that updates and reconfigure calls
are skipped when no changes are detected.
"""

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense import OPNsenseProvider, _normalize_field_value

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

    def test_option_data_dns_servers_as_option_dict_empty_selected(self) -> None:
        """DNS servers returned as the live empty-sentinel option-dict.

        Captured live shape from OPNsense 25.7.11_1 when no DNS server is set.
        Must extract to "" so it compares equal to a desired side that omits
        the field.  Regression for #756.
        """
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "option_data": {
                    "dns_servers": {"": {"value": "", "selected": 1}},
                    "domain_search": {"": {"value": "", "selected": 1}},
                    "v6_dnr": "",
                },
            }
        }
        result = OPNsenseProvider._extract_subnet_fields(api_response)
        assert result["option_data.dns_servers"] == ""
        assert result["option_data.domain_search"] == ""

    def test_option_data_dns_servers_as_option_dict_with_value(self) -> None:
        """DNS servers option-dict with one entry selected returns that key."""
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "option_data": {
                    "dns_servers": {
                        "2606:4700::1": {"value": "2606:4700::1", "selected": 1},
                        "2001:4860:4860::8888": {
                            "value": "2001:4860:4860::8888",
                            "selected": 0,
                        },
                    },
                    "domain_search": {"": {"value": "", "selected": 1}},
                },
            }
        }
        result = OPNsenseProvider._extract_subnet_fields(api_response)
        assert result["option_data.dns_servers"] == "2606:4700::1"
        assert result["option_data.domain_search"] == ""

    def test_option_data_dns_servers_as_option_dict_multiple_selected(self) -> None:
        """Multiple DNS servers selected — sorted and comma-joined (matches interface)."""
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "option_data": {
                    "dns_servers": {
                        "2606:4700::1": {"value": "2606:4700::1", "selected": 1},
                        "2001:4860:4860::8888": {
                            "value": "2001:4860:4860::8888",
                            "selected": 1,
                        },
                    },
                },
            }
        }
        result = OPNsenseProvider._extract_subnet_fields(api_response)
        assert result["option_data.dns_servers"] == "2001:4860:4860::8888,2606:4700::1"

    def test_option_data_domain_search_as_option_dict(self) -> None:
        """Domain search returned as an option-dict with one selected entry."""
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "option_data": {
                    "dns_servers": {"": {"value": "", "selected": 1}},
                    "domain_search": {
                        "example.com": {"value": "example.com", "selected": 1},
                        "other.example": {"value": "other.example", "selected": 0},
                    },
                },
            }
        }
        result = OPNsenseProvider._extract_subnet_fields(api_response)
        assert result["option_data.domain_search"] == "example.com"

    def test_option_data_dns_servers_plain_string_still_works(self) -> None:
        """Plain-string option_data.dns_servers (older OPNsense shape) still extracted.

        Backward-compatibility check — preserves the path used by OPNsense
        versions that return plain strings here.
        """
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "option_data": {
                    "dns_servers": "2606:4700::1",
                    "domain_search": "example.com",
                },
            }
        }
        result = OPNsenseProvider._extract_subnet_fields(api_response)
        assert result["option_data.dns_servers"] == "2606:4700::1"
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

    def test_subnet_unchanged_with_option_dict_dns_servers(self) -> None:
        """Subnet matches when API returns the empty-sentinel option-dict shape.

        Regression for #756: the user's prod box (OPNsense 25.7.11_1) returns
        ``option_data.dns_servers`` and ``option_data.domain_search`` as
        ``{"": {"value": "", "selected": 1}}`` even when no value is set, while
        the desired side has no ``option_data`` at all.  Extract must yield
        the same dict as build for plan to skip the update.
        """
        desired: dict[str, Any] = {
            "subnet": "fd00:1::/64",
            "interface": "opt1",
            "pools": "::10-::ff",
            "valid_lifetime": "3600",
            "description": "VLAN 10",
        }
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "interface": "opt1",
                "pools": "::10-::ff",
                "valid_lifetime": "3600",
                "description": "VLAN 10",
                "option_data": {
                    "dns_servers": {"": {"value": "", "selected": 1}},
                    "domain_search": {"": {"value": "", "selected": 1}},
                    "v6_dnr": "",
                },
            }
        }
        assert OPNsenseProvider._extract_subnet_fields(
            api_response
        ) == OPNsenseProvider._build_desired_subnet_fields(desired)

    def test_subnet_unchanged_with_option_dict_dns_servers_populated(self) -> None:
        """Subnet matches when API returns option-dict with a real value selected.

        Mirrors the above but with a populated DNS server — the desired side
        sends a plain string and the API returns an option-dict with that
        same value selected.
        """
        desired: dict[str, Any] = {
            "subnet": "fd00:1::/64",
            "interface": "opt1",
            "option_data": {
                "dns_servers": "2606:4700::1",
                "domain_search": "example.com",
            },
        }
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "interface": "opt1",
                "option_data": {
                    "dns_servers": {
                        "2606:4700::1": {"value": "2606:4700::1", "selected": 1},
                        "2001:4860:4860::8888": {
                            "value": "2001:4860:4860::8888",
                            "selected": 0,
                        },
                    },
                    "domain_search": {
                        "example.com": {"value": "example.com", "selected": 1},
                    },
                },
            }
        }
        assert OPNsenseProvider._extract_subnet_fields(
            api_response
        ) == OPNsenseProvider._build_desired_subnet_fields(desired)

    def test_subnet_unchanged_prod_live_fixture(self) -> None:
        """Lock in the exact captured-live shape from the user's prod box.

        Anonymized snapshot of the response that originally exposed #756.
        Combines option-dict ``interface``, option-dict empty-sentinel
        ``option_data.dns_servers`` / ``domain_search``, and a plain-string
        ``v6_dnr`` field — must round-trip equal to the built desired fields
        so plan skips the update.
        """
        desired: dict[str, Any] = {
            "subnet": "fd00:10::/64",
            "interface": "opt1",
            "pools": "fd00:10::100-fd00:10::1ff",
            "valid_lifetime": "4000",
            "description": "infrastructure-v6",
        }
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:10::/64",
                "interface": {
                    "opt1": {"value": "OPT1 (infrastructure)", "selected": 1},
                    "opt2": {"value": "OPT2 (servers)", "selected": 0},
                    "lan": {"value": "LAN", "selected": 0},
                    "wan": {"value": "WAN", "selected": 0},
                },
                "pools": "fd00:10::100-fd00:10::1ff",
                "valid_lifetime": "4000",
                "description": "infrastructure-v6",
                "option_data": {
                    "dns_servers": {"": {"value": "", "selected": 1}},
                    "domain_search": {"": {"value": "", "selected": 1}},
                    "v6_dnr": "",
                },
            }
        }
        assert OPNsenseProvider._extract_subnet_fields(
            api_response
        ) == OPNsenseProvider._build_desired_subnet_fields(desired)

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
# _normalize_field_value
# ---------------------------------------------------------------------------


class TestNormalizeFieldValue:
    """Tests for the _normalize_field_value helper."""

    def test_strips_whitespace(self) -> None:
        """Leading and trailing whitespace is stripped."""
        assert _normalize_field_value("  hello  ") == "hello"

    def test_empty_string(self) -> None:
        """Empty string remains empty."""
        assert _normalize_field_value("") == ""

    def test_single_line_no_change(self) -> None:
        """Single-line string without whitespace is unchanged."""
        assert _normalize_field_value("::10-::ff") == "::10-::ff"

    def test_multiline_sorted(self) -> None:
        """Multi-line values are sorted and whitespace-stripped."""
        assert _normalize_field_value("::20-::ff\n::10-::1f") == "::10-::1f\n::20-::ff"

    def test_multiline_whitespace_stripped(self) -> None:
        """Whitespace around each line is stripped."""
        assert _normalize_field_value("  ::10-::ff \n ::20-::ff  ") == "::10-::ff\n::20-::ff"

    def test_multiline_empty_lines_removed(self) -> None:
        """Empty lines within multi-line values are removed."""
        assert _normalize_field_value("::10-::ff\n\n::20-::ff") == "::10-::ff\n::20-::ff"


# ---------------------------------------------------------------------------
# Normalization edge cases (extract vs build matching)
# ---------------------------------------------------------------------------


class TestNormalizationEdgeCases:
    """Edge cases where extract and build must produce identical results."""

    def test_pools_with_trailing_whitespace(self) -> None:
        """Pools with trailing whitespace in API response still match desired."""
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "interface": "opt1",
                "pools": "::10-::ff ",
            }
        }
        desired: dict[str, Any] = {
            "subnet": "fd00:1::/64",
            "interface": "opt1",
            "pools": "::10-::ff",
        }
        assert OPNsenseProvider._extract_subnet_fields(
            api_response
        ) == OPNsenseProvider._build_desired_subnet_fields(desired)

    def test_pools_different_order(self) -> None:
        """Pool ranges in different order produce matching fields."""
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "interface": "opt1",
                "pools": "::20-::ff\n::10-::1f",
            }
        }
        desired: dict[str, Any] = {
            "subnet": "fd00:1::/64",
            "interface": "opt1",
            "pools": "::10-::1f\n::20-::ff",
        }
        assert OPNsenseProvider._extract_subnet_fields(
            api_response
        ) == OPNsenseProvider._build_desired_subnet_fields(desired)

    def test_valid_lifetime_int_in_api(self) -> None:
        """API returning valid_lifetime as int matches desired string."""
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "interface": "opt1",
                "valid_lifetime": 3600,
            }
        }
        desired: dict[str, Any] = {
            "subnet": "fd00:1::/64",
            "interface": "opt1",
            "valid_lifetime": "3600",
        }
        assert OPNsenseProvider._extract_subnet_fields(
            api_response
        ) == OPNsenseProvider._build_desired_subnet_fields(desired)

    def test_missing_option_data_matches_empty(self) -> None:
        """Missing option_data in API matches absent option_data in desired."""
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "interface": "opt1",
            }
        }
        desired: dict[str, Any] = {
            "subnet": "fd00:1::/64",
            "interface": "opt1",
        }
        assert OPNsenseProvider._extract_subnet_fields(
            api_response
        ) == OPNsenseProvider._build_desired_subnet_fields(desired)

    def test_empty_option_data_dict_matches_missing(self) -> None:
        """Empty option_data dict in API matches no option_data in desired."""
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "interface": "opt1",
                "option_data": {},
            }
        }
        desired: dict[str, Any] = {
            "subnet": "fd00:1::/64",
            "interface": "opt1",
        }
        assert OPNsenseProvider._extract_subnet_fields(
            api_response
        ) == OPNsenseProvider._build_desired_subnet_fields(desired)

    def test_option_data_with_whitespace(self) -> None:
        """Whitespace in option_data values is stripped."""
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "interface": "opt1",
                "option_data": {
                    "dns_servers": " fd00::1,fd00::2 ",
                    "domain_search": " example.com ",
                },
            }
        }
        desired: dict[str, Any] = {
            "subnet": "fd00:1::/64",
            "interface": "opt1",
            "option_data": {
                "dns_servers": "fd00::1,fd00::2",
                "domain_search": "example.com",
            },
        }
        assert OPNsenseProvider._extract_subnet_fields(
            api_response
        ) == OPNsenseProvider._build_desired_subnet_fields(desired)

    def test_interface_with_whitespace(self) -> None:
        """Whitespace around interface value is stripped."""
        api_response: dict[str, Any] = {
            "subnet6": {
                "subnet": "fd00:1::/64",
                "interface": " opt1 ",
            }
        }
        desired: dict[str, Any] = {
            "subnet": "fd00:1::/64",
            "interface": "opt1",
        }
        assert OPNsenseProvider._extract_subnet_fields(
            api_response
        ) == OPNsenseProvider._build_desired_subnet_fields(desired)


# ---------------------------------------------------------------------------
# Debug logging (_log_field_diff)
# ---------------------------------------------------------------------------


class TestLogFieldDiff:
    """Tests for _log_field_diff debug logging."""

    def test_logs_differing_fields(self, provider: OPNsenseProvider, caplog: Any) -> None:
        """Differing fields are logged at DEBUG level."""
        current = {"subnet": "fd00:1::/64", "description": "old"}
        desired = {"subnet": "fd00:1::/64", "description": "new"}
        with caplog.at_level(logging.DEBUG, logger="infrafoundry.providers.opnsense"):
            provider._log_field_diff("test-subnet", current, desired)
        assert "description" in caplog.text
        assert "'old'" in caplog.text
        assert "'new'" in caplog.text

    def test_no_log_when_fields_match(self, provider: OPNsenseProvider, caplog: Any) -> None:
        """No log output when all fields match."""
        fields = {"subnet": "fd00:1::/64", "description": "same"}
        with caplog.at_level(logging.DEBUG, logger="infrafoundry.providers.opnsense"):
            provider._log_field_diff("test-subnet", fields, fields)
        assert caplog.text == ""

    def test_no_log_above_debug(self, provider: OPNsenseProvider, caplog: Any) -> None:
        """No log output when log level is above DEBUG."""
        current = {"description": "old"}
        desired = {"description": "new"}
        with caplog.at_level(logging.INFO, logger="infrafoundry.providers.opnsense"):
            provider._log_field_diff("test-subnet", current, desired)
        assert caplog.text == ""


class TestDropNonRoundTripSubnetFields:
    """Tests for _drop_non_round_trip_subnet_fields.

    The OPNsense Kea DHCPv6 subnet API accepts ``valid_lifetime`` on
    write but does not return it on read (verified live on 25.7.11_1).
    Comparing it produces unconditional false-positive diffs every plan;
    this helper drops the field from comparison when the live response
    is missing/empty so apply isn't triggered by a value we can't observe.
    """

    def test_drops_valid_lifetime_from_both_when_current_empty(self) -> None:
        """The bug case: current has empty valid_lifetime, desired has a value."""
        current = {"subnet": "fd00:1::/64", "valid_lifetime": ""}
        desired = {"subnet": "fd00:1::/64", "valid_lifetime": "86400"}
        OPNsenseProvider._drop_non_round_trip_subnet_fields(current, desired)
        assert current == {"subnet": "fd00:1::/64"}
        assert desired == {"subnet": "fd00:1::/64"}

    def test_drops_valid_lifetime_from_both_when_current_missing(self) -> None:
        """The other arm of the bug: key missing entirely from current."""
        current = {"subnet": "fd00:1::/64"}
        desired = {"subnet": "fd00:1::/64", "valid_lifetime": "86400"}
        OPNsenseProvider._drop_non_round_trip_subnet_fields(current, desired)
        assert current == {"subnet": "fd00:1::/64"}
        assert desired == {"subnet": "fd00:1::/64"}

    def test_keeps_valid_lifetime_when_current_has_value(self) -> None:
        """Forward-compatible: future OPNsense versions returning the value re-engage comparison."""
        current = {"subnet": "fd00:1::/64", "valid_lifetime": "86400"}
        desired = {"subnet": "fd00:1::/64", "valid_lifetime": "86400"}
        OPNsenseProvider._drop_non_round_trip_subnet_fields(current, desired)
        assert current == {"subnet": "fd00:1::/64", "valid_lifetime": "86400"}
        assert desired == {"subnet": "fd00:1::/64", "valid_lifetime": "86400"}

    def test_keeps_valid_lifetime_to_detect_real_drift(self) -> None:
        """When current is non-empty and differs from desired, drift IS detected."""
        current = {"subnet": "fd00:1::/64", "valid_lifetime": "3600"}
        desired = {"subnet": "fd00:1::/64", "valid_lifetime": "86400"}
        OPNsenseProvider._drop_non_round_trip_subnet_fields(current, desired)
        assert current == {"subnet": "fd00:1::/64", "valid_lifetime": "3600"}
        assert desired == {"subnet": "fd00:1::/64", "valid_lifetime": "86400"}
        # Caller's equality check would still detect a difference.
        assert current != desired

    def test_does_not_touch_other_fields(self) -> None:
        """Helper only drops keys named in _ASYMMETRIC_SUBNET_FIELDS."""
        current = {"subnet": "fd00:1::/64", "description": "", "pools": "::10-::ff"}
        desired = {"subnet": "fd00:1::/64", "description": "new", "pools": "::10-::ff"}
        OPNsenseProvider._drop_non_round_trip_subnet_fields(current, desired)
        assert current == {"subnet": "fd00:1::/64", "description": "", "pools": "::10-::ff"}
        assert desired == {"subnet": "fd00:1::/64", "description": "new", "pools": "::10-::ff"}


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
) -> tuple[Any, Any, Any]:
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
