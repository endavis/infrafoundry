# Pluggable Runner System

## Overview

InfraFoundry now has a pluggable runner system that allows you to add support for any infrastructure tool (Terraform, Ansible, Pulumi, OpenTofu, etc.) without modifying core framework code.

## Architecture

```
src/infrafoundry/core/runners/
├── base_runner.py           # Abstract base class
├── terraform_runner.py      # Built-in Terraform support
├── ansible_runner.py        # Built-in Ansible support
├── pulumi_runner.py         # Example: Pulumi support
├── runner_registry.py       # Runner discovery and registration
└── __init__.py             # Auto-registration of built-in runners
```

## Built-in Runners

### TerraformRunner
- **Tool**: Terraform (>= 1.6)
- **Methods**: plan, apply, destroy, validate
- **Features**: Auto-init, state management, drift detection
- **Credentials**: Auto-loads from SecretManager

### AnsibleRunner
- **Tool**: Ansible (>= 2.15)
- **Methods**: plan (check mode), apply, validate
- **Features**: Playbook execution, syntax checking
- **Credentials**: Uses environment variables

## Creating a Custom Runner

### Step 1: Implement BaseRunner

```python
from pathlib import Path
from typing import Any, override
from rich.console import Console

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.runners import BaseRunner


class CustomRunner(BaseRunner):
    """Runner for your custom infrastructure tool."""

    @property
    @override
    def tool_name(self) -> str:
        return "mycustomtool"

    @override
    def is_available(self) -> bool:
        """Check if tool is installed."""
        import shutil
        return shutil.which("mycustomtool") is not None

    @override
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """Initialize tool in working directory."""
        # Your initialization logic
        return {"success": True}

    @override
    def plan(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Generate execution plan."""
        # Your plan logic
        return {"success": True}

    @override
    def apply(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Apply changes."""
        # Your apply logic
        return {"success": True}

    @override
    def destroy(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Destroy resources."""
        # Your destroy logic
        return {"success": True}
```

### Step 2: Register Your Runner

**Option A: Auto-registration (recommended)**

Place your runner in `src/infrafoundry/core/runners/`:

```python
# src/infrafoundry/core/runners/__init__.py
from infrafoundry.core.runners.custom_runner import CustomRunner

register_runner(CustomRunner)
```

**Option B: Manual registration**

Register at runtime:

```python
from infrafoundry.core.runners import register_runner
from myproject.custom_runner import CustomRunner

register_runner(CustomRunner)
```

### Step 3: Use Your Runner

```python
from infrafoundry.core.runners import get_runner, create_runner

# Get runner class
CustomRunner = get_runner("mycustomtool")

# Or create instance directly
runner = create_runner("mycustomtool", console=console)

# Check availability
if runner.is_available():
    # Use runner
    result = runner.plan(provider)
    if result["success"]:
        runner.apply(provider, auto_approve=True)
```

## Example: Pulumi Runner

See `pulumi_runner.py` for a complete example implementing:
- ✅ Stack management
- ✅ Preview (plan) support
- ✅ Auto-approve for apply/destroy
- ✅ Version checking
- ✅ Configuration validation

To use Pulumi:

```python
from infrafoundry.core.runners import register_runner
from infrafoundry.core.runners.pulumi_runner import PulumiRunner

# Register Pulumi runner
register_runner(PulumiRunner)

# Use in orchestrator
pulumi = create_runner("pulumi", stack="production")
pulumi.plan(provider)
pulumi.apply(provider, auto_approve=True)
```

## Runner Registry

The `RunnerRegistry` manages all available runners:

```python
from infrafoundry.core.runners import list_runners, get_runner

# List all registered runners
tools = list_runners()  # ['terraform', 'ansible', 'pulumi', ...]

# Get specific runner
TerraformRunner = get_runner("terraform")

# Check if runner exists
if get_runner("opentofu"):
    print("OpenTofu support available!")
```

## Integration with Orchestrator

Runners integrate seamlessly with the orchestrator:

```python
class Orchestrator:
    def __init__(self, ...):
        # Get runners from registry
        self.terraform_runner = create_runner("terraform", 
                                            secret_manager=secret_manager,
                                            console=console)
        self.ansible_runner = create_runner("ansible", console=console)
        
        # Or use custom runners
        if get_runner("pulumi"):
            self.pulumi_runner = create_runner("pulumi", stack="prod")
```

## Best Practices

### 1. Tool Availability
Always check if tool is installed:

```python
if not runner.is_available():
    console.print(f"[yellow]{runner.tool_name} not installed[/yellow]")
    return
```

### 2. Error Handling
Return consistent error format:

```python
try:
    result = subprocess.run(...)
    return {"success": True, "output": result.stdout}
except subprocess.CalledProcessError as e:
    return {"success": False, "error": str(e), "exit_code": e.returncode}
```

### 3. Initialization
Check for initialization before running commands:

```python
def apply(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
    # Initialize if needed
    init_result = self.initialize(provider.output_dir)
    if not init_result["success"]:
        return init_result
    
    # Run command
    ...
```

### 4. Version Compatibility
Implement `get_version()` for debugging:

```python
@override
def get_version(self) -> str | None:
    result = subprocess.run([self.tool_name, "--version"], ...)
    return result.stdout.strip()
```

## Testing Runners

Create tests for your custom runner:

```python
# tests/unit/test_custom_runner.py
import pytest
from infrafoundry.core.runners.custom_runner import CustomRunner


def test_tool_name():
    runner = CustomRunner()
    assert runner.tool_name == "mycustomtool"


def test_is_available(monkeypatch):
    runner = CustomRunner()
    # Mock tool availability
    monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/mycustomtool")
    assert runner.is_available()


def test_plan(mock_provider):
    runner = CustomRunner()
    result = runner.plan(mock_provider)
    assert result["success"]
```

## Supported Runner Methods

### Required Methods
- `tool_name` - Property returning tool name
- `is_available()` - Check if tool is installed
- `initialize()` - Set up tool in working directory
- `plan()` - Generate execution plan
- `apply()` - Apply changes
- `destroy()` - Destroy resources

### Optional Methods
- `get_version()` - Return tool version
- `validate_config()` - Validate configuration

## Future Runners

Potential runners to add:

- **OpenTofu** - Terraform fork
- **CDK (AWS/Terraform)** - Cloud Development Kit
- **Crossplane** - Kubernetes-native IaC
- **Chef/Puppet** - Configuration management
- **Salt** - Configuration management
- **CloudFormation** - AWS native IaC

## Migration from Old System

Old code:
```python
from infrafoundry.core.terraform_runner import TerraformRunner

runner = TerraformRunner(secret_manager, console)
```

New code (backward compatible):
```python
from infrafoundry.core.runners import TerraformRunner
# Or use registry:
from infrafoundry.core.runners import create_runner

runner = create_runner("terraform", 
                      secret_manager=secret_manager,
                      console=console)
```

## Benefits

✅ **Extensible** - Add new tools without modifying core code
✅ **Pluggable** - Drop in new runners via registration
✅ **Consistent** - All runners follow same interface
✅ **Testable** - Easy to mock and test runners
✅ **Discoverable** - Registry shows all available tools
✅ **Backward Compatible** - Old imports still work
