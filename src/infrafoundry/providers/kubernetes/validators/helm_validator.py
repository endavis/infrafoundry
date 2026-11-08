"""Helm release validation for Kubernetes provider."""

from __future__ import annotations

from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.kubernetes.validators.context import KubernetesHelmContext


class HelmValidator(SpecializedValidator[KubernetesHelmContext]):
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

    @override
    def validate(self, context: KubernetesHelmContext) -> None:
        """Validate helm release resources have required fields.

        Args:
            context: Helm release resources to validate.
        """
        helm_releases = context.helm_releases
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
