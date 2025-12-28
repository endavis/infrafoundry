"""Manage Terraform backend configuration and state management."""

import sys

import click

from infrafoundry.core.config import ConfigManager

from ...utils import console


def _create_backend_group() -> click.Group:
    """Create the backend command group."""

    @click.group()
    def backend() -> None:
        """Manage Terraform backend configuration (validate, migrate)."""

    return backend


# Create the backend group
_backend = _create_backend_group()


@_backend.command("validate")
@click.option("--env", "-e", required=True, help="Environment name")
@click.pass_context
def _backend_validate(ctx: click.Context, env: str) -> None:
    """Validate backend configuration for an environment.

    Checks backend configuration completeness, field requirements,
    and locking support. Does not test actual backend connectivity.

    Examples:

        # Validate backend configuration for prod environment
        infra backend validate --env prod

        # Validate dev environment backend
        infra backend validate -e dev
    """
    try:
        config_dir = (ctx.obj or {}).get("config_dir", ".")
        config_manager = ConfigManager(config_dir)

        console.print(f"[bold]Validating backend configuration for environment: {env}[/bold]\n")

        # Load environment configuration
        try:
            env_config = config_manager.load_environment(env)
        except FileNotFoundError:
            console.print(f"[red]✗[/red] Environment not found: {env}")
            sys.exit(1)

        # Check if backend is configured
        if not env_config.backend:
            console.print("[yellow]⚠[/yellow]  No backend configured (using local default)")
            console.print("\n[dim]Local backend does not support state locking.[/dim]")
            sys.exit(0)

        backend_config = env_config.backend

        console.print(f"[cyan]Backend Type:[/cyan] {backend_config.type.value}")

        # Validate backend configuration
        is_valid, error = backend_config.validate_backend()

        if not is_valid:
            console.print("\n[red]✗[/red] Backend configuration is invalid:")
            console.print(f"  [red]{error}[/red]")
            sys.exit(1)

        console.print("[green]✓[/green] Backend configuration is valid")

        # Display backend details
        backend_dict = backend_config.get_backend_config()
        console.print("\n[bold]Configuration:[/bold]")

        if backend_config.type.value == "s3":
            console.print(f"  Bucket: {backend_dict.get('bucket')}")
            console.print(f"  Key: {backend_dict.get('key')}")
            console.print(f"  Region: {backend_dict.get('region')}")
            console.print(f"  Encryption: {backend_dict.get('encrypt', True)}")
            if backend_dict.get("dynamodb_table"):
                console.print(f"  DynamoDB Table: {backend_dict.get('dynamodb_table')}")
            if backend_dict.get("kms_key_id"):
                console.print(f"  KMS Key: {backend_dict.get('kms_key_id')}")

        elif backend_config.type.value == "gcs":
            console.print(f"  Bucket: {backend_dict.get('bucket')}")
            console.print(f"  Prefix: {backend_dict.get('prefix')}")
            if backend_dict.get("credentials"):
                console.print(f"  Credentials: {backend_dict.get('credentials')}")

        elif backend_config.type.value == "azurerm":
            console.print(f"  Resource Group: {backend_dict.get('resource_group_name')}")
            console.print(f"  Storage Account: {backend_dict.get('storage_account_name')}")
            console.print(f"  Container: {backend_dict.get('container_name')}")
            console.print(f"  Key: {backend_dict.get('key')}")
            console.print(f"  Azure AD Auth: {backend_dict.get('use_azuread_auth', False)}")

        elif backend_config.type.value == "postgres":
            console.print(f"  Connection String: {backend_dict.get('conn_str')}")
            console.print(f"  Schema: {backend_dict.get('schema_name')}")

        elif backend_config.type.value == "remote":
            console.print(f"  Organization: {backend_dict.get('organization')}")
            workspaces = backend_dict.get("workspaces", {})
            if "name" in workspaces:
                console.print(f"  Workspace: {workspaces['name']}")
            elif "prefix" in workspaces:
                console.print(f"  Workspace Prefix: {workspaces['prefix']}")
            if backend_dict.get("hostname"):
                console.print(f"  Hostname: {backend_dict.get('hostname')}")

        # State locking information
        supports_locking = backend_config.supports_locking()
        console.print("\n[bold]State Locking:[/bold]")

        if supports_locking:
            console.print("  [green]✓[/green] Enabled")

            if backend_config.type.value == "s3":
                if backend_dict.get("dynamodb_table"):
                    console.print(
                        f"  [dim]Using DynamoDB table: {backend_dict['dynamodb_table']}[/dim]"
                    )
                else:
                    console.print(
                        "  [yellow]⚠[/yellow]  DynamoDB table not configured (locking disabled)"
                    )
            elif backend_config.type.value in {"gcs", "azurerm", "postgres", "remote"}:
                console.print("  [dim]Native backend locking support[/dim]")
        else:
            console.print("  [yellow]✗[/yellow] Not supported")
            console.print(
                "  [dim]State locking prevents concurrent modifications in team environments[/dim]"
            )

        # Recommendations
        if not supports_locking and backend_config.type.value != "local":
            console.print("\n[yellow]Recommendation:[/yellow]")
            if backend_config.type.value == "s3":
                console.print(
                    "  Add DynamoDB table configuration to enable state locking for S3 backend"
                )
            else:
                console.print(
                    "  Consider using a backend with locking support for team collaboration"
                )

        console.print("\n[green]✓[/green] Backend validation completed successfully")

    except Exception as e:
        console.print(f"[red]Error validating backend:[/red] {e}")
        sys.exit(1)


@_backend.command("migrate")
@click.option("--env", "-e", required=True, help="Environment name")
@click.option(
    "--from",
    "from_backend",
    type=click.Choice(["local", "s3", "gcs", "azurerm", "postgres", "remote"]),
    help="Source backend type (optional, will detect from current state)",
)
@click.option(
    "--to",
    "to_backend",
    type=click.Choice(["local", "s3", "gcs", "azurerm", "postgres", "remote"]),
    help="Target backend type (optional, will use configured backend)",
)
@click.option(
    "--auto-approve",
    is_flag=True,
    help="Skip confirmation prompt and migrate automatically",
)
@click.pass_context
def _backend_migrate(
    ctx: click.Context,
    env: str,
    from_backend: str | None,
    to_backend: str | None,
    auto_approve: bool,
) -> None:
    """Migrate Terraform state between backends.

    Migrates state from one backend to another. The migration process:

    1. Reads current backend configuration
    2. Updates backend.tf with new configuration
    3. Runs 'terraform init -migrate-state' to transfer state
    4. Verifies migration succeeded

    Examples:

        # Migrate from local to configured remote backend
        infra backend migrate --env prod

        # Migrate explicitly from local to S3
        infra backend migrate --env prod --from local --to s3

        # Auto-approve migration without confirmation
        infra backend migrate --env prod --auto-approve
    """
    console.print(
        "[yellow]Note:[/yellow] Backend migration is not yet implemented.\n"
        "This feature will be added in a future release.\n\n"
        "For now, you can manually migrate by:\n"
        "1. Updating backend configuration in settings.yaml\n"
        "2. Running: infra plan --env <env> (generates backend.tf)\n"
        "3. Running: cd generated/<env>/terraform/<provider> && terraform init -migrate-state"
    )
    sys.exit(1)


def register_commands(main_group: click.Group) -> None:
    """Register backend command group with main CLI."""
    main_group.add_command(_backend, name="backend")
