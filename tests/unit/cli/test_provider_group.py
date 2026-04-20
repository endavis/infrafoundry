"""Tests for the ``foundry provider`` top-level CLI group and plugin discovery."""

from __future__ import annotations

from unittest.mock import patch

import click
from click.testing import CliRunner

from infrafoundry.core.plugin_system.exceptions import PluginDiscoveryError
from infrafoundry.core.plugin_system.plugin_type import PluginMetadata


def _fresh_provider_group() -> click.Group:
    """Build a fresh ``provider`` group whose discovery is not yet populated.

    Tests that patch ``PluginDiscovery.discover_plugins`` must do so *before*
    Click triggers the group's ``list_commands``/``get_command`` callbacks so
    the patched return value is picked up.
    """
    from infrafoundry.cli.commands.provider import _ProviderGroup

    @click.group(cls=_ProviderGroup)
    def provider_group() -> None:
        """Test-only provider group."""

    return provider_group


def test_provider_group_registered():
    """``foundry --help`` lists the ``provider`` group."""
    from infrafoundry.cli.main import foundry

    runner = CliRunner()
    result = runner.invoke(foundry, ["--help"])
    assert result.exit_code == 0
    assert "provider" in result.output


def test_provider_discovers_proxmox():
    """Proxmox's ``register()`` is invoked and its commands are attached."""
    from infrafoundry.cli.main import foundry

    runner = CliRunner()
    result = runner.invoke(foundry, ["provider", "proxmox", "--help"])
    assert result.exit_code == 0, result.output
    assert "dump" in result.output
    assert "export" in result.output


def test_provider_ignores_provider_without_cli_hook():
    """A provider whose ProviderMetadata has no cli_registration is skipped."""

    fake_plugin = PluginMetadata(
        name="fakeprov",
        version="0.0.1",
        plugin_type="provider",
        description="No CLI",
        implementation=type("FakeImpl", (), {}),
        metadata={"cli_registration": None},
    )

    grp = _fresh_provider_group()
    with patch(
        "infrafoundry.cli.commands.provider.PluginDiscovery.discover_plugins",
        return_value=[fake_plugin],
    ):
        runner = CliRunner()
        result = runner.invoke(grp, ["--help"])

    assert result.exit_code == 0
    assert "fakeprov" not in result.output


def test_provider_handles_discovery_error(caplog):
    """A broken entry point is logged, not fatal."""

    grp = _fresh_provider_group()
    with (
        patch(
            "infrafoundry.cli.commands.provider.PluginDiscovery.discover_plugins",
            side_effect=PluginDiscoveryError("broken", entry_point_group="infrafoundry.providers"),
        ),
        caplog.at_level("WARNING", logger="infrafoundry.cli.commands.provider"),
    ):
        runner = CliRunner()
        result = runner.invoke(grp, ["--help"])

    # Group still works with no providers attached.
    assert result.exit_code == 0
    assert any("discovery failed" in rec.message.lower() for rec in caplog.records)


def test_provider_invokes_cli_registration_for_each_plugin():
    """The ``cli_registration`` callable receives the subgroup for each plugin."""

    calls: list[click.Group] = []

    def fake_register(grp: click.Group) -> None:
        calls.append(grp)

        @grp.command(name="ping")
        def _ping() -> None:
            click.echo("pong")

    fake_plugin = PluginMetadata(
        name="fakeprov",
        version="1.0.0",
        plugin_type="provider",
        description="Fake",
        implementation=type("FakeImpl", (), {}),
        metadata={"cli_registration": fake_register},
    )

    grp = _fresh_provider_group()
    with patch(
        "infrafoundry.cli.commands.provider.PluginDiscovery.discover_plugins",
        return_value=[fake_plugin],
    ):
        runner = CliRunner()
        result = runner.invoke(grp, ["fakeprov", "ping"])

    assert result.exit_code == 0, result.output
    assert "pong" in result.output
    assert len(calls) == 1


def test_config_no_longer_has_export_command():
    """The old ``foundry config export`` path is gone (breaking change)."""
    from infrafoundry.cli.main import foundry

    runner = CliRunner()
    result = runner.invoke(foundry, ["config", "--help"])
    assert result.exit_code == 0
    # A stronger check: invoking it fails.
    result = runner.invoke(foundry, ["config", "export", "--env", "x", "--output", "/tmp/x"])
    assert result.exit_code != 0
