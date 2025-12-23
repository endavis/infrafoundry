# Runner Protocol Quick Reference

This is a quick reference guide for working with InfraFoundry's protocol-based runner system. For comprehensive documentation, see [Implementing Runners](implementing-runners.md).

## Protocol Cheat Sheet

### All Available Protocols

```python
from infrafoundry.core.protocols import (
    Plannable,         # Generate execution plans
    Applyable,         # Apply infrastructure changes
    Destroyable,       # Destroy infrastructure
    StateAware,        # Track resource IDs/state
    DriftDetectable,   # Detect configuration drift
)
```

### Runner Protocol Matrix

| Runner | Plannable | Applyable | Destroyable | StateAware | DriftDetectable |
|--------|-----------|-----------|-------------|------------|-----------------|
| **TerraformRunner** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **AnsibleRunner** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **PyInfraRunner** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **PulumiRunner** | ✅ | ✅ | ✅ | ✅ | ✅ |

## Common Usage Patterns

### Checking Capabilities

```python
from infrafoundry.core.protocols import Plannable, Applyable, Destroyable

# Check if runner supports an operation
if isinstance(runner, Plannable):
    result = runner.plan(provider)

if isinstance(runner, Applyable):
    result = runner.apply(provider, auto_approve=True)

if isinstance(runner, Destroyable):
    result = runner.destroy(provider, auto_approve=True)
else:
    print(f"{runner.tool_name} does not support destroy operations")
```

### Using Protocol Methods

```python
# Plan (if supported)
if isinstance(runner, Plannable):
    plan_result: PlanResult = runner.plan(provider)
    if plan_result["success"]:
        print(f"Has changes: {plan_result.get('has_changes', False)}")

# Apply (if supported)
if isinstance(runner, Applyable):
    apply_result: ApplyResult = runner.apply(provider, auto_approve=True)
    if apply_result["success"]:
        print(f"Created: {apply_result.get('resources_created', 0)}")
        print(f"Updated: {apply_result.get('resources_updated', 0)}")

# Destroy (if supported)
if isinstance(runner, Destroyable):
    destroy_result: DestroyResult = runner.destroy(provider, auto_approve=True)
    if destroy_result["success"]:
        print(f"Destroyed: {destroy_result.get('resources_destroyed', 0)}")

# Get resource IDs (if supported)
if isinstance(runner, StateAware):
    resource_ids: dict[str, str] = runner.get_resource_ids(provider)
    for name, resource_id in resource_ids.items():
        print(f"{name}: {resource_id}")

# Detect drift (if supported)
if isinstance(runner, DriftDetectable) and isinstance(runner, Plannable):
    plan_result = runner.plan(provider)
    drift_info: DriftInfo = runner.parse_plan_for_drift(plan_result)
    if drift_info["has_changes"]:
        print(f"Drift detected: {drift_info['summary']}")
```

### Type Narrowing

```python
from typing import cast

# After isinstance check, mypy knows the type
for tool_name, runner in runners:
    if isinstance(runner, StateAware):
        # No cast needed - mypy understands type narrowing
        ids = runner.get_resource_ids(provider)

        # But if you want to be explicit:
        state_runner = cast(StateAware, runner)
        ids = state_runner.get_resource_ids(provider)
```

## Result Types

### PlanResult

```python
from infrafoundry.core.result_types import PlanResult

result: PlanResult = {
    "success": True,
    "has_changes": True,
    "changes_summary": "3 resources to add, 2 to change",
    "output": "Full plan output...",
    "plan_file": "/path/to/plan.tfplan",  # Optional, tool-specific
}
```

### ApplyResult

```python
from infrafoundry.core.result_types import ApplyResult

result: ApplyResult = {
    "success": True,
    "resources_created": 3,
    "resources_updated": 2,
    "resources_deleted": 1,
    "output": "Apply output...",
}
```

### DestroyResult

```python
from infrafoundry.core.result_types import DestroyResult

result: DestroyResult = {
    "success": True,
    "resources_destroyed": 5,
    "output": "Destroy output...",
}
```

### DriftInfo

```python
from infrafoundry.core.result_types import DriftInfo

drift: DriftInfo = {
    "has_changes": True,
    "summary": "2 resources changed, 1 added",
    "added": 1,
    "changed": 2,
    "destroyed": 0,
}
```

## Implementing a Runner

### Minimal Runner (Applyable Only)

```python
from infrafoundry.core.runners.base_runner import BaseRunner
from infrafoundry.core.result_types import ApplyResult
from infrafoundry.core.provider import ProviderBase
import shutil

class MyRunner(BaseRunner):
    @property
    def tool_name(self) -> str:
        return "mytool"

    def is_available(self) -> bool:
        return shutil.which("mytool") is not None

    def initialize(self, working_dir, **kwargs):
        return {"success": True}

    # Implement Applyable protocol
    def apply(self, provider: ProviderBase, auto_approve: bool = True, **kwargs) -> ApplyResult:
        # Your implementation
        return {"success": True}
```

### Full-Featured Runner (All Protocols)

```python
from infrafoundry.core.runners.base_runner import BaseRunner
from infrafoundry.core.result_types import (
    PlanResult, ApplyResult, DestroyResult, DriftInfo
)
from infrafoundry.core.provider import ProviderBase

class FullRunner(BaseRunner):
    # BaseRunner requirements
    @property
    def tool_name(self) -> str:
        return "fulltool"

    def is_available(self) -> bool:
        return True

    def initialize(self, working_dir, **kwargs):
        return {"success": True}

    # Plannable protocol
    def plan(self, provider: ProviderBase, **kwargs) -> PlanResult:
        return {
            "success": True,
            "has_changes": False,
        }

    # Applyable protocol
    def apply(self, provider: ProviderBase, auto_approve: bool = True, **kwargs) -> ApplyResult:
        return {
            "success": True,
            "resources_created": 0,
        }

    # Destroyable protocol
    def destroy(self, provider: ProviderBase, auto_approve: bool = True, **kwargs) -> DestroyResult:
        return {
            "success": True,
            "resources_destroyed": 0,
        }

    # StateAware protocol
    def get_resource_ids(self, provider: ProviderBase) -> dict[str, str]:
        return {}

    # DriftDetectable protocol
    def parse_plan_for_drift(self, plan_result: PlanResult) -> DriftInfo:
        return {
            "has_changes": False,
            "summary": "No drift detected",
        }
```

## Testing Protocol Compliance

```python
# tests/unit/test_runner_interfaces.py
from infrafoundry.core.protocols import Plannable, Applyable
from your_package.runners import MyRunner

def test_my_runner_protocols():
    runner = MyRunner()

    # Test implemented protocols
    assert isinstance(runner, Plannable)
    assert isinstance(runner, Applyable)

    # Test NOT implemented protocols
    assert not isinstance(runner, Destroyable)

    # Test methods are callable
    assert callable(runner.plan)
    assert callable(runner.apply)
```

## Common Patterns

### Safe Protocol Usage

```python
# ✅ Good - Always check protocol first
if isinstance(runner, Destroyable):
    runner.destroy(provider, auto_approve=True)
else:
    console.print(f"[yellow]{runner.tool_name} does not support destroy[/yellow]")

# ❌ Bad - Will raise AttributeError if protocol not supported
runner.destroy(provider, auto_approve=True)  # Unsafe!
```

### Conditional Execution

```python
# Execute only on runners that support the operation
for tool_name, runner in runners:
    if isinstance(runner, Applyable):
        console.print(f"[cyan]Applying with {tool_name}...[/cyan]")
        result = runner.apply(provider, auto_approve=auto_approve)

        if result["success"] and isinstance(runner, StateAware):
            # Bonus: Get resource IDs if supported
            ids = runner.get_resource_ids(provider)
    else:
        console.print(f"[dim]Skipping {tool_name}: no apply support[/dim]")
```

### Getting Runner Capabilities

```python
def get_capabilities(runner: BaseRunner) -> list[str]:
    """Get list of operations a runner supports."""
    capabilities = []

    if isinstance(runner, Plannable):
        capabilities.append("plan")
    if isinstance(runner, Applyable):
        capabilities.append("apply")
    if isinstance(runner, Destroyable):
        capabilities.append("destroy")
    if isinstance(runner, StateAware):
        capabilities.append("state_tracking")
    if isinstance(runner, DriftDetectable):
        capabilities.append("drift_detection")

    return capabilities

# Usage
caps = get_capabilities(runner)
print(f"{runner.tool_name} supports: {', '.join(caps)}")
# Output: "terraform supports: plan, apply, destroy, state_tracking, drift_detection"
```

## Error Handling

### Structured Error Results

```python
def apply(self, provider, auto_approve=True, **kwargs) -> ApplyResult:
    try:
        # Tool execution
        result = subprocess.run(...)

        if result.returncode == 0:
            return {
                "success": True,
                "resources_created": 3,
            }
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

### Checking Results

```python
result = runner.apply(provider)

if result["success"]:
    print("✓ Success!")
    print(f"Created: {result.get('resources_created', 0)}")
else:
    print("✗ Failed!")
    print(f"Error: {result.get('error', 'Unknown error')}")
    print(f"Exit code: {result.get('exit_code', 'N/A')}")
```

## mypy Configuration

Ensure your mypy config supports protocol type narrowing:

```toml
# pyproject.toml
[tool.mypy]
python_version = "3.10"
strict = true
warn_redundant_casts = true
warn_unused_ignores = true

# Protocol type narrowing requires mypy 0.971+
# Check version: mypy --version
```

## Quick Troubleshooting

### "AttributeError: 'XRunner' object has no attribute 'plan'"

**Cause:** Calling protocol method without checking isinstance first

**Fix:**
```python
# Before
runner.plan(provider)  # ❌ Will fail if runner doesn't implement Plannable

# After
if isinstance(runner, Plannable):  # ✅ Check first
    runner.plan(provider)
```

### "isinstance returns False but method exists"

**Cause:** Method signature doesn't match protocol exactly

**Fix:** Ensure exact signature match:
```python
# Protocol definition
def plan(self, provider: "ProviderBase", **kwargs: Any) -> PlanResult: ...

# Your implementation - must match exactly
def plan(self, provider: ProviderBase, **kwargs: Any) -> PlanResult:
    ...
```

### "mypy doesn't recognize protocol"

**Cause:** Missing `@runtime_checkable` decorator or wrong import

**Fix:** Protocols must be decorated:
```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class MyProtocol(Protocol):
    ...
```

## See Also

- [Implementing Runners (Full Guide)](implementing-runners.md)
- [Pluggable Runners Architecture](../architecture/pluggable-runners.md)
- [Custom Runner Example](../examples/custom-runner-example.md)
- [ADR-0004: Protocol-Based Runner Interfaces](../architecture/decisions/0004-protocol-based-runner-interfaces.md)

---

**Last Updated:** 2025-12-23

---
[Back to Development Guides](README.md)
