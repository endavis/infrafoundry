"""Runner registry for managing infrastructure tool runners."""

from typing import Any

from infrafoundry.core.runners.base_runner import BaseRunner


class RunnerRegistry:
    """Registry for infrastructure tool runners.

    Allows dynamic registration and discovery of runners for different
    infrastructure tools (Terraform, Ansible, Pulumi, etc.).
    """

    def __init__(self) -> None:
        """Initialize runner registry."""
        self._runners: dict[str, type[BaseRunner]] = {}

    def register(self, runner_class: type[BaseRunner], tool_name: str | None = None) -> None:
        """Register a runner class.

        Args:
            runner_class: Runner class to register
            tool_name: Optional tool name (if None, will be determined from class)
        """
        if tool_name is None:
            # Get tool_name from class attribute if available, otherwise derive from class name
            tool_name = getattr(runner_class, "_tool_name", None)
            if tool_name is None:
                # Fallback: derive from class name (e.g., TerraformRunner -> terraform)
                class_name = runner_class.__name__
                if class_name.endswith("Runner"):
                    tool_name = class_name[: -len("Runner")].lower()
                else:
                    tool_name = class_name.lower()

        self._runners[tool_name] = runner_class

    def get(self, tool_name: str) -> type[BaseRunner] | None:
        """Get a runner class by tool name.

        Args:
            tool_name: Name of the tool (e.g., 'terraform', 'ansible')

        Returns:
            Runner class or None if not found
        """
        return self._runners.get(tool_name)

    def list_runners(self) -> list[str]:
        """List all registered runner tool names.

        Returns:
            List of tool names
        """
        return list(self._runners.keys())

    def create_runner(self, tool_name: str, **kwargs: Any) -> BaseRunner | None:
        """Create a runner instance by tool name.

        Args:
            tool_name: Name of the tool
            **kwargs: Arguments to pass to runner constructor

        Returns:
            Runner instance or None if tool not found
        """
        runner_class = self.get(tool_name)
        if runner_class is None:
            return None
        return runner_class(**kwargs)


# Global registry instance
_registry = RunnerRegistry()


def register_runner(runner_class: type[BaseRunner]) -> None:
    """Register a runner class with the global registry.

    Args:
        runner_class: Runner class to register
    """
    _registry.register(runner_class)


def get_runner(tool_name: str) -> type[BaseRunner] | None:
    """Get a runner class from the global registry.

    Args:
        tool_name: Name of the tool

    Returns:
        Runner class or None if not found
    """
    return _registry.get(tool_name)


def list_runners() -> list[str]:
    """List all registered runners.

    Returns:
        List of tool names
    """
    return _registry.list_runners()


def create_runner(tool_name: str, **kwargs: Any) -> BaseRunner | None:
    """Create a runner instance from the global registry.

    Args:
        tool_name: Name of the tool
        **kwargs: Arguments to pass to runner constructor

    Returns:
        Runner instance or None if tool not found
    """
    return _registry.create_runner(tool_name, **kwargs)
