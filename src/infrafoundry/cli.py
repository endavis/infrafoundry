"""Command-line interface for InfraFoundry."""

import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.secrets import SecretManager

# Load environment variables
load_dotenv()

console = Console()


def _get_orchestrator(config_repo: Path | None = None) -> Orchestrator:
    """Create and configure orchestrator with all providers.

    Args:
        config_repo: Path to configuration repository
            (overrides INFRAFOUNDRY_CONFIG_REPO)
    """
    # Determine config and secrets directories
    if config_repo:
        config_dir = config_repo / "envs"
        secrets_dir = config_repo / "secrets"
        config_manager = ConfigManager(base_dir=config_dir)

        def secret_manager_init() -> SecretManager:
            return SecretManager(secrets_dir=secrets_dir)

    else:
        config_manager = ConfigManager()

        def secret_manager_init() -> SecretManager:
            return SecretManager()

    # Check if secrets are needed
    try:
        secret_manager = secret_manager_init()
    except (RuntimeError, ValueError) as e:
        if "SOPS_AGE_KEY_FILE" in str(e):
            console.print(
                "[yellow]Warning: Secrets not configured. "
                "Set SOPS_AGE_KEY_FILE to use encrypted secrets.[/yellow]"
            )
            secret_manager = None
        else:
            raise

    orchestrator = Orchestrator(config_manager, secret_manager)

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


@click.group()
@click.version_option(version="0.1.0", prog_name="infrafoundry")
@click.option(
    "--config-dir",
    "-c",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Path to configuration repository (overrides INFRAFOUNDRY_CONFIG_REPO)",
)
@click.pass_context
def main(ctx: click.Context, config_dir: Path | None) -> None:
    """InfraFoundry - Infrastructure automation framework."""
    ctx.ensure_object(dict)
    ctx.obj["config_dir"] = config_dir


@main.command()
@click.option("--env", "-e", required=True, help="Environment name (e.g., dev, prod)")
@click.option("--dry-run", is_flag=True, help="Show what would be done without doing it")
@click.option(
    "--resource",
    "-r",
    multiple=True,
    help="Specific resource name(s) to target (can be used multiple times)",
)
@click.pass_context
def plan(ctx: click.Context, env: str, dry_run: bool, resource: tuple[str, ...]) -> None:
    """Plan infrastructure changes."""
    try:
        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))
        orchestrator.plan(
            env, dry_run=dry_run, resource_filter=list(resource) if resource else None
        )

        if dry_run:
            console.print("\n[bold cyan]Dry run complete. No files generated.[/bold cyan]")
        else:
            console.print("\n[bold green]Plan generated successfully![/bold green]")
            console.print("Generated files are in: [cyan]generated/[/cyan]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


@main.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--auto-approve", is_flag=True, help="Skip confirmation prompts")
@click.option(
    "--resource",
    "-r",
    multiple=True,
    help="Specific resource name(s) to target (can be used multiple times)",
)
@click.pass_context
def apply(ctx: click.Context, env: str, auto_approve: bool, resource: tuple[str, ...]) -> None:
    """Apply infrastructure changes."""
    try:
        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))
        orchestrator.apply(
            env, auto_approve=auto_approve, resource_filter=list(resource) if resource else None
        )
        console.print("\n[bold green]Apply complete![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


@main.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--auto-approve", is_flag=True, help="Skip confirmation prompts")
@click.option(
    "--resource",
    "-r",
    multiple=True,
    help="Specific resource name(s) to target (can be used multiple times)",
)
@click.pass_context
def destroy(ctx: click.Context, env: str, auto_approve: bool, resource: tuple[str, ...]) -> None:
    """Destroy infrastructure."""
    try:
        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))
        orchestrator.destroy(
            env, auto_approve=auto_approve, resource_filter=list(resource) if resource else None
        )
        console.print("\n[bold green]Destroy complete![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


@main.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.pass_context
def status(ctx: click.Context, env: str) -> None:
    """Show infrastructure status."""
    try:
        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))
        orchestrator.status(env)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


@main.command()
@click.pass_context
def envs(ctx: click.Context) -> None:
    """List available environments."""
    try:
        config_repo = ctx.obj.get("config_dir")
        if config_repo:
            config_manager = ConfigManager(base_dir=config_repo / "envs")
        else:
            config_manager = ConfigManager()
        environments = config_manager.list_environments()

        if not environments:
            console.print(
                "[yellow]No environments found. Create one in the envs/ directory.[/yellow]"
            )
            return

        console.print("[bold cyan]Available environments:[/bold cyan]")
        for env_name in environments:
            env_config = config_manager.load_environment(env_name)
            console.print(f"  • {env_name}: {env_config.description or 'No description'}")
            console.print(f"    Providers: {', '.join(env_config.providers)}")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


@main.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--provider", "-p", help="Filter by provider (e.g., proxmox, opnsense)")
@click.option("--type", "-t", help="Filter by resource type (e.g., vms, firewall_rules)")
@click.pass_context
def list(ctx: click.Context, env: str, provider: str | None, type: str | None) -> None:
    """List all resources in an environment."""
    try:
        config_repo = ctx.obj.get("config_dir")
        if config_repo:
            config_manager = ConfigManager(base_dir=config_repo / "envs")
        else:
            config_manager = ConfigManager()

        # Get all resources from all providers (handles both formats)
        all_resources = config_manager.get_all_resources_all_providers(env)

        # Apply filters
        if provider:
            all_resources = [r for r in all_resources if r.provider == provider]
        if type:
            all_resources = [r for r in all_resources if r.type == type]

        if not all_resources:
            if type and provider:
                console.print(
                    f"[yellow]No resources found with provider '{provider}' "
                    f"and type '{type}'[/yellow]"
                )
            elif type:
                console.print(f"[yellow]No resources found with type '{type}'[/yellow]")
            elif provider:
                console.print(f"[yellow]No resources found with provider '{provider}'[/yellow]")
            else:
                console.print("[yellow]No resources found[/yellow]")
            return

        console.print(f"[bold cyan]Resources in {env}:[/bold cyan]\n")

        # Group by provider for display
        by_provider: dict[str, list] = {}
        for resource in all_resources:
            if resource.provider not in by_provider:
                by_provider[resource.provider] = []
            by_provider[resource.provider].append(resource)

        for provider_name, resources in sorted(by_provider.items()):
            console.print(f"[bold]{provider_name}[/bold] ({len(resources)} resources):")
            for resource in sorted(resources, key=lambda r: r.name):
                console.print(f"  • {resource.name:<40} [dim]({resource.type})[/dim]")
            console.print()

        console.print(f"[dim]Total: {len(all_resources)} resources[/dim]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


@main.group()
def secrets() -> None:
    """Manage encrypted secrets."""
    pass


@secrets.command("init")
@click.option("--key-file", default="secrets/age.key", help="Path to age key file")
def secrets_init(key_file: str) -> None:
    """Initialize secrets with a new age key."""
    key_path = Path(key_file)

    if key_path.exists():
        console.print(f"[yellow]Key file already exists: {key_path}[/yellow]")
        return

    key_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate age key
    import subprocess

    result = subprocess.run(
        ["age-keygen", "-o", str(key_path)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        console.print(f"[red]Failed to generate key: {result.stderr}[/red]")
        sys.exit(1)

    # Extract public key from output
    for line in result.stderr.split("\n"):
        if line.startswith("# public key:"):
            public_key = line.split(": ")[1]

            # Create .sops.yaml
            secret_manager = SecretManager(key_path.parent)
            secret_manager.create_sops_config(public_key)

            console.print(f"[green]Created age key: {key_path}[/green]")
            console.print(f"[green]Created .sops.yaml with public key: {public_key}[/green]")
            console.print("\n[bold]Add to .env:[/bold]")
            console.print(f"SOPS_AGE_KEY_FILE={key_path}")
            return

    console.print("[red]Failed to extract public key[/red]")
    sys.exit(1)


@secrets.command("encrypt")
@click.argument("file", type=click.Path())
def secrets_encrypt(file: str) -> None:
    """Encrypt a file with SOPS."""
    try:
        import subprocess
        from pathlib import Path

        # Resolve path relative to config repo if set
        config_repo = os.getenv("INFRAFOUNDRY_CONFIG_REPO")
        if config_repo and not Path(file).is_absolute():
            file_path = Path(config_repo) / file
            config_dir = Path(config_repo)
        else:
            file_path = Path(file)
            config_dir = file_path.parent.parent if "secrets" in file_path.parts else Path.cwd()

        if not file_path.exists():
            console.print(f"[red]File not found: {file_path}[/red]")
            sys.exit(1)

        # Run sops from config directory so it finds .sops.yaml
        result = subprocess.run(
            ["sops", "--encrypt", "--in-place", str(file_path)],
            capture_output=True,
            text=True,
            cwd=str(config_dir),
        )

        if result.returncode != 0:
            console.print(f"[red]Encryption failed: {result.stderr}[/red]")
            sys.exit(1)

        console.print(f"[green]Encrypted: {file_path}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@secrets.command("decrypt")
@click.argument("file", type=click.Path())
def secrets_decrypt(file: str) -> None:
    """Decrypt and display a SOPS-encrypted file."""
    try:
        import subprocess
        from pathlib import Path

        # Resolve path relative to config repo if set
        config_repo = os.getenv("INFRAFOUNDRY_CONFIG_REPO")
        if config_repo and not Path(file).is_absolute():
            file_path = Path(config_repo) / file
        else:
            file_path = Path(file)

        if not file_path.exists():
            console.print(f"[red]File not found: {file_path}[/red]")
            sys.exit(1)

        result = subprocess.run(
            ["sops", "--decrypt", str(file_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            console.print(f"[red]Decryption failed: {result.stderr}[/red]")
            sys.exit(1)

        console.print(result.stdout)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
