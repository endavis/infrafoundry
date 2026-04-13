"""Tests for custom Jinja2 filters and environment factory."""

from __future__ import annotations

import jinja2
import pytest

from infrafoundry.core.config.filters import (
    _FILTERS,
    bool_to_tf,
    cidr_ip,
    cidr_prefix,
    create_jinja2_env,
    generate_mac,
    to_gb,
    to_gib,
    to_mib,
)


class TestGenerateMac:
    """Tests for the generate_mac filter."""

    def test_deterministic(self) -> None:
        """Same input always produces the same MAC."""
        assert generate_mac("test") == generate_mac("test")

    def test_starts_with_local_admin_prefix(self) -> None:
        """MAC starts with 02 (locally administered, unicast)."""
        mac = generate_mac("anything")
        assert mac.startswith("02:")

    def test_format(self) -> None:
        """MAC has correct colon-separated hex format."""
        mac = generate_mac("test")
        parts = mac.split(":")
        assert len(parts) == 6
        for part in parts:
            assert len(part) == 2

    def test_different_inputs_produce_different_macs(self) -> None:
        """Different inputs produce different MACs."""
        assert generate_mac("host-a") != generate_mac("host-b")


class TestToMib:
    """Tests for the to_mib filter (GB to MiB)."""

    def test_integer_gb(self) -> None:
        assert to_mib(8) == 8192

    def test_fractional_gb(self) -> None:
        assert to_mib(0.5) == 512

    def test_string_input(self) -> None:
        assert to_mib("4") == 4096

    def test_zero(self) -> None:
        assert to_mib(0) == 0

    def test_returns_int(self) -> None:
        result = to_mib(1)
        assert isinstance(result, int)


class TestToGib:
    """Tests for the to_gib filter (MiB to GiB)."""

    def test_whole_gib(self) -> None:
        assert to_gib(8192) == 8.0

    def test_fractional_gib(self) -> None:
        assert to_gib(512) == 0.5

    def test_string_input(self) -> None:
        assert to_gib("4096") == 4.0

    def test_zero(self) -> None:
        assert to_gib(0) == 0.0

    def test_returns_float(self) -> None:
        result = to_gib(1024)
        assert isinstance(result, float)


class TestToGb:
    """Tests for the to_gb filter (alias for to_gib)."""

    def test_is_alias_for_to_gib(self) -> None:
        """to_gb produces the same result as to_gib."""
        assert to_gb(8192) == to_gib(8192)

    def test_basic(self) -> None:
        assert to_gb(2048) == 2.0


class TestBoolToTf:
    """Tests for the bool_to_tf filter."""

    def test_true(self) -> None:
        assert bool_to_tf(True) == "true"

    def test_false(self) -> None:
        assert bool_to_tf(False) == "false"

    def test_truthy_string(self) -> None:
        assert bool_to_tf("yes") == "true"

    def test_falsy_value(self) -> None:
        assert bool_to_tf(0) == "false"
        assert bool_to_tf("") == "false"
        assert bool_to_tf(None) == "false"

    def test_returns_string(self) -> None:
        result = bool_to_tf(True)
        assert isinstance(result, str)


class TestCidrIp:
    """Tests for the cidr_ip filter."""

    def test_ipv4(self) -> None:
        assert cidr_ip("10.0.0.1/24") == "10.0.0.1"

    def test_ipv6(self) -> None:
        assert cidr_ip("fd00::1/64") == "fd00::1"

    def test_host_route(self) -> None:
        assert cidr_ip("192.168.1.1/32") == "192.168.1.1"


class TestCidrPrefix:
    """Tests for the cidr_prefix filter."""

    def test_ipv4(self) -> None:
        assert cidr_prefix("10.0.0.1/24") == "24"

    def test_ipv6(self) -> None:
        assert cidr_prefix("fd00::1/64") == "64"

    def test_host_route(self) -> None:
        assert cidr_prefix("192.168.1.1/32") == "32"


class TestCreateJinja2Env:
    """Tests for the create_jinja2_env factory function."""

    def test_has_all_filters(self) -> None:
        """Environment has all filters from the registry."""
        env = create_jinja2_env()
        for name in _FILTERS:
            assert name in env.filters, f"Missing filter: {name}"

    def test_default_undefined_is_permissive(self) -> None:
        """Default undefined mode allows missing variables."""
        env = create_jinja2_env()
        template = env.from_string("{{ missing_var }}")
        result = template.render()
        assert result == ""

    def test_strict_undefined(self) -> None:
        """StrictUndefined raises on missing variables."""
        env = create_jinja2_env(undefined=jinja2.StrictUndefined)
        template = env.from_string("{{ missing_var }}")
        with pytest.raises(jinja2.UndefinedError):
            template.render()

    def test_permissive_undefined(self) -> None:
        """Explicit Undefined is permissive."""
        env = create_jinja2_env(undefined=jinja2.Undefined)
        template = env.from_string("{{ missing_var }}")
        result = template.render()
        assert result == ""

    def test_filters_work_in_templates(self) -> None:
        """Filters are usable in rendered templates."""
        env = create_jinja2_env()
        template = env.from_string("{{ 8 | to_mib }}")
        assert template.render() == "8192"

    def test_generate_mac_works_in_templates(self) -> None:
        """Pre-existing generate_mac filter works in factory env."""
        env = create_jinja2_env()
        template = env.from_string('{{ "test" | generate_mac }}')
        result = template.render()
        assert result.startswith("02:")

    def test_bool_to_tf_in_template(self) -> None:
        """bool_to_tf filter works in templates."""
        env = create_jinja2_env()
        template = env.from_string("{{ enabled | bool_to_tf }}")
        assert template.render(enabled=True) == "true"
        assert template.render(enabled=False) == "false"

    def test_cidr_filters_in_template(self) -> None:
        """CIDR filters work in templates."""
        env = create_jinja2_env()
        template = env.from_string("{{ addr | cidr_ip }}/{{ addr | cidr_prefix }}")
        assert template.render(addr="10.0.0.1/24") == "10.0.0.1/24"
