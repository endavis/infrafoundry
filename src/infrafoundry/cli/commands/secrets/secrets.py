"""Manage encrypted secrets commands."""

import os
from pathlib import Path

import click

from infrafoundry.core.exceptions import InfraFoundryError, SecretError
from infrafoundry.core.secrets import SecretManager

from ...utils import console, raise_cli_error


@click.group()
def secrets() -> None:
    """Manage encrypted secrets."""
    pass


@secrets.command("init")
@click.option(
    "--key-file",
    default=None,
    help="Path to age key file (defaults to envs/age.key in config repo)",
)
@click.pass_context
def secrets_init(ctx: click.Context, key_file: str | None) -> None:
    """Initialize secrets with a new age key."""
    if key_file:
        key_path = Path(key_file)
    else:
        ctx_config_dir = ctx.obj.get("config_dir") if ctx and ctx.obj else None
        base_dir = Path(ctx_config_dir) if ctx_config_dir else None
        if not base_dir:
            config_repo = os.getenv("INFRAFOUNDRY_CONFIG_REPO")
            base_dir = Path(config_repo) if config_repo else Path.cwd()

        key_path = base_dir / "envs" / "age.key"

    if key_path.exists():
        console.warning(f"Key file already exists: {key_path}")
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
        raise click.ClickException(f"Failed to generate key: {result.stderr}")

    # Extract public key from output
    for line in result.stderr.split("\n"):
        if line.startswith("# public key:"):
            public_key = line.split(": ")[1]

            # Create .sops.yaml
            secret_manager = SecretManager(str(key_path.parent))
            secret_manager.create_sops_config(public_key)

            console.success(f"Created age key: {key_path}")
            console.success(f"Created .sops.yaml with public key: {public_key}")
            console.info("Add to .env:")
            console.info(f"SOPS_AGE_KEY_FILE={key_path}")
            return

    raise click.ClickException("Failed to extract age public key from age-keygen output")


@secrets.command("encrypt")
@click.argument("file", type=click.Path())
def secrets_encrypt(file: str) -> None:
    """Encrypt a file with SOPS."""
    try:
        import subprocess

        config_repo = os.getenv("INFRAFOUNDRY_CONFIG_REPO")
        if config_repo and not Path(file).is_absolute():
            file_path = Path(config_repo) / file
            config_dir = Path(config_repo)
        else:
            file_path = Path(file)
            config_dir = file_path.parent.parent if "secrets" in file_path.parts else Path.cwd()

        if not file_path.exists():
            raise click.ClickException(f"File not found: {file_path}")

        result = subprocess.run(
            ["sops", "--encrypt", "--in-place", str(file_path)],
            capture_output=True,
            text=True,
            cwd=str(config_dir),
        )

        if result.returncode != 0:
            raise click.ClickException(f"Encryption failed: {result.stderr}")

        console.success(f"Encrypted: {file_path}")
    except click.ClickException:
        raise
    except SecretError as exc:
        raise_cli_error("Encryption failed", exc)
    except InfraFoundryError as exc:
        raise_cli_error("Encryption failed", exc)
    except Exception as exc:
        raise_cli_error("Encryption failed", exc)


@secrets.command("decrypt")
@click.argument("file", type=click.Path())
def secrets_decrypt(file: str) -> None:
    """Decrypt and display a SOPS-encrypted file."""
    try:
        import subprocess

        config_repo = os.getenv("INFRAFOUNDRY_CONFIG_REPO")
        if config_repo and not Path(file).is_absolute():
            file_path = Path(config_repo) / file
        else:
            file_path = Path(file)

        if not file_path.exists():
            raise click.ClickException(f"File not found: {file_path}")

        result = subprocess.run(
            ["sops", "--decrypt", str(file_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise click.ClickException(f"Decryption failed: {result.stderr}")

        console.print(result.stdout)
    except click.ClickException:
        raise
    except SecretError as exc:
        raise_cli_error("Decryption failed", exc)
    except InfraFoundryError as exc:
        raise_cli_error("Decryption failed", exc)
    except Exception as exc:
        raise_cli_error("Decryption failed", exc)


@secrets.command("rotate")
@click.option(
    "--env",
    "-e",
    required=True,
    help="Environment name (e.g., dev, prod)",
)
@click.option(
    "--new-key-file",
    type=click.Path(exists=True, path_type=Path),
    help="Path to new age key file (alternative to --generate-new-key)",
)
@click.option(
    "--generate-new-key",
    is_flag=True,
    help="Generate a new age key automatically",
)
@click.option(
    "--files",
    multiple=True,
    help=(
        "Specific file patterns to rotate (e.g., 'secrets.yaml'). Can be specified multiple times."
    ),
)
@click.option(
    "--no-verify",
    is_flag=True,
    help="Skip verification after re-encryption (not recommended)",
)
@click.option(
    "--no-backup",
    is_flag=True,
    help="Don't keep backup after successful rotation (not recommended)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be rotated without actually rotating",
)
@click.pass_context
def secrets_rotate(
    ctx: click.Context,
    env: str,
    new_key_file: Path | None,
    generate_new_key: bool,
    files: tuple[str, ...],
    no_verify: bool,
    no_backup: bool,
    dry_run: bool,
) -> None:
    """Rotate secrets with a new age encryption key.

    Re-encrypts all secrets (or specific files) with a new age key. This is useful
    when rotating encryption keys for security compliance or after key compromise.

    The rotation process:
    1. Creates a backup of all encrypted files
    2. Generates a new age key (or uses provided key)
    3. Decrypts all secrets with the old key
    4. Updates .sops.yaml with the new public key
    5. Re-encrypts all secrets with the new key
    6. Verifies decryption works with new key
    7. Keeps backup (unless --no-backup specified)

    On failure, automatically rolls back to the backup.

    Examples:

        # Generate new key and rotate all secrets for dev environment
        infra secrets rotate --env dev --generate-new-key

        # Rotate with an existing new key file
        infra secrets rotate --env prod --new-key-file /path/to/new_age.key

        # Rotate specific files only
        infra secrets rotate --env dev --generate-new-key --files proxmox.yaml --files opnsense.yaml

        # Dry run to see what would be rotated
        infra secrets rotate --env dev --generate-new-key --dry-run

    IMPORTANT: After rotation, you must:
    1. Update SOPS_AGE_KEY_FILE to point to the new key
    2. Securely delete or archive the old key
    3. Distribute the new key to team members (if applicable)
    """
    try:
        if not generate_new_key and not new_key_file:
            raise click.ClickException("Must specify either --new-key-file or --generate-new-key")

        if generate_new_key and new_key_file:
            raise click.ClickException("Cannot specify both --new-key-file and --generate-new-key")

        # Get config directory
        config_dir = (ctx.obj or {}).get("config_dir")
        if not config_dir:
            config_repo = os.getenv("INFRAFOUNDRY_CONFIG_REPO")
            config_dir = Path(config_repo) if config_repo else Path.cwd()
        else:
            config_dir = Path(config_dir)

        secrets_dir = config_dir / "envs" / env

        if not secrets_dir.exists():
            raise click.ClickException(f"Environment directory not found: {secrets_dir}")

        console.print(f"\n[bold]Rotating secrets for environment: {env}[/bold]\n")
        console.print(f"[cyan]Secrets directory:[/cyan] {secrets_dir}")

        # Initialize secret manager
        secret_manager = SecretManager(env_name=env, secrets_dir=secrets_dir)

        # Dry run mode
        if dry_run:
            console.print("\n[yellow]DRY RUN MODE - No changes will be made[/yellow]\n")

            file_patterns = list(files) if files else None
            from infrafoundry.core.secrets.rotation import SecretsRotator

            rotator = SecretsRotator(secrets_dir=secrets_dir)
            encrypted_files = rotator.get_encrypted_files(file_patterns)

            console.print("[cyan]Files that would be rotated:[/cyan]")
            for f in encrypted_files:
                console.print(f"  • {f.name}")

            console.print(f"\n[cyan]Total files:[/cyan] {len(encrypted_files)}")

            if generate_new_key:
                console.print("\n[cyan]Action:[/cyan] Generate new age key")
            else:
                console.print(f"\n[cyan]Action:[/cyan] Use key from {new_key_file}")

            console.print("\n[yellow]Run without --dry-run to perform rotation[/yellow]")
            return

        # Perform rotation
        console.print("\n[bold]Starting rotation...[/bold]")

        result = secret_manager.rotate_secrets(
            new_key_file=new_key_file,
            generate_new_key=generate_new_key,
            file_patterns=list(files) if files else None,
            verify=not no_verify,
            keep_backup=not no_backup,
        )

        if result["success"]:
            console.print("\n[green]✓[/green] Secrets rotation completed successfully!\n")

            console.print("[cyan]Files rotated:[/cyan]")
            for filename in result["files_rotated"]:
                console.print(f"  • {filename}")

            console.print(f"\n[cyan]New public key:[/cyan] {result['new_public_key']}")

            if result.get("backup_path"):
                console.print(f"[cyan]Backup location:[/cyan] {result['backup_path']}")

            console.print("\n[bold yellow]IMPORTANT NEXT STEPS:[/bold yellow]")
            console.print("1. Update SOPS_AGE_KEY_FILE environment variable to point to new key")
            console.print("2. Test decryption with new key:")
            console.print(f"   export SOPS_AGE_KEY_FILE={secrets_dir}/age.key.new")
            console.print(f"   infra secrets decrypt envs/{env}/secrets.yaml")
            console.print("3. Securely delete or archive the old key")
            console.print("4. Distribute new key to team members (if applicable)")

            if generate_new_key:
                new_key_path = secrets_dir / "age.key.new"
                console.print(f"\n[cyan]New key saved to:[/cyan] {new_key_path}")
                console.print(
                    "[yellow]Rename to 'age.key' after testing:[/yellow] "
                    f"mv {new_key_path} {secrets_dir}/age.key"
                )

        else:
            console.print("\n[red]✗[/red] Secrets rotation failed\n")
            if result.get("errors"):
                for error in result["errors"]:
                    console.print(f"[red]Error:[/red] {error}")

    except click.ClickException:
        raise
    except SecretError as exc:
        raise_cli_error("Rotation failed", exc)
    except InfraFoundryError as exc:
        raise_cli_error("Rotation failed", exc)
    except Exception as exc:
        raise_cli_error("Rotation failed", exc)
