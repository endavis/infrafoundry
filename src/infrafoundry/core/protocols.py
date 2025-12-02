"""Protocol classes for structural subtyping in InfraFoundry.

Protocols provide duck-typing interfaces without requiring inheritance,
offering more flexibility than abstract base classes (ABCs) in type hints.

Example:
    >>> from infrafoundry.core.protocols import HasLogger
    >>>
    >>> def log_operation(obj: HasLogger, message: str) -> None:
    ...     obj.logger.info(message)
    >>>
    >>> # Works with any object that has a logger property
    >>> log_operation(my_manager, "Operation started")
    >>> log_operation(my_provider, "Generation complete")
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from jinja2 import Template

if TYPE_CHECKING:
    from infrafoundry.core.provider import ProviderBase, ResourceConfig


@runtime_checkable
class HasLogger(Protocol):
    """Protocol for objects that have a logger.

    Any class with a `logger` property that returns a logging.Logger
    satisfies this protocol, enabling flexible logging across the codebase.

    Example:
        >>> def debug_log(obj: HasLogger, message: str) -> None:
        ...     obj.logger.debug(message)
    """

    @property
    def logger(self) -> logging.Logger:
        """Logger instance for this object."""
        ...


@runtime_checkable
class HasTemplateRenderer(Protocol):
    """Protocol for objects that can render Jinja2 templates.

    Classes implementing TemplateRendererMixin or providing equivalent
    functionality satisfy this protocol.

    Example:
        >>> def render_config(obj: HasTemplateRenderer, template: str) -> str:
        ...     return obj.render_template(template, {"env": "prod"})
    """

    def render_template(self, template_name: str, context: dict[str, Any]) -> str:
        """Render a template with given context.

        Args:
            template_name: Name or path of the template
            context: Template variables

        Returns:
            Rendered template content
        """
        ...

    def get_template(self, template_name: str) -> Template:
        """Load a template by name.

        Args:
            template_name: Name or path of the template

        Returns:
            Loaded Jinja2 template object
        """
        ...


@runtime_checkable
class HasResourceGrouper(Protocol):
    """Protocol for objects that can group resources by type.

    Classes implementing ResourceGrouperMixin or providing equivalent
    functionality satisfy this protocol.

    Example:
        >>> def process_by_type(obj: HasResourceGrouper, resources: list) -> None:
        ...     grouped = obj.group_resources_by_type(resources)
        ...     for type_name, items in grouped.items():
        ...         print(f"Processing {len(items)} {type_name} resources")
    """

    def group_resources_by_type(
        self, resources: list["ResourceConfig"]
    ) -> dict[str, list["ResourceConfig"]]:
        """Group resources by their type field.

        Args:
            resources: List of resource configurations

        Returns:
            Dictionary mapping resource types to lists of resources
        """
        ...


# Runner Protocol Interfaces (for Interface Segregation)


@runtime_checkable
class Plannable(Protocol):
    """Protocol for runners that can generate execution plans.

    Runners supporting plan operations (like Terraform) satisfy this protocol.

    Example:
        >>> def create_plan(runner: Plannable, provider: ProviderBase) -> dict:
        ...     return runner.plan(provider)
    """

    def plan(self, provider: "ProviderBase", **kwargs: Any) -> dict[str, Any]:
        """Generate an execution plan.

        Args:
            provider: Provider instance to plan for
            **kwargs: Additional plan options

        Returns:
            Plan result dictionary
        """
        ...


@runtime_checkable
class Applyable(Protocol):
    """Protocol for runners that can apply infrastructure changes.

    All runners supporting apply operations satisfy this protocol.

    Example:
        >>> def apply_changes(runner: Applyable, provider: ProviderBase) -> dict:
        ...     return runner.apply(provider, auto_approve=True)
    """

    def apply(self, provider: "ProviderBase", **kwargs: Any) -> dict[str, Any]:
        """Apply infrastructure changes.

        Args:
            provider: Provider instance to apply
            **kwargs: Additional apply options (e.g., auto_approve)

        Returns:
            Apply result dictionary
        """
        ...


@runtime_checkable
class Destroyable(Protocol):
    """Protocol for runners that can destroy infrastructure.

    All runners supporting destroy operations satisfy this protocol.

    Example:
        >>> def cleanup(runner: Destroyable, provider: ProviderBase) -> dict:
        ...     return runner.destroy(provider, auto_approve=True)
    """

    def destroy(self, provider: "ProviderBase", **kwargs: Any) -> dict[str, Any]:
        """Destroy infrastructure resources.

        Args:
            provider: Provider instance to destroy
            **kwargs: Additional destroy options

        Returns:
            Destroy result dictionary
        """
        ...


@runtime_checkable
class DriftDetectable(Protocol):
    """Protocol for runners that can detect configuration drift.

    Runners supporting drift detection (like Terraform) satisfy this protocol.

    Example:
        >>> def check_drift(runner: DriftDetectable, plan: dict) -> dict:
        ...     return runner.parse_plan_for_drift(plan)
    """

    def parse_plan_for_drift(self, plan_result: dict[str, Any]) -> dict[str, Any]:
        """Parse plan output to detect configuration drift.

        Args:
            plan_result: Plan result to analyze for drift

        Returns:
            Dictionary with drift information (changes, additions, deletions)
        """
        ...


@runtime_checkable
class StateAware(Protocol):
    """Protocol for runners that track infrastructure state.

    Runners that manage state (like Terraform) satisfy this protocol.

    Example:
        >>> def list_resources(runner: StateAware, provider: ProviderBase) -> dict:
        ...     return runner.get_resource_ids(provider)
    """

    def get_resource_ids(self, provider: "ProviderBase") -> dict[str, str]:
        """Get mapping of resource names to their IDs from state.

        Args:
            provider: Provider instance to query state for

        Returns:
            Dictionary mapping resource names to infrastructure IDs
        """
        ...


# Path-related Protocols


@runtime_checkable
class HasPathResolution(Protocol):
    """Protocol for objects that can resolve filesystem paths.

    Managers implementing PathBasedManager or equivalent functionality
    satisfy this protocol.

    Example:
        >>> def get_config_path(obj: HasPathResolution) -> Path:
        ...     return obj._resolve_path(None, env_var="CONFIG_DIR", default="config")
    """

    def _resolve_path(
        self,
        path: Path | str | None,
        env_var: str | None = None,
        default: str | Path | None = None,
        create: bool = False,
    ) -> Path:
        """Resolve a path with environment variable and default fallback.

        Args:
            path: Explicit path to use
            env_var: Environment variable name to check
            default: Default path if neither path nor env_var is set
            create: Whether to create the directory if it doesn't exist

        Returns:
            Resolved Path object
        """
        ...


# Logging Helper Protocols


@runtime_checkable
class HasStructuredLogging(Protocol):
    """Protocol for objects with structured logging methods.

    Classes inheriting from BaseManager or implementing equivalent logging
    methods satisfy this protocol.

    Example:
        >>> def log_operation(obj: HasStructuredLogging, operation: str) -> None:
        ...     obj._log_info(f"Starting {operation}")
        ...     try:
        ...         # ... operation logic ...
        ...         obj._log_info(f"Completed {operation}")
        ...     except Exception as e:
        ...         obj._log_error(f"Failed {operation}", exception=e)
    """

    def _log_info(self, message: str, **kwargs: Any) -> None:
        """Log info message with optional context."""
        ...

    def _log_warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message with optional context."""
        ...

    def _log_error(self, message: str, exception: Exception | None = None, **kwargs: Any) -> None:
        """Log error message with optional exception and context."""
        ...

    def _log_debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message with optional context."""
        ...
