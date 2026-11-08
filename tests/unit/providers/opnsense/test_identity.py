"""Tests for the shared OPNsense description-suffix identity helpers."""

from __future__ import annotations

import pytest

from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.providers.opnsense.services import _identity, cron_jobs, firewall_rule, nat_rule


class TestEncodeIdentity:
    """``encode_identity`` appends the marker as a suffix."""

    def test_with_description(self) -> None:
        assert (
            _identity.encode_identity("my-rule", "Allow web") == "Allow web [infrafoundry:my-rule]"
        )

    def test_empty_description(self) -> None:
        assert _identity.encode_identity("my-rule", "") == "[infrafoundry:my-rule]"


class TestParseIdentity:
    """``parse_identity`` splits a description into name and user text."""

    @pytest.mark.parametrize("user_description", ["Allow web", ""])
    def test_round_trip(self, user_description: str) -> None:
        encoded = _identity.encode_identity("my-rule", user_description)
        assert _identity.parse_identity(encoded) == ("my-rule", user_description)

    @pytest.mark.parametrize("description", ["Allow web", ""])
    def test_unmanaged(self, description: str) -> None:
        assert _identity.parse_identity(description) == (None, description)

    @pytest.mark.parametrize(
        "description",
        [
            "x [infrafoundry:]",
            "x [infrafoundry:My-Rule]",
            "x [infrafoundry:my_rule]",
            "x [infrafoundry:my-rule] trailing",
            "x [[infrafoundry:my-rule]]",
        ],
    )
    def test_malformed_raises(self, description: str) -> None:
        with pytest.raises(_identity.OpnsenseDriftError):
            _identity.parse_identity(description)

    def test_default_label_in_message(self) -> None:
        with pytest.raises(_identity.OpnsenseDriftError, match="Record description contains"):
            _identity.parse_identity("[infrafoundry:]")

    def test_custom_label_in_message(self) -> None:
        with pytest.raises(_identity.OpnsenseDriftError, match="NAT rule description contains"):
            _identity.parse_identity("[infrafoundry:]", record_label="NAT rule")


def test_drift_error_is_infrafoundry_error() -> None:
    assert issubclass(_identity.OpnsenseDriftError, InfraFoundryError)


class TestHasIdentityMarker:
    """``has_identity_marker`` detects a marker in any position."""

    @pytest.mark.parametrize(
        "description",
        ["[infrafoundry:my-rule]", "x [infrafoundry:]", "[infrafoundry:a] tail"],
    )
    def test_true(self, description: str) -> None:
        assert _identity.has_identity_marker(description) is True

    @pytest.mark.parametrize("description", ["Allow web", ""])
    def test_false(self, description: str) -> None:
        assert _identity.has_identity_marker(description) is False


@pytest.mark.parametrize("module", [firewall_rule, nat_rule, cron_jobs])
def test_services_share_one_definition(module: object) -> None:
    assert module.OpnsenseDriftError is _identity.OpnsenseDriftError  # type: ignore[attr-defined]
    assert module.encode_identity is _identity.encode_identity  # type: ignore[attr-defined]
    assert module.parse_identity is _identity.parse_identity  # type: ignore[attr-defined]
