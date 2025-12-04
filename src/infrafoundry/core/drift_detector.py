"""Drift detection for infrastructure resources."""

import traceback
from typing import Any

from rich.console import Console

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.events import EventManager, EventType
from infrafoundry.core.exceptions import (
    ConfigurationError,
    InfraFoundryError,
    TerraformError,
)
from infrafoundry.core.protocols import DriftDetectable
from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.runners import RunnerRegistry


class DriftDetector:
    """Detects infrastructure drift from declared configuration."""

    def __init__(
        self,
        config_manager: ConfigManager,
        runner_registry: RunnerRegistry,
        event_manager: EventManager,
        providers: dict[str, ProviderBase],
        console: Console | None = None,
    ) -> None:
        """Initialize drift detector.

        Args:
            config_manager: Configuration manager instance
            runner_registry: Registry for creating tool runners
            event_manager: Event manager for notifications
            providers: Dict of registered provider instances
            console: Rich console for output (creates default if None)
        """
        self.config_manager = config_manager
        self.runner_registry = runner_registry
        self.event_manager = event_manager
        self.providers = providers
        self.console = console or Console()

    def detect(self, env_name: str) -> dict[str, Any]:
        """Detect infrastructure drift from declared configuration.

        Compares the actual infrastructure state (from Terraform state) with
        the declared configuration to identify resources that have been
        modified, added, or deleted outside of InfraFoundry.

        Args:
            env_name: Environment name

        Returns:
            Dict with drift detection results per provider:
                {
                    "provider_name": {
                        "has_changes": bool,
                        "to_add": int,
                        "to_change": int,
                        "to_destroy": int,
                        "summary": str,
                        "raw_output": str
                    }
                }
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

        # Dynamically create the runner
        terraform_runner = self.runner_registry.create_runner("terraform", console=self.console)
        if not terraform_runner:
            raise InfraFoundryError("Could not create terraform runner")

        try:
            # Get all resources and discover providers dynamically
            all_resources = self.config_manager.get_all_resources_all_providers(env_name)

            # Group resources by provider
            resources_by_provider: dict[str, list[Any]] = {}
            for resource in all_resources:
                if resource.provider not in resources_by_provider:
                    resources_by_provider[resource.provider] = []
                resources_by_provider[resource.provider].append(resource)

            for provider_name, _resources in resources_by_provider.items():
                if provider_name not in self.providers:
                    continue

                provider = self.providers[provider_name]

                self.console.print(f"\n[bold]Checking {provider_name}...[/bold]")

                # Run terraform plan to detect drift
                # This will compare current state with declared config
                plan_result = terraform_runner.run(provider, "plan", auto_approve=False)

                if not isinstance(terraform_runner, DriftDetectable):
                    self.console.print(
                        f"  [yellow]⚠ Runner {terraform_runner.tool_name} "
                        "does not support drift detection[/yellow]"
                    )
                    continue

                # Parse the plan output to detect changes
                drift_info = terraform_runner.parse_plan_for_drift(plan_result)

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

        except (ConfigurationError, TerraformError) as e:
            self.console.print(f"\n[bold red]Error detecting drift:[/bold red] {e}")
            raise
        except InfraFoundryError as e:
            self.console.print(f"\n[bold red]InfraFoundry error detecting drift:[/bold red] {e}")
            raise
        except Exception as e:
            self.console.print(f"\n[bold red]Unexpected error detecting drift:[/bold red] {e}")
            self.console.print(traceback.format_exc(), style="dim red")  # Log full traceback
            raise

        return results
