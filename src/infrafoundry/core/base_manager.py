"""Base manager class providing standard patterns for all managers.

This module defines the common interface and patterns that all manager classes
should follow for consistency across the codebase.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class BaseManager(ABC):
    """Abstract base class for all manager classes.

    Provides standard patterns for:
    - Logging configuration
    - Error handling
    - Initialization
    - Optional context manager support

    All managers (SecretManager, ConfigManager, StateManager, EventManager,
    NotificationManager) should inherit from this class to ensure consistent
    behavior across the codebase.

    Example:
        class MyManager(BaseManager):
            def __init__(self, config_path: Path):
                super().__init__()
                self.config_path = config_path
                self._validate_config()

            def _validate_config(self) -> None:
                # Validation logic
                pass

            def cleanup(self) -> None:
                # Cleanup resources
                pass
    """

    def __init__(self) -> None:
        """Initialize base manager with logging."""
        self._logger = logging.getLogger(self.__class__.__name__)
        self._initialized = False

    @property
    def logger(self) -> logging.Logger:
        """Get logger for this manager.

        Returns:
            Logger instance configured for this manager's class
        """
        return self._logger

    def _log_info(self, message: str, **kwargs: Any) -> None:
        """Log info message with optional context.

        Args:
            message: Log message
            **kwargs: Additional context to log
        """
        if kwargs:
            self._logger.info(f"{message} - {kwargs}")
        else:
            self._logger.info(message)

    def _log_warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message with optional context.

        Args:
            message: Warning message
            **kwargs: Additional context to log
        """
        if kwargs:
            self._logger.warning(f"{message} - {kwargs}")
        else:
            self._logger.warning(message)

    def _log_error(self, message: str, exception: Exception | None = None, **kwargs: Any) -> None:
        """Log error message with optional exception and context.

        Args:
            message: Error message
            exception: Optional exception to include
            **kwargs: Additional context to log
        """
        if exception:
            self._logger.error(f"{message}: {exception}", exc_info=True, extra=kwargs)
        elif kwargs:
            self._logger.error(f"{message} - {kwargs}")
        else:
            self._logger.error(message)

    def _log_debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message with optional context.

        Args:
            message: Debug message
            **kwargs: Additional context to log
        """
        if kwargs:
            self._logger.debug(f"{message} - {kwargs}")
        else:
            self._logger.debug(message)

    def _handle_error(
        self,
        message: str,
        exception: Exception,
        raise_error: bool = True,
    ) -> None:
        """Standard error handling pattern.

        Logs the error and optionally re-raises it.

        Args:
            message: Error description
            exception: Exception that occurred
            raise_error: Whether to re-raise the exception (default: True)

        Raises:
            Exception: Re-raises the original exception if raise_error=True
        """
        self._log_error(message, exception)
        if raise_error:
            raise

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up resources used by this manager.

        Subclasses should implement this to close connections, release locks,
        or perform other cleanup operations.

        Example:
            def cleanup(self) -> None:
                if hasattr(self, 'connection'):
                    self.connection.close()
                    self._log_info("Connection closed")
        """
        pass

    def __enter__(self) -> "BaseManager":
        """Context manager entry.

        Returns:
            Self for use in with statements
        """
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit with cleanup.

        Args:
            exc_type: Exception type if an exception occurred
            exc_val: Exception value if an exception occurred
            exc_tb: Exception traceback if an exception occurred
        """
        try:
            self.cleanup()
        except Exception as e:
            self._log_error("Error during cleanup", e)
            # Don't suppress original exception

    def __repr__(self) -> str:
        """String representation of manager.

        Returns:
            Manager class name
        """
        return f"<{self.__class__.__name__}>"


class PathBasedManager(BaseManager):
    """Base manager for managers that work with filesystem paths.

    Provides common patterns for:
    - Path resolution with environment variable support
    - Directory creation
    - Path validation

    Example:
        class ConfigManager(PathBasedManager):
            def __init__(self, base_dir: Path | None = None):
                super().__init__()
                self.base_dir = self._resolve_path(
                    base_dir,
                    env_var="INFRAFOUNDRY_CONFIG_DIR",
                    default="envs"
                )
                self._ensure_directory_exists(self.base_dir)
    """

    def _resolve_path(
        self,
        path: Path | str | None,
        env_var: str | None = None,
        default: str | Path | None = None,
        create: bool = False,
    ) -> Path:
        """Resolve a path with environment variable and default fallback.

        Resolution order:
        1. Explicit path parameter
        2. Environment variable (if provided)
        3. Default value (if provided)
        4. Current working directory

        Args:
            path: Explicit path to use
            env_var: Environment variable name to check
            default: Default path if neither path nor env_var is set
            create: Whether to create the directory if it doesn't exist

        Returns:
            Resolved Path object
        """
        if path is not None:
            resolved = Path(path)
        elif env_var and (env_val := self._get_env_var(env_var)):
            resolved = Path(env_val)
        elif default is not None:
            resolved = Path.cwd() / Path(default)
        else:
            resolved = Path.cwd()

        if create and not resolved.exists():
            self._ensure_directory_exists(resolved)

        return resolved

    def _get_env_var(self, var_name: str) -> str | None:
        """Get environment variable value with logging.

        Args:
            var_name: Environment variable name

        Returns:
            Environment variable value or None
        """
        import os

        value = os.getenv(var_name)
        if value:
            self._log_debug(f"Using {var_name}", value=value)
        return value

    def _ensure_directory_exists(self, path: Path) -> None:
        """Ensure directory exists, creating it if necessary.

        Args:
            path: Directory path to create
        """
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            self._log_debug(f"Created directory: {path}")

    def _validate_path_exists(self, path: Path, path_description: str = "Path") -> None:
        """Validate that a path exists.

        Args:
            path: Path to validate
            path_description: Description for error message

        Raises:
            FileNotFoundError: If path doesn't exist
        """
        if not path.exists():
            raise FileNotFoundError(f"{path_description} not found: {path}")

    def cleanup(self) -> None:
        """No cleanup needed for path-based managers by default."""
        pass
