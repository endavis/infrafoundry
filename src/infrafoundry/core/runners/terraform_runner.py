"""Terraform runner implementation."""

import json
import os
import re
import subprocess  # nosec B404 - required for running terraform
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
        try:
            _ = self.tool_path
            return True
        except FileNotFoundError:
            return False

    @override
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """Initialize Terraform in the working directory.

        Args:
            working_dir: Directory to initialize
            **kwargs: Additional terraform init options:
                - reconfigure (bool): Force reconfiguration of backend
                - migrate_state (bool): Migrate state to new backend
                - upgrade (bool): Upgrade provider plugins

        Returns:
            Dict with initialization results
        """
        if not self.is_available():
            return {"success": False, "error": "terraform command not found"}

        # Check if backend configuration exists
        backend_file = working_dir / "backend.tf"
        has_backend = backend_file.exists()

        # Check if already initialized
        is_initialized = (working_dir / ".terraform").exists()

        # Determine if we need to reinitialize for backend changes
        reconfigure = kwargs.get("reconfigure", False)
        migrate_state = kwargs.get("migrate_state", False)
        upgrade = kwargs.get("upgrade", False)

        # If already initialized and no special flags, check if backend changed
        if is_initialized and not (reconfigure or migrate_state or upgrade):
            # If backend.tf exists now but wasn't used before, or vice versa,
            # we need to reconfigure
            terraform_state = working_dir / ".terraform" / "terraform.tfstate"
            if terraform_state.exists():
                import json

                try:
                    with open(terraform_state) as f:
                        state_data = json.load(f)
                        backend_type = state_data.get("backend", {}).get("type")

                        # If we have a backend.tf but state shows local backend (or no backend),
                        # or we don't have backend.tf but state shows remote backend,
                        # we need to reconfigure
                        if (has_backend and backend_type == "local") or (
                            not has_backend and backend_type and backend_type != "local"
                        ):
                            reconfigure = True
                            self.console.print(
                                "[yellow]Backend configuration changed, reconfiguring...[/yellow]"
                            )
                except (json.JSONDecodeError, FileNotFoundError):
                    pass

            if not reconfigure:
                return {"success": True, "message": "Already initialized"}

        # Build init command using full path to terraform binary
        cmd = [self.tool_path, "init"]
        if reconfigure:
            cmd.append("-reconfigure")
        if migrate_state:
            cmd.append("-migrate-state")
        if upgrade:
            cmd.append("-upgrade")

        try:
            msg = "Initializing Terraform..."
            if reconfigure:
                msg = "Reconfiguring Terraform backend..."
            elif migrate_state:
                msg = "Migrating Terraform state..."
            self.console.print(f"[dim]{msg}[/dim]")

            result = subprocess.run(  # nosec B603
                cmd,
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
            **kwargs: Additional terraform plan options:
                - target_resources: List of resource names to target with -target

        Returns:
            Dict with plan results
        """
        target_resources = kwargs.get("target_resources")
        return self._run_terraform(provider, "plan", target_resources=target_resources)

    def apply(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Apply Terraform configuration.

        Args:
            provider: Provider instance
            **kwargs: Options including auto_approve, target_resources

        Returns:
            Dict with apply results
        """
        auto_approve = kwargs.get("auto_approve", False)
        target_resources = kwargs.get("target_resources")
        return self._run_terraform(
            provider, "apply", auto_approve=auto_approve, target_resources=target_resources
        )

    def destroy(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Destroy Terraform-managed infrastructure.

        Args:
            provider: Provider instance
            **kwargs: Options including auto_approve, target_resources

        Returns:
            Dict with destroy results
        """
        auto_approve = kwargs.get("auto_approve", False)
        target_resources = kwargs.get("target_resources")
        return self._run_terraform(
            provider, "destroy", auto_approve=auto_approve, target_resources=target_resources
        )

    @override
    def get_version(self) -> str | None:
        """Get Terraform version."""
        if not self.is_available():
            return None

        try:
            result = subprocess.run(  # nosec B603
                [self.tool_path, "version", "-json"],
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
            result = subprocess.run(  # nosec B603
                [self.tool_path, "validate"],
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
        self,
        provider: ProviderBase,
        command: str,
        auto_approve: bool = False,
        target_resources: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run Terraform command for a provider.

        Args:
            provider: Provider instance
            command: Terraform command (plan, apply, destroy)
            auto_approve: If True, add -auto-approve flag
            target_resources: Optional list of resource names to target with -target

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

        # Build command using full path to terraform binary
        cmd = [self.tool_path, command]
        if auto_approve and command in {"apply", "destroy"}:
            cmd.append("-auto-approve")

        # Add -target flags for resource filtering
        if target_resources:
            targets = self._resolve_terraform_targets(tf_dir, target_resources)
            for target in targets:
                cmd.extend(["-target", target])

        # Run command with environment variables; capture output for plan so drift parsing works
        capture = command == "plan"
        result = subprocess.run(  # nosec B603
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

    def _resolve_terraform_targets(self, tf_dir: Path, resource_names: list[str]) -> list[str]:
        """Resolve resource names to terraform resource addresses.

        Scans generated .tf files for resource blocks matching the given names
        (with dashes converted to underscores).

        Args:
            tf_dir: Terraform working directory
            resource_names: List of resource names (e.g., ["infra-web", "esx-01"])

        Returns:
            List of terraform resource addresses (e.g.,
            ["proxmox_virtual_environment_vm.infra_web"])
        """
        # Convert resource names to terraform-style names (dashes to underscores)
        tf_names = {name.replace("-", "_") for name in resource_names}

        targets: list[str] = []
        # Pattern matches: resource "type" "name" {
        resource_pattern = re.compile(r'^resource\s+"([^"]+)"\s+"([^"]+)"')

        for tf_file in tf_dir.glob("*.tf"):
            with open(tf_file) as f:
                for line in f:
                    match = resource_pattern.match(line)
                    if match:
                        resource_type = match.group(1)
                        resource_name = match.group(2)
                        if resource_name in tf_names:
                            targets.append(f"{resource_type}.{resource_name}")

        return targets

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
            result = subprocess.run(  # nosec B603
                [self.tool_path, "show", "-json"],
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
