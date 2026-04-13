"""Config doctor command - Check configuration repository health."""

from __future__ import annotations

import os
from pathlib import Path

import click

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import InfraFoundryError

from ...utils import console as cli_console
from ...utils import raise_cli_error
from ..doctor_utils import (
    CheckResult,
    render_check_results_json,
    render_check_results_text,
)
from .envs import _get_state_db_environments


def _check_config_repo(config_dir: Path | None) -> CheckResult:
    """Check if configuration repository is set and valid.

    Args:
        config_dir: Path to the config repository, or ``None``.

    Returns:
        A ``CheckResult`` describing the config repo status.
    """
    if config_dir:
        if config_dir.exists():
            envs_dir = config_dir / "envs"
            if envs_dir.exists():
                return CheckResult(
                    name="Config Repository",
                    status="ok",
                    message=str(config_dir),
                )
            return CheckResult(
                name="Config Repository",
                status="warning",
                message=f"{config_dir} exists but missing envs/ directory",
                suggestion="Create envs/ directory with environment configurations",
            )
        return CheckResult(
            name="Config Repository",
            status="error",
            message=f"{config_dir} does not exist",
            suggestion="Check the path or create the directory",
        )

    env_value = os.getenv("INFRAFOUNDRY_CONFIG_REPO")
    if env_value:
        return _check_config_repo(Path(env_value))

    return CheckResult(
        name="Config Repository",
        status="warning",
        message="Not configured",
        suggestion="Set INFRAFOUNDRY_CONFIG_REPO or use --config-dir",
    )


def _check_environments(config_dir: Path | None) -> CheckResult:
    """Check available environments.

    Args:
        config_dir: Path to the config repository, or ``None``.

    Returns:
        A ``CheckResult`` describing environment availability.
    """
    try:
        if config_dir:
            config_manager = ConfigManager(base_dir=config_dir / "envs")
        elif config_repo := os.getenv("INFRAFOUNDRY_CONFIG_REPO"):
            config_manager = ConfigManager(base_dir=Path(config_repo) / "envs")
        else:
            return CheckResult(
                name="Environments",
                status="warning",
                message="Cannot check - config repo not set",
                suggestion="Configure INFRAFOUNDRY_CONFIG_REPO first",
            )

        environments = config_manager.list_environments()
        if environments:
            return CheckResult(
                name="Environments",
                status="ok",
                message=f"{len(environments)} found: {', '.join(environments)}",
            )
        return CheckResult(
            name="Environments",
            status="warning",
            message="No environments found",
            suggestion="Create environment directories in envs/",
        )
    except Exception as e:
        return CheckResult(
            name="Environments",
            status="error",
            message=f"Error: {e}",
            suggestion="Check configuration directory structure",
        )


def _check_state_backend() -> CheckResult:
    """Check state backend configuration.

    Returns:
        A ``CheckResult`` describing state backend status.
    """
    from infrafoundry.core.state.state_manager import StateManager

    try:
        StateManager()
        return CheckResult(
            name="State Backend",
            status="ok",
            message="SQLite backend initialized",
        )
    except Exception as e:
        return CheckResult(
            name="State Backend",
            status="warning",
            message=f"Not initialized: {e}",
            suggestion="Run 'infra state init' to initialize state backend",
        )


def _check_sops_keys() -> CheckResult:
    """Check if SOPS/age keys are configured.

    Returns:
        A ``CheckResult`` describing SOPS key availability.
    """
    age_key_file = Path.home() / ".config" / "sops" / "age" / "keys.txt"
    if age_key_file.exists():
        return CheckResult(
            name="SOPS/Age Keys",
            status="ok",
            message=f"Found at {age_key_file}",
        )

    sops_key_file = os.getenv("SOPS_AGE_KEY_FILE")
    if sops_key_file and Path(sops_key_file).exists():
        return CheckResult(
            name="SOPS/Age Keys",
            status="ok",
            message=f"Found via SOPS_AGE_KEY_FILE: {sops_key_file}",
        )

    return CheckResult(
        name="SOPS/Age Keys",
        status="warning",
        message="Not found",
        suggestion="Run 'age-keygen' and configure SOPS_AGE_KEY_FILE",
    )


def _check_consistency(config_dir: Path | None, deep: bool) -> CheckResult:
    """Check state/filesystem environment consistency.

    Args:
        config_dir: Path to the config repository, or ``None``.
        deep: Whether to include per-env resource counts.

    Returns:
        A ``CheckResult`` describing consistency status.
    """
    try:
        if config_dir:
            config_manager = ConfigManager(base_dir=config_dir / "envs")
        else:
            config_manager = ConfigManager()
        fs_envs = set(config_manager.list_environments())
    except Exception as e:
        return CheckResult(
            name="State Consistency",
            status="error",
            message=f"Cannot read filesystem environments: {e}",
            suggestion="Check configuration directory structure",
        )

    db_env_list, resource_counts, db_available = _get_state_db_environments()
    if not db_available:
        return CheckResult(
            name="State Consistency",
            status="warning",
            message="State database unavailable - cannot check consistency",
            suggestion="Initialize state backend first",
        )

    db_envs = set(db_env_list)
    fs_only = fs_envs - db_envs
    db_only = db_envs - fs_envs

    if fs_only or db_only:
        parts: list[str] = ["Mismatch found"]
        if fs_only:
            parts.append(f"filesystem-only: {', '.join(sorted(fs_only))}")
        if db_only:
            parts.append(f"state-db-only: {', '.join(sorted(db_only))}")
        message = "; ".join(parts)

        if deep and resource_counts:
            counts_msg = ", ".join(
                f"{env}: {resource_counts.get(env, 0)}" for env in sorted(db_envs)
            )
            message += f" (resource counts: {counts_msg})"

        return CheckResult(
            name="State Consistency",
            status="error",
            message=message,
            suggestion="Deploy missing environments or clean up stale state records",
        )

    message = "All environments consistent"
    if deep and resource_counts:
        counts_msg = ", ".join(f"{env}: {resource_counts.get(env, 0)}" for env in sorted(db_envs))
        message += f" (resource counts: {counts_msg})"

    return CheckResult(
        name="State Consistency",
        status="ok",
        message=message,
    )


def _check_blueprints() -> CheckResult:
    """Validate blueprint templates using static analysis.

    Returns:
        A ``CheckResult`` summarising blueprint health.
    """
    try:
        from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
        from infrafoundry.core.config.blueprint_validator import BlueprintValidator

        resolver = BlueprintResolver(base_dir=Path("."))
        names = resolver.list_blueprints()

        if not names:
            return CheckResult(
                name="Blueprints",
                status="ok",
                message="No blueprints found (nothing to validate)",
            )

        total_errors = 0
        total_warnings = 0
        error_details: list[str] = []

        for name in names:
            try:
                resolved = resolver.resolve(name)
                validator = BlueprintValidator(resolved)
                result = validator.validate()
                for prov in result.providers:
                    total_errors += len(prov.errors)
                    total_warnings += len(prov.warnings)
                    for err in prov.errors:
                        error_details.append(f"{name}/{prov.provider}: {err}")
            except Exception as e:
                total_errors += 1
                error_details.append(f"{name}: {e}")

        if total_errors > 0:
            message = (
                f"{len(names)} blueprint(s) checked, "
                f"{total_errors} error(s), {total_warnings} warning(s)"
            )
            if error_details:
                message += f": {error_details[0]}"
                if len(error_details) > 1:
                    message += f" (+{len(error_details) - 1} more)"
            return CheckResult(
                name="Blueprints",
                status="error",
                message=message,
                suggestion="Run 'config doctor --format json' for full details",
            )

        if total_warnings > 0:
            return CheckResult(
                name="Blueprints",
                status="warning",
                message=(f"{len(names)} blueprint(s) checked, {total_warnings} warning(s)"),
            )

        return CheckResult(
            name="Blueprints",
            status="ok",
            message=f"{len(names)} blueprint(s) checked, all clean",
        )
    except Exception as e:
        return CheckResult(
            name="Blueprints",
            status="error",
            message=f"Blueprint validation failed: {e}",
            suggestion="Check blueprint directory structure",
        )


@click.command("doctor")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
@click.option(
    "--deep",
    is_flag=True,
    default=False,
    help="Include per-environment resource counts in consistency check",
)
@click.pass_context
def doctor(ctx: click.Context, output_format: str, deep: bool) -> None:
    """Check configuration repository health.

    Runs six checks against the configuration repository:

    \b
    1. Config repo exists with envs/ directory
    2. Environments are defined
    3. State backend is initialized
    4. SOPS/age keys are configured
    5. State/filesystem consistency
    6. Blueprint template validation

    Use --deep to include per-environment resource counts.

    Examples:

        # Run all config checks
        config doctor

        # JSON output for scripting
        config doctor --format json

        # Include resource counts
        config doctor --deep
    """
    try:
        config_dir = ctx.obj.get("config_dir")

        results: list[CheckResult] = []

        if output_format == "text":
            cli_console.header("Config Doctor")
            cli_console.info("")

        results.append(_check_config_repo(config_dir))
        results.append(_check_environments(config_dir))
        results.append(_check_state_backend())
        results.append(_check_sops_keys())
        results.append(_check_consistency(config_dir, deep))
        results.append(_check_blueprints())

        if output_format == "json":
            render_check_results_json(results)
        else:
            render_check_results_text(results, title="Config Health Check Results")

        errors = sum(1 for r in results if r.status == "error")
        if errors > 0:
            ctx.exit(1)

    except click.exceptions.Exit:
        raise
    except InfraFoundryError as exc:
        raise_cli_error("Config doctor failed", exc)
    except Exception as exc:
        raise_cli_error("Config doctor failed", exc)
