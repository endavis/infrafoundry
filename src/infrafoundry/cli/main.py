"""Command-line interface for InfraFoundry."""

import os
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.orchestrator import Orchestrator, OrchestratorStrictConfig

# Load environment variables
load_dotenv()

console = Console()


def _resolve_bool_option(option: bool | None, env_var: str) -> bool | None:
    """Resolve a boolean option from CLI flag or environment variable."""
    if option is not None:
        return option

    value = os.getenv(env_var)
    if value is None:
        return None

    return value.strip().lower() in {"1", "true", "yes", "on"}


def _build_strict_config(
    strict_mode: bool | None,
    fail_on_missing_secrets: bool | None,
    fail_on_missing_snippets: bool | None,
) -> OrchestratorStrictConfig | None:
    """Construct strict configuration based on CLI flags/environment."""
    strict_kwargs: dict[str, bool] = {}

    if (value := _resolve_bool_option(strict_mode, "INFRAFOUNDRY_STRICT_MODE")) is not None:
        strict_kwargs["strict_mode"] = value

    if (
        value := _resolve_bool_option(
            fail_on_missing_secrets, "INFRAFOUNDRY_FAIL_ON_MISSING_SECRETS"
        )
    ) is not None:
        strict_kwargs["fail_on_missing_secrets"] = value

    if (
        value := _resolve_bool_option(
            fail_on_missing_snippets, "INFRAFOUNDRY_FAIL_ON_MISSING_SNIPPETS"
        )
    ) is not None:
        strict_kwargs["fail_on_missing_snippets"] = value

    if not strict_kwargs:
        return None

    return OrchestratorStrictConfig(**strict_kwargs)


def _get_orchestrator(
    config_repo: Path | None = None,
    strict_config: OrchestratorStrictConfig | None = None,
) -> Orchestrator:
    """Create and configure orchestrator with all providers.

    Args:
        config_repo: Path to configuration repository
            (overrides INFRAFOUNDRY_CONFIG_REPO)
    """
    # Determine config directory
    if config_repo:
        config_dir = config_repo / "envs"
        config_manager = ConfigManager(base_dir=config_dir)
    else:
        config_manager = ConfigManager()

    # Create orchestrator (SecretManager is created per-operation now)
    orchestrator = Orchestrator(config_manager, strict_config=strict_config)

    # Dynamically register available providers
    try:
        from infrafoundry.providers.proxmox import ProxmoxProvider

        orchestrator.register_provider(
            ProxmoxProvider(
                config_dir=config_manager.base_dir,
                output_dir=Path(os.getenv("INFRAFOUNDRY_OUTPUT_DIR", "generated")),
            )
        )
    except ImportError:
        pass

    try:
        from infrafoundry.providers.opnsense import OPNsenseProvider

        orchestrator.register_provider(
            OPNsenseProvider(
                config_dir=config_manager.base_dir,
                output_dir=Path(os.getenv("INFRAFOUNDRY_OUTPUT_DIR", "generated")),
            )
        )
    except ImportError:
        pass

    try:
        from infrafoundry.providers.kubernetes import KubernetesProvider

        orchestrator.register_provider(
            KubernetesProvider(
                config_dir=config_manager.base_dir,
                output_dir=Path(os.getenv("INFRAFOUNDRY_OUTPUT_DIR", "generated")),
            )
        )
    except ImportError:
        pass

    return orchestrator


def _load_env_credentials(env_name: str, config_dir: Path | None = None) -> None:
    """Load environment-specific credentials and update os.environ.

    Automatically loads credentials from secrets/{env}/ directory if it exists.
    This allows each environment to have different credentials without manual
    environment variable management.

    Args:
        env_name: Environment name (dev, staging, prod, etc.)
        config_dir: Configuration directory (defaults to context config_dir)
    """
    from infrafoundry.core.credential_loader import CredentialLoader
    from infrafoundry.core.credential_loader.base_loader import CredentialLoaderError

    try:
        loader = CredentialLoader(config_dir=config_dir)
        loader.load_and_apply(env_name)
    except CredentialLoaderError as exc:
        # Silently fail - credentials might be in environment already
        if os.getenv("INFRAFOUNDRY_LOG_LEVEL") == "DEBUG":
            console.print(f"[dim]Could not load env-specific credentials: {exc}[/dim]")


@click.group()
@click.version_option(version="0.1.0", prog_name="infrafoundry")
@click.option(
    "--config-dir",
    "-c",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Path to configuration repository (overrides INFRAFOUNDRY_CONFIG_REPO)",
)
@click.option(
    "--strict-mode/--no-strict-mode",
    default=None,
    help="Enable strict mode (fail on missing secrets/snippets). Env: INFRAFOUNDRY_STRICT_MODE",
)
@click.option(
    "--fail-on-missing-secrets/--allow-missing-secrets",
    default=None,
    help="Fail when secrets files are missing. Env: INFRAFOUNDRY_FAIL_ON_MISSING_SECRETS",
)
@click.option(
    "--fail-on-missing-snippets/--allow-missing-snippets",
    default=None,
    help="Fail when cloud-init snippets are missing. Env: INFRAFOUNDRY_FAIL_ON_MISSING_SNIPPETS",
)
@click.pass_context
def main(
    ctx: click.Context,
    config_dir: Path | None,
    strict_mode: bool | None,
    fail_on_missing_secrets: bool | None,
    fail_on_missing_snippets: bool | None,
) -> None:
    """InfraFoundry - Infrastructure automation framework."""
    ctx.ensure_object(dict)
    # Use --config-dir flag if provided, otherwise check environment variable
    if config_dir:
        ctx.obj["config_dir"] = config_dir
    elif config_repo := os.getenv("INFRAFOUNDRY_CONFIG_REPO"):
        ctx.obj["config_dir"] = Path(config_repo)
    else:
        ctx.obj["config_dir"] = None

    strict_config = _build_strict_config(
        strict_mode,
        fail_on_missing_secrets,
        fail_on_missing_snippets,
    )
    ctx.obj["strict_config"] = strict_config


# Auto-discover and register commands from commands/ directory
from infrafoundry.cli.command_loader import load_commands
from infrafoundry.cli.commands.state import state

load_commands(main)
main.add_command(state)


if __name__ == "__main__":
    main()
