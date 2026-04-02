"""Helm release validation for Kubernetes provider."""

from __future__ import annotations

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class HelmValidator:
    """Validates Helm release resource configurations.

    Performs local (report-only) validation that helm_release resources
    have the required fields (chart, repository). No API calls are made.
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize Helm validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    def validate(self, helm_releases: list[ResourceConfig]) -> None:
        """Validate helm release resources have required fields.

        Args:
            helm_releases: Helm release resources to validate
        """
        if not helm_releases:
            return

        for release in helm_releases:
            config = release.config or {}
            name = release.name

            has_chart = bool(config.get("chart"))
            has_repository = bool(config.get("repository"))

            if not has_chart:
                self.report.add_check(
                    check_name=f"kubernetes_helm_{name}_chart",
                    passed=False,
                    message=f"Helm release '{name}' is missing required 'chart' field",
                    level=ValidationLevel.ERROR,
                )

            if not has_repository:
                self.report.add_check(
                    check_name=f"kubernetes_helm_{name}_repository",
                    passed=False,
                    message=f"Helm release '{name}' is missing required 'repository' field",
                    level=ValidationLevel.ERROR,
                )

            if has_chart and has_repository:
                self.report.add_check(
                    check_name=f"kubernetes_helm_{name}",
                    passed=True,
                    message=(
                        f"Helm release '{name}' has valid chart "
                        f"'{config['chart']}' from '{config['repository']}'"
                    ),
                )
