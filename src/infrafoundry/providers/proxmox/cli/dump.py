"""Dump raw Proxmox cluster API state to JSON."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import click

from infrafoundry.cli.utils import console, raise_cli_error
from infrafoundry.core.config import ConfigManager
from infrafoundry.core.types import EnvironmentData
from infrafoundry.providers.proxmox.dumper import ProxmoxStateDumper


@click.command(name="dump")
@click.option("--env", "-e", required=True, help="Environment name to use for credentials")
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, file_okay=True, path_type=Path),
    required=True,
    help="Output JSON file (directory created if missing; existing file replaced atomically)",
)
@click.option(
    "--timeout",
    type=int,
    default=20,
    show_default=True,
    help="Per-request timeout in seconds (failed calls are captured inline)",
)
@click.pass_context
def dump(ctx: click.Context, env: str, output: Path, timeout: int) -> None:
    """Dump raw Proxmox cluster API state as a JSON snapshot.

    Walks a curated set of Proxmox Virtual Environment API endpoints
    (cluster, access, pools, storage, all nodes, all VMs/containers) and
    writes the unwrapped ``data`` payloads, grouped by section, to
    ``--output``. The file is updated atomically after each section, so
    an interrupted dump still yields a usable partial result.
    """
    try:
        config_repo = ctx.obj.get("config_dir")
        config_manager = ConfigManager(base_dir=config_repo / "envs" if config_repo else None)
        env_config = cast(EnvironmentData, config_manager.load_environment(env).model_dump())

        dumper = ProxmoxStateDumper(env_config, timeout=timeout)
        result = dumper.dump(output)

        console.success(f"Dumped {len(result)} sections to {output}")
    except click.ClickException:
        raise
    except Exception as exc:
        raise_cli_error("Failed to dump Proxmox state", exc)
