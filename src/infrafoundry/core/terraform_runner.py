"""Terraform execution and management."""

import json
import os
import re
import subprocess
from typing import Any

from rich.console import Console

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.secrets import SecretManager


class TerraformRunner:
    """Handles Terraform command execution and state management."""

    def __init__(self, secret_manager: SecretManager, console: Console | None = None) -> None:
        """Initialize Terraform runner.

        Args:
            secret_manager: Secret manager for loading credentials
            console: Rich console for output (creates default if None)
        """
        self.secret_manager = secret_manager
        self.console = console or Console()

    def run(
        self, provider: ProviderBase, command: str, auto_approve: bool = False
    ) -> dict[str, Any]:
        """Run Terraform command for a provider.

        Args:
            provider: Provider instance
            command: Terraform command (plan, apply, destroy)
            auto_approve: If True, add -auto-approve flag

        Returns:
            Dict with command results including exit_code and success
        """
        tf_dir = provider.terraform_dir

        # Load credentials and set environment variables
        env = self._prepare_environment(provider)

        # Initialize if needed
        if not (tf_dir / ".terraform").exists():
            self.console.print("[dim]Initializing Terraform...[/dim]")
            subprocess.run(["terraform", "init"], cwd=tf_dir, check=True, env=env)

        # Build command
        cmd = ["terraform", command]
        if auto_approve and command in {"apply", "destroy"}:
            cmd.append("-auto-approve")

        # Run command with environment variables
        result = subprocess.run(cmd, cwd=tf_dir, capture_output=False, env=env)

        return {"exit_code": result.returncode, "success": result.returncode == 0}

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
            Dict with drift information:
                - has_changes: bool indicating if drift detected
                - to_add: number of resources to add
                - to_change: number of resources to change
                - to_destroy: number of resources to destroy
                - summary: human-readable summary
                - raw_output: original terraform output
        """
        output = plan_result.get("output", "")

        # Look for Terraform's plan summary line
        # Example: "Plan: 1 to add, 2 to change, 0 to destroy."
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

        Args:
            provider: Provider instance

        Returns:
            Environment variables dict with credentials loaded
        """
        env = os.environ.copy()

        try:
            # Try provider-specific secrets file first (e.g., proxmox.yaml)
            secrets_file = f"{provider.name}.yaml"
            creds = self.secret_manager.decrypt_file(secrets_file)
        except FileNotFoundError:
            # Fall back to shared credentials file
            try:
                creds = self.secret_manager.decrypt_file("credentials.yaml")
            except Exception:
                creds = {}

        # Set provider-specific environment variables
        if provider.name == "proxmox":
            if "proxmox_api_url" in creds:
                # bpg/proxmox provider uses PROXMOX_VE_ENDPOINT
                env["PROXMOX_VE_ENDPOINT"] = creds["proxmox_api_url"]
            if "proxmox_api_token_id" in creds and "proxmox_api_token_secret" in creds:
                # bpg/proxmox uses PROXMOX_VE_API_TOKEN in format "user@realm!tokenid=secret"
                token_id = creds["proxmox_api_token_id"]
                token_secret = creds["proxmox_api_token_secret"]
                env["PROXMOX_VE_API_TOKEN"] = f"{token_id}={token_secret}"
            # Allow insecure TLS for self-signed certs
            env["PROXMOX_VE_INSECURE"] = "true"
        elif provider.name == "opnsense":
            if "opnsense_api_url" in creds:
                env["OPNSENSE_API_URL"] = creds["opnsense_api_url"]
                env["TF_VAR_opnsense_api_url"] = creds["opnsense_api_url"]
            if "opnsense_api_key" in creds:
                env["OPNSENSE_API_KEY"] = creds["opnsense_api_key"]
                env["TF_VAR_opnsense_api_key"] = creds["opnsense_api_key"]
            if "opnsense_api_secret" in creds:
                env["OPNSENSE_API_SECRET"] = creds["opnsense_api_secret"]
                env["TF_VAR_opnsense_api_secret"] = creds["opnsense_api_secret"]

        return env
