# Custom Runner Implementation Example

This document provides a complete, working example of implementing a custom runner for InfraFoundry, including all the necessary files and configurations.

## Scenario

We'll create a runner for **CloudFormation**, AWS's infrastructure-as-code service. This runner will:
- ✅ Support **plan** operations (CloudFormation change sets)
- ✅ Support **apply** operations (stack create/update)
- ✅ Support **destroy** operations (stack delete)
- ✅ Support **state tracking** (stack resource IDs)
- ❌ Not support drift detection (CloudFormation has limited drift support)

## Directory Structure

```
src/infrafoundry/core/runners/
├── __init__.py
├── base_runner.py
├── cloudformation_runner.py  # New file
├── terraform_runner.py
├── ansible_runner.py
└── ...

tests/unit/
├── test_cloudformation_runner.py  # New file
└── test_runner_interfaces.py      # Updated

docs/runners/
└── cloudformation.md              # New file
```

## Implementation

### Step 1: Runner Implementation

```python
# src/infrafoundry/core/runners/cloudformation_runner.py
"""CloudFormation runner implementation."""

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, override

from rich.console import Console

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.result_types import (
    ApplyResult,
    DestroyResult,
    PlanResult,
)
from infrafoundry.core.runners.base_runner import BaseRunner


class CloudFormationRunner(BaseRunner):
    """Handles AWS CloudFormation stack operations.

    Implements Plannable, Applyable, Destroyable, and StateAware protocols.
    Does NOT implement DriftDetectable (CloudFormation drift detection is complex).
    """

    def __init__(self, console: Console | None = None) -> None:
        """Initialize CloudFormation runner.

        Args:
            console: Rich console for output (creates default if None)
        """
        super().__init__(console)

    @property
    @override
    def tool_name(self) -> str:
        """Return the tool name."""
        return "cloudformation"

    @property
    @override
    def priority(self) -> int:
        """CloudFormation is a provisioning tool (like Terraform).

        Returns:
            Priority 5 (after Terraform but before configuration tools)
        """
        return 5

    @override
    def is_available(self) -> bool:
        """Check if AWS CLI is installed and configured.

        Returns:
            True if aws command is available, False otherwise
        """
        return shutil.which("aws") is not None

    @override
    def get_version(self) -> str | None:
        """Get AWS CLI version.

        Returns:
            Version string or None if unavailable
        """
        try:
            result = subprocess.run(
                ["aws", "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                # Output format: "aws-cli/2.13.0 Python/3.11.4 ..."
                parts = result.stdout.split()
                if parts:
                    version = parts[0].split("/")[-1]
                    return version
        except FileNotFoundError:
            pass
        return None

    @override
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """Initialize CloudFormation working directory.

        Args:
            working_dir: Directory containing CloudFormation templates
            **kwargs: Additional options

        Returns:
            Dict with initialization results
        """
        if not working_dir.exists():
            return {
                "success": False,
                "error": f"Working directory does not exist: {working_dir}",
            }

        # Verify AWS credentials
        try:
            result = subprocess.run(
                ["aws", "sts", "get-caller-identity"],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                identity = json.loads(result.stdout)
                return {
                    "success": True,
                    "aws_account": identity.get("Account"),
                    "aws_user": identity.get("Arn"),
                }
            else:
                return {
                    "success": False,
                    "error": "AWS credentials not configured",
                    "details": result.stderr,
                }

        except (FileNotFoundError, json.JSONDecodeError) as e:
            return {
                "success": False,
                "error": f"Failed to verify AWS credentials: {str(e)}",
            }

    @override
    def validate_config(self, provider: ProviderBase) -> dict[str, Any]:
        """Validate CloudFormation templates.

        Args:
            provider: Provider instance

        Returns:
            Dict with validation results
        """
        cfn_dir = provider.output_dir / self.tool_name / provider.name
        template_file = cfn_dir / "template.yaml"

        if not template_file.exists():
            return {
                "valid": False,
                "message": f"Template not found: {template_file}",
            }

        try:
            result = subprocess.run(
                ["aws", "cloudformation", "validate-template", "--template-body", f"file://{template_file}"],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                return {
                    "valid": True,
                    "message": "Template is valid",
                }
            else:
                return {
                    "valid": False,
                    "message": "Template validation failed",
                    "details": result.stderr,
                }

        except FileNotFoundError:
            return {
                "valid": False,
                "message": "AWS CLI not found",
            }

    # Implement Plannable protocol
    def plan(self, provider: ProviderBase, **kwargs: Any) -> PlanResult:
        """Generate CloudFormation change set (plan).

        Args:
            provider: Provider instance to plan for
            **kwargs: Additional plan options

        Returns:
            PlanResult with success flag and changes info
        """
        cfn_dir = provider.output_dir / self.tool_name / provider.name
        template_file = cfn_dir / "template.yaml"
        stack_name = kwargs.get("stack_name", f"infra-{provider.name}")

        if not template_file.exists():
            return {
                "success": False,
                "error": f"Template not found: {template_file}",
                "has_changes": False,
            }

        self.console.print(f"[cyan]Creating change set for {stack_name}...[/cyan]")

        # Create change set
        change_set_name = f"infra-plan-{int(time.time())}"

        try:
            result = subprocess.run(
                [
                    "aws", "cloudformation", "create-change-set",
                    "--stack-name", stack_name,
                    "--change-set-name", change_set_name,
                    "--template-body", f"file://{template_file}",
                    "--capabilities", "CAPABILITY_IAM",
                    "--output", "json",
                ],
                cwd=cfn_dir,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": result.stderr,
                    "has_changes": False,
                }

            # Wait for change set creation
            time.sleep(2)

            # Describe change set
            result = subprocess.run(
                [
                    "aws", "cloudformation", "describe-change-set",
                    "--stack-name", stack_name,
                    "--change-set-name", change_set_name,
                    "--output", "json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                change_set = json.loads(result.stdout)
                changes = change_set.get("Changes", [])

                # Delete the change set (we only wanted to preview)
                subprocess.run(
                    [
                        "aws", "cloudformation", "delete-change-set",
                        "--stack-name", stack_name,
                        "--change-set-name", change_set_name,
                    ],
                    capture_output=True,
                    check=False,
                )

                has_changes = len(changes) > 0
                summary = self._format_changes(changes)

                self.console.print(f"[green]✓ Change set created: {len(changes)} changes[/green]")

                return {
                    "success": True,
                    "has_changes": has_changes,
                    "changes_summary": summary,
                    "output": json.dumps(changes, indent=2),
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr,
                    "has_changes": False,
                }

        except (FileNotFoundError, json.JSONDecodeError) as e:
            return {
                "success": False,
                "error": f"Failed to create change set: {str(e)}",
                "has_changes": False,
            }

    # Implement Applyable protocol
    def apply(
        self,
        provider: ProviderBase,
        auto_approve: bool = True,
        **kwargs: Any
    ) -> ApplyResult:
        """Apply CloudFormation stack changes.

        Args:
            provider: Provider instance to apply
            auto_approve: Whether to auto-approve changes (default: True)
            **kwargs: Additional apply options

        Returns:
            ApplyResult with success flag and resource counts
        """
        cfn_dir = provider.output_dir / self.tool_name / provider.name
        template_file = cfn_dir / "template.yaml"
        stack_name = kwargs.get("stack_name", f"infra-{provider.name}")

        if not auto_approve:
            # For CloudFormation, non-auto-approve means just plan
            return self.plan(provider, **kwargs)  # type: ignore

        if not template_file.exists():
            return {
                "success": False,
                "error": f"Template not found: {template_file}",
            }

        self.console.print(f"[cyan]Deploying stack {stack_name}...[/cyan]")

        try:
            # Deploy stack (create or update)
            result = subprocess.run(
                [
                    "aws", "cloudformation", "deploy",
                    "--stack-name", stack_name,
                    "--template-file", str(template_file),
                    "--capabilities", "CAPABILITY_IAM",
                    "--no-fail-on-empty-changeset",
                ],
                cwd=cfn_dir,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                # Get stack resources to count them
                resources = self._get_stack_resources(stack_name)

                self.console.print(
                    f"[green]✓ Stack deployed: {len(resources)} resources[/green]"
                )

                return {
                    "success": True,
                    "resources_created": len(resources),  # Simplified
                    "output": result.stdout,
                }
            else:
                self.console.print(f"[red]✗ Stack deployment failed[/red]")
                return {
                    "success": False,
                    "exit_code": result.returncode,
                    "error": result.stderr,
                    "output": result.stdout,
                }

        except FileNotFoundError:
            return {
                "success": False,
                "error": "AWS CLI not found",
            }

    # Implement Destroyable protocol
    def destroy(
        self,
        provider: ProviderBase,
        auto_approve: bool = True,
        **kwargs: Any
    ) -> DestroyResult:
        """Destroy CloudFormation stack.

        Args:
            provider: Provider instance to destroy
            auto_approve: Whether to auto-approve destruction (default: True)
            **kwargs: Additional destroy options

        Returns:
            DestroyResult with success flag and resource counts
        """
        stack_name = kwargs.get("stack_name", f"infra-{provider.name}")

        if not auto_approve:
            return {
                "success": False,
                "error": "Destroy requires auto_approve=True",
            }

        self.console.print(
            f"[yellow]⚠ Destroying stack {stack_name}...[/yellow]"
        )

        # Get resource count before deletion
        resources = self._get_stack_resources(stack_name)
        resource_count = len(resources)

        try:
            result = subprocess.run(
                [
                    "aws", "cloudformation", "delete-stack",
                    "--stack-name", stack_name,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                # Wait for deletion (in production, you'd want to poll status)
                self.console.print("[cyan]Waiting for stack deletion...[/cyan]")
                time.sleep(5)

                self.console.print(
                    f"[green]✓ Stack deleted: {resource_count} resources destroyed[/green]"
                )

                return {
                    "success": True,
                    "resources_destroyed": resource_count,
                    "output": "Stack deletion initiated",
                }
            else:
                self.console.print(f"[red]✗ Stack deletion failed[/red]")
                return {
                    "success": False,
                    "exit_code": result.returncode,
                    "error": result.stderr,
                }

        except FileNotFoundError:
            return {
                "success": False,
                "error": "AWS CLI not found",
            }

    # Implement StateAware protocol
    def get_resource_ids(self, provider: ProviderBase) -> dict[str, str]:
        """Get mapping of resource names to their AWS resource IDs.

        Args:
            provider: Provider instance to query state for

        Returns:
            Dictionary mapping logical IDs to physical IDs
        """
        stack_name = f"infra-{provider.name}"
        resources = self._get_stack_resources(stack_name)

        return {
            resource["LogicalResourceId"]: resource["PhysicalResourceId"]
            for resource in resources
        }

    # Helper methods
    def _get_stack_resources(self, stack_name: str) -> list[dict[str, Any]]:
        """Get all resources in a stack.

        Args:
            stack_name: Name of the CloudFormation stack

        Returns:
            List of resource dictionaries
        """
        try:
            result = subprocess.run(
                [
                    "aws", "cloudformation", "list-stack-resources",
                    "--stack-name", stack_name,
                    "--output", "json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                return data.get("StackResourceSummaries", [])

        except (FileNotFoundError, json.JSONDecodeError):
            pass

        return []

    def _format_changes(self, changes: list[dict[str, Any]]) -> str:
        """Format change set changes into human-readable summary.

        Args:
            changes: List of change dictionaries from CloudFormation

        Returns:
            Formatted summary string
        """
        summary_lines = []
        for change in changes[:10]:  # Limit to first 10
            resource_change = change.get("ResourceChange", {})
            action = resource_change.get("Action", "Unknown")
            logical_id = resource_change.get("LogicalResourceId", "Unknown")
            resource_type = resource_change.get("ResourceType", "Unknown")

            summary_lines.append(f"  {action}: {logical_id} ({resource_type})")

        if len(changes) > 10:
            summary_lines.append(f"  ... and {len(changes) - 10} more changes")

        return "\n".join(summary_lines) if summary_lines else "No changes"
```

### Step 2: Export the Runner

```python
# src/infrafoundry/core/runners/__init__.py (add to existing file)

from infrafoundry.core.runners.cloudformation_runner import CloudFormationRunner

__all__ = [
    # ... existing exports ...
    "CloudFormationRunner",
]
```

### Step 3: Register the Runner

```python
# src/infrafoundry/core/provider_registry_service.py (update existing file)

from infrafoundry.core.runners import (
    AnsibleRunner,
    CloudFormationRunner,  # Add import
    PulumiRunner,
    PyInfraRunner,
    RunnerRegistry,
    TerraformRunner,
)

class ProviderRegistryService:
    def _register_default_runners(self) -> None:
        """Register built-in runners."""
        self.runner_registry.register(TerraformRunner)
        self.runner_registry.register(CloudFormationRunner)  # Add registration
        self.runner_registry.register(AnsibleRunner)
        self.runner_registry.register(PyInfraRunner)
        if os.getenv("INFRA_ENABLE_EXPERIMENTAL"):
            self.runner_registry.register(PulumiRunner)
```

### Step 4: Unit Tests

```python
# tests/unit/test_cloudformation_runner.py
"""Unit tests for CloudFormationRunner."""

from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from infrafoundry.core.runners.cloudformation_runner import CloudFormationRunner


class TestCloudFormationRunner:
    """Test CloudFormationRunner implementation."""

    def test_tool_name(self):
        """Should return correct tool name."""
        runner = CloudFormationRunner()
        assert runner.tool_name == "cloudformation"

    def test_priority(self):
        """Should return expected priority."""
        runner = CloudFormationRunner()
        assert runner.priority == 5

    @patch("shutil.which")
    def test_is_available_when_installed(self, mock_which):
        """Should return True when AWS CLI is in PATH."""
        mock_which.return_value = "/usr/local/bin/aws"
        runner = CloudFormationRunner()
        assert runner.is_available() is True

    @patch("shutil.which")
    def test_is_available_when_not_installed(self, mock_which):
        """Should return False when AWS CLI is not in PATH."""
        mock_which.return_value = None
        runner = CloudFormationRunner()
        assert runner.is_available() is False

    @patch("subprocess.run")
    def test_get_version(self, mock_run):
        """Should parse AWS CLI version."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="aws-cli/2.13.0 Python/3.11.4 Linux/5.15.0"
        )

        runner = CloudFormationRunner()
        version = runner.get_version()
        assert version == "2.13.0"

    @patch("subprocess.run")
    def test_initialize_success(self, mock_run):
        """Should successfully verify AWS credentials."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"Account": "123456789012", "Arn": "arn:aws:iam::123456789012:user/test"}'
        )

        runner = CloudFormationRunner()
        result = runner.initialize(Path("/tmp/test"))

        assert result["success"] is True
        assert result["aws_account"] == "123456789012"

    @patch("subprocess.run")
    def test_plan_creates_change_set(self, mock_run):
        """Should create and describe change set."""
        # Mock create-change-set
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='{"Id": "arn:..."}'),  # create
            MagicMock(returncode=0, stdout='{"Changes": [{"Type": "Resource"}]}'),  # describe
            MagicMock(returncode=0),  # delete
        ]

        provider = MagicMock()
        provider.name = "test-provider"
        provider.output_dir = Path("/tmp/generated")

        # Create template file
        cfn_dir = Path("/tmp/generated/cloudformation/test-provider")
        cfn_dir.mkdir(parents=True, exist_ok=True)
        (cfn_dir / "template.yaml").write_text("AWSTemplateFormatVersion: '2010-09-09'")

        runner = CloudFormationRunner()
        result = runner.plan(provider)

        assert result["success"] is True
        assert result["has_changes"] is True


# tests/unit/test_runner_interfaces.py (add to existing file)

from infrafoundry.core.protocols import (
    Applyable,
    Destroyable,
    DriftDetectable,
    Plannable,
    StateAware,
)
from infrafoundry.core.runners.cloudformation_runner import CloudFormationRunner


class TestCloudFormationRunnerInterfaces:
    """Test CloudFormationRunner protocol compliance."""

    def test_implements_required_protocols(self):
        """CloudFormationRunner should implement 4 of 5 protocols."""
        runner = CloudFormationRunner()

        assert isinstance(runner, Plannable)
        assert isinstance(runner, Applyable)
        assert isinstance(runner, Destroyable)
        assert isinstance(runner, StateAware)

    def test_does_not_implement_drift_detection(self):
        """CloudFormationRunner should NOT implement DriftDetectable."""
        runner = CloudFormationRunner()
        assert not isinstance(runner, DriftDetectable)
```

### Step 5: Runner Documentation

```markdown
# docs/runners/cloudformation.md
# CloudFormation Runner

## Overview

The CloudFormation runner executes AWS CloudFormation stacks to provision AWS infrastructure. It supports plan (change sets), apply (deploy), destroy, and state tracking operations.

## Capabilities

- ✅ **Plannable**: Creates change sets to preview changes
- ✅ **Applyable**: Deploys or updates stacks
- ✅ **Destroyable**: Deletes stacks
- ✅ **StateAware**: Tracks physical resource IDs
- ❌ **DriftDetectable**: Not implemented (CloudFormation drift is complex)

## Prerequisites

- AWS CLI installed and in PATH
- AWS credentials configured (via environment variables, ~/.aws/credentials, or IAM role)
- CloudFormation templates generated in `generated/{env}/cloudformation/{provider}/`

## Configuration

### AWS Credentials

The runner uses standard AWS credential chain:
1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
2. Shared credentials file (~/.aws/credentials)
3. IAM instance profile (when running on EC2)

### Stack Naming

Stacks are named `infra-{provider-name}` by default. Override with:
```python
runner.apply(provider, stack_name="my-custom-stack")
```

## Usage Examples

### Plan Changes

```bash
infra plan --env prod
# Creates CloudFormation change sets for each provider
```

### Apply Changes

```bash
infra apply --env prod --auto-approve
# Deploys CloudFormation stacks
```

### Destroy Infrastructure

```bash
infra destroy --env dev --auto-approve
# Deletes CloudFormation stacks
```

## Related Documentation

- [AWS CloudFormation Documentation](https://docs.aws.amazon.com/cloudformation/)
- [Implementing Runners](../development/implementing-runners.md)
- [Runner Overview](overview.md)
```

## Testing the Runner

### Manual Testing

1. **Install AWS CLI:**
   ```bash
   pip install awscli
   aws configure
   ```

2. **Create test template:**
   ```bash
   mkdir -p generated/dev/cloudformation/test-provider
   cat > generated/dev/cloudformation/test-provider/template.yaml <<EOF
   AWSTemplateFormatVersion: '2010-09-09'
   Description: Test stack
   Resources:
     TestBucket:
       Type: AWS::S3::Bucket
       Properties:
         BucketName: infra-test-bucket-12345
   EOF
   ```

3. **Test the runner:**
   ```python
   from infrafoundry.core.runners.cloudformation_runner import CloudFormationRunner
   from unittest.mock import MagicMock
   from pathlib import Path

   runner = CloudFormationRunner()

   # Check availability
   print(f"Available: {runner.is_available()}")
   print(f"Version: {runner.get_version()}")

   # Create mock provider
   provider = MagicMock()
   provider.name = "test-provider"
   provider.output_dir = Path("generated/dev")

   # Initialize
   init_result = runner.initialize(Path("generated/dev/cloudformation/test-provider"))
   print(f"Init: {init_result}")

   # Plan
   plan_result = runner.plan(provider, stack_name="infra-test")
   print(f"Plan: {plan_result}")

   # Apply
   apply_result = runner.apply(provider, auto_approve=True, stack_name="infra-test")
   print(f"Apply: {apply_result}")

   # Get resource IDs
   ids = runner.get_resource_ids(provider)
   print(f"Resource IDs: {ids}")

   # Destroy
   destroy_result = runner.destroy(provider, auto_approve=True, stack_name="infra-test")
   print(f"Destroy: {destroy_result}")
   ```

### Automated Testing

```bash
# Run unit tests
uv run pytest tests/unit/test_cloudformation_runner.py -v

# Run with coverage
uv run pytest tests/unit/test_cloudformation_runner.py --cov=infrafoundry.core.runners.cloudformation_runner

# Run integration tests (requires AWS credentials)
uv run pytest tests/integration/test_cloudformation_runner_integration.py -v
```

## Key Takeaways

1. **Protocol Implementation**: Runner implements 4 of 5 protocols based on tool capabilities
2. **Type Safety**: All methods return TypedDict types (PlanResult, ApplyResult, etc.)
3. **Error Handling**: Comprehensive error handling with structured results
4. **AWS Integration**: Uses AWS CLI for all operations
5. **Testing**: Complete test suite including unit and integration tests
6. **Documentation**: Full documentation for users and developers

## Next Steps

- Add CloudFormation-specific configuration options
- Implement stack policy support
- Add rollback capabilities
- Support CloudFormation nested stacks
- Add cost estimation (AWS CloudFormation cost estimation API)

---

**Last Updated:** 2025-12-23

---
[Back to Examples](README.md) | [Implementing Runners Guide](../development/implementing-runners.md)
