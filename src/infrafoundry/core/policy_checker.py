"""Policy validation for infrastructure resources."""

from typing import Any

from rich.console import Console

from infrafoundry.core.events import EventManager, EventType
from infrafoundry.core.policy import PolicyEngine, PolicyLevel


class PolicyChecker:
    """Validates resources against infrastructure policies."""

    def __init__(
        self,
        policy_engine: PolicyEngine,
        event_manager: EventManager,
        console: Console | None = None,
    ) -> None:
        """Initialize policy checker.

        Args:
            policy_engine: Policy engine instance
            event_manager: Event manager for notifications
            console: Rich console for output (creates default if None)
        """
        self.policy_engine = policy_engine
        self.event_manager = event_manager
        self.console = console or Console()

    def check(
        self, env_name: str, resources: list[Any], enforce: bool = False
    ) -> tuple[bool, list]:
        """Check resources against policies.

        Args:
            env_name: Environment name
            resources: List of resources to check
            enforce: If True, raise exception on ERROR-level violations

        Returns:
            Tuple of (passed, violations) where:
                - passed: bool indicating if all policies passed (no errors)
                - violations: list of policy violations found

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
