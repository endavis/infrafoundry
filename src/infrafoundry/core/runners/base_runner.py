"""Base runner interface for infrastructure tools."""

import shutil
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
    def priority(self) -> int:
        """Return the execution priority of the runner (lower runs first).

        Default priorities:
        - Terraform: 0 (Provisioning)
        - Ansible: 50 (Configuration)
        - PyInfra: 50 (Configuration)

        Returns:
            Priority integer
        """
        return 50

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Return the name of the tool this runner executes.

        Returns:
            Tool name (e.g., 'terraform', 'ansible', 'pulumi')
        """
        pass

    @property
    def tool_path(self) -> str:
        """Return the full path to the tool executable.

        Uses shutil.which() to resolve the full path, which is more secure
        than using a partial path that relies on PATH lookup at runtime.

        Returns:
            Full path to the tool executable, or tool_name if not found

        Raises:
            FileNotFoundError: If the tool is not found on PATH
        """
        path = shutil.which(self.tool_name)
        if path is None:
            raise FileNotFoundError(
                f"{self.tool_name} not found on PATH. Please install {self.tool_name}."
            )
        return path

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
