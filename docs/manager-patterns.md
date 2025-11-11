# Manager Pattern Documentation

This document describes the standard patterns all manager classes in InfraFoundry follow for consistency and maintainability.

## Overview

All managers inherit from either `BaseManager` or `PathBasedManager` to ensure consistent behavior for:
- Logging
- Error handling
- Resource cleanup
- Initialization patterns

## Class Hierarchy

```
BaseManager (ABC)
├── StateManager
├── EventManager
└── PathBasedManager
    ├── ConfigManager
    ├── SecretManager
    └── NotificationManager
```

## When to Use Each Base Class

### BaseManager

Use `BaseManager` for managers that:
- Don't primarily work with filesystem paths
- Manage in-memory state (EventManager)
- Manage database connections (StateManager)
- Coordinate other components

**Example managers:**
- `StateManager` - SQLite database management
- `EventManager` - In-memory event handler registry

### PathBasedManager

Use `PathBasedManager` for managers that:
- Work primarily with filesystem paths
- Need path resolution with environment variable support
- Load configuration from files
- Work with specific directories

**Example managers:**
- `ConfigManager` - Loads YAML configs from `envs/` directory
- `SecretManager` - Manages encrypted files in `secrets/` directory
- `NotificationManager` - Loads config from `notifications.yaml`

## Standard Initialization Pattern

All managers follow this initialization order:

```python
class MyManager(BaseManager):  # or PathBasedManager
    def __init__(self, param: Type):
        """Initialize manager.
        
        Args:
            param: Description
        """
        # 1. ALWAYS call super().__init__() FIRST
        super().__init__()
        
        # 2. Set instance variables
        self.param = param
        self.state = {}
        
        # 3. Perform initialization/validation
        self._validate_config()
        self._load_data()
        
        # 4. Log completion
        self._log_debug("MyManager initialized successfully")
```

### Why This Order?

1. **super().__init__()** must be called first to initialize logging
2. **Instance variables** can then be safely set
3. **Initialization logic** can use logging methods from BaseManager
4. **Log completion** provides visibility into initialization success

## Logging Methods

All managers have access to these logging methods from `BaseManager`:

```python
# Debug information (verbose mode)
self._log_debug("Loading config file", filename="settings.yaml")

# General information
self._log_info(f"Loaded {count} resources")

# Warnings (non-fatal issues)
self._log_warning("Template file not found, using default")

# Errors (with optional exception)
try:
    risky_operation()
except Exception as e:
    self._log_error("Operation failed", exception=e)
```

### Logging Best Practices

1. **Log initialization steps** for debugging
   ```python
   self._log_debug(f"Initialized ConfigManager with base_dir: {self.base_dir}")
   ```

2. **Log configuration sources**
   ```python
   self._log_debug("Using INFRAFOUNDRY_CONFIG_REPO", value=config_repo)
   ```

3. **Log errors with context** using the exception parameter
   ```python
   except Exception as e:
       self._log_error("Failed to load policy file", exception=e)
   ```

4. **Use structured data** via kwargs for better filtering
   ```python
   self._log_info("Deployment created", deployment_id=123, environment="prod")
   ```

## Error Handling Pattern

Managers follow this standard error handling pattern:

```python
def load_config(self, path: Path) -> dict:
    """Load configuration from file.
    
    Args:
        path: Path to config file
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid
    """
    # Validate inputs
    if not path.exists():
        error_msg = f"Config file not found: {path}"
        self._log_error(error_msg)
        raise FileNotFoundError(error_msg)
    
    # Try operation with error handling
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        error_msg = "Invalid YAML in config file"
        self._log_error(error_msg, exception=e)
        raise
```

### Error Handling Guidelines

1. **Validate inputs** before operations
2. **Log errors** before raising exceptions
3. **Provide context** in error messages (include paths, names, etc.)
4. **Re-raise exceptions** after logging (don't swallow them)
5. **Use specific exceptions** (FileNotFoundError, ValueError, etc.)

## Resource Cleanup

All managers must implement the `cleanup()` method:

```python
def cleanup(self) -> None:
    """Cleanup resources (required by BaseManager).
    
    [Describe what needs cleanup, or explicitly state if none needed]
    """
    # Close connections, release locks, etc.
    if hasattr(self, "engine"):
        self._log_debug("Disposing database engine")
        self.engine.dispose()
    
    self._log_debug("MyManager cleanup complete")
```

### Cleanup Guidelines

1. **Always implement cleanup()** even if no cleanup is needed
2. **Document what's being cleaned up** in the docstring
3. **Check for attribute existence** before cleanup (defensive programming)
4. **Log cleanup steps** for debugging
5. **Don't raise exceptions** from cleanup() if possible

### Examples

**Manager with resources to clean up:**
```python
def cleanup(self) -> None:
    """Cleanup database resources (required by BaseManager).
    
    Closes database engine and releases connections.
    """
    if hasattr(self, "engine"):
        self._log_debug("Disposing database engine")
        self.engine.dispose()
        self._log_debug("StateManager cleanup complete")
```

**Manager with no resources to clean up:**
```python
def cleanup(self) -> None:
    """Cleanup resources (required by BaseManager).
    
    No cleanup needed for ConfigManager as it doesn't maintain
    persistent connections or state.
    """
    self._log_debug("ConfigManager cleanup complete")
```

## Context Manager Support

Managers automatically support context manager protocol via `BaseManager`:

```python
# Automatically calls cleanup() on exit
with ConfigManager() as config:
    env = config.load_environment("dev")
    # ... use config ...
# cleanup() called here
```

### When Context Managers Are Useful

Use context managers when you need guaranteed cleanup:

```python
# Database managers - ensure connections close
with StateManager() as state:
    state.create_deployment(...)

# File managers - ensure file handles close
# (though most managers don't keep files open)
```

### When NOT to Use Context Managers

Most managers are designed for long-lived use:

```python
# Typical usage - manager lives for lifetime of orchestrator
class Orchestrator:
    def __init__(self):
        self.config = ConfigManager()  # Long-lived
        self.state = StateManager()    # Long-lived
        
    def cleanup(self):
        """Orchestrator cleanup calls manager cleanup."""
        self.config.cleanup()
        self.state.cleanup()
```

## PathBasedManager Specific Patterns

`PathBasedManager` provides additional utilities for path operations:

### Path Resolution

```python
def __init__(self, base_dir: Path | None = None):
    super().__init__()
    
    # Resolve path with fallback chain:
    # 1. Explicit path parameter
    # 2. Environment variable
    # 3. Default path
    self.base_dir = self._resolve_path(
        path=base_dir,
        env_var="INFRAFOUNDRY_CONFIG_DIR",
        default="envs",
        create=True  # Create if doesn't exist
    )
```

### Environment Variable Access

```python
# Get env var with automatic logging
config_repo = self._get_env_var("INFRAFOUNDRY_CONFIG_REPO")
if config_repo:
    # Logs: "Using INFRAFOUNDRY_CONFIG_REPO: /path/to/repo"
    self.base_dir = Path(config_repo) / "envs"
```

### Directory Operations

```python
# Ensure directory exists (creates if needed)
self._ensure_directory_exists(self.output_dir)

# Validate path exists (raises FileNotFoundError if not)
self._validate_path_exists(config_file, "Configuration file")
```

## Complete Manager Example

Here's a complete example showing all patterns:

```python
"""My manager module."""

from pathlib import Path
from typing import Any

import yaml

from infrafoundry.core.base_manager import PathBasedManager


class MyManager(PathBasedManager):
    """Manages my resources with consistent patterns.
    
    This manager demonstrates all standard patterns:
    - Proper initialization
    - Consistent logging
    - Error handling
    - Resource cleanup
    """
    
    def __init__(self, config_dir: Path | None = None):
        """Initialize manager.
        
        Args:
            config_dir: Configuration directory
                (defaults to INFRAFOUNDRY_MY_CONFIG or ./my_config)
        """
        # 1. Initialize base manager
        super().__init__()
        
        # 2. Resolve paths
        self.config_dir = self._resolve_path(
            path=config_dir,
            env_var="INFRAFOUNDRY_MY_CONFIG",
            default="my_config",
            create=True
        )
        
        # 3. Initialize state
        self.data: dict[str, Any] = {}
        
        # 4. Load configuration
        self._load_config()
        
        # 5. Log completion
        self._log_debug(f"MyManager initialized with config_dir: {self.config_dir}")
    
    def _load_config(self) -> None:
        """Load configuration from file."""
        config_file = self.config_dir / "config.yaml"
        
        if not config_file.exists():
            self._log_warning(f"Config file not found: {config_file}, using defaults")
            return
        
        try:
            self._log_debug(f"Loading config from: {config_file}")
            with open(config_file) as f:
                self.data = yaml.safe_load(f) or {}
            self._log_info(f"Loaded configuration with {len(self.data)} items")
        except yaml.YAMLError as e:
            error_msg = "Invalid YAML in config file"
            self._log_error(error_msg, exception=e)
            raise
    
    def get_value(self, key: str) -> Any:
        """Get configuration value.
        
        Args:
            key: Configuration key
            
        Returns:
            Configuration value
            
        Raises:
            KeyError: If key not found
        """
        if key not in self.data:
            error_msg = f"Configuration key not found: {key}"
            self._log_error(error_msg)
            raise KeyError(error_msg)
        
        return self.data[key]
    
    def cleanup(self) -> None:
        """Cleanup resources (required by BaseManager).
        
        No cleanup needed for MyManager as it doesn't maintain
        persistent connections or resources.
        """
        self._log_debug("MyManager cleanup complete")
```

## Testing Managers

When testing managers, ensure you test:

1. **Initialization variations**
   - With explicit parameters
   - With environment variables
   - With defaults

2. **Error conditions**
   - Missing files
   - Invalid data
   - Permission errors

3. **Cleanup**
   - Resources are properly released
   - Cleanup doesn't raise exceptions

Example test:

```python
def test_manager_initialization():
    """Test manager initialization with defaults."""
    manager = MyManager()
    assert manager.config_dir.exists()
    assert isinstance(manager.data, dict)

def test_manager_error_handling():
    """Test manager handles missing config gracefully."""
    with pytest.raises(FileNotFoundError) as exc_info:
        manager = MyManager(Path("/nonexistent"))
    assert "not found" in str(exc_info.value)

def test_manager_cleanup():
    """Test manager cleanup doesn't raise."""
    manager = MyManager()
    manager.cleanup()  # Should not raise
```

## Summary Checklist

When creating or reviewing a manager, verify:

- [ ] Inherits from `BaseManager` or `PathBasedManager` (choose appropriately)
- [ ] Calls `super().__init__()` as first line of `__init__()`
- [ ] Uses `_log_debug`, `_log_info`, `_log_error` consistently
- [ ] Implements `cleanup()` method (even if empty)
- [ ] Logs initialization completion
- [ ] Handles errors with logging before re-raising
- [ ] Provides clear docstrings with Args/Returns/Raises
- [ ] Has comprehensive unit tests
- [ ] Follows initialization order: super → vars → logic → log

## Related Documentation

- `base_manager.py` - Implementation of BaseManager and PathBasedManager
- `docs/testing-guide.md` - Testing patterns for managers
- `docs/architecture.md` - Overall architecture including manager roles
