"""Terraform runner implementation."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast, override

from rich.console import Console

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.runners.base_runner import BaseRunner


class TerraformRunner(BaseRunner):
    """Handles Terraform command execution and state management."""

    def __init__(self, console: Console | None = None) -> None:
        """Initialize Terraform runner.

        Args:
            console: Rich console for output (creates default if None)
        """
        super().__init__(console)

    @property
    @override
    def tool_name(self) -> str:
        """Return the name of the tool."""
        return "terraform"

    @property
    @override
    def priority(self) -> int:
        """Terraform must run first to provision resources."""
        return 0

    @override
    def is_available(self) -> bool:
        """Check if Terraform is installed."""
        return shutil.which("terraform") is not None

    @override
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """Initialize Terraform in the working directory.

        Args:
            working_dir: Directory to initialize
            **kwargs: Additional terraform init options

        Returns:
            Dict with initialization results
        """
        if not self.is_available():
            return {"success": False, "error": "terraform command not found"}

        if (working_dir / ".terraform").exists():
            return {"success": True, "message": "Already initialized"}

        try:
            self.console.print("[dim]Initializing Terraform...[/dim]")
            result = subprocess.run(
                ["terraform", "init"],
                cwd=working_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            return {"success": True, "output": result.stdout}
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": str(e), "output": e.stderr}

    def plan(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Generate Terraform execution plan.

        Args:
            provider: Provider instance
            **kwargs: Additional terraform plan options

        Returns:
            Dict with plan results
        """
        return self._run_terraform(provider, "plan", **kwargs)

    def apply(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Apply Terraform configuration.

        Args:
            provider: Provider instance
            **kwargs: Options including auto_approve

        Returns:
            Dict with apply results
        """
        auto_approve = kwargs.get("auto_approve", False)
        return self._run_terraform(provider, "apply", auto_approve=auto_approve)

    def destroy(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Destroy Terraform-managed infrastructure.

        Args:
            provider: Provider instance
            **kwargs: Options including auto_approve

        Returns:
            Dict with destroy results
        """
        auto_approve = kwargs.get("auto_approve", False)
        return self._run_terraform(provider, "destroy", auto_approve=auto_approve)

    @override
    def get_version(self) -> str | None:
        """Get Terraform version."""
        if not self.is_available():
            return None

        try:
            result = subprocess.run(
                ["terraform", "version", "-json"],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)
            return cast(str | None, data.get("terraform_version"))
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
            return None

    @override
    def validate_config(self, provider: ProviderBase) -> dict[str, Any]:
        """Validate Terraform configuration."""
        tf_dir = provider.terraform_dir

        if not tf_dir.exists():
            return {"valid": False, "error": "Terraform directory does not exist"}

        try:
            env = self._prepare_environment(provider)
            result = subprocess.run(
                ["terraform", "validate"],
                cwd=tf_dir,
                capture_output=True,
                text=True,
                env=env,
            )
            return {
                "valid": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
            }
        except subprocess.CalledProcessError as e:
            return {"valid": False, "error": str(e)}

    def _run_terraform(
        self, provider: ProviderBase, command: str, auto_approve: bool = False
    ) -> dict[str, Any]:
        """Run Terraform command for a provider.

        Args:
            provider: Provider instance
            command: Terraform command (plan, apply, destroy)
            auto_approve: If True, add -auto-approve flag

        Returns:
            Dict with command results
        """
        tf_dir = provider.terraform_dir

        # Load credentials and set environment variables
        env = self._prepare_environment(provider)

        # Initialize if needed
        init_result = self.initialize(tf_dir)
        if not init_result.get("success"):
            return init_result

        # Build command
        cmd = ["terraform", command]
        if auto_approve and command in {"apply", "destroy"}:
            cmd.append("-auto-approve")

        # Run command with environment variables; capture output for plan so drift parsing works
        capture = command == "plan"
        result = subprocess.run(
            cmd,
            cwd=tf_dir,
            capture_output=capture,
            text=capture,
            env=env,
        )

        response: dict[str, Any] = {
            "exit_code": result.returncode,
            "success": result.returncode == 0,
        }
        if capture:
            response["output"] = result.stdout or ""
            response["error"] = result.stderr or ""

        return response

    def get_resource_ids(self, provider: ProviderBase) -> dict[str, str]:
        """Extract Terraform resource IDs from state.

        Args:
            provider: Provider instance

        Returns:
            Dict mapping resource names to Terraform resource addresses
        """
        tf_dir = provider.terraform_dir

        try:
            # Run terraform show -json to get state
            result = subprocess.run(
                ["terraform", "show", "-json"],
                cwd=tf_dir,
                capture_output=True,
                text=True,
                check=True,
            )

            state = json.loads(result.stdout)
            resource_ids = {}

            # Extract resource addresses from state
            if "values" in state and "root_module" in state["values"]:
                root = state["values"]["root_module"]
                if "resources" in root:
                    for resource in root["resources"]:
                        # Resource address format: provider_type.resource_name
                        address = resource.get("address")
                        name = resource.get("name")
                        if address and name:
                            resource_ids[name] = address

            return resource_ids

        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
            self.console.print(f"[yellow]Warning: Could not extract Terraform IDs: {e}[/yellow]")
            return {}

    def parse_plan_for_drift(self, plan_result: dict[str, Any]) -> dict[str, Any]:
        """Parse Terraform plan output to detect drift.

        Args:
            plan_result: Result dictionary from run() with plan command

        Returns:
            Dict with drift information
        """
        output = plan_result.get("output", "")

        # Look for Terraform's plan summary line
        plan_pattern = r"Plan: (\d+) to add, (\d+) to change, (\d+) to destroy"
        match = re.search(plan_pattern, output)

        if match:
            to_add = int(match.group(1))
            to_change = int(match.group(2))
            to_destroy = int(match.group(3))

            has_changes = (to_add + to_change + to_destroy) > 0

            # Build summary message
            parts = []
            if to_add > 0:
                parts.append(f"{to_add} to add")
            if to_change > 0:
                parts.append(f"{to_change} to change")
            if to_destroy > 0:
                parts.append(f"{to_destroy} to destroy")

            summary = ", ".join(parts) if parts else "No changes"

            return {
                "has_changes": has_changes,
                "to_add": to_add,
                "to_change": to_change,
                "to_destroy": to_destroy,
                "summary": summary,
                "raw_output": output,
            }

        # If no plan line found, check for "No changes" message
        if "No changes" in output or "no changes are needed" in output.lower():
            return {
                "has_changes": False,
                "to_add": 0,
                "to_change": 0,
                "to_destroy": 0,
                "summary": "No changes",
                "raw_output": output,
            }

        # Unknown state
        return {
            "has_changes": None,
            "to_add": None,
            "to_change": None,
            "to_destroy": None,
            "summary": "Unable to parse plan output",
            "raw_output": output,
        }

    def _prepare_environment(self, provider: ProviderBase) -> dict[str, str]:
        """Prepare environment variables for Terraform execution.

        Note: Credentials should be loaded via CredentialLoader before calling this.
        This method uses environment variables that are already set.

        Args:
            provider: Provider instance

        Returns:
            Environment variables dict (credentials come from os.environ)
        """
        env = os.environ.copy()

        # Credentials are already set by CredentialLoader in CLI
        # No need to decrypt secrets here - they're loaded per-environment

        return env
