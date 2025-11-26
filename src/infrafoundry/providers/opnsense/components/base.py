"""Base component manager class for OPNsense operations."""

from abc import ABC
from pathlib import Path


class BaseComponentManager(ABC):
    """Base class for OPNsense component managers.

    Component managers provide high-level orchestration of service operations
    for specific OPNsense components. They handle business logic and coordinate
    multiple service calls.
    """

    def __init__(self, config_dir: Path) -> None:
        """Initialize component manager.

        Args:
            config_dir: Path to configuration directory
        """
        self.config_dir = config_dir
