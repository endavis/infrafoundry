"""Doctor command - Check InfraFoundry setup and dependencies."""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


@dataclass
class CheckResult:
    """Result of a health check."""

    name: str
    status: str  # "ok", "warning", "error"
    message: str
    suggestion: str = ""


def _check_dependency(name: str, command: str, suggestion: str) -> CheckResult:
    """Check if a command-line dependency is available."""
    path = shutil.which(command)
    if path:
        return CheckResult(
            name=name,
            status="ok",
            message=f"Found at {path}",
        )
    return CheckResult(
        name=name,
        status="error",
        message="Not found",
        suggestion=suggestion,
    )


def _check_config_repo(config_dir: Path | None) -> CheckResult:
    """Check if configuration repository is set and valid."""
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
    """Check available environments."""
    from infrafoundry.core.config import ConfigManager

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
    """Check state backend configuration."""
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
    """Check if SOPS/age keys are configured."""
    # Check for age key file
    age_key_file = Path.home() / ".config" / "sops" / "age" / "keys.txt"
    if age_key_file.exists():
        return CheckResult(
            name="SOPS/Age Keys",
            status="ok",
            message=f"Found at {age_key_file}",
        )

    # Check SOPS_AGE_KEY_FILE env var
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


@click.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Check InfraFoundry setup and dependencies.

    Validates that all required tools are installed and properly configured.
    """
    config_dir = ctx.obj.get("config_dir")

    console.print()
    console.print("[bold cyan]InfraFoundry Doctor[/bold cyan]")
    console.print()

    results: list[CheckResult] = []

    # Check dependencies
    console.print("[bold]Checking dependencies...[/bold]")
    results.append(
        _check_dependency(
            "Terraform",
            "terraform",
            "Install from https://terraform.io/downloads",
        )
    )
    results.append(
        _check_dependency(
            "Ansible",
            "ansible",
            "Install with: pip install ansible",
        )
    )
    results.append(
        _check_dependency(
            "SOPS",
            "sops",
            "Install from https://github.com/getsops/sops",
        )
    )
    results.append(
        _check_dependency(
            "Age",
            "age",
            "Install from https://github.com/FiloSottile/age",
        )
    )

    # Check configuration
    console.print("[bold]Checking configuration...[/bold]")
    results.append(_check_config_repo(config_dir))
    results.append(_check_environments(config_dir))
    results.append(_check_state_backend())
    results.append(_check_sops_keys())

    # Display results
    console.print()
    table = Table(title="Health Check Results", show_header=True)
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Details")

    status_icons = {
        "ok": "[green]OK[/green]",
        "warning": "[yellow]WARN[/yellow]",
        "error": "[red]FAIL[/red]",
    }

    errors = 0
    warnings = 0

    for result in results:
        status_display = status_icons.get(result.status, result.status)
        details = result.message
        if result.suggestion:
            details += f"\n[dim]{result.suggestion}[/dim]"
        table.add_row(result.name, status_display, details)

        if result.status == "error":
            errors += 1
        elif result.status == "warning":
            warnings += 1

    console.print(table)
    console.print()

    # Summary
    if errors > 0:
        console.print(f"[red]Found {errors} error(s) and {warnings} warning(s)[/red]")
        console.print("[dim]Fix errors before using InfraFoundry[/dim]")
    elif warnings > 0:
        console.print(f"[yellow]Found {warnings} warning(s)[/yellow]")
        console.print("[dim]InfraFoundry should work but some features may be limited[/dim]")
    else:
        console.print("[green]All checks passed![/green]")
        console.print("[dim]InfraFoundry is ready to use[/dim]")

    console.print()
