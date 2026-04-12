"""Show deployment status and resources for an environment."""

from collections import defaultdict
from typing import Any

import click

from infrafoundry.core.exceptions import InfraFoundryError, StateError
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.state.models import Resource

from ...decorators import with_orchestrator
from ...output import output_data
from ...utils import console, raise_cli_error

# Keys to search for IP address in resource config
_IP_KEYS = ("ip_address", "address", "ip")

# Keys to search for node/host in resource config
_NODE_KEYS = ("target_node", "node")

# Placeholder for missing values
_MISSING = "\u2014"


def _extract_field(config: dict[str, Any] | None, keys: tuple[str, ...]) -> str:
    """Extract the first matching key from a resource config dict.

    Args:
        config: Resource configuration dictionary (may be None).
        keys: Ordered tuple of key names to try.

    Returns:
        The first found value as a string, or the em-dash placeholder.
    """
    if not config:
        return _MISSING
    for key in keys:
        value = config.get(key)
        if value is not None:
            return str(value)
    return _MISSING


def _build_resource_entry(resource: Resource) -> dict[str, str]:
    """Build a display-ready dict for a single resource.

    Args:
        resource: A tracked Resource object.

    Returns:
        Dict with name, ip, node, and state fields.
    """
    state_str = resource.state.value if hasattr(resource.state, "value") else str(resource.state)
    return {
        "name": resource.name,
        "resource_type": resource.resource_type,
        "ip": _extract_field(resource.config, _IP_KEYS),
        "node": _extract_field(resource.config, _NODE_KEYS),
        "state": state_str,
    }


@click.command("deployed")
@click.option("--env", "-e", required=True, help="Environment name")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
@with_orchestrator("Failed to show deployment status", require_env=False, load_credentials=False)
def deployed(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    output_format: str,
) -> None:
    """Show deployment status and resources for an environment."""
    try:
        state_manager = orchestrator.state_manager

        # Get latest non-dry-run apply
        deployments = state_manager.get_deployment_history(
            environment=env,
            command="apply",
            exclude_dry_run=True,
            limit=1,
        )

        # Get tracked resources (returns newest first via created_at DESC)
        resources = state_manager.get_resources(environment=env)

        # Deduplicate: keep only the latest record per (provider, name)
        # and filter out deleted resources
        seen: set[tuple[str, str]] = set()
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for resource in resources:
            key = (resource.provider, resource.name)
            if key in seen:
                continue
            seen.add(key)
            state_str = (
                resource.state.value if hasattr(resource.state, "value") else str(resource.state)
            )
            if state_str == "deleted":
                continue
            entry = _build_resource_entry(resource)
            grouped[resource.provider].append(entry)

        # Sort resources within each provider by name
        for provider in grouped:
            grouped[provider].sort(key=lambda r: r["name"])

        if output_format == "json":
            _output_json(deployments, env, grouped)
        else:
            _output_text(deployments, env, grouped)

    except click.ClickException:
        raise
    except StateError as exc:
        if "no such table" in str(exc).lower():
            console.info("Run 'infra init' to initialize state tracking.")
        raise_cli_error("Failed to show deployment status", exc)
    except InfraFoundryError as exc:
        raise_cli_error("Failed to show deployment status", exc)
    except Exception as exc:
        if "no such table" in str(exc).lower():
            console.info("Run 'infra init' to initialize state tracking.")
        raise_cli_error("Failed to show deployment status", exc)


def _output_json(
    deployments: list[Any],
    env: str,
    grouped: dict[str, list[dict[str, str]]],
) -> None:
    """Emit JSON output for the deployed command.

    Args:
        deployments: List of Deployment objects (0 or 1 items).
        env: Environment name.
        grouped: Resources grouped by provider.
    """
    data: dict[str, Any] = {"environment": env}

    if deployments:
        dep = deployments[0]
        status_str = dep.status.value if hasattr(dep.status, "value") else str(dep.status)
        data["last_deployment"] = {
            "id": dep.id,
            "status": status_str,
            "started_at": dep.started_at.isoformat() if dep.started_at else None,
            "completed_at": dep.completed_at.isoformat() if dep.completed_at else None,
            "user": dep.user or "unknown",
        }
    else:
        data["last_deployment"] = None

    data["resources"] = dict(sorted(grouped.items()))

    output_data(data, "json")


def _output_text(
    deployments: list[Any],
    env: str,
    grouped: dict[str, list[dict[str, str]]],
) -> None:
    """Emit human-readable text output for the deployed command.

    Args:
        deployments: List of Deployment objects (0 or 1 items).
        env: Environment name.
        grouped: Resources grouped by provider.
    """
    console.header(f"Environment: {env}")

    if deployments:
        dep = deployments[0]
        status_str = dep.status.value if hasattr(dep.status, "value") else str(dep.status)
        started = dep.started_at.strftime("%Y-%m-%d %H:%M") if dep.started_at else _MISSING
        completed = dep.completed_at.strftime("%Y-%m-%d %H:%M") if dep.completed_at else _MISSING
        user = dep.user or "unknown"

        console.info("Last deployment:")
        console.info(f"  Status:    {status_str}")
        console.info(f"  Started:   {started}")
        console.info(f"  Completed: {completed}")
        console.info(f"  User:      {user}")
    else:
        console.warning(f"No deployments found for environment '{env}'.")

    console.info("")

    if not grouped:
        console.warning(f"No tracked resources for environment '{env}'.")
        return

    console.info("Resources:")
    for provider in sorted(grouped):
        console.info(f"  {provider}:")
        for entry in grouped[provider]:
            name = entry["name"]
            ip = entry["ip"]
            node = entry["node"]
            state = entry["state"]
            console.info(f"    {name:<20s} {ip:<16s} {node:<8s} {state}")
