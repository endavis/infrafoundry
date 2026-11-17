"""Firewall selection for ``infra plan|apply|destroy|doctor`` (#1450, ADR-0024).

Each firewall of an environment is a provider instance: ``opnsense`` for the primary,
``opnsense@<name>`` for the others. The core ``provider_filter`` matches provider ids
exactly, so this helper turns the CLI's ``-P`` / ``--firewall`` values into exact ids
before they reach the orchestrator.
"""

from __future__ import annotations

import click

from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.provider_instances import (
    declared_instances,
    instance_provider_id,
    qualified_provider_id,
)

BASE = "opnsense"

FIREWALL_HELP = (
    "Limit operation to the named firewall(s) of provider opnsense (can be used multiple "
    "times). Combines with --provider opnsense; mutually exclusive with --package and "
    "--resource."
)


def expand_provider_filter(
    orchestrator: Orchestrator,
    env: str,
    providers: tuple[str, ...],
    firewalls: tuple[str, ...],
) -> list[str] | None:
    """Turn ``-P`` and ``--firewall`` values into exact provider ids.

    - ``-P opnsense`` selects every firewall of the environment that has resources:
      ``opnsense`` plus each declared ``opnsense@<name>``.
    - ``--firewall <name>`` selects one firewall: ``opnsense`` for the primary,
      ``opnsense@<name>`` for the others.
    - An environment without ``firewalls:`` keeps the legacy behaviour.

    Args:
        orchestrator: Orchestrator whose config manager reads the environment.
        env: Environment name.
        providers: ``--provider`` values.
        firewalls: ``--firewall`` values.

    Returns:
        The provider ids for ``provider_filter``, or ``None`` when neither option is set.

    Raises:
        click.UsageError: If ``--firewall`` names an undeclared firewall, the
            environment declares no ``firewalls:``, or ``--provider`` excludes opnsense.
    """
    if not providers and not firewalls:
        return None
    provider_list = list(providers)
    if not firewalls and BASE not in provider_list:
        return provider_list

    try:
        settings = orchestrator.config_manager.load_environment(env).provider_settings
    except (AttributeError, FileNotFoundError):
        # Settings unreadable here: treat the environment as having no firewalls: map and
        # let the orchestrator report a missing environment itself.
        settings = {}
    declared = declared_instances(BASE, settings)

    if not firewalls:
        return _expand_family(orchestrator, env, provider_list, declared, settings)

    if not declared:
        raise click.UsageError(
            f"--firewall needs provider_settings.{BASE}.firewalls in environment '{env}'"
        )
    unknown = [name for name in firewalls if name not in declared]
    if unknown:
        raise click.UsageError(
            f"Unknown firewall(s) {', '.join(unknown)}; declared: {', '.join(declared)}"
        )
    if provider_list and BASE not in provider_list:
        raise click.UsageError(
            "--firewall selects opnsense firewalls; add '-P opnsense' or drop -P"
        )
    ids = [instance_provider_id(BASE, name, settings) for name in dict.fromkeys(firewalls)]
    return [p for p in provider_list if p != BASE] + ids


def _expand_family(
    orchestrator: Orchestrator,
    env: str,
    provider_list: list[str],
    declared: list[str],
    settings: object,
) -> list[str]:
    """Replace ``opnsense`` in ``provider_list`` with every firewall that has resources."""
    if not declared:
        return provider_list
    present = {r.provider for r in orchestrator.config_manager.get_all_resources_all_providers(env)}
    family = [BASE] + [
        qualified_provider_id(BASE, name)
        for name in declared
        if qualified_provider_id(BASE, name) in present
    ]
    expanded: list[str] = []
    for provider in provider_list:
        expanded.extend(family if provider == BASE else [provider])
    return list(dict.fromkeys(expanded))
