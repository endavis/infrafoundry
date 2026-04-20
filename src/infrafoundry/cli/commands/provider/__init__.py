"""Provider-specific CLI commands.

The ``provider`` group is populated on first access by scanning the
``infrafoundry.providers`` entry point group. Each provider whose
:class:`~infrafoundry.providers.plugin_type.ProviderMetadata` exposes a
``cli_registration`` callback gets a subgroup (e.g. ``foundry provider
proxmox dump``). Discovery runs lazily to avoid import-time cycles between
provider packages and the CLI utilities they depend on.

See ADR ``0005-provider-cli-extensibility`` for the rationale.
"""

from __future__ import annotations

import logging

import click

from infrafoundry.core.plugin_system.discovery import PluginDiscovery
from infrafoundry.core.plugin_system.exceptions import PluginDiscoveryError
from infrafoundry.providers.plugin_type import ProviderPluginType

logger = logging.getLogger(__name__)


class _ProviderGroup(click.Group):
    """Click group that discovers provider subcommands on first access.

    The lookup hooks (``list_commands`` and ``get_command``) call
    :meth:`_populate` once; subsequent calls are no-ops. Discovery happens
    outside module import time so that provider packages which depend on
    :mod:`infrafoundry.cli.utils` (and therefore pull
    :mod:`infrafoundry.cli.main` into the import graph) do not form an
    import cycle with this module.
    """

    _populated: bool = False

    def _populate(self) -> None:
        if self._populated:
            return
        self._populated = True
        _register_provider_clis(self)

    def list_commands(self, ctx: click.Context) -> list[str]:
        self._populate()
        return super().list_commands(ctx)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        self._populate()
        return super().get_command(ctx, cmd_name)


@click.group(cls=_ProviderGroup)
def provider() -> None:
    """Provider-specific commands.

    Subcommands are registered dynamically by discovered provider plugins.
    Run ``foundry provider --help`` to list providers that expose a CLI.
    """


def _register_provider_clis(group: click.Group) -> None:
    """Discover providers via entry points and invoke their ``cli_registration``.

    Discovery errors are logged but never raised: a broken third-party plugin
    must not prevent the rest of the CLI from loading.
    """
    provider_type = ProviderPluginType()
    discovery = PluginDiscovery()
    try:
        plugins = discovery.discover_plugins(provider_type)
    except PluginDiscoveryError as exc:
        logger.warning("Provider plugin discovery failed: %s", exc)
        return

    for plugin in plugins:
        cli_hook = plugin.metadata.get("cli_registration") if plugin.metadata else None
        if not callable(cli_hook):
            logger.debug("Provider %s has no cli_registration hook; skipping", plugin.name)
            continue

        subgroup = click.Group(
            name=plugin.name,
            help=plugin.description or f"{plugin.name} provider commands",
        )
        try:
            cli_hook(subgroup)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to register CLI for provider %s: %s", plugin.name, exc)
            continue

        group.add_command(subgroup, name=plugin.name)


__all__ = ["provider"]
