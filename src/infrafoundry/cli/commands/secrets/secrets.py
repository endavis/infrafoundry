"""Manage encrypted secrets commands."""

import os
import subprocess  # nosec B404  # runs age-keygen and sops with fixed argv
import sys
from pathlib import Path

import click

from infrafoundry.core import ssh_host_key_store as host_key_store
from infrafoundry.core.exceptions import InfraFoundryError, SecretError
from infrafoundry.core.jumphost_preflight import deployment_state
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.secrets import SecretManager
from infrafoundry.core.secrets.age_key_manager import create_sops_config

from ...decorators import with_orchestrator
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

    # Generate age key using subprocess with hardcoded command (not user input)
    result = subprocess.run(  # fixed age-keygen/sops argv, no shell
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

            # Create .sops.yaml (call directly - SecretManager requires SOPS_AGE_KEY_FILE)
            create_sops_config(key_path.parent, public_key)

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
        config_repo = os.getenv("INFRAFOUNDRY_CONFIG_REPO")
        if config_repo and not Path(file).is_absolute():
            file_path = Path(config_repo) / file
            config_dir = Path(config_repo)
        else:
            file_path = Path(file)
            config_dir = file_path.parent.parent if "secrets" in file_path.parts else Path.cwd()

        if not file_path.exists():
            raise click.ClickException(f"File not found: {file_path}")

        result = subprocess.run(  # fixed age-keygen/sops argv, no shell
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
        config_repo = os.getenv("INFRAFOUNDRY_CONFIG_REPO")
        if config_repo and not Path(file).is_absolute():
            file_path = Path(config_repo) / file
        else:
            file_path = Path(file)

        if not file_path.exists():
            raise click.ClickException(f"File not found: {file_path}")

        result = subprocess.run(  # fixed age-keygen/sops argv, no shell
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


def _host_key_candidates(
    resources: list[ResourceConfig], packages: tuple[str, ...]
) -> list[ResourceConfig]:
    """Return the VMs and OCI instances that set ``ssh_host_key``, limited to the named packages."""
    from infrafoundry.core.ssh_host_keys import HOST_KEY_FIELD

    wanted = set(packages)
    found: list[ResourceConfig] = []
    for resource in resources:
        if (
            resource.type not in ("vm", "instance")
            or (resource.config or {}).get(HOST_KEY_FIELD) is None
        ):
            continue
        if wanted and not ({resource.package_path, resource.package_name} & wanted):
            continue
        found.append(resource)
    return found


@secrets.command("host-keys")
@click.option("--env", "-e", required=True, help="Environment name (e.g., dev, prod)")
@click.option(
    "--package",
    "packages",
    multiple=True,
    help="Limit to a package (its path under the environment or its name). Repeatable.",
)
@click.option(
    "--regenerate",
    "regenerate",
    multiple=True,
    help=(
        "Replace the recorded key of a VM that is not deployed; for a VM pinned while "
        "deployed, run it after destroying the VM and before rebuilding it. Repeatable."
    ),
)
@click.option("--dry-run", is_flag=True, help="Show what would be done without changing anything")
@with_orchestrator("Host key setup failed")
def secrets_host_keys(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    packages: tuple[str, ...],
    regenerate: tuple[str, ...],
    dry_run: bool,
) -> None:
    """Pin SSH host keys for the VMs and OCI instances that blueprints build.

    For each VM or instance that sets ``ssh_host_key``, records a host key in its package's SOPS
    ``secrets.yaml`` under ``variables.ssh_host_keys.<name>``. A VM that is not deployed
    gets a generated key pair, which cloud-init installs at first boot. A VM that is
    already deployed is pinned: the key it presents now is recorded and the VM is not
    changed. A VM with a recorded key is skipped. Only fingerprints are printed.

    Run it once before the first apply, and once after upgrading a package that now sets
    ``ssh_host_key``.

    Examples:

        # Record keys for every package in dev
        foundry secrets host-keys --env dev

        # Show what would be done
        foundry secrets host-keys --env dev --dry-run

        # After destroying a pinned VM, replace its key before the rebuild
        foundry secrets host-keys --env dev --regenerate aiqum-01
    """
    config_manager = orchestrator.config_manager
    all_resources = config_manager.get_all_resources_all_providers(env)
    candidates = _host_key_candidates(all_resources, packages)
    unknown = sorted(set(regenerate) - {r.name for r in candidates})
    if unknown:
        raise click.ClickException(
            f"--regenerate names no VM or instance that sets ssh_host_key: {', '.join(unknown)}"
        )
    if not candidates:
        console.info("No VM or instance sets ssh_host_key; nothing to do.")
        return

    plan = host_key_store.plan_actions(
        candidates, deployment_state(orchestrator.state_manager, env), regenerate
    )
    failed = False
    for item in plan:
        resource = item.resource
        label = f"{resource.name} ({resource.package_path})"
        if item.action is host_key_store.HostKeyAction.SKIP:
            console.print(f"skipped   {label}: {item.reason}", markup=False)
            continue
        if item.action is host_key_store.HostKeyAction.REFUSE:
            console.print(f"refused   {label}: {item.reason}", markup=False)
            failed = True
            continue
        if dry_run:
            verb = "pin" if item.action is host_key_store.HostKeyAction.PIN else "generate"
            console.print(f"would {verb}   {label}", markup=False)
            continue
        try:
            path = config_manager.base_dir / env / str(resource.package_path) / "secrets.yaml"
            host_key_store.ensure_secrets_file(path, config_manager.base_dir.parent)
            outcome = _apply_host_key_action(item, path)
        except (SecretError, ValueError) as exc:
            console.print(f"failed    {label}: {exc}", markup=False)
            failed = True
            continue
        console.print(f"{outcome}   {label}", markup=False)
    if failed:
        sys.exit(1)


def _apply_host_key_action(item: host_key_store.PlannedAction, path: Path) -> str:
    """Record one VM's host key and return the line to print (a fingerprint, never a key)."""
    from infrafoundry.core.ssh_host_keys import host_key_config

    resource = item.resource
    if item.action is host_key_store.HostKeyAction.PIN:
        spec = host_key_config(resource)
        address = spec.address if spec else resource.name
        jumphost = str((resource.package_variables or {}).get("jumphost", "")).strip() or None
        public = host_key_store.scan_public_key(address, jumphost)
        host_key_store.write_entry(path, resource.name, {"ed25519_public": public})
        return f"pinned    {host_key_store.fingerprint(public)}"
    private, public = host_key_store.generate_keypair(resource.name)
    host_key_store.write_entry(
        path, resource.name, {"ed25519_private": private, "ed25519_public": public}
    )
    return f"generated {host_key_store.fingerprint(public)}"
