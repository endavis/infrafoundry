"""Unit tests for OPNsense DHCPv6 change detection helpers.

Covers the module-private helpers in
``infrafoundry.providers.opnsense.services.kea_dhcp`` that extract and
normalize fields from OPNsense API responses and desired configuration:
``_extract_subnet_fields``, ``_extract_reservation_fields``,
``_build_desired_subnet_fields``, ``_build_desired_reservation_fields``,
``_drop_non_round_trip_subnet_fields``, ``_log_field_diff``,
``_normalize_field_value``.

The integration tests that previously exercised
``OPNsenseProvider._generate_kea_dhcp6_resources`` end-to-end have been
migrated to ``test_kea_dhcp6_subnet_manager.py`` and
``test_kea_dhcp6_reservation_manager.py`` along with the manager refactor
in #758.
"""

import logging
from typing import Any

from infrafoundry.providers.opnsense.services.kea_dhcp import (
    _build_desired_reservation_fields,
    _build_desired_subnet_fields,
    _drop_non_round_trip_subnet_fields,
    _extract_reservation_fields,
    _extract_subnet_fields,
    _log_field_diff,
    _normalize_field_value,
)

# ---------------------------------------------------------------------------
# _extract_subnet_fields
# ---------------------------------------------------------------------------


class TestExtractSubnetFields:
    """Tests for _extract_subnet_fields."""

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
        result = _extract_subnet_fields(api_response)
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
        result = _extract_subnet_fields(api_response)
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
        result = _extract_subnet_fields(api_response)
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
        result = _extract_subnet_fields(api_response)
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
        result = _extract_subnet_fields(api_response)
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
        result = _extract_subnet_fields(api_response)
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
        result = _extract_subnet_fields(api_response)
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
        result = _extract_subnet_fields(api_response)
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
        result = _extract_subnet_fields(api_response)
        assert result["option_data.dns_servers"] == "2606:4700::1"
        assert result["option_data.domain_search"] == "example.com"

    def test_missing_fields_default_to_empty(self) -> None:
        """Missing or None fields default to empty strings."""
        api_response: dict[str, Any] = {"subnet6": {}}
        result = _extract_subnet_fields(api_response)
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
        result = _extract_subnet_fields(api_response)
        assert result["subnet"] == ""
        assert result["interface"] == ""
        assert result["pools"] == ""

    def test_missing_wrapper_key(self) -> None:
        """Response without the 'subnet6' wrapper key returns empty fields."""
        api_response: dict[str, Any] = {}
        result = _extract_subnet_fields(api_response)
        assert result["subnet"] == ""
        assert result["interface"] == ""


# ---------------------------------------------------------------------------
# _extract_reservation_fields
# ---------------------------------------------------------------------------


class TestExtractReservationFields:
    """Tests for _extract_reservation_fields."""

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
        result = _extract_reservation_fields(api_response)
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
        result = _extract_reservation_fields(api_response)
        assert result["subnet"] == "uuid-1234"

    def test_missing_fields_default_to_empty(self) -> None:
        """Missing fields default to empty strings."""
        api_response: dict[str, Any] = {"reservation": {}}
        result = _extract_reservation_fields(api_response)
        assert result["ip_address"] == ""
        assert result["duid"] == ""
        assert result["hostname"] == ""
        assert result["description"] == ""
        assert result["subnet"] == ""

    def test_missing_wrapper_key(self) -> None:
        """Response without the 'reservation' wrapper key returns empty fields."""
        api_response: dict[str, Any] = {}
        result = _extract_reservation_fields(api_response)
        assert result["subnet"] == ""
        assert result["ip_address"] == ""


# ---------------------------------------------------------------------------
# _build_desired_subnet_fields
# ---------------------------------------------------------------------------


class TestBuildDesiredSubnetFields:
    """Tests for _build_desired_subnet_fields."""

    def test_basic_subnet_data(self) -> None:
        """Build normalized fields from basic subnet data."""
        subnet_data: dict[str, Any] = {
            "subnet": "fd00:1::/64",
            "interface": "opt1",
            "pools": "::10-::ff",
            "valid_lifetime": "3600",
            "description": "VLAN 10",
        }
        result = _build_desired_subnet_fields(subnet_data)
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
        result = _build_desired_subnet_fields(subnet_data)
        assert result["option_data.dns_servers"] == "fd00::1,fd00::2"
        assert result["option_data.domain_search"] == "example.com"

    def test_missing_fields_default_to_empty(self) -> None:
        """Missing fields default to empty strings."""
        result = _build_desired_subnet_fields({})
        assert result["subnet"] == ""
        assert result["interface"] == ""
        assert result["pools"] == ""
        assert result["valid_lifetime"] == ""
        assert result["description"] == ""


# ---------------------------------------------------------------------------
# _build_desired_reservation_fields
# ---------------------------------------------------------------------------


class TestBuildDesiredReservationFields:
    """Tests for _build_desired_reservation_fields."""

    def test_basic_reservation_data(self) -> None:
        """Build normalized fields from basic reservation data."""
        reservation_data: dict[str, Any] = {
            "subnet": "uuid-1234",
            "ip_address": "fd00:1::10",
            "duid": "00:01:00:01:2c:3d:00:01",
            "hostname": "server1",
            "description": "Main server",
        }
        result = _build_desired_reservation_fields(reservation_data)
        assert result["subnet"] == "uuid-1234"
        assert result["ip_address"] == "fd00:1::10"
        assert result["duid"] == "00:01:00:01:2c:3d:00:01"
        assert result["hostname"] == "server1"
        assert result["description"] == "Main server"

    def test_missing_fields_default_to_empty(self) -> None:
        """Missing fields default to empty strings."""
        result = _build_desired_reservation_fields({})
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
        assert _extract_subnet_fields(api_response) == _build_desired_subnet_fields(desired)

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
        assert _extract_subnet_fields(api_response) != _build_desired_subnet_fields(desired)

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
        assert _extract_subnet_fields(api_response) == _build_desired_subnet_fields(desired)

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
        assert _extract_subnet_fields(api_response) == _build_desired_subnet_fields(desired)

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
        assert _extract_subnet_fields(api_response) == _build_desired_subnet_fields(desired)

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
        assert _extract_reservation_fields(api_response) == _build_desired_reservation_fields(
            desired
        )

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
        assert _extract_reservation_fields(api_response) != _build_desired_reservation_fields(
            desired
        )


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
            _extract_subnet_fields(api_response)["valid_lifetime"]
            == _build_desired_subnet_fields(desired)["valid_lifetime"]
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
        assert _extract_subnet_fields(api_response) == _build_desired_subnet_fields(desired)

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
        assert _extract_subnet_fields(api_response) == _build_desired_subnet_fields(desired)

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
        assert _extract_subnet_fields(api_response) == _build_desired_subnet_fields(desired)

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
        assert _extract_subnet_fields(api_response) == _build_desired_subnet_fields(desired)

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
        assert _extract_subnet_fields(api_response) == _build_desired_subnet_fields(desired)

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
        assert _extract_subnet_fields(api_response) == _build_desired_subnet_fields(desired)

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
        assert _extract_subnet_fields(api_response) == _build_desired_subnet_fields(desired)


# ---------------------------------------------------------------------------
# Debug logging (_log_field_diff)
# ---------------------------------------------------------------------------


# The helpers' logger lives on the kea_dhcp service module after #758;
# caplog filters propagate to the root via the shared
# ``infrafoundry.providers.opnsense`` ancestor.
_LOGGER_NAME = "infrafoundry.providers.opnsense.services.kea_dhcp"


class TestLogFieldDiff:
    """Tests for _log_field_diff debug logging."""

    def test_logs_differing_fields(self, caplog: Any) -> None:
        """Differing fields are logged at DEBUG level."""
        current = {"subnet": "fd00:1::/64", "description": "old"}
        desired = {"subnet": "fd00:1::/64", "description": "new"}
        with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
            _log_field_diff("test-subnet", current, desired)
        assert "description" in caplog.text
        assert "'old'" in caplog.text
        assert "'new'" in caplog.text

    def test_no_log_when_fields_match(self, caplog: Any) -> None:
        """No log output when all fields match."""
        fields = {"subnet": "fd00:1::/64", "description": "same"}
        with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
            _log_field_diff("test-subnet", fields, fields)
        assert caplog.text == ""

    def test_no_log_above_debug(self, caplog: Any) -> None:
        """No log output when log level is above DEBUG."""
        current = {"description": "old"}
        desired = {"description": "new"}
        with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
            _log_field_diff("test-subnet", current, desired)
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
        _drop_non_round_trip_subnet_fields(current, desired)
        assert current == {"subnet": "fd00:1::/64"}
        assert desired == {"subnet": "fd00:1::/64"}

    def test_drops_valid_lifetime_from_both_when_current_missing(self) -> None:
        """The other arm of the bug: key missing entirely from current."""
        current = {"subnet": "fd00:1::/64"}
        desired = {"subnet": "fd00:1::/64", "valid_lifetime": "86400"}
        _drop_non_round_trip_subnet_fields(current, desired)
        assert current == {"subnet": "fd00:1::/64"}
        assert desired == {"subnet": "fd00:1::/64"}

    def test_keeps_valid_lifetime_when_current_has_value(self) -> None:
        """Forward-compatible: future OPNsense versions returning the value re-engage comparison."""
        current = {"subnet": "fd00:1::/64", "valid_lifetime": "86400"}
        desired = {"subnet": "fd00:1::/64", "valid_lifetime": "86400"}
        _drop_non_round_trip_subnet_fields(current, desired)
        assert current == {"subnet": "fd00:1::/64", "valid_lifetime": "86400"}
        assert desired == {"subnet": "fd00:1::/64", "valid_lifetime": "86400"}

    def test_keeps_valid_lifetime_to_detect_real_drift(self) -> None:
        """When current is non-empty and differs from desired, drift IS detected."""
        current = {"subnet": "fd00:1::/64", "valid_lifetime": "3600"}
        desired = {"subnet": "fd00:1::/64", "valid_lifetime": "86400"}
        _drop_non_round_trip_subnet_fields(current, desired)
        assert current == {"subnet": "fd00:1::/64", "valid_lifetime": "3600"}
        assert desired == {"subnet": "fd00:1::/64", "valid_lifetime": "86400"}
        # Caller's equality check would still detect a difference.
        assert current != desired

    def test_does_not_touch_other_fields(self) -> None:
        """Helper only drops keys named in _ASYMMETRIC_SUBNET_FIELDS."""
        current = {"subnet": "fd00:1::/64", "description": "", "pools": "::10-::ff"}
        desired = {"subnet": "fd00:1::/64", "description": "new", "pools": "::10-::ff"}
        _drop_non_round_trip_subnet_fields(current, desired)
        assert current == {"subnet": "fd00:1::/64", "description": "", "pools": "::10-::ff"}
        assert desired == {"subnet": "fd00:1::/64", "description": "new", "pools": "::10-::ff"}
