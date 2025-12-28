"""Detect infrastructure drift and remediation commands."""

import click
from rich.table import Table

from infrafoundry.core.config.models import DriftRemediationConfig
from infrafoundry.core.drift_remediation import DriftRemediator
from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...utils import console, raise_cli_error


@click.group()
def drift() -> None:
    """Detect and remediate infrastructure drift."""
    pass


@drift.command("detect")
@click.option("--env", "-e", required=True, help="Environment name")
@with_orchestrator("Drift detection failed")
def drift_detect(_ctx: click.Context, orchestrator: Orchestrator, env: str) -> None:
    """Detect infrastructure drift from declared configuration.

    Checks if actual infrastructure state matches the declared configuration
    by running terraform plan and identifying any unexpected changes.
    """
    # Run drift detection
    results = orchestrator.detect_drift(env)

    # Display detailed results
    console.info("")
    console.header("Drift Detection Results")

    total_drift = False
    for provider_name, drift_info in results.items():
        if drift_info.get("has_changes"):
            total_drift = True

            table = Table(title=f"{provider_name.title()} Drift")
            table.add_column("Change Type", style="cyan")
            table.add_column("Count", style="yellow")

            if drift_info.get("to_add", 0) > 0:
                table.add_row("To Add", str(drift_info["to_add"]))
            if drift_info.get("to_change", 0) > 0:
                table.add_row("To Change", str(drift_info["to_change"]))
            if drift_info.get("to_destroy", 0) > 0:
                table.add_row("To Destroy", str(drift_info["to_destroy"]))

            console.print(table)

            console.warning(f"Summary: {drift_info['summary']}")

    if not total_drift:
        console.success("No drift detected - infrastructure matches configuration")
    else:
        console.warning("Drift detected!")
        console.status("Run 'infra plan' to see detailed changes, or 'infra apply' to reconcile.")


@drift.command("remediate")
@click.option("--env", "-e", required=True, help="Environment name")
@click.option(
    "--auto-approve",
    is_flag=True,
    help="Automatically approve remediation if within thresholds",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Detect drift and show remediation decision without applying",
)
@click.option(
    "--max-changes",
    type=int,
    help="Override max total changes threshold",
)
@click.option(
    "--max-add",
    type=int,
    help="Override max resources to add threshold",
)
@click.option(
    "--max-change",
    type=int,
    help="Override max resources to change threshold",
)
@click.option(
    "--max-destroy",
    type=int,
    help="Override max resources to destroy threshold",
)
@with_orchestrator("Drift remediation failed")
def drift_remediate(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    auto_approve: bool,
    dry_run: bool,
    max_changes: int | None,
    max_add: int | None,
    max_change: int | None,
    max_destroy: int | None,
) -> None:
    """Detect drift and automatically remediate if within configured thresholds.

    This command detects infrastructure drift and optionally applies changes
    automatically if they are within configured safety thresholds.

    Examples:

        # Detect drift and show what would be remediated
        infra drift remediate --env dev --dry-run

        # Auto-remediate if within configured thresholds
        infra drift remediate --env dev --auto-approve

        # Override max changes threshold for this run
        infra drift remediate --env dev --auto-approve --max-changes 10

        # Set custom thresholds for different operations
        infra drift remediate --env dev --auto-approve --max-add 5 --max-change 3 --max-destroy 0

    IMPORTANT: Ensure drift_remediation is configured in your environment settings.yaml
    """
    try:
        # Load environment config to get drift remediation settings
        env_config = orchestrator.config_manager.load_environment(env)
        if not env_config:
            raise click.ClickException(f"Environment '{env}' not found")

        # Get or create drift remediation config
        remediation_config = env_config.drift_remediation or DriftRemediationConfig()

        # Apply CLI overrides
        if dry_run:
            remediation_config.dry_run = True
        if auto_approve:
            remediation_config.enabled = True
        if max_changes is not None:
            remediation_config.auto_apply_threshold = max_changes
        if max_add is not None:
            remediation_config.max_to_add = max_add
        if max_change is not None:
            remediation_config.max_to_change = max_change
        if max_destroy is not None:
            remediation_config.max_to_destroy = max_destroy

        console.info("")
        console.header(f"Drift Remediation: {env}")

        # Show configuration
        console.print("\n[cyan]Configuration:[/cyan]")
        console.print(f"  Enabled: {remediation_config.enabled}")
        console.print(f"  Dry Run: {remediation_config.dry_run}")
        console.print(f"  Max Total Changes: {remediation_config.auto_apply_threshold}")
        console.print(f"  Max To Add: {remediation_config.max_to_add}")
        console.print(f"  Max To Change: {remediation_config.max_to_change}")
        console.print(f"  Max To Destroy: {remediation_config.max_to_destroy}")

        # Initialize remediator
        remediator = DriftRemediator(
            drift_detector=orchestrator.drift_detector,
            event_manager=orchestrator.event_manager,
        )

        # Run remediation
        console.print("\n[cyan]Detecting drift...[/cyan]")
        results = remediator.remediate(
            env_name=env,
            config=remediation_config,
            apply_fn=orchestrator.apply,
        )

        # Display results
        console.print("\n[cyan]Results:[/cyan]")

        if not results["drift_detected"]:
            console.success("✓ No drift detected - infrastructure matches configuration")
            return

        # Show drift details
        drift_info = results.get("drift_info", {})
        console.warning(
            f"Drift detected: {drift_info.get('to_add', 0)} to add, "
            f"{drift_info.get('to_change', 0)} to change, "
            f"{drift_info.get('to_destroy', 0)} to destroy"
        )
        console.print(f"  Providers: {', '.join(results['providers_with_drift'])}")

        # Show remediation decision
        console.print(f"\n[cyan]Remediation Decision:[/cyan] {results['reason']}")

        if results["auto_applied"]:
            console.success("✓ Drift automatically remediated!")
            console.print("\n[cyan]Remediation completed successfully[/cyan]")
        elif remediation_config.dry_run:
            console.status("Dry-run mode - no changes applied")
        elif not remediation_config.enabled:
            console.status(
                "Drift remediation disabled. Enable in settings.yaml or use --auto-approve"
            )
        else:
            console.status(
                "Drift not remediated automatically. Run 'infra apply' to remediate manually."
            )

    except click.ClickException:
        raise
    except Exception as exc:
        raise_cli_error("Drift remediation failed", exc)


@drift.command("history")
@click.option("--env", "-e", help="Filter by environment name")
@click.option("--limit", "-n", type=int, default=10, help="Number of entries to show (default: 10)")
@with_orchestrator("Failed to retrieve remediation history")
def drift_history(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str | None,
    limit: int,
) -> None:
    """Show drift remediation history.

    Displays a history of automated and manual drift remediation actions,
    including when drift was detected, whether it was auto-remediated,
    and the results of the remediation.

    Examples:

        # Show last 10 remediation entries
        infra drift history

        # Show last 20 entries for dev environment
        infra drift history --env dev --limit 20

        # Show all recent remediation attempts
        infra drift history --limit 50
    """
    try:
        console.info("")
        console.header("Drift Remediation History")

        # Initialize remediator to access history
        remediator = DriftRemediator(
            drift_detector=orchestrator.drift_detector,
            event_manager=orchestrator.event_manager,
        )

        history = remediator.get_history(env_name=env, limit=limit)

        if not history:
            console.info("No remediation history found")
            return

        # Display history table
        table = Table(title=f"Remediation History ({len(history)} entries)")
        table.add_column("Timestamp", style="cyan")
        table.add_column("Environment", style="yellow")
        table.add_column("Drift", style="magenta")
        table.add_column("Auto-Applied", style="green")
        table.add_column("Reason", style="white")

        for entry in history:
            timestamp = entry.get("timestamp", "Unknown")
            env_name = entry.get("env_name", "Unknown")
            drift_detected = "Yes" if entry.get("drift_detected") else "No"
            auto_applied = "Yes" if entry.get("auto_applied") else "No"
            reason = entry.get("reason", "N/A")

            # Truncate reason if too long
            if len(reason) > 60:
                reason = reason[:57] + "..."

            table.add_row(timestamp, env_name, drift_detected, auto_applied, reason)

        console.print(table)

        # Show summary
        drift_count = sum(1 for e in history if e.get("drift_detected"))
        remediated_count = sum(1 for e in history if e.get("auto_applied"))

        console.print("\n[cyan]Summary:[/cyan]")
        console.print(f"  Total checks: {len(history)}")
        console.print(f"  Drift detected: {drift_count}")
        console.print(f"  Auto-remediated: {remediated_count}")

    except Exception as exc:
        raise_cli_error("Failed to retrieve remediation history", exc)
