"""Shell completion commands for bash, zsh, and fish."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

from ..utils import console

# Shell completion script templates
# These use Click's built-in completion mechanism
BASH_SCRIPT = """\
# InfraFoundry bash completion
# Add this to ~/.bashrc or ~/.bash_completion

eval "$(_FOUNDRY_COMPLETE=bash_source foundry)"
"""

ZSH_SCRIPT = """\
# InfraFoundry zsh completion
# Add this to ~/.zshrc

eval "$(_FOUNDRY_COMPLETE=zsh_source foundry)"
"""

FISH_SCRIPT = """\
# InfraFoundry fish completion
# Add this to ~/.config/fish/completions/foundry.fish

eval (env _FOUNDRY_COMPLETE=fish_source foundry)
"""

# Shell config file paths
SHELL_CONFIGS = {
    "bash": [
        Path.home() / ".bashrc",
        Path.home() / ".bash_profile",
    ],
    "zsh": [
        Path.home() / ".zshrc",
    ],
    "fish": [
        Path.home() / ".config" / "fish" / "completions" / "foundry.fish",
    ],
}

COMPLETION_MARKER = "_FOUNDRY_COMPLETE"


def _detect_shell() -> str | None:
    """Detect the current shell.

    Returns:
        Shell name (bash, zsh, fish) or None if unknown
    """
    shell = os.environ.get("SHELL", "")
    if "bash" in shell:
        return "bash"
    elif "zsh" in shell:
        return "zsh"
    elif "fish" in shell:
        return "fish"
    return None


def _get_completion_script(shell: str) -> str:
    """Get the completion script for a shell.

    Args:
        shell: Shell name (bash, zsh, fish)

    Returns:
        Completion script content
    """
    scripts = {
        "bash": BASH_SCRIPT,
        "zsh": ZSH_SCRIPT,
        "fish": FISH_SCRIPT,
    }
    return scripts.get(shell, "")


def _find_config_file(shell: str) -> Path | None:
    """Find the appropriate config file for a shell.

    Args:
        shell: Shell name

    Returns:
        Path to config file or None
    """
    for config_path in SHELL_CONFIGS.get(shell, []):
        if shell == "fish":
            # For fish, we create the completions file directly
            return config_path
        if config_path.exists():
            return config_path
    return None


def _is_completion_installed(config_path: Path) -> bool:
    """Check if completion is already installed.

    Args:
        config_path: Path to shell config file

    Returns:
        True if completion marker is found
    """
    if not config_path.exists():
        return False
    content = config_path.read_text()
    return COMPLETION_MARKER in content


@click.group()
def completion() -> None:
    """Manage shell completion for bash, zsh, and fish.

    Examples:

        # Install completion for your shell
        foundry completion bash
        foundry completion zsh
        foundry completion fish

        # Remove completion (auto-detects installed shells)
        foundry completion uninstall
    """
    pass


def _install_completion(shell_type: str) -> None:
    """Install completion for a specific shell.

    Args:
        shell_type: Shell name (bash, zsh, fish)
    """
    script = _get_completion_script(shell_type)
    config_path = _find_config_file(shell_type)

    if not config_path:
        console.error(f"Could not find config file for {shell_type}")
        console.info(f"Manually add this to your shell config:\n\n{script}")
        sys.exit(1)

    # Check if already installed
    if _is_completion_installed(config_path):
        console.success(f"Completion already installed in {config_path}")
        return

    # Install completion
    try:
        if shell_type == "fish":
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(script)
            console.success(f"Completion installed to {config_path}")
        else:
            with open(config_path, "a") as f:
                f.write(f"\n{script}\n")
            console.success(f"Completion installed to {config_path}")

        console.info("")
        console.info("To activate, either:")
        console.info("  1. Restart your terminal")
        console.info(f"  2. Run: source {config_path}")

    except PermissionError:
        console.error(f"Permission denied writing to {config_path}")
        console.info(f"Manually add this to your shell config:\n\n{script}")
        sys.exit(1)
    except OSError as e:
        console.error(f"Failed to install completion: {e}")
        sys.exit(1)


@completion.command(name="bash")
def completion_bash() -> None:
    """Install bash completion to ~/.bashrc."""
    _install_completion("bash")


@completion.command(name="zsh")
def completion_zsh() -> None:
    """Install zsh completion to ~/.zshrc."""
    _install_completion("zsh")


@completion.command(name="fish")
def completion_fish() -> None:
    """Install fish completion to ~/.config/fish/completions/."""
    _install_completion("fish")


def _get_installed_shells() -> list[str]:
    """Find which shells have completion installed.

    Returns:
        List of shell names with completion installed
    """
    installed = []
    for shell in ["bash", "zsh", "fish"]:
        config_path = _find_config_file(shell)
        if config_path and _is_completion_installed(config_path):
            installed.append(shell)
    return installed


def _uninstall_completion(shell_type: str) -> bool:
    """Uninstall completion for a specific shell.

    Args:
        shell_type: Shell name (bash, zsh, fish)

    Returns:
        True if uninstalled, False if not installed
    """
    config_path = _find_config_file(shell_type)
    if not config_path or not config_path.exists():
        return False

    if not _is_completion_installed(config_path):
        return False

    try:
        if shell_type == "fish":
            config_path.unlink()
        else:
            content = config_path.read_text()
            script = _get_completion_script(shell_type)
            new_content = content.replace(f"\n{script}\n", "\n")
            new_content = new_content.replace(script, "")
            config_path.write_text(new_content)

        console.success(f"Removed {shell_type} completion")
        return True

    except PermissionError:
        console.error(f"Permission denied modifying {config_path}")
        return False
    except OSError as e:
        console.error(f"Failed to remove {shell_type} completion: {e}")
        return False


@completion.command(name="uninstall")
def completion_uninstall() -> None:
    """Remove shell completion.

    Detects which shells have completion installed and prompts
    you to select which ones to remove.
    """
    installed = _get_installed_shells()

    if not installed:
        console.info("No shell completions are currently installed")
        return

    # Build choices: individual shells + "all" option
    if len(installed) == 1:
        # Only one installed, just remove it
        shell = installed[0]
        if _uninstall_completion(shell):
            console.info("Restart your terminal to apply changes")
        return

    # Multiple installed - prompt user
    console.info("Found completion installed for:")
    for i, shell in enumerate(installed, 1):
        console.info(f"  {i}. {shell}")
    console.info(f"  {len(installed) + 1}. all")

    choice = click.prompt(
        "Which to uninstall?",
        type=click.IntRange(1, len(installed) + 1),
    )

    if choice == len(installed) + 1:
        # Uninstall all
        for shell in installed:
            _uninstall_completion(shell)
    else:
        _uninstall_completion(installed[choice - 1])

    console.info("Restart your terminal to apply changes")
