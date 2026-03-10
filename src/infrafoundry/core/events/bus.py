"""Unified event bus for InfraFoundry.

Replaces both EventManager and HookManager with a single event system.
"""

import traceback
from collections import defaultdict
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from rich.console import Console

from infrafoundry.core.base_manager import BaseManager
from infrafoundry.core.events.context import Event, EventContext, EventResult
from infrafoundry.core.events.handlers.base import BaseHandler
from infrafoundry.core.events.handlers.python import PythonHandler
from infrafoundry.core.events.handlers.script import ScriptHandler
from infrafoundry.core.events.handlers.webhook import WebhookHandler
from infrafoundry.core.events.types import ABORTABLE_EVENTS, EventType, HandlerType


class EventAbortedError(Exception):
    """Raised when an event handler aborts the workflow."""

    def __init__(self, event_type: EventType, result: EventResult) -> None:
        """Initialize abort exception.

        Args:
            event_type: Event that was aborted
            result: Handler result that caused the abort
        """
        self.event_type = event_type
        self.result = result
        message = f"Event {event_type.value} aborted by {result.handler_name}: {result.reason}"
        super().__init__(message)


class EventHandlerError(Exception):
    """Error raised when an event handler fails.

    Backward compatibility class from legacy EventManager.
    """

    def __init__(
        self,
        handler: Any,
        event: Event,
        original: Exception,
    ) -> None:
        """Initialize handler error.

        Args:
            handler: The handler that failed
            event: The event being processed
            original: The original exception
        """
        self.handler = handler
        self.event = event
        self.original = original
        self.handler_name = self._describe_handler(handler)
        message = f"Handler '{self.handler_name}' failed for {event.event_type.value}: {original}"
        super().__init__(message)

    @staticmethod
    def _describe_handler(handler: Any) -> str:
        """Return a human-friendly handler name for logging."""
        if hasattr(handler, "__qualname__"):
            return str(handler.__qualname__)
        if hasattr(handler, "__name__"):
            return str(handler.__name__)
        return repr(handler)


class UnifiedEventBus(BaseManager):
    """Unified event bus for all InfraFoundry events.

    Supports multiple handler types:
    - Python callables
    - Shell scripts
    - Webhooks

    Handlers can:
    - React to any event type
    - Return abort signals for abortable events
    - Access rich event context
    - Chain with previous handler results
    """

    def __init__(
        self,
        config_base_dir: Path | None = None,
        secret_resolver: Callable[[str, str], str] | None = None,
        console: Console | None = None,
    ) -> None:
        """Initialize the event bus.

        Args:
            config_base_dir: Base directory for config (for script handlers)
            secret_resolver: Function to resolve secrets (env_name, secret_path) -> value
            console: Rich console for user-facing output
        """
        super().__init__()
        self.config_base_dir = config_base_dir or Path.cwd()
        self.secret_resolver = secret_resolver
        self.console = console or Console()

        # Handlers by event type
        self._handlers: dict[EventType, list[BaseHandler]] = defaultdict(list)

        # Legacy Python callbacks (for backward compatibility)
        self._callbacks: dict[EventType, list[Callable[[Event], None]]] = defaultdict(list)
        self._global_callbacks: list[Callable[[Event], None]] = []

        self._log_debug("UnifiedEventBus initialized")

    def register_handler(
        self,
        event_type: EventType,
        handler_config: dict[str, Any],
    ) -> None:
        """Register a handler from configuration.

        Args:
            event_type: Event type to handle
            handler_config: Handler configuration dict with 'type' field

        Raises:
            ValueError: If handler type is unknown or config is invalid
        """
        handler = self._create_handler(handler_config)
        errors = handler.validate_config()
        if errors:
            raise ValueError(f"Invalid handler config: {', '.join(errors)}")

        self._handlers[event_type].append(handler)
        self._log_debug(f"Registered {handler.name} for {event_type.value}")

    def _create_handler(self, config: dict[str, Any]) -> BaseHandler:
        """Create a handler instance from configuration.

        Args:
            config: Handler configuration

        Returns:
            Handler instance

        Raises:
            ValueError: If handler type is unknown
        """
        handler_type = config.get("type", HandlerType.PYTHON.value)

        if handler_type == HandlerType.PYTHON.value:
            return PythonHandler(config)

        elif handler_type == HandlerType.SCRIPT.value:
            return ScriptHandler(
                config,
                config_base_dir=self.config_base_dir,
                secret_resolver=self.secret_resolver,
            )

        elif handler_type == HandlerType.WEBHOOK.value:
            return WebhookHandler(config)

        else:
            raise ValueError(f"Unknown handler type: {handler_type}")

    def subscribe(
        self,
        event_type: EventType,
        callback: Callable[[Event], None],
    ) -> None:
        """Subscribe a Python callback to an event type.

        This is the legacy API for backward compatibility with EventManager.

        Args:
            event_type: Event type to subscribe to
            callback: Function to call when event is emitted
        """
        self._callbacks[event_type].append(callback)
        self._log_debug(f"Subscribed callback to {event_type.value}")

    def subscribe_all(self, callback: Callable[[Event], None]) -> None:
        """Subscribe a callback to all events.

        Args:
            callback: Function to call for any event
        """
        self._global_callbacks.append(callback)

    def unsubscribe(
        self,
        event_type: EventType,
        callback: Callable[[Event], None],
    ) -> None:
        """Unsubscribe a callback from an event type.

        Args:
            event_type: Event type to unsubscribe from
            callback: Callback to remove
        """
        if callback in self._callbacks[event_type]:
            self._callbacks[event_type].remove(callback)

    def emit(
        self,
        context: EventContext,
        abort_on_failure: bool = True,
    ) -> list[EventResult]:
        """Emit an event to all registered handlers.

        Args:
            context: Event context with all relevant information
            abort_on_failure: If True, raise EventAbortedError on handler abort

        Returns:
            List of results from all handlers

        Raises:
            EventAbortedError: If a handler aborts and abort_on_failure is True
        """
        event_type = context.event_type
        self._log_debug(f"Emitting event: {event_type.value}")

        results: list[EventResult] = []
        event = Event(context)

        # Execute registered handlers
        for handler in self._handlers[event_type]:
            result = self._execute_handler(handler, context, results)
            results.append(result)
            self._print_handler_result(handler, result)

            # Check for abort
            if result.abort and abort_on_failure and event_type in ABORTABLE_EVENTS:
                raise EventAbortedError(event_type, result)

        # Execute legacy callbacks
        for callback in self._callbacks[event_type]:
            self._invoke_callback(callback, event)

        for callback in self._global_callbacks:
            self._invoke_callback(callback, event)

        return results

    def emit_event(
        self,
        event_type: EventType,
        environment: str,
        data: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[EventResult]:
        """Convenience method to create context and emit.

        This matches the legacy EventManager API.

        Args:
            event_type: Type of event
            environment: Environment name
            data: Event-specific data (dict or TypedDict)
            **kwargs: Additional context fields (provider, resource, etc.)

        Returns:
            List of handler results
        """
        context = EventContext(
            event_type=event_type,
            environment=environment,
            data=dict(data) if data else {},
            **kwargs,
        )
        return self.emit(context)

    def _execute_handler(
        self,
        handler: BaseHandler,
        context: EventContext,
        previous_results: list[EventResult],
    ) -> EventResult:
        """Execute a single handler with error handling.

        Args:
            handler: Handler to execute
            context: Event context
            previous_results: Results from previous handlers

        Returns:
            Handler result
        """
        # Update context with previous results
        context.previous_results = previous_results

        try:
            return handler.execute(context)

        except Exception as e:
            self.logger.error(
                "Handler %s failed for %s: %s\n%s",
                handler.name,
                context.event_type.value,
                e,
                traceback.format_exc(),
            )
            return EventResult(
                success=False,
                reason=f"Handler error: {e}",
                handler_name=handler.name,
            )

    def _print_handler_result(
        self,
        handler: BaseHandler,
        result: EventResult,
    ) -> None:
        """Print handler execution result to console.

        Args:
            handler: The handler that was executed
            result: The result from the handler
        """
        name = handler.name
        if result.success:
            self.console.print(f"  [green]✓[/green] Event handler [bold]{name}[/bold] completed")
            if result.stdout:
                for line in result.stdout.strip().splitlines():
                    self.console.print(f"    {line}")
        else:
            self.console.print(
                f"  [red]✗[/red] Event handler [bold]{name}[/bold] failed: {result.reason}"
            )
            if result.stderr:
                for line in result.stderr.strip().splitlines():
                    self.console.print(f"    [red]{line}[/red]")
            if result.stdout:
                for line in result.stdout.strip().splitlines():
                    self.console.print(f"    {line}")

    def _invoke_callback(
        self,
        callback: Callable[[Event], None],
        event: Event,
    ) -> None:
        """Invoke a legacy callback with error handling.

        Args:
            callback: Callback to invoke
            event: Event to pass
        """
        try:
            callback(event)
        except Exception as e:
            self.logger.error(
                "Callback failed for %s: %s\n%s",
                event.event_type.value,
                e,
                traceback.format_exc(),
            )

    def load_config(self, events_config: dict[str, list[dict[str, Any]]]) -> None:
        """Load handlers from configuration dictionary.

        Args:
            events_config: Dict mapping event type names to handler configs

        Example:
            {
                "AFTER_PLAN": [
                    {"type": "python", "module": "hooks.approval"},
                    {"type": "script", "script": "scripts/notify.sh"},
                ],
                "DRIFT_DETECTED": [
                    {"type": "webhook", "url": "https://slack.com/..."},
                ],
            }
        """
        for event_name, handlers in events_config.items():
            try:
                event_type = EventType(event_name.lower())
            except ValueError:
                self._log_warning(f"Unknown event type in config: {event_name}")
                continue

            for handler_config in handlers:
                try:
                    self.register_handler(event_type, handler_config)
                except ValueError as e:
                    self._log_error(f"Failed to register handler: {e}")

    def clear_handlers(self) -> None:
        """Remove all registered handlers (not legacy callbacks).

        Use this before re-loading config-based handlers to prevent
        duplicate registrations across repeated workflow calls.
        """
        handler_count = sum(len(h) for h in self._handlers.values())
        self._handlers.clear()
        self._log_debug(f"Cleared {handler_count} config handlers")

    def clear(self) -> None:
        """Clear all handlers and callbacks."""
        handler_count = self.handler_count()
        self._handlers.clear()
        self._callbacks.clear()
        self._global_callbacks.clear()
        self._log_debug(f"Cleared {handler_count} handlers")

    def handler_count(self, event_type: EventType | None = None) -> int:
        """Get count of registered handlers.

        Args:
            event_type: Specific event type, or None for total

        Returns:
            Number of handlers registered
        """
        if event_type:
            return len(self._handlers[event_type]) + len(self._callbacks[event_type])

        total = sum(len(h) for h in self._handlers.values())
        total += sum(len(c) for c in self._callbacks.values())
        total += len(self._global_callbacks)
        return total

    def cleanup(self) -> None:
        """Cleanup resources (required by BaseManager)."""
        self.clear()
        self._log_debug("UnifiedEventBus cleanup complete")


# Backward compatibility alias
EventManager = UnifiedEventBus
