"""Instance selection for ``infra plan|apply|destroy|doctor`` (#1450, ADR-0024).

Each instance of an instance-capable provider (see
:data:`infrafoundry.core.provider_instances.INSTANCE_SPECS`) is a provider instance:
the plain id (``opnsense``) for the primary, ``<base>@<name>`` for the others. The core
``provider_filter`` matches provider ids exactly, so this helper turns the CLI's ``-P``
and instance options (currently ``--firewall``) into exact ids before they reach the
orchestrator.
"""

from __future__ import annotations

import click

from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.provider_instances import (
    INSTANCE_SPECS,
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
    return _expand(BASE, "--firewall", firewalls, provider_list, orchestrator, env)


def _expand(
    base: str,
    option: str,
    names: tuple[str, ...],
    provider_list: list[str],
    orchestrator: Orchestrator,
    env: str,
) -> list[str]:
    """Expand one provider family's ``-P`` and instance-option values into exact ids.

    Args:
        base: Base provider id with an ``InstanceSpec``.
        option: The instance option's flag, for messages (``--firewall``).
        names: The instance names given with that option.
        provider_list: ``--provider`` values.
        orchestrator: Orchestrator whose config manager reads the environment.
        env: Environment name.

    Raises:
        click.UsageError: On an undeclared instance, a missing instance map, or a
            ``--provider`` list that excludes ``base``.
    """
    spec = INSTANCE_SPECS[base]
    try:
        settings = orchestrator.config_manager.load_environment(env).provider_settings
    except (AttributeError, FileNotFoundError):
        # Settings unreadable here: treat the environment as having no instance map and
        # let the orchestrator report a missing environment itself.
        settings = {}
    declared = declared_instances(base, settings)

    if not names:
        return _expand_family(base, orchestrator, env, provider_list, declared)

    if not declared:
        raise click.UsageError(
            f"{option} needs provider_settings.{base}.{spec.map_key} in environment '{env}'"
        )
    unknown = [name for name in names if name not in declared]
    if unknown:
        raise click.UsageError(
            f"Unknown {spec.noun}(s) {', '.join(unknown)}; declared: {', '.join(declared)}"
        )
    if provider_list and base not in provider_list:
        raise click.UsageError(f"{option} selects {base} {spec.noun}s; add '-P {base}' or drop -P")
    ids = [instance_provider_id(base, name, settings) for name in dict.fromkeys(names)]
    return [p for p in provider_list if p != base] + ids


def _expand_family(
    base: str,
    orchestrator: Orchestrator,
    env: str,
    provider_list: list[str],
    declared: list[str],
) -> list[str]:
    """Replace ``base`` in ``provider_list`` with every instance that has resources."""
    if not declared:
        return provider_list
    present = {r.provider for r in orchestrator.config_manager.get_all_resources_all_providers(env)}
    family = [base] + [
        qualified_provider_id(base, name)
        for name in declared
        if qualified_provider_id(base, name) in present
    ]
    expanded: list[str] = []
    for provider in provider_list:
        expanded.extend(family if provider == base else [provider])
    return list(dict.fromkeys(expanded))
