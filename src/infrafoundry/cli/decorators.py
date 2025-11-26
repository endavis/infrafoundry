"""CLI decorators shared across commands."""

from __future__ import annotations

import inspect
import sys
import traceback
from collections.abc import Callable
from functools import wraps
from typing import Any

import click
from rich.console import Console

from infrafoundry.core.exceptions import (
    ConfigurationError,
    EnvironmentNotFoundError,
    InfraFoundryError,
)

from .utils import raise_cli_error

console = Console()


def with_orchestrator(
    action: str,
    *,
    require_env: bool = True,
    load_credentials: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Inject orchestrator + shared error handling into CLI commands.

    Args:
        action: Human-friendly description for error messages.
        require_env: Whether the command requires an --env option.
        load_credentials: Whether to load environment credentials automatically.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())
        # Skip ctx + orchestrator when mapping args -> parameter names
        command_param_names = param_names[2:]

        @click.pass_context
        @wraps(func)
        def wrapper(ctx: click.Context, *args: Any, **kwargs: Any) -> Any:
            config_dir = (ctx.obj or {}).get("config_dir")

            bound_params: dict[str, Any] = {}
            for name, value in zip(command_param_names, args, strict=False):
                bound_params[name] = value
            bound_params.update(kwargs)

            env_name = bound_params.get("env")
            if require_env and not env_name:
                raise click.ClickException("Environment (--env) is required for this command.")

            try:
                if load_credentials and env_name:
                    from .main import _load_env_credentials

                    _load_env_credentials(env_name, config_dir)

                from .main import _get_orchestrator

                orchestrator = _get_orchestrator(
                    config_dir,
                    (ctx.obj or {}).get("strict_config"),
                )
                return func(ctx, orchestrator, *args, **kwargs)
            except click.ClickException:
                # Already a Click exception, re-raise as-is
                raise
            except KeyboardInterrupt as exc:
                # User cancelled, convert to Click exception
                raise click.ClickException("Operation cancelled") from exc
            except (EnvironmentNotFoundError, ConfigurationError) as exc:
                # Configuration errors - show helpful message
                raise_cli_error(action, exc)
            except InfraFoundryError as exc:
                # Other InfraFoundry errors - show with context
                raise_cli_error(action, exc)
            except Exception as exc:
                console.print(f"[bold red]ERROR:[/bold red] {action} - {exc}")
                console.print(traceback.format_exc(), style="dim red")  # Log full traceback
                sys.exit(1)

        return wrapper

    return decorator
