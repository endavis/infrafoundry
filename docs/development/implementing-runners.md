# Implementing Custom Runners

## Overview

This guide walks you through creating custom infrastructure tool runners for InfraFoundry. Runners execute external tools (like Terraform, Ansible, etc.) to provision and configure infrastructure. The runner system uses a protocol-based architecture that allows you to implement only the capabilities your tool supports.

## Audience and Prerequisites

- **Audience:** Developers adding new infrastructure tool support to InfraFoundry
- **Prerequisites:**
  - Python 3.10+ knowledge
  - Understanding of Python protocols and type hints
  - Familiarity with the infrastructure tool you're integrating
  - Basic understanding of InfraFoundry's provider system

## When to Use This

- Integrating a new infrastructure automation tool (e.g., CloudFormation, Chef, Puppet)
- Creating tool-specific execution wrappers
- Building custom deployment workflows
- Extending InfraFoundry's capabilities without modifying core code

## Architecture Overview

### Protocol-Based Design (Interface Segregation Principle)

InfraFoundry uses Python protocols to define runner capabilities. This means:

1. **Implement only what you need** - Your runner only needs the protocols it supports
2. **Type safety** - mypy and IDEs understand protocol compliance
3. **Runtime checking** - Code can check capabilities using `isinstance()`
4. **Clear contracts** - Each protocol defines a specific capability

### Available Protocols

```python
from infrafoundry.core.protocols import (
    Plannable,         # Generate execution plans
    Applyable,         # Apply infrastructure changes
    Destroyable,       # Destroy infrastructure
    StateAware,        # Track infrastructure state/IDs
    DriftDetectable,   # Detect configuration drift
)
```

**Protocol Support Matrix:**

| Runner | Plannable | Applyable | Destroyable | StateAware | DriftDetectable |
|--------|-----------|-----------|-------------|------------|-----------------|
| TerraformRunner | ✅ | ✅ | ✅ | ✅ | ✅ |
| AnsibleRunner | ✅ | ✅ | ❌ | ❌ | ❌ |
| PyInfraRunner | ✅ | ✅ | ❌ | ❌ | ❌ |
| PulumiRunner | ✅ | ✅ | ✅ | ✅ | ✅ |

### BaseRunner Contract

All runners **must** extend `BaseRunner` and implement:

```python
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

class BaseRunner(ABC):
    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Return the name of the tool (e.g., 'terraform', 'ansible')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the tool is installed and available."""
        pass

    @abstractmethod
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """Initialize the tool in the working directory."""
        pass

    @property
    def priority(self) -> int:
        """Execution priority (lower runs first). Default: 50."""
        return 50
```

## Step-by-Step Implementation

### Step 1: Create Your Runner Class

Create a new file in `src/infrafoundry/core/runners/`:

```python
# src/infrafoundry/core/runners/mycustom_runner.py
"""Custom infrastructure tool runner."""

import shutil
import subprocess
from pathlib import Path
from typing import Any, override

from rich.console import Console

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.result_types import ApplyResult, PlanResult
from infrafoundry.core.runners.base_runner import BaseRunner


class MyCustomRunner(BaseRunner):
    """Handles MyCustomTool command execution.

    Implements Plannable and Applyable protocols.
    """

    def __init__(self, console: Console | None = None) -> None:
        """Initialize runner.

        Args:
            console: Rich console for output (creates default if None)
        """
        super().__init__(console)

    @property
    @override
    def tool_name(self) -> str:
        """Return the tool name."""
        return "mycustomtool"

    @property
    @override
    def priority(self) -> int:
        """Set execution priority.

        Common priorities:
        - 0-10: Provisioning tools (Terraform, CloudFormation)
        - 40-60: Configuration tools (Ansible, Chef, Puppet)
        - 70-80: Application deployment (PyInfra, custom deployers)

        Returns:
            Priority integer (lower runs first)
        """
        return 50  # Configuration tool priority

    @override
    def is_available(self) -> bool:
        """Check if tool is installed.

        Returns:
            True if tool is in PATH, False otherwise
        """
        return shutil.which("mycustomtool") is not None

    @override
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """Initialize the tool in the working directory.

        Args:
            working_dir: Directory containing tool configuration
            **kwargs: Tool-specific initialization options

        Returns:
            Dict with initialization results
        """
        try:
            result = subprocess.run(
                ["mycustomtool", "init"],
                cwd=working_dir,
                capture_output=True,
                text=True,
                check=False,
            )

            return {
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "mycustomtool not found in PATH",
            }

    @override
    def get_version(self) -> str | None:
        """Get the version of the installed tool.

        Returns:
            Version string or None if unavailable
        """
        try:
            result = subprocess.run(
                ["mycustomtool", "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                # Parse version from output (adjust for your tool)
                return result.stdout.strip().split()[-1]
        except FileNotFoundError:
            pass
        return None
```

### Step 2: Implement Protocol Methods

Add the protocol methods your tool supports:

```python
# Continue in mycustom_runner.py

    # Implement Plannable protocol
    def plan(self, provider: ProviderBase, **kwargs: Any) -> PlanResult:
        """Generate an execution plan.

        Args:
            provider: Provider instance to plan for
            **kwargs: Additional plan options (tool-specific)

        Returns:
            PlanResult with success flag and changes info
        """
        tool_dir = provider.output_dir / self.tool_name / provider.name

        if not tool_dir.exists():
            return {
                "success": False,
                "error": f"Tool directory not found: {tool_dir}",
                "has_changes": False,
            }

        self.console.print(f"[cyan]Planning {provider.name} with {self.tool_name}...[/cyan]")

        try:
            # Run your tool's plan/dry-run command
            result = subprocess.run(
                ["mycustomtool", "plan", "--dry-run"],
                cwd=tool_dir,
                capture_output=True,
                text=True,
                check=False,
            )

            # Parse output to detect changes (tool-specific)
            has_changes = "will be created" in result.stdout or "will be updated" in result.stdout

            if result.returncode == 0:
                self.console.print(f"[green]✓ Plan completed[/green]")
                return {
                    "success": True,
                    "has_changes": has_changes,
                    "changes_summary": self._parse_changes(result.stdout),
                    "output": result.stdout,
                }
            else:
                self.console.print(f"[red]✗ Plan failed[/red]")
                return {
                    "success": False,
                    "exit_code": result.returncode,
                    "error": result.stderr,
                    "output": result.stdout,
                    "has_changes": False,
                }

        except FileNotFoundError:
            return {
                "success": False,
                "error": "mycustomtool not found in PATH",
                "has_changes": False,
            }

    # Implement Applyable protocol
    def apply(
        self,
        provider: ProviderBase,
        auto_approve: bool = True,
        **kwargs: Any
    ) -> ApplyResult:
        """Apply infrastructure changes.

        Args:
            provider: Provider instance to apply
            auto_approve: Whether to auto-approve changes (default: True)
                         If False, tool should run in check/dry-run mode if supported
            **kwargs: Additional apply options

        Returns:
            ApplyResult with success flag and resource counts
        """
        tool_dir = provider.output_dir / self.tool_name / provider.name

        if not tool_dir.exists():
            return {
                "success": False,
                "error": f"Tool directory not found: {tool_dir}",
            }

        # Build command based on auto_approve
        cmd = ["mycustomtool", "apply"]
        if auto_approve:
            cmd.append("--auto-approve")
        else:
            # Some tools interpret auto_approve=False as "dry-run only"
            cmd.extend(["--dry-run", "--check"])

        self.console.print(
            f"[cyan]Applying {provider.name} with {self.tool_name} "
            f"(auto_approve={auto_approve})...[/cyan]"
        )

        try:
            result = subprocess.run(
                cmd,
                cwd=tool_dir,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                # Parse output for resource counts (tool-specific)
                created = self._count_resources(result.stdout, "created")
                updated = self._count_resources(result.stdout, "updated")
                deleted = self._count_resources(result.stdout, "deleted")

                self.console.print(
                    f"[green]✓ Apply completed: "
                    f"{created} created, {updated} updated, {deleted} deleted[/green]"
                )

                return {
                    "success": True,
                    "resources_created": created,
                    "resources_updated": updated,
                    "resources_deleted": deleted,
                    "output": result.stdout,
                }
            else:
                self.console.print(f"[red]✗ Apply failed[/red]")
                return {
                    "success": False,
                    "exit_code": result.returncode,
                    "error": result.stderr,
                    "output": result.stdout,
                }

        except FileNotFoundError:
            return {
                "success": False,
                "error": "mycustomtool not found in PATH",
            }

    # Helper methods
    def _parse_changes(self, output: str) -> str:
        """Parse plan output to create human-readable summary."""
        # Implement tool-specific parsing
        lines = [line for line in output.split('\n') if 'will be' in line]
        return '\n'.join(lines[:10])  # First 10 changes

    def _count_resources(self, output: str, action: str) -> int:
        """Count resources in output by action (created/updated/deleted)."""
        # Implement tool-specific parsing
        import re
        pattern = rf"(\d+)\s+resources?\s+{action}"
        match = re.search(pattern, output, re.IGNORECASE)
        return int(match.group(1)) if match else 0
```

### Step 3: Implement Optional Protocols (If Supported)

If your tool supports additional capabilities:

```python
# Continue in mycustom_runner.py
from infrafoundry.core.result_types import DestroyResult, DriftInfo

    # Implement Destroyable protocol (if your tool supports destroy)
    def destroy(
        self,
        provider: ProviderBase,
        auto_approve: bool = True,
        **kwargs: Any
    ) -> DestroyResult:
        """Destroy infrastructure resources.

        Args:
            provider: Provider instance to destroy
            auto_approve: Whether to auto-approve destruction (default: True)
            **kwargs: Additional destroy options

        Returns:
            DestroyResult with success flag and resource counts
        """
        tool_dir = provider.output_dir / self.tool_name / provider.name

        cmd = ["mycustomtool", "destroy"]
        if auto_approve:
            cmd.append("--auto-approve")

        self.console.print(
            f"[yellow]⚠ Destroying {provider.name} with {self.tool_name}...[/yellow]"
        )

        try:
            result = subprocess.run(
                cmd,
                cwd=tool_dir,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                destroyed = self._count_resources(result.stdout, "destroyed")
                self.console.print(f"[green]✓ Destroyed {destroyed} resources[/green]")

                return {
                    "success": True,
                    "resources_destroyed": destroyed,
                    "output": result.stdout,
                }
            else:
                return {
                    "success": False,
                    "exit_code": result.returncode,
                    "error": result.stderr,
                    "output": result.stdout,
                }

        except FileNotFoundError:
            return {
                "success": False,
                "error": "mycustomtool not found in PATH",
            }

    # Implement StateAware protocol (if your tool tracks resource IDs)
    def get_resource_ids(self, provider: ProviderBase) -> dict[str, str]:
        """Get mapping of resource names to their infrastructure IDs.

        Args:
            provider: Provider instance to query state for

        Returns:
            Dictionary mapping resource names to infrastructure IDs
        """
        tool_dir = provider.output_dir / self.tool_name / provider.name

        try:
            result = subprocess.run(
                ["mycustomtool", "state", "list", "--json"],
                cwd=tool_dir,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                import json
                state_data = json.loads(result.stdout)
                # Parse tool-specific state format
                return {
                    resource["name"]: resource["id"]
                    for resource in state_data.get("resources", [])
                }

        except (FileNotFoundError, json.JSONDecodeError):
            pass

        return {}

    # Implement DriftDetectable protocol (if your tool supports drift detection)
    def parse_plan_for_drift(self, plan_result: PlanResult) -> DriftInfo:
        """Parse plan output to detect configuration drift.

        Args:
            plan_result: Plan result to analyze for drift

        Returns:
            DriftInfo with has_changes flag and summary
        """
        if not plan_result.get("success"):
            return {
                "has_changes": False,
                "summary": "Plan failed - cannot detect drift",
            }

        output = plan_result.get("output", "")

        # Parse tool-specific output for drift indicators
        added = self._count_resources(output, "created")
        changed = self._count_resources(output, "updated")
        destroyed = self._count_resources(output, "deleted")

        has_drift = added > 0 or changed > 0 or destroyed > 0

        summary_parts = []
        if added > 0:
            summary_parts.append(f"{added} resources added")
        if changed > 0:
            summary_parts.append(f"{changed} resources changed")
        if destroyed > 0:
            summary_parts.append(f"{destroyed} resources removed")

        summary = (
            ", ".join(summary_parts) if summary_parts
            else "No drift detected - infrastructure matches configuration"
        )

        return {
            "has_changes": has_drift,
            "summary": summary,
            "added": added,
            "changed": changed,
            "destroyed": destroyed,
        }
```

### Step 4: Export Your Runner

Add your runner to the package exports:

```python
# src/infrafoundry/core/runners/__init__.py

from infrafoundry.core.runners.mycustom_runner import MyCustomRunner

__all__ = [
    # ... existing exports ...
    "MyCustomRunner",
]
```

### Step 5: Register Your Runner

Runners are automatically registered via `ProviderRegistryService`. For custom runners:

**Option A: Modify ProviderRegistryService (for built-in runners)**

```python
# src/infrafoundry/core/provider_registry_service.py

from infrafoundry.core.runners import MyCustomRunner

class ProviderRegistryService:
    def _register_default_runners(self) -> None:
        """Register built-in runners."""
        self.runner_registry.register(TerraformRunner)
        self.runner_registry.register(AnsibleRunner)
        self.runner_registry.register(PyInfraRunner)
        self.runner_registry.register(MyCustomRunner)  # Add yours here
```

**Option B: Register Programmatically (for external plugins)**

```python
# In your application code or plugin initialization
from infrafoundry.core.runners import register_runner
from your_package.runners import MyCustomRunner

register_runner(MyCustomRunner)
```

**Option C: Environment Variable Gating (for experimental runners)**

```python
# In provider_registry_service.py
def _register_default_runners(self) -> None:
    # ... existing registrations ...

    # Register experimental runners
    if os.getenv("INFRA_ENABLE_EXPERIMENTAL"):
        self.runner_registry.register(MyCustomRunner)
```

## Testing Your Runner

### Unit Tests

Create comprehensive unit tests:

```python
# tests/unit/test_mycustom_runner.py
"""Unit tests for MyCustomRunner."""

from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from infrafoundry.core.runners.mycustom_runner import MyCustomRunner


class TestMyCustomRunner:
    """Test MyCustomRunner implementation."""

    def test_tool_name(self):
        """Should return correct tool name."""
        runner = MyCustomRunner()
        assert runner.tool_name == "mycustomtool"

    def test_priority(self):
        """Should return expected priority."""
        runner = MyCustomRunner()
        assert runner.priority == 50

    @patch("shutil.which")
    def test_is_available_when_installed(self, mock_which):
        """Should return True when tool is in PATH."""
        mock_which.return_value = "/usr/bin/mycustomtool"
        runner = MyCustomRunner()
        assert runner.is_available() is True
        mock_which.assert_called_once_with("mycustomtool")

    @patch("shutil.which")
    def test_is_available_when_not_installed(self, mock_which):
        """Should return False when tool is not in PATH."""
        mock_which.return_value = None
        runner = MyCustomRunner()
        assert runner.is_available() is False

    @patch("subprocess.run")
    def test_initialize_success(self, mock_run):
        """Should successfully initialize tool."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Initialized successfully",
            stderr=""
        )

        runner = MyCustomRunner()
        result = runner.initialize(Path("/tmp/test"))

        assert result["success"] is True
        assert result["exit_code"] == 0
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_plan_with_changes(self, mock_run):
        """Should detect changes in plan output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="3 resources will be created\n2 resources will be updated",
            stderr=""
        )

        provider = MagicMock()
        provider.name = "test-provider"
        provider.output_dir = Path("/tmp/generated")

        # Create the expected directory structure
        tool_dir = Path("/tmp/generated/mycustomtool/test-provider")
        tool_dir.mkdir(parents=True, exist_ok=True)

        runner = MyCustomRunner()
        result = runner.plan(provider)

        assert result["success"] is True
        assert result["has_changes"] is True
        assert "changes_summary" in result

    @patch("subprocess.run")
    def test_apply_success(self, mock_run):
        """Should successfully apply changes."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Apply complete! 3 resources created, 2 resources updated, 1 resources deleted",
            stderr=""
        )

        provider = MagicMock()
        provider.name = "test-provider"
        provider.output_dir = Path("/tmp/generated")

        tool_dir = Path("/tmp/generated/mycustomtool/test-provider")
        tool_dir.mkdir(parents=True, exist_ok=True)

        runner = MyCustomRunner()
        result = runner.apply(provider, auto_approve=True)

        assert result["success"] is True
        assert result.get("resources_created", 0) >= 0
        assert result.get("resources_updated", 0) >= 0
```

### Protocol Compliance Tests

Verify your runner implements the expected protocols:

```python
# tests/unit/test_runner_interfaces.py (add to existing file)

from infrafoundry.core.protocols import (
    Applyable,
    Destroyable,
    DriftDetectable,
    Plannable,
    StateAware,
)
from infrafoundry.core.runners.mycustom_runner import MyCustomRunner


class TestMyCustomRunnerInterfaces:
    """Test MyCustomRunner protocol compliance."""

    def test_implements_required_protocols(self):
        """MyCustomRunner should implement core protocols."""
        runner = MyCustomRunner()

        # Check protocols your runner implements
        assert isinstance(runner, Plannable)
        assert isinstance(runner, Applyable)

    def test_does_not_implement_optional_protocols(self):
        """MyCustomRunner should NOT implement protocols it doesn't support."""
        runner = MyCustomRunner()

        # Check protocols your runner does NOT implement
        # (Adjust based on your implementation)
        assert not isinstance(runner, Destroyable)
        assert not isinstance(runner, StateAware)
        assert not isinstance(runner, DriftDetectable)

    def test_methods_have_correct_signatures(self):
        """Protocol methods should have correct signatures."""
        runner = MyCustomRunner()

        # Verify callable
        assert callable(runner.plan)
        assert callable(runner.apply)

        # Verify methods exist if protocols are implemented
        if isinstance(runner, Destroyable):
            assert callable(runner.destroy)
        if isinstance(runner, StateAware):
            assert callable(runner.get_resource_ids)
        if isinstance(runner, DriftDetectable):
            assert callable(runner.parse_plan_for_drift)
```

### Integration Tests

Test your runner with actual tool execution:

```python
# tests/integration/test_mycustom_runner_integration.py
"""Integration tests for MyCustomRunner."""

import pytest
from pathlib import Path

from infrafoundry.core.runners.mycustom_runner import MyCustomRunner


@pytest.mark.skipif(
    not MyCustomRunner().is_available(),
    reason="mycustomtool not installed"
)
class TestMyCustomRunnerIntegration:
    """Integration tests requiring actual mycustomtool installation."""

    def test_full_workflow(self, tmp_path):
        """Test complete plan -> apply -> destroy workflow."""
        runner = MyCustomRunner()

        # Setup test provider
        provider = MagicMock()
        provider.name = "integration-test"
        provider.output_dir = tmp_path

        # Create tool directory with config
        tool_dir = tmp_path / "mycustomtool" / "integration-test"
        tool_dir.mkdir(parents=True)
        (tool_dir / "config.yaml").write_text("# test config")

        # Initialize
        init_result = runner.initialize(tool_dir)
        assert init_result["success"] is True

        # Plan
        plan_result = runner.plan(provider)
        assert plan_result["success"] is True

        # Apply
        apply_result = runner.apply(provider, auto_approve=True)
        assert apply_result["success"] is True

        # Destroy (if supported)
        if isinstance(runner, Destroyable):
            destroy_result = runner.destroy(provider, auto_approve=True)
            assert destroy_result["success"] is True
```

## Best Practices

### 1. Error Handling

Always handle errors gracefully and return structured results:

```python
def apply(self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any) -> ApplyResult:
    try:
        # Tool execution
        result = subprocess.run(...)

        if result.returncode == 0:
            return {"success": True, ...}
        else:
            return {
                "success": False,
                "exit_code": result.returncode,
                "error": result.stderr,
            }

    except FileNotFoundError:
        return {
            "success": False,
            "error": f"{self.tool_name} not found in PATH",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
        }
```

### 2. Console Output

Use Rich console for user-friendly output:

```python
from rich.console import Console

# Success
self.console.print("[green]✓ Apply completed[/green]")

# Warning
self.console.print("[yellow]⚠ Warning: No changes detected[/yellow]")

# Error
self.console.print("[red]✗ Apply failed[/red]")

# Info
self.console.print(f"[cyan]Planning {provider.name}...[/cyan]")

# Dim/debug info
self.console.print(f"[dim]Using directory: {tool_dir}[/dim]")
```

### 3. Type Safety

Use TypedDict return types for type safety:

```python
from infrafoundry.core.result_types import ApplyResult

def apply(...) -> ApplyResult:
    return {
        "success": True,
        "resources_created": 3,
        "resources_updated": 2,
        "output": "...",
    }
```

### 4. Working Directory Management

Always use the tool's dedicated directory:

```python
def plan(self, provider: ProviderBase, **kwargs: Any) -> PlanResult:
    # Standard directory structure: generated/{tool_name}/{provider_name}
    tool_dir = provider.output_dir / self.tool_name / provider.name

    if not tool_dir.exists():
        return {
            "success": False,
            "error": f"Tool directory not found: {tool_dir}",
        }

    # Execute in tool directory
    result = subprocess.run(
        ["mycustomtool", "plan"],
        cwd=tool_dir,  # Important!
        ...
    )
```

### 5. Tool Availability Checking

Implement robust availability checking:

```python
import shutil

def is_available(self) -> bool:
    """Check if tool is available."""
    # Check PATH
    if shutil.which(self.tool_name) is None:
        return False

    # Optionally: Check minimum version
    version = self.get_version()
    if version and not self._check_minimum_version(version):
        return False

    return True

def _check_minimum_version(self, version: str) -> bool:
    """Check if version meets minimum requirements."""
    from packaging import version as pkg_version
    return pkg_version.parse(version) >= pkg_version.parse("1.0.0")
```

### 6. Subprocess Execution

Use safe subprocess patterns:

```python
import subprocess

# Good: Capture output, check=False, handle errors
result = subprocess.run(
    ["tool", "command"],
    cwd=working_dir,
    capture_output=True,  # Capture stdout/stderr
    text=True,            # Decode as text
    check=False,          # Don't raise exception on error
    timeout=300,          # Prevent hanging
)

# Handle result
if result.returncode == 0:
    # Success
    pass
else:
    # Failure - use result.stderr for error message
    pass
```

### 7. Configuration Parsing

Parse tool output carefully:

```python
def _parse_output(self, output: str) -> dict[str, int]:
    """Parse tool output for resource counts."""
    import re

    counts = {
        "created": 0,
        "updated": 0,
        "deleted": 0,
    }

    # Use regex for reliable parsing
    for action, pattern in [
        ("created", r"(\d+)\s+resources?\s+created"),
        ("updated", r"(\d+)\s+resources?\s+updated"),
        ("deleted", r"(\d+)\s+resources?\s+deleted"),
    ]:
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            counts[action] = int(match.group(1))

    return counts
```

## Advanced Topics

### Custom Result Types

If the standard TypedDict types don't fit your needs:

```python
# In your runner file or create a custom result_types module
from typing import NotRequired, TypedDict

class MyCustomResult(TypedDict):
    """Custom result type for your tool."""
    success: bool
    exit_code: NotRequired[int]
    error: NotRequired[str]

    # Tool-specific fields
    custom_metric: NotRequired[int]
    execution_time: NotRequired[float]
    warnings: NotRequired[list[str]]
```

### Environment-Specific Configuration

Support per-environment configuration:

```python
def apply(self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any) -> ApplyResult:
    # Get environment from provider
    env_name = kwargs.get("env_name")

    # Build command with environment-specific flags
    cmd = [self.tool_name, "apply"]
    if env_name == "production":
        cmd.extend(["--extra-validation", "--audit-log"])

    # Execute
    result = subprocess.run(cmd, ...)
```

### Parallel Execution Support

If your tool supports parallel execution:

```python
def apply(self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any) -> ApplyResult:
    parallelism = kwargs.get("parallelism", 10)

    cmd = [self.tool_name, "apply", f"--parallelism={parallelism}"]
    # ...
```

### Progress Reporting

For long-running operations:

```python
from rich.progress import Progress

def apply(self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any) -> ApplyResult:
    with Progress() as progress:
        task = progress.add_task(
            f"[cyan]Applying {provider.name}...",
            total=100
        )

        # Stream output and update progress
        process = subprocess.Popen(
            ["mycustomtool", "apply"],
            cwd=tool_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        for line in process.stdout:
            # Parse line for progress indicators
            if "Progress:" in line:
                percent = self._parse_percent(line)
                progress.update(task, completed=percent)

        process.wait()
        # ...
```

## Troubleshooting

### Runner Not Found

**Symptom:** `"mycustomtool runner not available"`

**Solutions:**
1. Check tool is in PATH: `which mycustomtool`
2. Verify runner is registered in `ProviderRegistryService`
3. Check `is_available()` implementation
4. Enable debug logging:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

### Tool Execution Fails

**Symptom:** `subprocess.run()` returns non-zero exit code

**Solutions:**
1. Test command manually in terminal
2. Check working directory exists and has correct files
3. Verify tool-specific requirements (environment variables, credentials)
4. Capture and log stderr: `print(result.stderr)`
5. Add verbose flag to tool command: `["tool", "-v", "command"]`

### Protocol Not Detected

**Symptom:** `isinstance(runner, Plannable)` returns False

**Solutions:**
1. Verify method signature matches protocol exactly:
   ```python
   # Protocol definition
   def plan(self, provider: "ProviderBase", **kwargs: Any) -> PlanResult: ...

   # Your implementation - must match exactly
   def plan(self, provider: ProviderBase, **kwargs: Any) -> PlanResult:
   ```
2. Check return type is correct TypedDict
3. Import protocol at runtime: `from infrafoundry.core.protocols import Plannable`
4. Ensure protocol is decorated with `@runtime_checkable`

### Type Checking Errors

**Symptom:** mypy reports type errors

**Solutions:**
1. Use correct return types from `result_types.py`
2. Add type hints to all method parameters
3. Use `cast()` when necessary:
   ```python
   from typing import cast
   from infrafoundry.core.protocols import StateAware

   if isinstance(runner, StateAware):
       state_runner = cast(StateAware, runner)
       ids = state_runner.get_resource_ids(provider)
   ```

### Import Errors

**Symptom:** `ImportError: cannot import name 'MyCustomRunner'`

**Solutions:**
1. Check runner is in `__all__` in `runners/__init__.py`
2. Verify file is in correct directory
3. Check for circular imports
4. Ensure Python can find the module: `python -c "from infrafoundry.core.runners import MyCustomRunner"`

## Examples and Templates

### Minimal Runner Template

```python
"""Minimal runner template."""

import shutil
from pathlib import Path
from typing import Any, override

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.result_types import ApplyResult
from infrafoundry.core.runners.base_runner import BaseRunner


class MinimalRunner(BaseRunner):
    """Minimal runner implementing only Applyable."""

    @property
    @override
    def tool_name(self) -> str:
        return "minimal"

    @override
    def is_available(self) -> bool:
        return shutil.which("minimal") is not None

    @override
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        return {"success": True}

    def apply(self, provider: ProviderBase, auto_approve: bool = True, **kwargs: Any) -> ApplyResult:
        """Apply changes."""
        # Your implementation here
        return {"success": True}
```

### Complete Runner Example

See `src/infrafoundry/core/runners/terraform_runner.py` for a complete, production-ready example implementing all protocols.

## Related Documentation

- [Pluggable Runners Architecture](../architecture/pluggable-runners.md)
- [Protocols Reference](../architecture/design-principles-assessment.md)
- [Runner Execution Overview](../runners/overview.md)
- [Implementing Providers](implementing-providers.md)
- [Testing Guide](../testing/TESTING_MAINTENANCE_REPORT.md)

## Next Steps

1. **Create your runner** following the step-by-step guide
2. **Write tests** to verify protocol compliance
3. **Test integration** with actual infrastructure
4. **Register runner** in ProviderRegistryService
5. **Document usage** in `docs/runners/{your_tool}.md`
6. **Submit PR** with your new runner

---

**Last Updated:** 2025-12-23 (Protocol-based runner system - PR #77)

---
[Back to Table of Contents](../index.md)
