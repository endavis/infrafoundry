# InfraFoundry Coding Standards

This document defines coding standards and best practices for InfraFoundry development.

Last Updated: 2025-11-20

## Table of Contents

1. [Exception Handling](#exception-handling)
2. [Type Safety](#type-safety)
3. [Code Organization](#code-organization)
4. [Testing](#testing)
5. [Documentation](#documentation)

---

## Exception Handling

### Exception Hierarchy

InfraFoundry uses a comprehensive exception hierarchy with 31 exception types organized into 11 categories. All exceptions inherit from `InfraFoundryError`.

**Import from:**
```python
from infrafoundry.core.exceptions import (
    InfraFoundryError,
    ConfigurationError,
    ValidationError,
    APIError,
    # ... specific exceptions as needed
)
```

### Categories

1. **Configuration**: `ConfigurationError`, `EnvironmentNotFoundError`, `InvalidConfigurationError`, `MissingConfigurationError`
2. **Provider**: `ProviderError`, `ProviderNotFoundError`, `ProviderInitializationError`, `UnsupportedResourceTypeError`
3. **API**: `APIError`, `ConnectionError`, `AuthenticationError`, `TimeoutError`
4. **Validation**: `ValidationError`, `ConnectivityValidationError`, `ReferenceValidationError`, `SchemaValidationError`
5. **State**: `StateError`, `DeploymentNotFoundError`, `ResourceNotFoundError`, `StateInconsistencyError`
6. **Deployment**: `DeploymentError`, `TerraformError`, `AnsibleError`, `RollbackError`
7. **Policy**: `PolicyError`, `PolicyViolationError`, `PolicyNotFoundError`
8. **Credentials**: `CredentialError`, `MissingCredentialError`, `InvalidCredentialError`
9. **Secrets**: `SecretError`, `SecretNotFoundError`, `SecretDecryptionError`
10. **Dependencies**: `DependencyError`, `CircularDependencyError`, `MissingDependencyError`
11. **Template**: `TemplateError`

### Standard Exception Handling Pattern

**ALWAYS follow this pattern:**

```python
try:
    # Your operation
    result = some_operation()
except click.ClickException:
    # For CLI code: preserve Click's error handling
    raise
except SpecificError1 as e:
    # Handle specific error type first
    handle_specific_case(e)
except SpecificError2 as e:
    # Handle another specific type
    handle_another_case(e)
except InfraFoundryError as e:
    # Catch any InfraFoundry error
    handle_infrafoundry_error(e)
except Exception as e:
    # Final fallback for unexpected errors
    handle_unexpected_error(e)
```

### Using Context

`InfraFoundryError` and its subclasses support a `context` dict for debugging:

```python
raise TemplateError(
    "Failed to render template",
    context={
        "template": template_name,
        "variables": list(context.keys()),
        "error_line": 42
    }
)

# APIError has built-in context support:
raise APIError(
    "API request failed",
    status_code=500,
    response=response_text,
    provider="proxmox"
)
```

### CLI Error Handling

In CLI commands, use the `raise_cli_error` helper:

```python
from infrafoundry.cli.utils import raise_cli_error

try:
    # operation
except (ConfigurationError, ValidationError) as exc:
    raise_cli_error("Command failed", exc)
```

The helper automatically formats InfraFoundryError exceptions with context and shows stack traces when `INFRAFOUNDRY_LOG_LEVEL=DEBUG`.

### When to Use Generic Exception

Generic `except Exception` is appropriate in these cases:

1. **Final Fallback**: After specific exception handlers
2. **Defensive Patterns**: Code that must not crash (events, notifications, orchestrator status updates)
3. **Error Recording**: When you want to catch and record but also re-raise

**Example - Defensive Pattern (orchestrator):**
```python
try:
    # Deploy resources
    provider.apply()
except Exception as exc:
    # Update deployment status to FAILED
    self.state_manager.update_deployment_status(
        deployment_id, DeploymentStatus.FAILED, str(exc)
    )
    # Re-raise to propagate error
    raise
```

---

## Type Safety

### Type Annotations

**ALWAYS use type annotations** for function parameters and return values:

```python
# Good
def load_environment(self, env_name: str) -> EnvironmentConfig:
    """Load environment configuration."""
    ...

# Bad
def load_environment(self, env_name):
    """Load environment configuration."""
    ...
```

### Avoid Generic Types

Replace generic types with specific ones:

```python
# Bad
def process_resources(self, resources: list[Any]) -> dict[str, Any]:
    ...

# Good
def process_resources(
    self, resources: list[ResourceConfig]
) -> dict[str, DeploymentResult]:
    ...
```

### Use TypedDict for Complex Structures

For complex dictionaries, create TypedDict definitions:

```python
from typing import TypedDict

class RollbackData(TypedDict):
    """Snapshot data for deployment rollback."""
    environment: str
    timestamp: str  # ISO format
    resources: list[RollbackResourceSnapshot]

class RollbackResourceSnapshot(TypedDict):
    """Individual resource snapshot."""
    provider: str
    type: str
    name: str
    config: dict[str, Any]
```

**Location**: Define in `core/types.py` or provider-specific files.

### Type Checking Configuration

The project uses mypy and ruff for type checking:

**pyproject.toml:**
```toml
[tool.mypy]
python_version = "3.12"
disallow_untyped_defs = true
warn_return_any = true
check_untyped_defs = true

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "ANN", "B", "C4", "RUF"]
```

Run type checking:
```bash
uv run mypy src/infrafoundry
uv run ruff check src/
```

### When Any is Acceptable

Use `Any` only when:
1. Dealing with truly dynamic content (YAML parsing, JSON responses)
2. Type cannot be determined statically
3. Annotating would require complex Union types that reduce readability

**Document why Any is used:**
```python
def load_yaml(self, path: Path) -> dict[str, Any]:
    """Load YAML file.

    Returns:
        Parsed YAML content. Uses Any because content is dynamic.
    """
    ...
```

---

## Code Organization

### File Structure

```
src/infrafoundry/
├── core/              # Core framework
│   ├── config/        # Configuration management (package)
│   ├── state/         # State tracking (package)
│   ├── policy/        # Policy engine (package)
│   ├── exceptions.py  # Exception hierarchy
│   ├── types.py       # Shared type definitions
│   └── ...
├── providers/         # Provider implementations
│   ├── proxmox/
│   ├── opnsense/
│   └── kubernetes/
├── cli/              # CLI commands
│   ├── commands/     # Individual commands
│   ├── decorators.py # CLI decorators
│   └── utils.py      # CLI utilities
└── ...
```

### Module Organization

1. **Imports**: Standard library → Third-party → Local imports
2. **Constants**: Module-level constants after imports
3. **Classes**: One primary class per file (exceptions: mixins, helpers)
4. **Functions**: Helper functions after classes

### Package vs Module

Use packages (directories with `__init__.py`) when:
- Module exceeds 500 lines
- Multiple related classes that could be separate
- Clear sub-components exist

**Maintain backward compatibility** via `__init__.py` re-exports:
```python
# core/config/__init__.py
from .manager import ConfigManager
from .models import EnvironmentConfig

__all__ = ["ConfigManager", "EnvironmentConfig"]
```

---

## Testing

### Test Coverage

- **Target**: 100% coverage for all new code
- **Current**: 70% overall (459/459 tests passing)
- Run tests: `uv run pytest tests/`

### Test Organization

```
tests/
├── integration/       # End-to-end tests
│   ├── test_cli.py
│   └── test_orchestrator_workflows.py
└── unit/             # Unit tests
    ├── test_config.py
    ├── test_exceptions.py
    └── test_*.py
```

### Test Naming

```python
class TestConfigManager:
    """Tests for ConfigManager class."""

    def test_load_environment_success(self):
        """Test loading a valid environment."""
        ...

    def test_load_environment_not_found(self):
        """Test loading non-existent environment raises error."""
        ...
```

### Testing Exception Handling

Test both success and failure cases:

```python
def test_api_error_handling(self):
    """Test API error is raised and formatted correctly."""
    with pytest.raises(APIError) as exc_info:
        client.request("GET", "invalid/endpoint")

    assert exc_info.value.context["status_code"] == 404
    assert "invalid/endpoint" in str(exc_info.value)
```

---

## Documentation

### Docstrings

Use Google-style docstrings with type information:

```python
def validate_resource(
    self,
    resource: ResourceConfig,
    report: ValidationReport
) -> bool:
    """Validate a single resource configuration.

    Checks connectivity, references, and policy compliance.

    Args:
        resource: Resource configuration to validate
        report: Validation report to append results to

    Returns:
        True if validation passed, False otherwise

    Raises:
        ValidationError: If validation cannot be performed
        APIError: If API connectivity fails
    """
    ...
```

### Code Comments

- **Why, not what**: Explain reasoning, not obvious operations
- **Defensive patterns**: Document intentional exception catching
- **Complex logic**: Explain non-obvious algorithms
- **TODOs**: Use `# TODO: description` with issue reference if applicable

```python
# Good comments:
# NOTE: We catch all exceptions here to ensure deployment status is always updated
# This prevents orphaned "in_progress" records in the database
try:
    provider.apply()
except Exception as exc:
    self.state_manager.update_deployment_status(id, "failed", str(exc))
    raise

# Bad comments:
# Increment counter
counter += 1  # This comment adds no value
```

### Inline Documentation

For complex type definitions:

```python
class DeploymentResult(TypedDict):
    """Result of a deployment operation.

    Attributes:
        status: Overall status (success, failed, partial)
        resources_applied: Number of resources successfully applied
        errors: List of error messages if any failures occurred
        duration_seconds: Total deployment time
    """
    status: str
    resources_applied: int
    errors: list[str]
    duration_seconds: float
```

---

## Pre-commit Hooks

The project uses pre-commit hooks for automatic code quality checks:

```bash
# Install hooks
uv run pre-commit install

# Run manually
uv run pre-commit run --all-files
```

**Hooks configured:**
- ruff format: Auto-format code
- ruff check: Lint and fix issues
- mypy: Type checking (if configured)

---

## Quick Reference

### Starting a New Module

```python
"""Brief description of module purpose."""

from __future__ import annotations  # For Python 3.12+ features

from typing import Any, TypedDict

from infrafoundry.core.exceptions import InfraFoundryError

# Your code here
```

### Adding a New Exception Type

1. Add to `core/exceptions.py` in appropriate category
2. Add to `__all__` export list
3. Document in this guide
4. Add tests for the exception

### Adding a New CLI Command

1. Create in `cli/commands/your_command.py`
2. Use `@with_orchestrator` decorator if needs orchestrator
3. Follow exception handling pattern
4. Add to CLI_REFERENCE.md

---

## Additional Resources

- **Architecture**: `docs/architecture/ARCHITECTURE.md`
- **CLI Reference**: `docs/CLI_REFERENCE.md`
- **API Documentation**: `docs/architecture/api-documentation.md`
- **Refactoring Status**: `REFACTORING_TODO.md`
- **Testing Status**: `docs/development/TESTING_STATUS.md`

---

## Version History

- **2025-11-20**: Initial version based on Phase 2C refactoring work
  - Exception handling patterns (Task #9)
  - Type safety standards (Task #8)
  - Code organization guidelines
