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


def _check_iac_tools() -> list[CheckResult]:
    """Check for Terraform and OpenTofu as alternative IaC runners.

    Only one is required. If at least one is installed, the missing one is
    reported as a warning (optional alternative). If neither is installed,
    both are reported as errors.

    Returns:
        Check results for Terraform followed by OpenTofu.
    """
    tf_path = shutil.which("terraform")
    tofu_path = shutil.which("tofu")
    has_any = bool(tf_path or tofu_path)

    def _result(name: str, path: str | None, install_url: str) -> CheckResult:
        if path:
            return CheckResult(name=name, status="ok", message=f"Found at {path}")
        if has_any:
            return CheckResult(
                name=name,
                status="warning",
                message="Not found (optional alternative)",
                suggestion=f"Optional; install from {install_url} if you prefer it",
            )
        return CheckResult(
            name=name,
            status="error",
            message="Not found",
            suggestion=f"Install from {install_url}",
        )

    return [
        _result("Terraform", tf_path, "https://terraform.io/downloads"),
        _result("OpenTofu", tofu_path, "https://opentofu.org/docs/intro/install/"),
    ]


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

    results.extend(_check_iac_tools())
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
