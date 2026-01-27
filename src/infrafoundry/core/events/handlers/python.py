"""Python callable handler for events."""

import importlib
import time
import traceback
from collections.abc import Callable
from typing import Any, override

from infrafoundry.core.events.context import EventContext, EventResult
from infrafoundry.core.events.handlers.base import BaseHandler


class PythonHandler(BaseHandler):
    """Handler that executes a Python callable.

    Configuration:
        module: Python module path (e.g., "myproject.hooks.approval")
        function: Function name in the module (default: "handle")
        name: Optional handler name for logging

    The callable must accept an EventContext and return an EventResult.

    Example config:
        type: python
        module: hooks.approval
        function: validate_plan
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize Python handler.

        Args:
            config: Handler configuration with module and optional function
        """
        super().__init__(config)
        # Callable may return EventResult or any value (which we wrap)
        self._callable: Callable[[EventContext], Any] | None = None

    @override
    def validate_config(self) -> list[str]:
        """Validate handler configuration."""
        errors: list[str] = []

        if "module" not in self.config:
            errors.append("Python handler requires 'module' field")

        return errors

    def _load_callable(self) -> Callable[[EventContext], Any]:
        """Load the Python callable from config.

        Returns:
            The callable to execute (may return EventResult or any value)

        Raises:
            ImportError: If module cannot be imported
            AttributeError: If function not found in module
        """
        if self._callable is not None:
            return self._callable

        module_path = self.config["module"]
        function_name = self.config.get("function", "handle")

        module = importlib.import_module(module_path)
        self._callable = getattr(module, function_name)
        return self._callable

    @override
    def execute(self, context: EventContext) -> EventResult:
        """Execute the Python handler.

        Args:
            context: Event context

        Returns:
            EventResult from the handler or error result
        """
        start_time = time.monotonic()

        try:
            callable_fn = self._load_callable()
            result = callable_fn(context)

            # Ensure we have an EventResult
            if not isinstance(result, EventResult):
                result = EventResult(
                    success=True,
                    data={"return_value": result} if result is not None else {},
                )

            result.handler_name = self.name
            result.duration_seconds = time.monotonic() - start_time
            return result

        except ImportError as e:
            return EventResult(
                success=False,
                reason=f"Failed to import module: {e}",
                handler_name=self.name,
                duration_seconds=time.monotonic() - start_time,
            )

        except AttributeError as e:
            return EventResult(
                success=False,
                reason=f"Function not found: {e}",
                handler_name=self.name,
                duration_seconds=time.monotonic() - start_time,
            )

        except Exception as e:
            return EventResult(
                success=False,
                reason=f"Handler error: {e}",
                stderr=traceback.format_exc(),
                handler_name=self.name,
                duration_seconds=time.monotonic() - start_time,
            )
