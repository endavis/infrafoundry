"""Type definitions for runner operation results.

This module defines TypedDict classes for type-safe result handling
from runner operations. Using TypedDict provides IDE autocomplete and
mypy type checking while maintaining backward compatibility with existing
dict-based code.
"""

from typing import NotRequired, TypedDict


class BaseResult(TypedDict):
    """Base result for all runner operations.

    All runner operations return at minimum a success flag.
    Additional fields are operation-specific.
    """

    success: bool
    """Whether the operation completed successfully."""

    exit_code: NotRequired[int]
    """Exit code from the underlying tool (if applicable)."""

    error: NotRequired[str]
    """Error message if operation failed."""

    output: NotRequired[str]
    """Raw output from the tool."""


class PlanResult(BaseResult):
    """Result from plan operation.

    Plan operations generate an execution plan showing what changes
    would be made without actually applying them.
    """

    has_changes: NotRequired[bool]
    """Whether the plan detected any changes."""

    changes_summary: NotRequired[str]
    """Human-readable summary of planned changes."""

    plan_file: NotRequired[str]
    """Path to saved plan file (Terraform-specific)."""


class ApplyResult(BaseResult):
    """Result from apply operation.

    Apply operations make actual changes to infrastructure.
    """

    resources_created: NotRequired[int]
    """Number of resources created."""

    resources_updated: NotRequired[int]
    """Number of resources updated."""

    resources_deleted: NotRequired[int]
    """Number of resources deleted."""


class DestroyResult(BaseResult):
    """Result from destroy operation.

    Destroy operations remove infrastructure resources.
    """

    resources_destroyed: NotRequired[int]
    """Number of resources destroyed."""


class DriftInfo(TypedDict):
    """Information about infrastructure drift.

    Drift detection compares actual infrastructure state against
    declared configuration to find discrepancies.
    """

    has_changes: bool
    """Whether drift was detected."""

    summary: str
    """Human-readable drift summary."""

    added: NotRequired[int]
    """Number of resources that exist but shouldn't."""

    changed: NotRequired[int]
    """Number of resources that differ from config."""

    destroyed: NotRequired[int]
    """Number of resources that should exist but don't."""


class ResourceIds(TypedDict):
    """Mapping of resource names to infrastructure IDs.

    Used by state-aware runners to track resource identifiers
    in the infrastructure provider's system.
    """

    # Dynamic keys - resource name -> ID
    # Example: {"vm1": "i-1234567890abcdef0", "vm2": "i-0987654321fedcba0"}
