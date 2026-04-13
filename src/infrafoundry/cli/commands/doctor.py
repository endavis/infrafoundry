"""Doctor command - Check InfraFoundry system dependencies."""

import click

from .doctor_utils import (
    CheckResult,
    check_dependency,
    console,
    render_check_results_json,
    render_check_results_text,
)


@click.command()
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
@click.pass_context
def doctor(ctx: click.Context, output_format: str) -> None:
    """Check system dependencies for InfraFoundry.

    Validates that all required CLI tools (Terraform, OpenTofu, Ansible,
    SOPS, Age) are installed and available on the PATH.

    Use 'config doctor' for configuration-level checks and
    'infra doctor' for provider API validation.
    """
    results: list[CheckResult] = []

    if output_format == "text":
        console.print()
        console.print("[bold cyan]InfraFoundry Doctor[/bold cyan]")
        console.print()
        console.print("[bold]Checking system dependencies...[/bold]")

    results.append(
        check_dependency(
            "Terraform",
            "terraform",
            "Install from https://terraform.io/downloads",
        )
    )
    results.append(
        check_dependency(
            "OpenTofu",
            "tofu",
            "Install from https://opentofu.org/docs/intro/install/",
        )
    )
    results.append(
        check_dependency(
            "Ansible",
            "ansible",
            "Install with: pip install ansible",
        )
    )
    results.append(
        check_dependency(
            "SOPS",
            "sops",
            "Install from https://github.com/getsops/sops",
        )
    )
    results.append(
        check_dependency(
            "Age",
            "age",
            "Install from https://github.com/FiloSottile/age",
        )
    )

    if output_format == "json":
        render_check_results_json(results)
    else:
        render_check_results_text(results)
