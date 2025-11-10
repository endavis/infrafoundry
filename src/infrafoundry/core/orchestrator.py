"""Core orchestration for infrastructure deployment."""

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.dependencies import DependencyGraph
from infrafoundry.core.events import Event, EventManager, EventType
from infrafoundry.core.notifications import NotificationManager
from infrafoundry.core.policy import PolicyEngine, PolicyLevel
from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.secrets import SecretManager
from infrafoundry.core.state import DeploymentStatus, ResourceState, StateManager


class Orchestrator:
    """Orchestrates infrastructure deployment across providers."""

    def __init__(
        self,
        config_manager: ConfigManager,
        secret_manager: SecretManager,
        output_dir: Path | None = None,
        state_manager: StateManager | None = None,
        event_manager: EventManager | None = None,
        policy_dir: Path | None = None,
        notifications_config: Path | None = None,
    ) -> None:
        """Initialize orchestrator.

        Args:
            config_manager: Configuration manager instance
            secret_manager: Secret manager instance
            output_dir: Directory for generated files (defaults to ./generated)
            state_manager: State manager instance (creates default if None)
            event_manager: Event manager instance (creates default if None)
            policy_dir: Directory containing policy files (defaults to ./policies)
            notifications_config: Path to notifications config file
        """
        self.config_manager = config_manager
        self.secret_manager = secret_manager
        self.output_dir = output_dir or Path.cwd() / "generated"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.console = Console()
        self.providers: dict[str, ProviderBase] = {}

        # Initialize state, event, policy, and notification managers
        self.state_manager = state_manager or StateManager()
        self.state_manager.initialize()  # Initialize database schema
        self.event_manager = event_manager or EventManager()
        self.policy_engine = PolicyEngine(policy_dir)
        self.notification_manager = NotificationManager(notifications_config)

        # Subscribe notification manager to events
        self._setup_notifications()

        # Get current user for tracking
        self._current_user = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"

    def _setup_notifications(self) -> None:
        """Set up notification handlers for events."""
        if not self.notification_manager or not self.notification_manager.channels:
            return

        # Subscribe to all events
        def event_handler(event: Event) -> None:
            """Forward events to notification manager."""
            self.notification_manager.notify(event.event_type.value, event.environment, event.data)

        # Subscribe to all event types
        for event_type in EventType:
            self.event_manager.subscribe(event_type, event_handler)

    def register_provider(self, provider: ProviderBase) -> None:
        """Register a provider plugin.

        Args:
            provider: Provider instance to register
        """
        self.providers[provider.name] = provider

    def validate_resources(self, resources: list[Any]) -> None:
        """Validate that all resources have providers that support their types.

        Args:
            resources: List of ResourceConfig objects to validate

        Raises:
            ValueError: If a resource's provider doesn't support its type
        """
        for resource in resources:
            provider_name = resource.provider
            resource_type = resource.type

            # Check if provider is registered
            if provider_name not in self.providers:
                raise ValueError(
                    f"Provider '{provider_name}' not registered for resource "
                    f"'{resource.name}' (type: {resource_type})"
                )

            # Check if provider supports the resource type
            provider = self.providers[provider_name]
            supported_types = provider.get_resource_types()
            if resource_type not in supported_types:
                raise ValueError(
                    f"Provider '{provider_name}' does not support resource type "
                    f"'{resource_type}' for resource '{resource.name}'. "
                    f"Supported types: {', '.join(supported_types)}"
                )

    def build_dependency_graph(self, env_name: str) -> DependencyGraph:
        """Build dependency graph for an environment.

        Args:
            env_name: Environment name

        Returns:
            DependencyGraph with all resources and dependencies
        """
        graph = DependencyGraph()

        # Get all resources for the environment
        all_resources = self.config_manager.get_all_resources_all_providers(env_name)

        # Build a map of resources by provider and type for dependency resolution
        resources_by_provider: dict[str, list[Any]] = {}
        for resource in all_resources:
            if resource.provider not in resources_by_provider:
                resources_by_provider[resource.provider] = []
            resources_by_provider[resource.provider].append(resource)

        # Add all resources to graph with their dependencies
        for resource in all_resources:
            provider_name = resource.provider
            dependencies: list[str] = []

            if provider_name in self.providers:
                provider = self.providers[provider_name]
                dependency_rules = provider.get_dependencies()

                # Check if this resource type has dependencies
                if resource.type in dependency_rules:
                    required_types = dependency_rules[resource.type]

                    # Find resources of required types from same provider
                    provider_resources = resources_by_provider.get(provider_name, [])
                    for other_resource in provider_resources:
                        if (
                            other_resource.type in required_types
                            and other_resource.name != resource.name
                        ):
                            dependencies.append(other_resource.name)

            graph.add_resource(
                provider=resource.provider,
                resource_type=resource.type,
                name=resource.name,
                dependencies=dependencies,
            )

        return graph

    def check_policies(
        self, env_name: str, resources: list[Any], enforce: bool = False
    ) -> tuple[bool, list]:
        """Check resources against policies.

        Args:
            env_name: Environment name
            resources: List of resources to check
            enforce: If True, raise exception on ERROR-level violations

        Returns:
            Tuple of (passed, violations)

        Raises:
            Exception: If enforce=True and ERROR-level violations exist
        """
        self.event_manager.emit_event(
            EventType.POLICY_CHECK_STARTED,
            env_name,
            {"resource_count": len(resources)},
        )

        violations = self.policy_engine.evaluate_resources(resources, env_name)

        # Group violations by level
        errors = [v for v in violations if v.level == PolicyLevel.ERROR]
        warnings = [v for v in violations if v.level == PolicyLevel.WARNING]
        infos = [v for v in violations if v.level == PolicyLevel.INFO]

        # Display violations
        if violations:
            self.console.print("\n[bold yellow]Policy Violations:[/bold yellow]")

            if errors:
                self.console.print(f"\n[bold red]Errors ({len(errors)}):[/bold red]")
                for v in errors:
                    self.console.print(
                        f"  [red]✗[/red] {v.resource_name} ({v.provider}): {v.message}"
                    )
                    self.event_manager.emit_event(
                        EventType.POLICY_VIOLATION,
                        env_name,
                        {
                            "policy": v.policy_name,
                            "resource": v.resource_name,
                            "level": "error",
                            "message": v.message,
                        },
                    )

            if warnings:
                self.console.print(f"\n[bold yellow]Warnings ({len(warnings)}):[/bold yellow]")
                for v in warnings:
                    self.console.print(
                        f"  [yellow]⚠[/yellow] {v.resource_name} ({v.provider}): {v.message}"
                    )
                    self.event_manager.emit_event(
                        EventType.POLICY_VIOLATION,
                        env_name,
                        {
                            "policy": v.policy_name,
                            "resource": v.resource_name,
                            "level": "warning",
                            "message": v.message,
                        },
                    )

            if infos:
                self.console.print(f"\n[dim]Info ({len(infos)}):[/dim]")
                for v in infos:
                    self.console.print(
                        f"  [dim]ℹ[/dim] {v.resource_name} ({v.provider}): {v.message}"
                    )

        # Check if policies passed
        passed = len(errors) == 0

        if passed:
            self.event_manager.emit_event(
                EventType.POLICY_CHECK_PASSED,
                env_name,
                {"violations": len(violations)},
            )
            if not violations:
                self.console.print("\n[green]✓ All policies passed[/green]")
        else:
            self.event_manager.emit_event(
                EventType.POLICY_CHECK_FAILED,
                env_name,
                {"errors": len(errors), "warnings": len(warnings)},
            )

            if enforce:
                raise Exception(
                    f"Policy check failed with {len(errors)} error(s). "
                    "Fix violations or use --skip-policies to bypass."
                )

        return passed, violations

    def detect_drift(self, env_name: str) -> dict[str, Any]:
        """Detect infrastructure drift from declared configuration.

        Compares the actual infrastructure state (from Terraform state) with
        the declared configuration to identify resources that have been
        modified, added, or deleted outside of InfraFoundry.

        Args:
            env_name: Environment name

        Returns:
            Dict with drift detection results per provider
        """
        # Emit drift check started event
        self.event_manager.emit_event(
            EventType.DRIFT_CHECK_STARTED,
            env_name,
            {"environment": env_name},
        )

        self.console.print(f"\n[bold cyan]Checking for drift in: {env_name}[/bold cyan]")

        results = {}
        drift_detected = False

        try:
            # Get all resources and discover providers dynamically
            all_resources = self.config_manager.get_all_resources_all_providers(env_name)

            # Group resources by provider
            resources_by_provider: dict[str, list[Any]] = {}
            for resource in all_resources:
                if resource.provider not in resources_by_provider:
                    resources_by_provider[resource.provider] = []
                resources_by_provider[resource.provider].append(resource)

            for provider_name, resources in resources_by_provider.items():
                if provider_name not in self.providers:
                    continue

                provider = self.providers[provider_name]

                self.console.print(f"\n[bold]Checking {provider_name}...[/bold]")

                # Run terraform plan to detect drift
                # This will compare current state with declared config
                plan_result = self._run_terraform(provider, "plan", auto_approve=False)

                # Parse the plan output to detect changes
                drift_info = self._parse_terraform_plan_for_drift(plan_result)

                if drift_info["has_changes"]:
                    drift_detected = True
                    self.console.print(
                        f"  [yellow]⚠ Drift detected: {drift_info['summary']}[/yellow]"
                    )

                    # Emit drift detected event
                    self.event_manager.emit_event(
                        EventType.DRIFT_DETECTED,
                        env_name,
                        {
                            "provider": provider_name,
                            "changes": drift_info,
                        },
                    )
                else:
                    self.console.print("  [green]✓ No drift detected[/green]")

                results[provider_name] = drift_info

            # Emit drift check completed event
            self.event_manager.emit_event(
                EventType.DRIFT_CHECK_COMPLETED,
                env_name,
                {
                    "drift_detected": drift_detected,
                    "results": results,
                },
            )

            if not drift_detected:
                self.console.print(
                    "\n[bold green]✓ All infrastructure matches declared configuration[/bold green]"
                )

        except Exception as e:
            self.console.print(f"\n[bold red]Error detecting drift:[/bold red] {e}")
            raise

        return results

    def _parse_terraform_plan_for_drift(self, plan_result: dict[str, Any]) -> dict[str, Any]:
        """Parse Terraform plan output to detect drift.

        Args:
            plan_result: Result dictionary from _run_terraform

        Returns:
            Dict with drift information
        """
        output = plan_result.get("output", "")

        # Look for Terraform's plan summary line
        # Example: "Plan: 1 to add, 2 to change, 0 to destroy."
        import re

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

    def plan(
        self,
        env_name: str,
        dry_run: bool = False,
        resource_filter: list[str] | None = None,
        enforce_policies: bool = False,
    ) -> dict[str, Any]:
        """Plan infrastructure changes.

        Args:
            env_name: Environment name
            dry_run: If True, only show what would be done
            resource_filter: Optional list of resource names to target
            enforce_policies: If True, block on policy violations

        Returns:
            Dict with plan results per provider
        """
        # Create deployment record
        deployment_id = self.state_manager.create_deployment(
            environment=env_name,
            command="plan",
            user=self._current_user,
            dry_run=dry_run,
            metadata={"resource_filter": resource_filter},
        )

        # Emit before_plan event
        self.event_manager.emit_event(
            EventType.BEFORE_PLAN,
            env_name,
            {"deployment_id": deployment_id, "dry_run": dry_run},
        )

        results = {}

        try:
            if resource_filter:
                self.console.print(
                    f"\n[bold cyan]Planning infrastructure for: {env_name} "
                    f"(resources: {', '.join(resource_filter)})[/bold cyan]"
                )
            else:
                self.console.print(
                    f"\n[bold cyan]Planning infrastructure for: {env_name}[/bold cyan]"
                )

            # Get all resources and discover providers dynamically
            all_resources = self.config_manager.get_all_resources_all_providers(env_name)

            # Check policies if there are any defined
            if self.policy_engine.policies:
                self.check_policies(env_name, all_resources, enforce=enforce_policies)

            # Group resources by provider
            resources_by_provider: dict[str, list[Any]] = {}
            for resource in all_resources:
                if resource.provider not in resources_by_provider:
                    resources_by_provider[resource.provider] = []
                resources_by_provider[resource.provider].append(resource)

            for provider_name, resources in resources_by_provider.items():
                if provider_name not in self.providers:
                    self.console.print(
                        f"[yellow]Warning: Provider '{provider_name}' not registered[/yellow]"
                    )
                    continue

                provider = self.providers[provider_name]

                # Validate resources before processing
                self.validate_resources(resources)

                # Filter resources if specified
                if resource_filter:
                    original_count = len(resources)
                    resources = [r for r in resources if r.name in resource_filter]
                    if not resources:
                        continue  # Skip provider if no matching resources
                    self.console.print(
                        f"\n[bold]{provider_name}[/bold]: {len(resources)} of "
                        f"{original_count} resources (filtered)"
                    )
                else:
                    self.console.print(
                        f"\n[bold]{provider_name}[/bold]: {len(resources)} resources"
                    )

                # Track resources in state
                for resource in resources:
                    tracked_resource = self.state_manager.track_resource(
                        deployment_id=deployment_id,
                        environment=env_name,
                        provider=provider_name,
                        resource_type=resource.type,
                        name=resource.name,
                        state=ResourceState.PLANNED,
                        config=resource.config,
                    )
                    self.event_manager.emit_event(
                        EventType.RESOURCE_PLANNED,
                        env_name,
                        {
                            "resource_id": tracked_resource.id,
                            "provider": provider_name,
                            "name": resource.name,
                        },
                    )

                if dry_run:
                    self.console.print("  [dim]Would generate Terraform and Ansible files[/dim]")
                    results[provider_name] = {"resources": len(resources), "dry_run": True}
                    continue

                # Set environment for provider to ensure correct output directory
                provider.set_environment(env_name)

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

            # Mark deployment as completed
            self.state_manager.update_deployment_status(deployment_id, DeploymentStatus.COMPLETED)

            # Emit after_plan event
            self.event_manager.emit_event(
                EventType.AFTER_PLAN,
                env_name,
                {"deployment_id": deployment_id, "results": results},
            )

        except Exception as e:
            # Mark deployment as failed
            self.state_manager.update_deployment_status(
                deployment_id, DeploymentStatus.FAILED, str(e)
            )
            self.event_manager.emit_event(
                EventType.PLAN_FAILED, env_name, {"deployment_id": deployment_id, "error": str(e)}
            )
            raise

        return results

    def apply(
        self,
        env_name: str,
        auto_approve: bool = False,
        resource_filter: list[str] | None = None,
        parallel: bool = False,
        max_workers: int = 4,
    ) -> dict[str, Any]:
        """Apply infrastructure changes.

        Args:
            env_name: Environment name
            auto_approve: If True, skip confirmation prompts
            resource_filter: Optional list of resource names to target
            parallel: If True, apply resources in parallel where possible
            max_workers: Maximum number of parallel workers (default: 4)

        Returns:
            Dict with apply results per provider
        """
        # First, generate the plans
        self.plan(env_name, dry_run=False, resource_filter=resource_filter)

        # Create deployment record for apply
        deployment_id = self.state_manager.create_deployment(
            environment=env_name,
            command="apply",
            user=self._current_user,
            dry_run=False,
            metadata={"resource_filter": resource_filter, "auto_approve": auto_approve},
        )

        # Emit before_apply event
        self.event_manager.emit_event(
            EventType.BEFORE_APPLY,
            env_name,
            {"deployment_id": deployment_id, "auto_approve": auto_approve},
        )

        results = {}

        try:
            if resource_filter:
                self.console.print(
                    f"\n[bold green]Applying infrastructure for: {env_name} "
                    f"(resources: {', '.join(resource_filter)})[/bold green]"
                )
            else:
                self.console.print(
                    f"\n[bold green]Applying infrastructure for: {env_name}[/bold green]"
                )

            # Get all resources and discover providers dynamically
            all_resources = self.config_manager.get_all_resources_all_providers(env_name)

            # Capture configuration snapshot for rollback
            rollback_snapshot = {
                "environment": env_name,
                "timestamp": datetime.utcnow().isoformat(),
                "resources": [
                    {
                        "provider": r.provider,
                        "type": r.type,
                        "name": r.name,
                        "config": r.config,
                    }
                    for r in all_resources
                ],
            }

            # Store rollback data in deployment
            self.state_manager.update_deployment_rollback_data(
                deployment_id=deployment_id, rollback_data=rollback_snapshot
            )

            # Group resources by provider
            resources_by_provider: dict[str, list[Any]] = {}
            for resource in all_resources:
                if resource.provider not in resources_by_provider:
                    resources_by_provider[resource.provider] = []
                resources_by_provider[resource.provider].append(resource)

            # Apply providers (parallel or serial based on flag)
            if parallel and len(resources_by_provider) > 1:
                results = self._apply_providers_parallel(
                    env_name=env_name,
                    deployment_id=deployment_id,
                    resources_by_provider=resources_by_provider,
                    resource_filter=resource_filter,
                    auto_approve=auto_approve,
                    max_workers=max_workers,
                )
            else:
                results = self._apply_providers_serial(
                    env_name=env_name,
                    deployment_id=deployment_id,
                    resources_by_provider=resources_by_provider,
                    resource_filter=resource_filter,
                    auto_approve=auto_approve,
                )

            # Mark deployment as completed
            self.state_manager.update_deployment_status(deployment_id, DeploymentStatus.COMPLETED)

            # Emit after_apply event
            self.event_manager.emit_event(
                EventType.AFTER_APPLY,
                env_name,
                {"deployment_id": deployment_id, "results": results},
            )

        except Exception as e:
            # Mark deployment as failed
            self.state_manager.update_deployment_status(
                deployment_id, DeploymentStatus.FAILED, str(e)
            )
            self.event_manager.emit_event(
                EventType.APPLY_FAILED, env_name, {"deployment_id": deployment_id, "error": str(e)}
            )
            raise

        return results

    def _apply_providers_serial(
        self,
        env_name: str,
        deployment_id: int,
        resources_by_provider: dict[str, list[Any]],
        resource_filter: list[str] | None,
        auto_approve: bool,
    ) -> dict[str, Any]:
        """Apply providers sequentially.

        Args:
            env_name: Environment name
            deployment_id: Deployment ID
            resources_by_provider: Dict mapping provider names to resources
            resource_filter: Optional list of resource names to target
            auto_approve: If True, skip confirmation prompts

        Returns:
            Dict with apply results per provider
        """
        results = {}

        for provider_name, resources in resources_by_provider.items():
            if provider_name not in self.providers:
                continue

            provider = self.providers[provider_name]

            # Check if any resources match filter for this provider
            if resource_filter:
                resources = [r for r in resources if r.name in resource_filter]
                if not resources:
                    continue  # Skip provider if no matching resources

            self.console.print(f"\n[bold]Applying {provider_name}...[/bold]")

            # Set environment for provider to ensure correct output directory
            provider.set_environment(env_name)

            result = self._apply_single_provider(
                env_name=env_name,
                deployment_id=deployment_id,
                provider_name=provider_name,
                provider=provider,
                resources=resources,
                auto_approve=auto_approve,
            )
            results[provider_name] = result

        return results

    def _apply_providers_parallel(
        self,
        env_name: str,
        deployment_id: int,
        resources_by_provider: dict[str, list[Any]],
        resource_filter: list[str] | None,
        auto_approve: bool,
        max_workers: int,
    ) -> dict[str, Any]:
        """Apply providers in parallel.

        Args:
            env_name: Environment name
            deployment_id: Deployment ID
            resources_by_provider: Dict mapping provider names to resources
            resource_filter: Optional list of resource names to target
            auto_approve: If True, skip confirmation prompts
            max_workers: Maximum number of parallel workers

        Returns:
            Dict with apply results per provider
        """
        results = {}
        self.console.print(
            f"\n[bold cyan]Applying {len(resources_by_provider)} providers in parallel "
            f"(max {max_workers} workers)...[/bold cyan]"
        )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all provider apply tasks
            future_to_provider = {}
            for provider_name, resources in resources_by_provider.items():
                if provider_name not in self.providers:
                    continue

                provider = self.providers[provider_name]

                # Set environment for provider to ensure correct output directory
                provider.set_environment(env_name)

                # Check if any resources match filter for this provider
                if resource_filter:
                    resources = [r for r in resources if r.name in resource_filter]
                    if not resources:
                        continue  # Skip provider if no matching resources

                future = executor.submit(
                    self._apply_single_provider,
                    env_name=env_name,
                    deployment_id=deployment_id,
                    provider_name=provider_name,
                    provider=provider,
                    resources=resources,
                    auto_approve=auto_approve,
                )
                future_to_provider[future] = provider_name

            # Collect results as they complete
            with Progress(
                SpinnerColumn(), TextColumn("[progress.description]{task.description}")
            ) as progress:
                task = progress.add_task(
                    "[cyan]Applying providers...", total=len(future_to_provider)
                )

                for future in as_completed(future_to_provider):
                    provider_name = future_to_provider[future]
                    try:
                        result = future.result()
                        results[provider_name] = result
                        self.console.print(f"[green]✓ {provider_name} completed[/green]")
                    except Exception as e:
                        self.console.print(f"[red]✗ {provider_name} failed: {e}[/red]")
                        results[provider_name] = {"error": str(e)}
                    progress.update(task, advance=1)

        return results

    def _apply_single_provider(
        self,
        env_name: str,
        deployment_id: int,
        provider_name: str,
        provider: ProviderBase,
        resources: list[Any],
        auto_approve: bool,
    ) -> dict[str, Any]:
        """Apply a single provider's resources.

        Args:
            env_name: Environment name
            deployment_id: Deployment ID
            provider_name: Provider name
            provider: Provider instance
            resources: List of resources to apply
            auto_approve: If True, skip confirmation prompts

        Returns:
            Dict with apply results
        """
        # Track resources being applied and store their IDs
        resource_ids = {}
        for resource in resources:
            tracked_resource = self.state_manager.track_resource(
                deployment_id=deployment_id,
                environment=env_name,
                provider=provider_name,
                resource_type=resource.type,
                name=resource.name,
                state=ResourceState.CREATING,
                config=resource.config,
            )
            resource_ids[resource.name] = tracked_resource.id
            self.event_manager.emit_event(
                EventType.RESOURCE_CREATING,
                env_name,
                {
                    "resource_id": tracked_resource.id,
                    "provider": provider_name,
                    "name": resource.name,
                },
            )

        # Run Terraform apply
        tf_result = self._run_terraform(provider, "apply", auto_approve)

        # Extract Terraform resource IDs from state if apply was successful
        if tf_result["success"]:
            terraform_ids = self._get_terraform_resource_ids(provider)

            # Update tracked resources with Terraform IDs
            for resource_name, terraform_id in terraform_ids.items():
                if resource_name in resource_ids:
                    db_resource_id = resource_ids[resource_name]
                    # Update resource with Terraform ID
                    self.state_manager.update_resource(
                        resource_id=db_resource_id,
                        terraform_id=terraform_id,
                    )

        # Run Ansible playbook (check mode for dry run)
        ansible_result = self._run_ansible(provider, check_mode=not auto_approve)

        # Update resource states to ACTIVE after successful apply
        for resource in resources:
            if resource.name in resource_ids:
                self.state_manager.update_resource_state(
                    resource_id=resource_ids[resource.name],
                    state=ResourceState.ACTIVE,
                )
                self.event_manager.emit_event(
                    EventType.RESOURCE_CREATED,
                    env_name,
                    {"provider": provider_name, "name": resource.name},
                )

        return {
            "terraform": tf_result,
            "ansible": ansible_result,
        }

    def destroy(
        self,
        env_name: str,
        auto_approve: bool = False,
        resource_filter: list[str] | None = None,
    ) -> dict[str, Any]:
        """Destroy infrastructure.

        Args:
            env_name: Environment name
            auto_approve: If True, skip confirmation prompts
            resource_filter: Optional list of resource names to target

        Returns:
            Dict with destroy results per provider
        """
        # Create deployment record for destroy
        deployment_id = self.state_manager.create_deployment(
            environment=env_name,
            command="destroy",
            user=self._current_user,
            dry_run=False,
            metadata={"resource_filter": resource_filter, "auto_approve": auto_approve},
        )

        # Emit before_destroy event
        self.event_manager.emit_event(
            EventType.BEFORE_DESTROY,
            env_name,
            {"deployment_id": deployment_id, "auto_approve": auto_approve},
        )

        results = {}

        try:
            if resource_filter:
                self.console.print(
                    f"\n[bold red]Destroying infrastructure for: {env_name} "
                    f"(resources: {', '.join(resource_filter)})[/bold red]"
                )
            else:
                self.console.print(
                    f"\n[bold red]Destroying infrastructure for: {env_name}[/bold red]"
                )

            if not auto_approve:
                response = input("Are you sure you want to destroy? (yes/no): ")
                if response.lower() != "yes":
                    self.console.print("[yellow]Aborted[/yellow]")
                    # Mark deployment as failed with abort message
                    self.state_manager.update_deployment_status(
                        deployment_id, DeploymentStatus.FAILED, "User aborted"
                    )
                    return {}

            # Get all resources and discover providers dynamically
            all_resources = self.config_manager.get_all_resources_all_providers(env_name)

            # Group resources by provider
            resources_by_provider: dict[str, list[Any]] = {}
            for resource in all_resources:
                if resource.provider not in resources_by_provider:
                    resources_by_provider[resource.provider] = []
                resources_by_provider[resource.provider].append(resource)

            for provider_name, resources in resources_by_provider.items():
                if provider_name not in self.providers:
                    continue

                provider = self.providers[provider_name]

                # Check if any resources match filter for this provider
                if resource_filter:
                    resources = [r for r in resources if r.name in resource_filter]
                    if not resources:
                        continue  # Skip provider if no matching resources

                self.console.print(f"\n[bold]Destroying {provider_name}...[/bold]")

                # Set environment for provider to ensure correct output directory
                provider.set_environment(env_name)

                # Track resources being destroyed and store their IDs
                resource_ids = {}
                for resource in resources:
                    tracked_resource = self.state_manager.track_resource(
                        deployment_id=deployment_id,
                        environment=env_name,
                        provider=provider_name,
                        resource_type=resource.type,
                        name=resource.name,
                        state=ResourceState.DELETING,
                        config=resource.config,
                    )
                    resource_ids[resource.name] = tracked_resource.id
                    self.event_manager.emit_event(
                        EventType.RESOURCE_DELETING,
                        env_name,
                        {
                            "resource_id": tracked_resource.id,
                            "provider": provider_name,
                            "name": resource.name,
                        },
                    )

                # Run Terraform destroy
                tf_result = self._run_terraform(provider, "destroy", auto_approve)

                # Update resource states to DELETED after successful destroy
                for resource in resources:
                    if resource.name in resource_ids:
                        self.state_manager.update_resource_state(
                            resource_id=resource_ids[resource.name],
                            state=ResourceState.DELETED,
                        )
                        self.event_manager.emit_event(
                            EventType.RESOURCE_DELETED,
                            env_name,
                            {"provider": provider_name, "name": resource.name},
                        )

                results[provider_name] = {"terraform": tf_result}

            # Mark deployment as completed
            self.state_manager.update_deployment_status(deployment_id, DeploymentStatus.COMPLETED)

            # Emit after_destroy event
            self.event_manager.emit_event(
                EventType.AFTER_DESTROY,
                env_name,
                {"deployment_id": deployment_id, "results": results},
            )

        except Exception as e:
            # Mark deployment as failed
            self.state_manager.update_deployment_status(
                deployment_id, DeploymentStatus.FAILED, str(e)
            )
            self.event_manager.emit_event(
                EventType.DESTROY_FAILED,
                env_name,
                {"deployment_id": deployment_id, "error": str(e)},
            )
            raise

        return results

    def rollback(self, deployment_id: int, auto_approve: bool = False) -> dict[str, Any]:
        """Rollback infrastructure to a previous deployment state.

        Args:
            deployment_id: ID of deployment to rollback to
            auto_approve: If True, skip confirmation prompts

        Returns:
            Dict with rollback results

        Raises:
            ValueError: If deployment not found or has no rollback data
        """
        # Get deployment with rollback data
        deployment = self.state_manager.get_deployment_by_id(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment {deployment_id} not found")

        if not deployment.rollback_data:
            raise ValueError(f"Deployment {deployment_id} has no rollback data")

        rollback_data = deployment.rollback_data
        env_name = rollback_data["environment"]

        self.console.print(
            f"\n[bold yellow]Rolling back {env_name} to deployment {deployment_id}[/bold yellow]"
        )
        self.console.print(
            f"[dim]Deployment from: {deployment.started_at.strftime('%Y-%m-%d %H:%M:%S')}[/dim]"
        )
        self.console.print(f"[dim]Resources: {len(rollback_data.get('resources', []))}[/dim]\n")

        if not auto_approve:
            confirm = input("Are you sure you want to rollback? (yes/no): ")
            if confirm.lower() != "yes":
                self.console.print("[yellow]Rollback cancelled.[/yellow]")
                return {}

        # Create deployment record for rollback
        rollback_deployment_id = self.state_manager.create_deployment(
            environment=env_name,
            command="apply",
            user=self._current_user,
            dry_run=False,
            metadata={"rollback_from": deployment_id, "rollback": True},
        )

        try:
            # Write rollback configurations to temporary files
            # For now, we'll use the current config structure and rely on users
            # having the correct configuration in their repo
            # In a production system, you'd want to write the configs to temp files

            self.console.print(
                f"\n[bold yellow]⚠ Note: Rollback requires the configuration "
                f"repository to be at the state from deployment {deployment_id}[/bold yellow]"
            )
            self.console.print(
                "[dim]Consider using git to checkout the appropriate commit if needed.[/dim]\n"
            )

            # Apply the infrastructure using current configuration
            # This assumes the user has set their config repo to the correct state
            results = self.apply(env_name, auto_approve=True, resource_filter=None)

            self.state_manager.update_deployment_status(
                rollback_deployment_id, DeploymentStatus.COMPLETED
            )

            self.console.print(
                f"\n[bold green]✓ Rollback to deployment {deployment_id} completed![/bold green]"
            )

            return results

        except Exception as e:
            self.state_manager.update_deployment_status(
                rollback_deployment_id, DeploymentStatus.FAILED, str(e)
            )
            self.console.print(f"\n[bold red]✗ Rollback failed: {e}[/bold red]")
            raise

    def _get_terraform_resource_ids(self, provider: ProviderBase) -> dict[str, str]:
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
        table = Table(title=f"Infrastructure Status: {env_name}")
        table.add_column("Provider", style="cyan")
        table.add_column("Resources", style="magenta")
        table.add_column("Status", style="green")

        # Get all resources and discover providers dynamically
        all_resources = self.config_manager.get_all_resources_all_providers(env_name)

        # Group resources by provider
        resources_by_provider: dict[str, list[Any]] = {}
        for resource in all_resources:
            if resource.provider not in resources_by_provider:
                resources_by_provider[resource.provider] = []
            resources_by_provider[resource.provider].append(resource)

        for provider_name, resources in sorted(resources_by_provider.items()):
            if provider_name not in self.providers:
                table.add_row(provider_name, "N/A", "[yellow]Not registered[/yellow]")
                continue

            provider = self.providers[provider_name]

            # Check if Terraform state exists
            state_file = provider.terraform_dir / "terraform.tfstate"
            status = "[green]Deployed[/green]" if state_file.exists() else "[dim]Not deployed[/dim]"

            table.add_row(provider_name, str(len(resources)), status)

        self.console.print(table)
