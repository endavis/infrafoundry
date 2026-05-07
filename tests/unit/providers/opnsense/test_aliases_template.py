"""Unit tests for OPNsense firewall alias Terraform template generation.

Mirrors the structure of `test_unbound_host_override.py`. Covers the
post-#765 argument names — `ip_protocol` (was `proto`), `update_freq`
(was `updatefreq`) — and verifies the deliberately-dropped `counters`
argument is never rendered, even when present in the YAML config.
"""

from pathlib import Path

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense import OPNsenseProvider


class TestAliasesTemplates:
    """Test firewall alias Terraform template generation."""

    @pytest.fixture
    def provider(self, tmp_path: Path) -> OPNsenseProvider:
        """Create an OPNsense provider rooted in a per-test tmp dir."""
        config_dir = tmp_path / "config"
        output_dir = tmp_path / "output"
        return OPNsenseProvider(config_dir, output_dir)

    def test_generate_basic_alias(self, provider: OPNsenseProvider) -> None:
        """A minimal alias renders the always-present args and no
        optional args.
        """
        alias = ResourceConfig(
            provider="opnsense",
            type="aliases",
            name="alias-min",
            config={
                "name": "alias-min",
                "type": "host",
                "content": ["192.168.1.10", "192.168.1.11"],
            },
        )

        provider.generate_terraform([alias])

        content = (provider.terraform_dir / "aliases.tf").read_text()
        assert 'resource "opnsense_firewall_alias" "alias_min"' in content
        assert 'name        = "alias-min"' in content
        assert 'type        = "host"' in content
        assert '"192.168.1.10"' in content
        assert '"192.168.1.11"' in content
        # No optional args — these are gated on `is defined`.
        assert "ip_protocol" not in content
        assert "update_freq" not in content
        assert "categories" not in content
        assert "interface" not in content

    def test_generate_alias_with_all_optional_fields(self, provider: OPNsenseProvider) -> None:
        """Aliases with `proto` / `updatefreq` / `categories` / `interface`
        in the YAML config render the renamed terraform argument names
        (#765). `counters` was deliberately dropped post-#765 (provider has
        no settable equivalent — `stats` is computed/read-only) and must
        NOT appear in the rendered HCL even when set in the YAML.
        """
        alias = ResourceConfig(
            provider="opnsense",
            type="aliases",
            name="alias-full",
            config={
                "name": "alias-full",
                "type": "urltable",
                "description": "all-optionals alias",
                "content": ["https://example.com/list.txt"],
                "enabled": True,
                "proto": "IPv4",
                "updatefreq": "0.5",
                "categories": ["cat-a", "cat-b"],
                # Counters is set in the YAML to assert it's still ignored.
                "counters": True,
                "interface": "lan",
            },
        )

        provider.generate_terraform([alias])

        content = (provider.terraform_dir / "aliases.tf").read_text()
        # Renamed args must use the provider schema names.
        assert 'ip_protocol = "IPv4"' in content
        assert 'update_freq = "0.5"' in content
        # Categories rendered as a list.
        assert "categories" in content
        assert '"cat-a"' in content
        assert '"cat-b"' in content
        # Interface rendered.
        assert 'interface = "lan"' in content
        # Legacy YAML-internal names must NEVER appear as rendered arg names.
        assert "proto =" not in content
        assert "updatefreq =" not in content
        # `counters` must never be rendered (no provider equivalent, #765).
        assert "counters" not in content
