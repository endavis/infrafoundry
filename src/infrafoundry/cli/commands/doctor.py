"""Doctor command - Check InfraFoundry system dependencies."""

import shutil

import click

from .doctor_utils import (
    CheckResult,
    check_dependency,
    console,
    render_check_results_json,
    render_check_results_text,
)


def _check_iac_tool() -> CheckResult:
    """Check that at least one supported IaC runner is installed.

    Terraform and OpenTofu are alternatives — only one is required. If both
    are installed, the result notes both paths. If neither is installed, the
    check fails with install instructions for both.

    Returns:
        A single ``CheckResult`` summarizing IaC tool availability.
    """
    tf_path = shutil.which("terraform")
    tofu_path = shutil.which("tofu")

    if tf_path and tofu_path:
        return CheckResult(
            name="IaC Tool",
            status="ok",
            message=f"Terraform: {tf_path}; OpenTofu: {tofu_path}",
        )
    if tf_path:
        return CheckResult(
            name="IaC Tool",
            status="ok",
            message=f"Terraform found at {tf_path}",
        )
    if tofu_path:
        return CheckResult(
            name="IaC Tool",
            status="ok",
            message=f"OpenTofu found at {tofu_path}",
        )
    return CheckResult(
        name="IaC Tool",
        status="error",
        message="Neither Terraform nor OpenTofu found",
        suggestion=(
            "Install one of: Terraform (https://terraform.io/downloads) "
            "or OpenTofu (https://opentofu.org/docs/intro/install/)"
        ),
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

    Validates that all required CLI tools are installed and available on the
    PATH: an IaC tool (Terraform or OpenTofu — either works), Ansible, SOPS,
    and Age.

    Use 'config doctor' for configuration-level checks and
    'infra doctor' for provider API validation.
    """
    results: list[CheckResult] = []

    if output_format == "text":
        console.print()
        console.print("[bold cyan]InfraFoundry Doctor[/bold cyan]")
        console.print()
        console.print("[bold]Checking system dependencies...[/bold]")

    results.append(_check_iac_tool())
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
