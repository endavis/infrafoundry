"""Pulumi runner implementation (example of pluggable runner)."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, override

from rich.console import Console

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.runners.base_runner import BaseRunner


class PulumiRunner(BaseRunner):
    """Handles Pulumi program execution.

    This is an example implementation showing how to add new infrastructure
    tools to InfraFoundry using the pluggable runner system.
    """

    def __init__(self, console: Console | None = None, stack: str | None = None) -> None:
        """Initialize Pulumi runner.

        Args:
            console: Rich console for output
            stack: Default stack name to use
        """
        super().__init__(console)
        self.default_stack = stack

    @property
    @override
    def tool_name(self) -> str:
        """Return the name of the tool."""
        return "pulumi"

    @override
    def is_available(self) -> bool:
        """Check if Pulumi is installed."""
        return shutil.which("pulumi") is not None

    @override
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """Initialize Pulumi stack.

        Args:
            working_dir: Directory containing Pulumi program
            **kwargs: Options including stack name

        Returns:
            Dict with initialization results
        """
        if not self.is_available():
            return {"success": False, "error": "pulumi command not found"}

        stack = kwargs.get("stack", self.default_stack or "dev")

        try:
            # Check if stack exists
            result = subprocess.run(
                ["pulumi", "stack", "ls", "--json"],
                cwd=working_dir,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                stacks = json.loads(result.stdout)
                stack_exists = any(s.get("name") == stack for s in stacks)

                if not stack_exists:
                    # Create stack if it doesn't exist
                    self.console.print(f"[dim]Creating Pulumi stack: {stack}...[/dim]")
                    subprocess.run(
                        ["pulumi", "stack", "init", stack],
                        cwd=working_dir,
                        check=True,
                    )
                else:
                    # Select existing stack
                    subprocess.run(
                        ["pulumi", "stack", "select", stack],
                        cwd=working_dir,
                        check=True,
                    )

                return {"success": True, "stack": stack}

        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            return {"success": False, "error": str(e)}

        return {"success": False, "error": "Unknown error"}

    def plan(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Generate Pulumi preview (plan).

        Args:
            provider: Provider instance
            **kwargs: Additional pulumi preview options

        Returns:
            Dict with preview results
        """
        pulumi_dir = provider.output_dir / "pulumi" / provider.name

        if not pulumi_dir.exists():
            return {"success": False, "error": "Pulumi directory does not exist"}

        try:
            result = subprocess.run(
                ["pulumi", "preview", "--non-interactive"],
                cwd=pulumi_dir,
                capture_output=True,
                text=True,
            )
            return {
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
            }
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": str(e)}

    def apply(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Apply Pulumi program.

        Args:
            provider: Provider instance
            **kwargs: Options including auto_approve

        Returns:
            Dict with apply results
        """
        pulumi_dir = provider.output_dir / "pulumi" / provider.name
        auto_approve = kwargs.get("auto_approve", False)

        if not pulumi_dir.exists():
            return {"success": False, "error": "Pulumi directory does not exist"}

        try:
            cmd = ["pulumi", "up"]
            if auto_approve:
                cmd.append("--yes")

            result = subprocess.run(
                cmd,
                cwd=pulumi_dir,
                capture_output=False,
            )
            return {"success": result.returncode == 0, "exit_code": result.returncode}
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": str(e)}

    def destroy(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Destroy Pulumi-managed infrastructure.

        Args:
            provider: Provider instance
            **kwargs: Options including auto_approve

        Returns:
            Dict with destroy results
        """
        pulumi_dir = provider.output_dir / "pulumi" / provider.name
        auto_approve = kwargs.get("auto_approve", False)

        if not pulumi_dir.exists():
            return {"success": False, "error": "Pulumi directory does not exist"}

        try:
            cmd = ["pulumi", "destroy"]
            if auto_approve:
                cmd.append("--yes")

            result = subprocess.run(
                cmd,
                cwd=pulumi_dir,
                capture_output=False,
            )
            return {"success": result.returncode == 0, "exit_code": result.returncode}
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": str(e)}

    @override
    def get_version(self) -> str | None:
        """Get Pulumi version."""
        if not self.is_available():
            return None

        try:
            result = subprocess.run(
                ["pulumi", "version"],
                capture_output=True,
                text=True,
                check=True,
            )
            # Pulumi version output is like "v3.88.1"
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    @override
    def validate_config(self, provider: ProviderBase) -> dict[str, Any]:
        """Validate Pulumi program."""
        pulumi_dir = provider.output_dir / "pulumi" / provider.name

        if not pulumi_dir.exists():
            return {"valid": False, "error": "Pulumi directory does not exist"}

        # Check for Pulumi.yaml
        if not (pulumi_dir / "Pulumi.yaml").exists():
            return {"valid": False, "error": "Pulumi.yaml not found"}

        return {"valid": True, "message": "Pulumi configuration valid"}

    def get_resource_ids(self, provider: ProviderBase) -> dict[str, str]:
        """Get resource IDs from Pulumi state.

        Args:
            provider: Provider instance

        Returns:
            Dict mapping resource names to URNs (Pulumi resource identifiers)
        """
        pulumi_dir = provider.output_dir / "pulumi" / provider.name

        if not pulumi_dir.exists():
            return {}

        try:
            result = subprocess.run(
                ["pulumi", "stack", "export"],
                cwd=pulumi_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            state = json.loads(result.stdout)
            resources = state.get("deployment", {}).get("resources", [])

            # Extract URNs as resource identifiers
            return {res.get("type", ""): res.get("urn", "") for res in resources if res.get("urn")}
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
            return {}

    def parse_plan_for_drift(self, plan_result: dict[str, Any]) -> dict[str, Any]:
        """Parse Pulumi preview for drift.

        Args:
            plan_result: Result from run() with preview command

        Returns:
            Dict with drift information
        """
        # Check if there were any changes in the preview
        has_changes = plan_result.get("success", False) and plan_result.get("exit_code") == 0
        output = plan_result.get("output", "")

        # Pulumi preview shows if there are changes
        # This is a simple heuristic - could be improved
        if "no changes" in output.lower() or "no updates" in output.lower():
            has_changes = False

        return {
            "has_changes": has_changes,
            "summary": "Changes detected in Pulumi preview" if has_changes else "No changes",
        }
