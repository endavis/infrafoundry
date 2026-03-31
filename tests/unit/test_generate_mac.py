"""Tests for the generate_mac Jinja2 filter."""

from __future__ import annotations

import re

import jinja2
import pytest

from infrafoundry.core.config.filters import generate_mac


class TestGenerateMac:
    """Tests for the generate_mac filter function."""

    def test_deterministic_same_input(self) -> None:
        """Same input always produces the same MAC address."""
        result1 = generate_mac("test-vm-01")
        result2 = generate_mac("test-vm-01")
        assert result1 == result2

    def test_different_inputs_produce_different_macs(self) -> None:
        """Different inputs produce different MAC addresses."""
        mac1 = generate_mac("vm-alpha")
        mac2 = generate_mac("vm-beta")
        assert mac1 != mac2

    def test_first_octet_is_02(self) -> None:
        """First octet is always 02 (locally administered, unicast)."""
        for name in ["a", "server-1", "long-name-with-many-chars"]:
            mac = generate_mac(name)
            assert mac.startswith("02:"), f"MAC for '{name}' does not start with 02: {mac}"

    def test_format_matches_mac_pattern(self) -> None:
        """Output matches the expected 02:xx:xx:xx:xx:xx format."""
        pattern = re.compile(r"^02:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}$")
        for name in ["foo", "bar", "baz-123", ""]:
            mac = generate_mac(name)
            assert pattern.match(mac), f"MAC '{mac}' for input '{name}' doesn't match pattern"

    def test_empty_string_does_not_crash(self) -> None:
        """Empty string input produces a valid MAC without errors."""
        mac = generate_mac("")
        assert mac.startswith("02:")
        assert len(mac) == 17  # 02:xx:xx:xx:xx:xx = 17 chars

    def test_works_as_jinja2_filter(self) -> None:
        """Filter integrates correctly in a Jinja2 environment."""
        env = jinja2.Environment()
        env.filters["generate_mac"] = generate_mac
        template = env.from_string("{{ name | generate_mac }}")
        result = template.render(name="my-server")
        assert result == generate_mac("my-server")

    @pytest.mark.parametrize(
        "input_value",
        [
            "simple",
            "with spaces",
            "with-dashes",
            "with_underscores",
            "CamelCase",
            "123numeric",
            "special!@#$%",
        ],
    )
    def test_various_inputs(self, input_value: str) -> None:
        """Various string inputs all produce valid MAC addresses."""
        mac = generate_mac(input_value)
        assert mac.startswith("02:")
        parts = mac.split(":")
        assert len(parts) == 6
        for part in parts:
            assert len(part) == 2
