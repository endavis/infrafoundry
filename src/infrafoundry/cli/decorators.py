"""CLI decorators shared across commands."""

from __future__ import annotations

import inspect
import os
import sys
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


def _is_debug_mode() -> bool:
    """Check if debug mode is enabled."""
    return os.getenv("INFRAFOUNDRY_LOG_LEVEL") == "DEBUG"


def _get_error_hint(exc: Exception) -> str | None:
    """Get a helpful hint for common errors.

    Args:
        exc: The exception to analyze

    Returns:
        A hint string, or None if no hint is available
    """
    exc_str = str(exc).lower()

    if isinstance(exc, FileNotFoundError):
        if "generated" in exc_str or "terraform" in exc_str:
            return "Make sure you're running from the project root directory."
        if "kubeconfig" in exc_str or ".kube" in exc_str:
            return "Check that your kubeconfig file exists and is readable."
        return "Check that the file path is correct and the file exists."

    if isinstance(exc, PermissionError):
        return "Check file permissions or try running with appropriate access."

    if isinstance(exc, ConnectionError | OSError) and "connection" in exc_str:
        return "Check your network connection and that the service is reachable."

    if "timeout" in exc_str:
        return "The operation timed out. Try again or increase the timeout."

    if "authentication" in exc_str or "unauthorized" in exc_str:
        return "Check your credentials and authentication settings."

    return None


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
                # Show user-friendly error message
                console.print(f"[bold red]Error:[/bold red] {action}")
                console.print(f"  {exc}")

                # Show hint if available
                if hint := _get_error_hint(exc):
                    console.print(f"\n[yellow]Hint:[/yellow] {hint}")

                # Show traceback only in debug mode
                if _is_debug_mode():
                    console.print("\n[dim]Debug traceback:[/dim]")
                    console.print_exception(show_locals=False)
                else:
                    console.print("\n[dim]Use --debug for full error details.[/dim]")

                sys.exit(1)

        return wrapper

    return decorator
