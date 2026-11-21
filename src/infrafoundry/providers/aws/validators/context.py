"""Validation contexts for the AWS sub-validators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationContext


@dataclass(frozen=True, kw_only=True)
class AWSConfigContext(ValidationContext):
    """Context for the resource-config validators.

    Attributes:
        security_group_names: Names of the declared ``security_group`` resources.
        instances_by_name: Declared ``instance`` resources keyed by name.
    """

    security_group_names: frozenset[str] = frozenset()
    instances_by_name: dict[str, ResourceConfig] = field(default_factory=dict)

    @classmethod
    def from_resources(
        cls,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig] | None = None,
    ) -> AWSConfigContext:
        """Build a context with the cross-reference indexes filled in.

        Args:
            resources: All AWS resources being validated.
            reference_resources: Every AWS resource in the environment; the name
                indexes are built from it plus ``resources`` (#1568).

        Returns:
            A context carrying ``resources`` and the name indexes.
        """
        pool = [*(reference_resources or []), *resources]
        return cls(
            resources=resources,
            reference_resources=list(reference_resources or []),
            security_group_names=frozenset(r.name for r in pool if r.type == "security_group"),
            instances_by_name={r.name: r for r in pool if r.type == "instance"},
        )


@dataclass(frozen=True, kw_only=True)
class AWSSettingsContext(ValidationContext):
    """Context for the provider-settings validator.

    Attributes:
        provider_settings: The ``provider_settings.aws`` mapping.
        env_region: True when ``AWS_REGION`` or ``AWS_DEFAULT_REGION`` is set.
    """

    provider_settings: dict[str, Any] = field(default_factory=dict)
    env_region: bool = False
