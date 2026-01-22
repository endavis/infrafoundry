"""Ansible runner implementation."""

import subprocess  # nosec B404 - required for running ansible-playbook
from pathlib import Path
from typing import Any, override

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.runners.base_runner import BaseRunner


class AnsibleRunner(BaseRunner):
    """Handles Ansible playbook execution."""

    @property
    @override
    def tool_name(self) -> str:
        """Return the name of the tool."""
        return "ansible-playbook"

    @override
    def is_available(self) -> bool:
        """Check if Ansible is installed."""
        try:
            _ = self.tool_path
            return True
        except FileNotFoundError:
            return False

    @override
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """Initialize Ansible (no-op, Ansible doesn't require initialization).

        Args:
            working_dir: Directory to initialize
            **kwargs: Additional options

        Returns:
            Dict with initialization results
        """
        if not self.is_available():
            return {"success": False, "error": "ansible-playbook command not found"}
        return {"success": True, "message": "Ansible is available"}

    def plan(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Run Ansible playbook in check mode (dry run).

        Args:
            provider: Provider instance
            **kwargs: Additional ansible options

        Returns:
            Dict with plan results
        """
        return self._run_ansible(provider, check_mode=True)

    def apply(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Run Ansible playbook.

        Args:
            provider: Provider instance
            **kwargs: Additional ansible options

        Returns:
            Dict with apply results
        """
        return self._run_ansible(provider, check_mode=False)

    @override
    def get_version(self) -> str | None:
        """Get Ansible version."""
        if not self.is_available():
            return None

        try:
            result = subprocess.run(  # nosec B603 - trusted command
                [self.tool_path, "--version"],
                capture_output=True,
                text=True,
                check=True,
            )
            # First line contains version info
            first_line = result.stdout.split("\n")[0]
            # Extract version number (e.g., "ansible-playbook 2.15.0")
            parts = first_line.split()
            if len(parts) >= 2:
                return parts[1]
            return first_line
        except (subprocess.CalledProcessError, IndexError):
            return None

    @override
    def validate_config(self, provider: ProviderBase) -> dict[str, Any]:
        """Validate Ansible playbook syntax.

        Args:
            provider: Provider instance

        Returns:
            Dict with validation results
        """
        ansible_dir = provider.ansible_dir
        playbook = ansible_dir / "playbook.yml"

        if not playbook.exists():
            return {"valid": True, "message": "No playbook found (optional)"}

        try:
            result = subprocess.run(  # nosec B603 - trusted command
                [self.tool_path, "--syntax-check", str(playbook)],
                cwd=ansible_dir,
                capture_output=True,
                text=True,
            )
            return {
                "valid": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
            }
        except subprocess.CalledProcessError as e:
            return {"valid": False, "error": str(e)}

    def _run_ansible(self, provider: ProviderBase, check_mode: bool = True) -> dict[str, Any]:
        """Run Ansible playbook for a provider.

        Args:
            provider: Provider instance
            check_mode: If True, run in check mode (dry run)

        Returns:
            Dict with command results
        """
        ansible_dir = provider.ansible_dir
        playbook = ansible_dir / "playbook.yml"
        inventory = ansible_dir / "inventory.yml"

        if not playbook.exists():
            self.console.print("[dim]No Ansible playbook found, skipping...[/dim]")
            return {"skipped": True, "success": True}

        if not self.is_available():
            self.console.print(
                "[yellow]ansible-playbook not found. Install Ansible to use this feature.[/yellow]"
            )
            return {"error": "ansible-playbook not found", "success": False}

        # Build command using full path to ansible-playbook binary
        cmd = [self.tool_path, "-i", str(inventory), str(playbook)]
        if check_mode:
            cmd.append("--check")
            self.console.print("[dim]Running Ansible in check mode (dry run)...[/dim]")
        else:
            self.console.print("[dim]Running Ansible playbook...[/dim]")

        # Run command - nosec B603: trusted command with validated inputs
        try:
            result = subprocess.run(cmd, cwd=ansible_dir, capture_output=False)  # nosec B603
            return {"exit_code": result.returncode, "success": result.returncode == 0}
        except FileNotFoundError:
            return {"error": "ansible-playbook not found", "success": False}
