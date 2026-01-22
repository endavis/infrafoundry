"""PyInfra runner implementation."""

import subprocess  # nosec B404 - required for running pyinfra
import sys
from pathlib import Path
from typing import Any, override

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.runners.base_runner import BaseRunner


class PyInfraRunner(BaseRunner):
    """Handles pyinfra execution."""

    @property
    @override
    def tool_name(self) -> str:
        """Return the name of the tool."""
        return "pyinfra"

    @override
    def is_available(self) -> bool:
        """Check if pyinfra is installed."""
        try:
            _ = self.tool_path
            return True
        except FileNotFoundError:
            return False

    @override
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """Initialize pyinfra (no-op).

        Args:
            working_dir: Directory to initialize
            **kwargs: Additional options

        Returns:
            Dict with initialization results
        """
        if not self.is_available():
            return {"success": False, "error": "pyinfra command not found"}
        return {"success": True, "message": "pyinfra is available"}

    def plan(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Run pyinfra in dry-run mode.

        Args:
            provider: Provider instance
            **kwargs: Additional options

        Returns:
            Dict with plan results
        """
        return self._run_pyinfra(provider, dry_run=True)

    def apply(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Run pyinfra.

        Args:
            provider: Provider instance
            **kwargs: Additional options

        Returns:
            Dict with apply results
        """
        return self._run_pyinfra(provider, dry_run=False)

    @override
    def get_version(self) -> str | None:
        """Get pyinfra version."""
        if not self.is_available():
            return None

        try:
            result = subprocess.run(  # nosec B603
                [self.tool_path, "--version"],
                capture_output=True,
                text=True,
                check=True,
            )
            # Output format: "pyinfra v2.x.x"
            return result.stdout.strip().split("v")[-1]
        except (subprocess.CalledProcessError, IndexError):
            return None

    @override
    def validate_config(self, provider: ProviderBase) -> dict[str, Any]:
        """Validate pyinfra configuration.

        Args:
            provider: Provider instance

        Returns:
            Dict with validation results
        """
        pyinfra_dir = getattr(provider, "pyinfra_dir", None)
        if not pyinfra_dir:
            return {"valid": False, "error": "Provider does not support pyinfra"}

        deploy_file = pyinfra_dir / "deploy.py"
        inventory_file = pyinfra_dir / "inventory.py"

        if not deploy_file.exists():
            return {"valid": True, "message": "No deploy.py found (optional)"}

        if not inventory_file.exists():
            return {"valid": False, "error": "inventory.py missing"}

        # Basic syntax check using python -m py_compile
        try:
            subprocess.run(  # nosec B603
                [sys.executable, "-m", "py_compile", str(deploy_file)],
                check=True,
                capture_output=True,
            )
            subprocess.run(  # nosec B603
                [sys.executable, "-m", "py_compile", str(inventory_file)],
                check=True,
                capture_output=True,
            )
            return {"valid": True}
        except subprocess.CalledProcessError as e:
            return {"valid": False, "error": f"Syntax error: {e}"}

    def _run_pyinfra(self, provider: ProviderBase, dry_run: bool = True) -> dict[str, Any]:
        """Run pyinfra for a provider.

        Args:
            provider: Provider instance
            dry_run: If True, run in dry-run mode

        Returns:
            Dict with command results
        """
        pyinfra_dir = getattr(provider, "pyinfra_dir", None)
        if not pyinfra_dir:
            return {"error": "Provider has no pyinfra_dir", "success": False}

        deploy_file = pyinfra_dir / "deploy.py"
        inventory_file = pyinfra_dir / "inventory.py"

        if not deploy_file.exists():
            self.console.print("[dim]No pyinfra deploy.py found, skipping...[/dim]")
            return {"skipped": True, "success": True}

        if not self.is_available():
            self.console.print(
                "[yellow]pyinfra not found. Install pyinfra to use this feature.[/yellow]"
            )
            return {"error": "pyinfra not found", "success": False}

        # Build command using full path to pyinfra binary
        # pyinfra [options] INVENTORY DEPLOY
        cmd = [self.tool_path]
        if dry_run:
            cmd.append("--dry")
            self.console.print("[dim]Running pyinfra in dry-run mode...[/dim]")
        else:
            cmd.append("--yes")  # Non-interactive
            self.console.print("[dim]Running pyinfra...[/dim]")

        cmd.append(str(inventory_file))
        cmd.append(str(deploy_file))

        # Run command
        try:
            # pyinfra outputs to stderr mostly for progress
            result = subprocess.run(cmd, cwd=pyinfra_dir, capture_output=False)  # nosec B603
            return {"exit_code": result.returncode, "success": result.returncode == 0}
        except FileNotFoundError:
            return {"error": "pyinfra not found", "success": False}
