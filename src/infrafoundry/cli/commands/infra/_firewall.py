"""Instance selection for ``infra plan|apply|destroy|doctor`` (#1450, #1539, ADR-0024, ADR-0030).

Each instance of an instance-capable provider (see
:data:`infrafoundry.core.provider_instances.INSTANCE_SPECS`) is a provider instance:
the plain id (``opnsense``) for the primary, ``<base>@<name>`` for the others. The core
``provider_filter`` matches provider ids exactly, so this helper turns the CLI's ``-P``
and instance options (``--firewall``, ``--cluster``) into exact ids before they reach the
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
CLUSTER_BASE = "kubernetes"

FIREWALL_HELP = (
    "Limit operation to the named firewall(s) of provider opnsense (can be used multiple "
    "times). Combines with --provider opnsense; mutually exclusive with --package and "
    "--resource."
)

CLUSTER_HELP = (
    "Limit operation to the named cluster(s) of provider kubernetes (can be used multiple "
    "times). Combines with --provider kubernetes; mutually exclusive with --package and "
    "--resource."
)


def expand_provider_filter(
    orchestrator: Orchestrator,
    env: str,
    providers: tuple[str, ...],
    firewalls: tuple[str, ...],
    clusters: tuple[str, ...] = (),
) -> list[str] | None:
    """Turn ``-P``, ``--firewall`` and ``--cluster`` values into exact provider ids.

    - ``-P opnsense`` selects every firewall of the environment that has resources:
      ``opnsense`` plus each declared ``opnsense@<name>``.
    - ``--firewall <name>`` selects one firewall: ``opnsense`` for the primary,
      ``opnsense@<name>`` for the others.
    - ``-P kubernetes`` and ``--cluster <name>`` work the same way for ``kubernetes`` and
      ``kubernetes@<name>``.
    - An environment without the instance map keeps the legacy behaviour.

    Args:
        orchestrator: Orchestrator whose config manager reads the environment.
        env: Environment name.
        providers: ``--provider`` values.
        firewalls: ``--firewall`` values.
        clusters: ``--cluster`` values.

    Returns:
        The provider ids for ``provider_filter``, or ``None`` when no option is set.

    Raises:
        click.UsageError: If an instance option names an undeclared instance, the
            environment declares no instance map, or ``--provider`` excludes the family.
    """
    if not providers and not firewalls and not clusters:
        return None
    current = list(providers)
    for base, option, names in (
        (BASE, "--firewall", firewalls),
        (CLUSTER_BASE, "--cluster", clusters),
    ):
        if names or base in providers:
            current = _expand(
                base, option, names, current, orchestrator, env, scope=list(providers)
            )
    return current


def _expand(
    base: str,
    option: str,
    names: tuple[str, ...],
    provider_list: list[str],
    orchestrator: Orchestrator,
    env: str,
    *,
    scope: list[str] | None = None,
) -> list[str]:
    """Expand one provider family's ``-P`` and instance-option values into exact ids.

    Args:
        base: Base provider id with an ``InstanceSpec``.
        option: The instance option's flag, for messages (``--firewall``).
        names: The instance names given with that option.
        provider_list: ``--provider`` values.
        orchestrator: Orchestrator whose config manager reads the environment.
        env: Environment name.
        scope: The user's original ``--provider`` values, when ``provider_list`` already
            carries other families' expansion; defaults to ``provider_list``.

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
    requested = provider_list if scope is None else scope
    if requested and base not in requested:
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
