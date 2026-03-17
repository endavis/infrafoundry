"""Event context and result models."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.events.types import EventType
from infrafoundry.core.types import DeploymentEventData, ResourceEventData, RunnerEventData

# Backward compatibility type aliases from legacy EventManager
type EventPayload = ResourceEventData | DeploymentEventData | RunnerEventData | dict[str, Any]


@dataclass
class EventContext:
    """Context passed to event handlers.

    Provides handlers with information about the current operation,
    environment, and any relevant data.

    Attributes:
        event_type: Type of event being handled
        environment: Environment name (e.g., "dev", "prod")
        data: Event-specific data dictionary
        provider: Provider name if applicable (e.g., "proxmox")
        resource: Resource name if applicable
        runner: Runner name if applicable (e.g., "terraform")
        deployment_id: Deployment ID if in a deployment context
        plan_output: Plan output data if available
        target_resources: Resource names targeted by -r filter (None = all)
        previous_results: Results from previous handlers in chain
    """

    event_type: EventType
    environment: str
    data: dict[str, Any] = field(default_factory=dict)
    provider: str | None = None
    resource: str | None = None
    runner: str | None = None
    deployment_id: int | None = None
    plan_output: dict[str, Any] | None = None
    target_resources: list[str] | None = None
    previous_results: list["EventResult"] = field(default_factory=list)
    package_variables: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        parts = [f"EventContext({self.event_type.value}, env={self.environment}"]
        if self.provider:
            parts.append(f", provider={self.provider}")
        if self.resource:
            parts.append(f", resource={self.resource}")
        parts.append(")")
        return "".join(parts)


@dataclass
class EventResult:
    """Result returned by an event handler.

    Handlers can signal whether to continue or abort the workflow,
    and provide additional data or messages.

    Attributes:
        success: Whether the handler executed successfully
        abort: If True, abort the current workflow
        reason: Human-readable reason for abort or failure
        data: Additional data returned by the handler
        stdout: Captured stdout (for script handlers)
        stderr: Captured stderr (for script handlers)
        duration_seconds: Execution time
        handler_name: Name of the handler that produced this result
    """

    success: bool = True
    abort: bool = False
    reason: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    handler_name: str = ""

    @property
    def continue_workflow(self) -> bool:
        """Whether the workflow should continue after this handler."""
        return self.success and not self.abort

    def __repr__(self) -> str:
        status = "success" if self.success else "failed"
        if self.abort:
            status = "aborted"
        return f"EventResult({status}, handler={self.handler_name})"


class Event:
    """Event object for the unified event system.

    Supports both legacy and new APIs:
    - Legacy: Event(event_type, environment, data)
    - New: Event(context=EventContext(...))
    """

    def __init__(
        self,
        event_type_or_context: EventType | EventContext | None = None,
        environment: str | None = None,
        data: dict[str, Any] | None = None,
        *,
        context: EventContext | None = None,
    ) -> None:
        """Initialize event.

        Args:
            event_type_or_context: EventType (legacy) or EventContext (new)
            environment: Environment name (legacy API)
            data: Event data (legacy API)
            context: EventContext (new API, keyword-only)
        """
        if context is not None:
            self.context = context
        elif isinstance(event_type_or_context, EventContext):
            self.context = event_type_or_context
        elif isinstance(event_type_or_context, EventType):
            # Legacy API
            self.context = EventContext(
                event_type=event_type_or_context,
                environment=environment or "",
                data=data or {},
            )
        else:
            raise ValueError("Event requires either context or event_type")

    @property
    def event_type(self) -> EventType:
        """Event type shortcut."""
        return self.context.event_type

    @property
    def environment(self) -> str:
        """Environment shortcut."""
        return self.context.environment

    @property
    def data(self) -> dict[str, Any]:
        """Data shortcut."""
        return self.context.data

    def __repr__(self) -> str:
        return f"Event({self.event_type}, env={self.environment}, data={self.data})"


# EventHandler type alias (must be after Event class definition)
type EventHandler = Callable[[Event], None]
