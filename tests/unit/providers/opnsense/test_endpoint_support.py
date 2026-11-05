"""Tests for the OPNsense version/endpoint check (#1239), against the bundled specs."""

from __future__ import annotations

from unittest.mock import MagicMock

from opnsense_openapi import newest_spec_version

from infrafoundry.core.exceptions import APIError
from infrafoundry.providers.opnsense.endpoint_support import check_box, check_resource_types


def test_supported_types_are_clean_on_26_1_6() -> None:
    result = check_resource_types(
        "26.1.6", ["firewall.rules", "kea.dhcp4.subnets", "system.firmware", "system.tuning"]
    )
    assert result.errors == []
    assert result.warnings == []
    assert result.version == "26.1.6"


def test_extension_endpoints_are_skipped() -> None:
    assert check_resource_types("26.1.6", ["interfaces.assignments"]).errors == []


def test_retired_type_is_an_error_naming_endpoint_type_and_version() -> None:
    result = check_resource_types("26.1.6", ["system.hostname"])
    assert len(result.errors) == 2
    assert "GET system/general/get" in result.errors[0]
    assert "system.hostname" in result.errors[0]
    assert "26.1.6" in result.errors[0]


def test_security_patch_suffix_is_ignored() -> None:
    result = check_resource_types("26.1.6_2", ["firewall.rules"])
    assert result.errors == []
    assert result.warnings == []


def test_version_without_exact_spec_warns_and_still_checks() -> None:
    newest = newest_spec_version("26.1")
    major, minor, patch = newest.split(".")
    uncovered = f"{major}.{minor}.{int(patch) + 1}"
    result = check_resource_types(uncovered, ["firewall.rules", "system.hostname"])
    assert any(uncovered in w and newest_spec_version() in w for w in result.warnings)
    assert any("system.hostname" in e for e in result.errors)


def test_version_older_than_every_spec_warns_without_errors() -> None:
    result = check_resource_types("19.1", ["firewall.rules"])
    assert result.errors == []
    assert any("19.1" in w for w in result.warnings)


def test_newer_series_does_not_reject_firewall_rules() -> None:
    assert check_resource_types(newest_spec_version(), ["firewall.rules"]).errors == []


def test_unknown_types_and_duplicates() -> None:
    result = check_resource_types("26.1.6", ["nope", "system.hostname", "system.hostname"])
    assert len(result.errors) == 2


def test_check_box_unreadable_version_warns() -> None:
    client = MagicMock()
    client.detect_version.side_effect = APIError("down", provider="opnsense")
    result = check_box(client, ["firewall.rules"])
    assert result.errors == []
    assert result.version is None
    assert len(result.warnings) == 1


def test_check_box_empty_types_never_calls_the_box() -> None:
    client = MagicMock()
    assert check_box(client, []).errors == []
    client.detect_version.assert_not_called()


def test_check_box_uses_detected_version() -> None:
    client = MagicMock()
    client.detect_version.return_value = "26.1.6_2"
    result = check_box(client, ["system.hostname"])
    assert result.version == "26.1.6_2"
    assert result.errors
