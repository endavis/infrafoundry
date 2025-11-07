"""Core orchestration for infrastructure deployment."""

import subprocess
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.secrets import SecretManager


class Orchestrator:
    """Orchestrates infrastructure deployment across providers."""

    def __init__(
        self,
        config_manager: ConfigManager,
        secret_manager: SecretManager,
        output_dir: Path | None = None,
    ) -> None:
        """Initialize orchestrator.

        Args:
            config_manager: Configuration manager instance
            secret_manager: Secret manager instance
            output_dir: Directory for generated files (defaults to ./generated)
        """
        self.config_manager = config_manager
        self.secret_manager = secret_manager
        self.output_dir = output_dir or Path.cwd() / "generated"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.console = Console()
        self.providers: dict[str, ProviderBase] = {}

    def register_provider(self, provider: ProviderBase) -> None:
        """Register a provider plugin.

        Args:
            provider: Provider instance to register
        """
        self.providers[provider.name] = provider

    def plan(self, env_name: str, dry_run: bool = False) -> dict[str, Any]:
        """Plan infrastructure changes.

        Args:
            env_name: Environment name
            dry_run: If True, only show what would be done

        Returns:
            Dict with plan results per provider
        """
        env_config = self.config_manager.load_environment(env_name)
        results = {}

        self.console.print(f"\n[bold cyan]Planning infrastructure for: {env_name}[/bold cyan]")

        for provider_name in env_config.providers:
            if provider_name not in self.providers:
                self.console.print(
                    f"[yellow]Warning: Provider '{provider_name}' not registered[/yellow]"
                )
                continue

            provider = self.providers[provider_name]
            resources = self.config_manager.get_all_resources(env_name, provider_name)

            self.console.print(f"\n[bold]{provider_name}[/bold]: {len(resources)} resources")

            if dry_run:
                self.console.print("  [dim]Would generate Terraform and Ansible files[/dim]")
                results[provider_name] = {"resources": len(resources), "dry_run": True}
                continue

            # Generate Terraform and Ansible files
            provider.ensure_directories()
            provider.generate_terraform(resources)
            provider.generate_ansible(resources)

            # Export secrets for this provider
            try:
                secrets_file = f"{provider_name}.yaml"
                tf_vars = provider.terraform_dir / "secrets.auto.tfvars"
                self.secret_manager.export_for_terraform(secrets_file, tf_vars)
            except FileNotFoundError:
                self.console.print(f"[yellow]No secrets file for {provider_name}[/yellow]")

            # Run terraform plan
            self.console.print("  [dim]Running terraform plan...[/dim]")
            tf_result = self._run_terraform(provider, "plan", auto_approve=False)

            results[provider_name] = {
                "resources": len(resources),
                "terraform_plan": tf_result,
            }

        return results

    def apply(self, env_name: str, auto_approve: bool = False) -> dict[str, Any]:
        """Apply infrastructure changes.

        Args:
            env_name: Environment name
            auto_approve: If True, skip confirmation prompts

        Returns:
            Dict with apply results per provider
        """
        # First, generate the plans
        self.plan(env_name, dry_run=False)

        env_config = self.config_manager.load_environment(env_name)
        results = {}

        self.console.print(f"\n[bold green]Applying infrastructure for: {env_name}[/bold green]")

        for provider_name in env_config.providers:
            if provider_name not in self.providers:
                continue

            provider = self.providers[provider_name]
            self.console.print(f"\n[bold]Applying {provider_name}...[/bold]")

            # Run Terraform apply
            tf_result = self._run_terraform(provider, "apply", auto_approve)

            # Run Ansible playbook (check mode for dry run)
            ansible_result = self._run_ansible(provider, check_mode=not auto_approve)

            results[provider_name] = {
                "terraform": tf_result,
                "ansible": ansible_result,
            }

        return results

    def destroy(self, env_name: str, auto_approve: bool = False) -> dict[str, Any]:
        """Destroy infrastructure.

        Args:
            env_name: Environment name
            auto_approve: If True, skip confirmation prompts

        Returns:
            Dict with destroy results per provider
        """
        env_config = self.config_manager.load_environment(env_name)
        results = {}

        self.console.print(f"\n[bold red]Destroying infrastructure for: {env_name}[/bold red]")

        if not auto_approve:
            response = input("Are you sure you want to destroy? (yes/no): ")
            if response.lower() != "yes":
                self.console.print("[yellow]Aborted[/yellow]")
                return {}

        for provider_name in env_config.providers:
            if provider_name not in self.providers:
                continue

            provider = self.providers[provider_name]
            self.console.print(f"\n[bold]Destroying {provider_name}...[/bold]")

            # Run Terraform destroy
            tf_result = self._run_terraform(provider, "destroy", auto_approve)
            results[provider_name] = {"terraform": tf_result}

        return results

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

        # Initialize if needed
        if not (tf_dir / ".terraform").exists():
            self.console.print("[dim]Initializing Terraform...[/dim]")
            subprocess.run(["terraform", "init"], cwd=tf_dir, check=True)

        # Build command
        cmd = ["terraform", command]
        if auto_approve and command in ("apply", "destroy"):
            cmd.append("-auto-approve")

        # Run command
        result = subprocess.run(cmd, cwd=tf_dir, capture_output=False)

        return {"exit_code": result.returncode, "success": result.returncode == 0}

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
            return {"skipped": True}

        # Build command
        cmd = ["ansible-playbook", "-i", str(inventory), str(playbook)]
        if check_mode:
            cmd.append("--check")
            self.console.print("[dim]Running Ansible in check mode (dry run)...[/dim]")
        else:
            self.console.print("[dim]Running Ansible playbook...[/dim]")

        # Run command
        try:
            result = subprocess.run(cmd, cwd=ansible_dir, capture_output=False)
            return {"exit_code": result.returncode, "success": result.returncode == 0}
        except FileNotFoundError:
            self.console.print(
                "[yellow]ansible-playbook not found. Install Ansible to use this feature.[/yellow]"
            )
            return {"error": "ansible-playbook not found", "success": False}

    def status(self, env_name: str) -> None:
        """Show status of infrastructure.

        Args:
            env_name: Environment name
        """
        env_config = self.config_manager.load_environment(env_name)

        table = Table(title=f"Infrastructure Status: {env_name}")
        table.add_column("Provider", style="cyan")
        table.add_column("Resources", style="magenta")
        table.add_column("Status", style="green")

        for provider_name in env_config.providers:
            if provider_name not in self.providers:
                table.add_row(provider_name, "N/A", "[yellow]Not registered[/yellow]")
                continue

            resources = self.config_manager.get_all_resources(env_name, provider_name)
            provider = self.providers[provider_name]

            # Check if Terraform state exists
            state_file = provider.terraform_dir / "terraform.tfstate"
            status = "[green]Deployed[/green]" if state_file.exists() else "[dim]Not deployed[/dim]"

            table.add_row(provider_name, str(len(resources)), status)

        self.console.print(table)
