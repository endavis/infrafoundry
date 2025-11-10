"""Validate infrastructure configuration command."""

import sys

import click
from rich.console import Console

console = Console()


@click.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.option(
    "--check-api",
    is_flag=True,
    default=False,
    help="Check API connectivity to providers",
)
@click.option(
    "--check-refs",
    is_flag=True,
    default=False,
    help="Validate resource references (templates, networks, etc.)",
)
@click.pass_context
def validate(ctx: click.Context, env: str, check_api: bool, check_refs: bool) -> None:
    """Validate infrastructure configuration before deployment.

    Performs pre-flight checks including:
    - YAML syntax validation
    - Resource type support
    - Configuration completeness
    - API connectivity (with --check-api)
    - Resource reference validation (with --check-refs)
    """
    try:
        from collections import defaultdict

        from infrafoundry.core.validation import ValidationReport

        # Import helper functions from main module
        from ..main import _get_orchestrator, _load_env_credentials

        # Load environment-specific credentials
        _load_env_credentials(env, ctx.obj.get("config_dir"))

        console.print(f"\n[bold]Validating environment:[/bold] {env}")

        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))

        # Load environment config
        env_config_dict = orchestrator.config.load_environment(env)
        console.print("[green]✓[/green] Loaded environment configuration")

        # Load resources
        resources = orchestrator.config.get_all_resources_all_providers(env)
        console.print(f"[green]✓[/green] Found {len(resources)} resource(s)")

        # Validate resources have supported providers
        try:
            orchestrator.validate_resources(resources)
            console.print("[green]✓[/green] All resources have registered providers")
        except ValueError as e:
            console.print(f"[red]✗[/red] {e}")
            sys.exit(1)

        # Create validation report
        report = ValidationReport()

        # Group resources by provider
        resources_by_provider: dict[str, list] = defaultdict(list)
        for resource in resources:
            resources_by_provider[resource.provider].append(resource)

        # Run provider-specific validations
        for provider_name, provider_resources in resources_by_provider.items():
            provider = orchestrator.providers.get(provider_name)
            if not provider:
                continue

            console.print(
                f"\n[bold cyan]Validating {provider_name}:[/bold cyan] "
                f"{len(provider_resources)} resource(s)"
            )

            # API connectivity check
            if check_api:
                console.print("  Checking API connectivity...")
                provider.validate_connectivity(env_config_dict.model_dump(), report)

            # Reference validation
            if check_refs:
                console.print("  Validating resource references...")
                provider.validate_references(
                    provider_resources, env_config_dict.model_dump(), report
                )

        # Display results
        console.print(report)

        # Exit with error if validation failed
        if report.has_errors():
            console.print("\n[bold red]❌ Validation failed with errors[/bold red]")
            sys.exit(1)
        elif report.has_warnings():
            console.print("\n[bold yellow]⚠️  Validation passed with warnings[/bold yellow]")
        else:
            console.print("\n[bold green]✅ Validation passed successfully[/bold green]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback

        console.print(traceback.format_exc())
        sys.exit(1)
