"""Base runner interface for infrastructure tools."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from rich.console import Console

from infrafoundry.core.provider import ProviderBase


class BaseRunner(ABC):
    """Abstract base class for infrastructure tool runners.

    Runners execute external tools (Terraform, Ansible, Pulumi, etc.) to
    provision and configure infrastructure. Each runner implements tool-specific
    execution logic while providing a consistent interface.
    """

    def __init__(self, console: Console | None = None) -> None:
        """Initialize runner.

        Args:
            console: Rich console for output (creates default if None)
        """
        self.console = console or Console()

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Return the name of the tool this runner executes.

        Returns:
            Tool name (e.g., 'terraform', 'ansible', 'pulumi')
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the tool is installed and available.

        Returns:
            True if tool is available, False otherwise
        """
        pass

    @abstractmethod
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """Initialize the tool in the working directory.

        Args:
            working_dir: Directory to initialize
            **kwargs: Tool-specific initialization options

        Returns:
            Dict with initialization results
        """
        pass

    @abstractmethod
    def plan(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Generate an execution plan showing what changes will be made.

        Args:
            provider: Provider instance
            **kwargs: Tool-specific plan options

        Returns:
            Dict with plan results including exit_code and success
        """
        pass

    @abstractmethod
    def apply(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Apply infrastructure changes.

        Args:
            provider: Provider instance
            **kwargs: Tool-specific apply options (e.g., auto_approve)

        Returns:
            Dict with apply results including exit_code and success
        """
        pass

    @abstractmethod
    def destroy(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Destroy infrastructure resources.

        Args:
            provider: Provider instance
            **kwargs: Tool-specific destroy options (e.g., auto_approve)

        Returns:
            Dict with destroy results including exit_code and success
        """
        pass

    @abstractmethod
    def run(
        self, provider: ProviderBase, command: str, auto_approve: bool = False
    ) -> dict[str, Any]:
        """Run a tool command for a provider.

        Args:
            provider: Provider instance
            command: Command to run (e.g., 'plan', 'apply', 'destroy')
            auto_approve: Whether to auto-approve changes

        Returns:
            Dict with command results including exit_code and success
        """
        pass

    @abstractmethod
    def get_resource_ids(self, provider: ProviderBase) -> dict[str, str]:
        """Extract resource IDs from tool state.

        Args:
            provider: Provider instance

        Returns:
            Dict mapping resource names to their IDs in the tool's state
        """
        pass

    @abstractmethod
    def parse_plan_for_drift(self, plan_result: dict[str, Any]) -> dict[str, Any]:
        """Parse plan output to detect infrastructure drift.

        Args:
            plan_result: Result dictionary from run() with plan command

        Returns:
            Dict with drift information including has_changes and summary
        """
        pass

    def get_version(self) -> str | None:
        """Get the version of the installed tool.

        Returns:
            Version string or None if unavailable
        """
        return None

    def validate_config(self, provider: ProviderBase) -> dict[str, Any]:
        """Validate tool configuration without making changes.

        Args:
            provider: Provider instance

        Returns:
            Dict with validation results
        """
        return {"valid": True, "message": "Validation not implemented"}
