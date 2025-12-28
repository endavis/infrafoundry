"""Exception hierarchy for the plugin system.

This module defines all exceptions that can be raised by the plugin system.
All exceptions inherit from PluginError for easy catching.

Example:
    >>> try:
    ...     registry.get("provider", "unknown")
    ... except PluginNotFoundError as e:
    ...     print(f"Plugin not found: {e}")
"""


class PluginError(Exception):
    """Base exception for all plugin-related errors.

    All plugin system exceptions inherit from this class, allowing
    users to catch all plugin errors with a single except clause.

    Args:
        message: Human-readable error message
        plugin_type: Optional plugin type (e.g., "provider", "secret_backend")
        plugin_name: Optional plugin name
        details: Optional additional error details
    """

    def __init__(
        self,
        message: str,
        plugin_type: str | None = None,
        plugin_name: str | None = None,
        details: dict[str, str] | None = None,
    ) -> None:
        """Initialize plugin error."""
        super().__init__(message)
        self.message = message
        self.plugin_type = plugin_type
        self.plugin_name = plugin_name
        self.details = details or {}

    def __str__(self) -> str:
        """Return formatted error message."""
        parts = [self.message]

        if self.plugin_type:
            parts.append(f"Plugin type: {self.plugin_type}")

        if self.plugin_name:
            parts.append(f"Plugin name: {self.plugin_name}")

        if self.details:
            detail_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            parts.append(f"Details: {detail_str}")

        return " | ".join(parts)


class PluginDiscoveryError(PluginError):
    """Raised when plugin discovery fails.

    This can occur when:
    - Entry point group cannot be scanned
    - Entry point is malformed
    - Multiple errors during discovery

    Args:
        message: Human-readable error message
        entry_point_group: The entry point group being scanned
        failed_plugins: List of plugin names that failed discovery
    """

    def __init__(
        self,
        message: str,
        entry_point_group: str | None = None,
        failed_plugins: list[str] | None = None,
    ) -> None:
        """Initialize discovery error."""
        details = {}
        if entry_point_group:
            details["entry_point_group"] = entry_point_group
        if failed_plugins:
            details["failed_plugins"] = ",".join(failed_plugins)

        super().__init__(message, details=details)
        self.entry_point_group = entry_point_group
        self.failed_plugins = failed_plugins or []


class PluginLoadError(PluginError):
    """Raised when a plugin cannot be loaded.

    This can occur when:
    - Entry point cannot be loaded
    - Import fails
    - Module is missing
    - Initialization fails

    Args:
        message: Human-readable error message
        plugin_type: Plugin type (e.g., "provider")
        plugin_name: Plugin name
        entry_point: Entry point string that failed
        cause: Original exception that caused the failure
    """

    def __init__(
        self,
        message: str,
        plugin_type: str | None = None,
        plugin_name: str | None = None,
        entry_point: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        """Initialize load error."""
        details = {}
        if entry_point:
            details["entry_point"] = entry_point
        if cause:
            details["cause"] = str(cause)

        super().__init__(message, plugin_type, plugin_name, details)
        self.entry_point = entry_point
        self.cause = cause


class PluginValidationError(PluginError):
    """Raised when plugin validation fails.

    This can occur when:
    - Plugin doesn't implement required protocol
    - Missing required methods or attributes
    - Invalid metadata
    - Configuration validation fails

    Args:
        message: Human-readable error message
        plugin_type: Plugin type (e.g., "provider")
        plugin_name: Plugin name
        validation_errors: List of specific validation errors
    """

    def __init__(
        self,
        message: str,
        plugin_type: str | None = None,
        plugin_name: str | None = None,
        validation_errors: list[str] | None = None,
    ) -> None:
        """Initialize validation error."""
        details = {}
        if validation_errors:
            details["validation_errors"] = "; ".join(validation_errors)

        super().__init__(message, plugin_type, plugin_name, details)
        self.validation_errors = validation_errors or []


class PluginNotFoundError(PluginError):
    """Raised when a requested plugin is not found.

    This can occur when:
    - Plugin is not installed
    - Plugin name is misspelled
    - Plugin type is incorrect

    Args:
        message: Human-readable error message
        plugin_type: Plugin type (e.g., "provider")
        plugin_name: Plugin name that was not found
        available_plugins: List of available plugin names (for suggestions)
    """

    def __init__(
        self,
        message: str,
        plugin_type: str | None = None,
        plugin_name: str | None = None,
        available_plugins: list[str] | None = None,
    ) -> None:
        """Initialize not found error."""
        details = {}
        if available_plugins:
            details["available"] = ",".join(available_plugins)

        super().__init__(message, plugin_type, plugin_name, details)
        self.available_plugins = available_plugins or []


class PluginConflictError(PluginError):
    """Raised when there is a plugin naming conflict.

    This can occur when:
    - Two plugins register with the same name
    - Plugin name collides with built-in
    - Version conflict between dependencies

    Args:
        message: Human-readable error message
        plugin_type: Plugin type (e.g., "provider")
        plugin_name: Conflicting plugin name
        existing_version: Version of existing plugin
        new_version: Version of new plugin
    """

    def __init__(
        self,
        message: str,
        plugin_type: str | None = None,
        plugin_name: str | None = None,
        existing_version: str | None = None,
        new_version: str | None = None,
    ) -> None:
        """Initialize conflict error."""
        details = {}
        if existing_version:
            details["existing_version"] = existing_version
        if new_version:
            details["new_version"] = new_version

        super().__init__(message, plugin_type, plugin_name, details)
        self.existing_version = existing_version
        self.new_version = new_version


class PluginTypeError(PluginError):
    """Raised when there is an error with plugin type system.

    This can occur when:
    - Plugin type not found
    - Plugin type registration fails
    - Invalid plugin type definition
    - Plugin type protocol violation

    Args:
        message: Human-readable error message
        plugin_type_name: Name of the plugin type
        available_types: List of available plugin type names
    """

    def __init__(
        self,
        message: str,
        plugin_type_name: str | None = None,
        available_types: list[str] | None = None,
    ) -> None:
        """Initialize plugin type error."""
        details = {}
        if available_types:
            details["available_types"] = ",".join(available_types)

        super().__init__(message, plugin_type=plugin_type_name, details=details)
        self.plugin_type_name = plugin_type_name
        self.available_types = available_types or []


class PluginVersionError(PluginError):
    """Raised when there is a version compatibility issue.

    This can occur when:
    - Plugin requires newer core version
    - Core requires newer plugin version
    - Semantic versioning constraint violation

    Args:
        message: Human-readable error message
        plugin_type: Plugin type (e.g., "provider")
        plugin_name: Plugin name
        plugin_version: Version of the plugin
        required_version: Required version constraint
    """

    def __init__(
        self,
        message: str,
        plugin_type: str | None = None,
        plugin_name: str | None = None,
        plugin_version: str | None = None,
        required_version: str | None = None,
    ) -> None:
        """Initialize version error."""
        details = {}
        if plugin_version:
            details["plugin_version"] = plugin_version
        if required_version:
            details["required_version"] = required_version

        super().__init__(message, plugin_type, plugin_name, details)
        self.plugin_version = plugin_version
        self.required_version = required_version
