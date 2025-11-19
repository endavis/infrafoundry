"""Manage encrypted secrets commands."""

import os
from pathlib import Path

import click
from rich.console import Console

from infrafoundry.core.secrets import SecretManager

from ..utils import raise_cli_error

console = Console()


@click.group()
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
        raise click.ClickException(f"Failed to generate key: {result.stderr}")

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

        console.print(f"[green]Encrypted: {file_path}[/green]")
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
    except Exception as exc:
        raise_cli_error("Decryption failed", exc)
