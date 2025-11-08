"""Command-line interface for InfraFoundry."""

import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

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
    # Use --config-dir flag if provided, otherwise check environment variable
    if config_dir:
        ctx.obj["config_dir"] = config_dir
    elif config_repo := os.getenv("INFRAFOUNDRY_CONFIG_REPO"):
        ctx.obj["config_dir"] = Path(config_repo)
    else:
        ctx.obj["config_dir"] = None


@main.command()
def init() -> None:
    """Initialize InfraFoundry state database."""
    from infrafoundry.core.state import StateManager

    try:
        console.print("[cyan]Initializing InfraFoundry state database...[/cyan]")

        # Get state backend configuration
        state_backend = os.getenv("INFRAFOUNDRY_STATE_BACKEND", "sqlite")
        connection_string = os.getenv("INFRAFOUNDRY_STATE_CONNECTION")

        if state_backend == "sqlite" and not connection_string:
            state_dir = Path.home() / ".infrafoundry"
            state_dir.mkdir(parents=True, exist_ok=True)
            db_path = state_dir / "state.db"
            console.print(f"[dim]Using SQLite database at: {db_path}[/dim]")

        state_manager = StateManager(connection_string)
        state_manager.initialize()

        console.print("[bold green]✓ State database initialized successfully![/bold green]")

        if state_backend == "sqlite":
            console.print(f"\n[dim]Database location: {db_path}[/dim]")

        console.print("\n[bold]State tracking is now enabled.[/bold]")
        console.print("Deployment history and resource state will be recorded.")

    except Exception as e:
        console.print(f"[bold red]Error initializing state database:[/bold red] {e}")
        sys.exit(1)


@main.command()
@click.option("--env", "-e", help="Filter by environment")
@click.option(
    "--command",
    "-c",
    type=click.Choice(["plan", "apply", "destroy"]),
    help="Filter by command type",
)
@click.option(
    "--status",
    "-s",
    type=click.Choice(["completed", "failed", "in_progress", "planned"]),
    help="Filter by status",
)
@click.option("--limit", "-n", default=50, help="Number of deployments to show")
@click.option("--exclude-dry-runs", is_flag=True, help="Exclude dry-run deployments from history")
def history(
    env: str | None,
    command: str | None,
    status: str | None,
    limit: int,
    exclude_dry_runs: bool,
) -> None:
    """Show deployment history."""
    from rich.table import Table

    from infrafoundry.core.state import DeploymentStatus, StateManager

    try:
        state_manager = StateManager()

        # Convert status string to enum if provided
        status_enum = None
        if status:
            status_enum = DeploymentStatus(status)

        deployments = state_manager.get_deployment_history(
            environment=env,
            command=command,
            status=status_enum,
            limit=limit,
            exclude_dry_run=exclude_dry_runs,
        )

        if not deployments:
            console.print("[yellow]No deployment history found.[/yellow]")
            console.print("\n[dim]Run 'infra init' to initialize state tracking.[/dim]")
            return

        table = Table(title="Deployment History")
        table.add_column("ID", style="cyan")
        table.add_column("Environment", style="green")
        table.add_column("Command", style="blue")
        table.add_column("Status", style="magenta")
        table.add_column("Dry Run", style="yellow")
        table.add_column("Started", style="dim")
        table.add_column("User", style="yellow")

        for deployment in deployments:
            # Get status value (handle both enum and string)
            status_str = (
                deployment.status.value
                if hasattr(deployment.status, "value")
                else str(deployment.status)
            )

            status_color = {
                "completed": "green",
                "failed": "red",
                "in_progress": "yellow",
                "planned": "cyan",
            }.get(status_str, "white")

            # Format dry_run indicator
            dry_run_indicator = "✓" if deployment.dry_run else ""

            table.add_row(
                str(deployment.id),
                deployment.environment,
                deployment.command,
                f"[{status_color}]{status_str}[/{status_color}]",
                dry_run_indicator,
                (
                    deployment.started_at.strftime("%Y-%m-%d %H:%M:%S")
                    if deployment.started_at
                    else ""
                ),
                deployment.user or "unknown",
            )

        console.print(table)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        if "no such table" in str(e).lower():
            console.print("\n[dim]Run 'infra init' to initialize state tracking.[/dim]")
        sys.exit(1)


@main.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--resource", "-r", required=True, help="Resource name to analyze")
def impact(env: str, resource: str) -> None:
    """Analyze the impact of changes to a resource.

    Shows what other resources depend on the specified resource and the risk level
    of making changes to it.
    """
    from rich.panel import Panel

    orchestrator = _get_orchestrator()

    try:
        # Build dependency graph for the environment
        console.print(f"[dim]Analyzing dependencies for {resource} in {env}...[/dim]\n")
        graph = orchestrator.build_dependency_graph(env)

        # Get impact analysis
        analysis = graph.get_impact_analysis(f"proxmox:{resource}")

        if not analysis or "error" in analysis:
            console.print(
                f"[yellow]Resource '{resource}' not found in environment '{env}'[/yellow]"
            )
            console.print("\n[dim]Available resources:[/dim]")
            for node_name in graph.nodes.keys():
                console.print(f"  - {node_name}")
            return

        # Display results
        console.print(
            Panel(
                f"[bold]Impact Analysis for: {resource}[/bold]",
                style="cyan",
            )
        )

        console.print("\n[bold]Risk Level:[/bold] ", end="")
        risk_color = {
            "LOW": "green",
            "MEDIUM": "yellow",
            "HIGH": "orange1",
            "CRITICAL": "red",
        }.get(analysis["risk_level"], "white")
        console.print(f"[{risk_color}]{analysis['risk_level']}[/{risk_color}]")

        console.print(f"[bold]Direct Dependents:[/bold] {analysis['direct_dependents']}")
        console.print(f"[bold]Total Affected:[/bold] {analysis['total_dependents']}")

        if analysis.get("dependent_resources"):
            console.print("\n[bold]Dependent Resources:[/bold]")
            for dep in analysis["dependent_resources"]:
                console.print(f"  ↳ {dep}")

        console.print("\n[bold]Impact:[/bold]")
        if analysis["total_dependents"] == 0:
            console.print("  [green]✓ No other resources depend on this[/green]")
            console.print("  [green]  Safe to modify or delete[/green]")
        elif analysis["risk_level"] == "LOW":
            console.print(
                f"  [green]✓ {analysis['direct_dependents']} resource(s) depend on this[/green]"
            )
            console.print("  [green]  Low risk - safe to change[/green]")
        elif analysis["risk_level"] == "MEDIUM":
            console.print(
                f"  [yellow]⚠ {analysis['total_dependents']} resource(s) may be affected[/yellow]"
            )
            console.print("  [yellow]  Medium risk - review dependencies before changes[/yellow]")
        elif analysis["risk_level"] == "HIGH":
            console.print(
                f"  [red]⚠ {analysis['total_dependents']} resource(s) will be affected[/red]"
            )
            console.print("  [red]  High risk - plan changes carefully[/red]")
        else:  # CRITICAL
            console.print(
                f"  [bold red]⛔ {analysis['total_dependents']} resource(s) "
                "will be affected[/bold red]"
            )
            console.print(
                "  [bold red]  Critical risk - changes may cause " "widespread impact[/bold red]"
            )

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@main.command()
@click.option("--env", "-e", required=True, help="Environment name")
def drift(env: str) -> None:
    """Detect infrastructure drift from declared configuration.

    Checks if actual infrastructure state matches the declared configuration
    by running terraform plan and identifying any unexpected changes.
    """
    from rich.panel import Panel
    from rich.table import Table

    orchestrator = _get_orchestrator()

    try:
        # Run drift detection
        results = orchestrator.detect_drift(env)

        # Display detailed results
        console.print("\n")
        console.print(Panel("[bold]Drift Detection Results[/bold]", style="cyan"))

        total_drift = False
        for provider_name, drift_info in results.items():
            if drift_info.get("has_changes"):
                total_drift = True

                table = Table(title=f"{provider_name.title()} Drift")
                table.add_column("Change Type", style="cyan")
                table.add_column("Count", style="yellow")

                if drift_info.get("to_add", 0) > 0:
                    table.add_row("To Add", str(drift_info["to_add"]))
                if drift_info.get("to_change", 0) > 0:
                    table.add_row("To Change", str(drift_info["to_change"]))
                if drift_info.get("to_destroy", 0) > 0:
                    table.add_row("To Destroy", str(drift_info["to_destroy"]))

                console.print(table)

                console.print(f"\n[yellow]Summary:[/yellow] {drift_info['summary']}")

        if not total_drift:
            console.print(
                "\n[bold green]✓ No drift detected - infrastructure matches configuration[/bold green]"
            )
        else:
            console.print("\n[bold yellow]⚠ Drift detected![/bold yellow]")
            console.print(
                "[dim]Run 'infra plan' to see detailed changes, or 'infra apply' to reconcile.[/dim]"
            )

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@main.command()
@click.option("--env", "-e", help="Show policies for specific environment")
@click.pass_context
def policies(ctx: click.Context, env: str | None) -> None:
    """List available infrastructure policies."""
    try:
        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))

        if env:
            policies_list = orchestrator.policy_engine.get_policies_for_environment(env)
            console.print(f"\n[bold]Policies for {env}:[/bold]")
        else:
            policies_list = orchestrator.policy_engine.policies
            console.print("\n[bold]All Policies:[/bold]")

        if not policies_list:
            console.print("[yellow]No policies found.[/yellow]")
            console.print(
                "[dim]Create policy files in the 'policies' directory.[/dim]"
            )
            return

        # Display policies in a table
        table = Table(show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="blue")
        table.add_column("Level", style="yellow")
        table.add_column("Enabled", style="green")
        table.add_column("Environments", style="magenta")
        table.add_column("Description", style="dim")

        for policy in policies_list:
            level_color = {
                "error": "red",
                "warning": "yellow",
                "info": "blue",
            }.get(policy.level.value, "white")

            table.add_row(
                policy.name,
                policy.type.value,
                f"[{level_color}]{policy.level.value}[/{level_color}]",
                "✓" if policy.enabled else "✗",
                ", ".join(policy.environments) if policy.environments else "all",
                policy.description,
            )

        console.print(table)
        console.print(f"\n[dim]Total: {len(policies_list)} policy/policies[/dim]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback

        console.print(traceback.format_exc())
        sys.exit(1)


@main.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--limit", "-l", default=10, help="Maximum number of rollback points to show")
@click.pass_context
def rollback_points(ctx: click.Context, env: str, limit: int) -> None:
    """List available rollback points for an environment."""
    try:
        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))

        # Get rollback points
        deployments = orchestrator.state_manager.get_rollback_points(env, limit=limit)

        if not deployments:
            console.print(f"\n[yellow]No rollback points found for {env}.[/yellow]")
            console.print(
                "[dim]Rollback points are created from successful apply operations.[/dim]"
            )
            return

        # Display rollback points in a table
        table = Table(title=f"Rollback Points for {env}", show_header=True)
        table.add_column("ID", style="cyan")
        table.add_column("Date", style="green")
        table.add_column("User", style="blue")
        table.add_column("Resources", style="yellow")
        table.add_column("Commit", style="dim")

        for deployment in deployments:
            resource_count = len(deployment.rollback_data.get("resources", []))
            table.add_row(
                str(deployment.id),
                deployment.completed_at.strftime("%Y-%m-%d %H:%M:%S"),
                deployment.user or "unknown",
                str(resource_count),
                deployment.commit_sha or "N/A",
            )

        console.print()
        console.print(table)
        console.print(
            f"\n[dim]Use 'infra rollback --deployment-id <ID>' to rollback to a specific point[/dim]"
        )

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback

        console.print(traceback.format_exc())
        sys.exit(1)


@main.command()
@click.option("--deployment-id", "-d", required=True, type=int, help="Deployment ID to rollback to")
@click.option(
    "--auto-approve",
    is_flag=True,
    help="Skip confirmation prompt and apply immediately",
)
@click.pass_context
def rollback(ctx: click.Context, deployment_id: int, auto_approve: bool) -> None:
    """Rollback infrastructure to a previous deployment state."""
    try:
        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))

        # Perform rollback
        orchestrator.rollback(deployment_id=deployment_id, auto_approve=auto_approve)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback

        console.print(traceback.format_exc())
        sys.exit(1)


@main.command()
@click.option("--env", "-e", help="Filter by environment name")
@click.option("--provider", "-p", help="Filter by provider (proxmox, opnsense, kubernetes)")
@click.option(
    "--type",
    "-t",
    help="Filter by resource type (vm, deployment, firewall_rule, etc.)",
)
@click.option(
    "--state",
    "-s",
    help="Filter by state (PLANNED, CREATING, ACTIVE, DELETING, DELETED, FAILED)",
)
@click.pass_context
def resources(
    ctx: click.Context,
    env: str | None,
    provider: str | None,
    type: str | None,
    state: str | None,
) -> None:
    """List tracked infrastructure resources."""
    try:
        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))

        # Parse state filter
        resource_state = None
        if state:
            from infrafoundry.core.state import ResourceState

            try:
                resource_state = ResourceState[state.upper()]
            except KeyError:
                console.print(f"[bold red]Invalid state:[/bold red] {state}")
                console.print("Valid states: PLANNED, CREATING, ACTIVE, DELETING, DELETED, FAILED")
                sys.exit(1)

        # Get resources
        resources_list = orchestrator.state_manager.get_resources(
            environment=env,
            provider=provider,
            resource_type=type,
            state=resource_state,
        )

        if not resources_list:
            console.print("\n[yellow]No resources found matching filters.[/yellow]")
            return

        # Display resources in a table
        table = Table(title="Infrastructure Resources", show_header=True)
        table.add_column("Environment", style="cyan")
        table.add_column("Provider", style="magenta")
        table.add_column("Type", style="blue")
        table.add_column("Name", style="green")
        table.add_column("State", style="yellow")
        table.add_column("Terraform ID", style="dim")
        table.add_column("Last Updated", style="dim")

        for resource in resources_list:
            # Color code state
            state_colors = {
                "PLANNED": "blue",
                "CREATING": "yellow",
                "ACTIVE": "green",
                "DELETING": "orange",
                "DELETED": "red",
                "FAILED": "bold red",
            }
            state_color = state_colors.get(resource.state.name, "white")
            state_text = f"[{state_color}]{resource.state.name}[/{state_color}]"

            table.add_row(
                resource.environment,
                resource.provider,
                resource.resource_type,
                resource.name,
                state_text,
                resource.terraform_id or "[dim]N/A[/dim]",
                resource.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            )

        console.print()
        console.print(table)
        console.print(f"\n[dim]Total: {len(resources_list)} resource(s)[/dim]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback

        console.print(traceback.format_exc())
        sys.exit(1)


@main.command()
@click.option("--env", "-e", required=True, help="Environment name (e.g., dev, prod)")
@click.option("--dry-run", is_flag=True, help="Show what would be done without doing it")
@click.option(
    "--resource",
    "-r",
    multiple=True,
    help="Specific resource name(s) to target (can be used multiple times)",
)
@click.option(
    "--enforce-policies",
    is_flag=True,
    help="Enforce policy checks (block on violations)",
)
@click.pass_context
def plan(
    ctx: click.Context,
    env: str,
    dry_run: bool,
    resource: tuple[str, ...],
    enforce_policies: bool,
) -> None:
    """Plan infrastructure changes."""
    try:
        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))
        orchestrator.plan(
            env,
            dry_run=dry_run,
            resource_filter=list(resource) if resource else None,
            enforce_policies=enforce_policies,
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
@click.option(
    "--parallel",
    is_flag=True,
    help="Apply providers in parallel (experimental)",
)
@click.option(
    "--max-workers",
    type=int,
    default=4,
    help="Maximum number of parallel workers (default: 4)",
)
@click.pass_context
def apply(
    ctx: click.Context,
    env: str,
    auto_approve: bool,
    resource: tuple[str, ...],
    parallel: bool,
    max_workers: int,
) -> None:
    """Apply infrastructure changes."""
    try:
        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))
        orchestrator.apply(
            env,
            auto_approve=auto_approve,
            resource_filter=list(resource) if resource else None,
            parallel=parallel,
            max_workers=max_workers,
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

        # Sort all resources by name
        all_resources.sort(key=lambda r: r.name)

        # Display each resource on a single line
        for resource in all_resources:
            console.print(
                f"  • {resource.name:<40} [bold]{resource.provider:<12}[/bold] "
                f"[dim]({resource.type})[/dim]"
            )

        console.print(f"\n[dim]Total: {len(all_resources)} resources[/dim]")

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
