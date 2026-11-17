"""Unit tests for ``infrafoundry.core.runner_results``."""

from __future__ import annotations

import pytest

from infrafoundry.core.exceptions import DeploymentError, TerraformError
from infrafoundry.core.runner_results import raise_on_runner_failure


def test_raise_on_runner_failure_no_op_on_success() -> None:
    """A successful run_result returns None and raises nothing."""
    result = {"success": True, "output": "ok"}
    assert raise_on_runner_failure(result, provider_name="proxmox", phase="apply") is None  # type: ignore[func-returns-value]


def test_raise_on_runner_failure_raises_with_error_field() -> None:
    """A failed run_result with ``error`` raises TerraformError with context."""
    result = {
        "success": False,
        "error": "Instance cannot be destroyed",
        "exit_code": 1,
        "stderr": "detailed stderr",
        "output": "stdout body",
    }

    with pytest.raises(TerraformError) as exc_info:
        raise_on_runner_failure(result, provider_name="proxmox", phase="destroy")

    err = exc_info.value
    assert "destroy" in str(err)
    assert "proxmox" in str(err)
    assert "Instance cannot be destroyed" in str(err)
    assert err.exit_code == 1
    assert err.stderr == "detailed stderr"
    assert err.stdout == "stdout body"


def test_raise_on_runner_failure_falls_back_to_stderr_when_no_error() -> None:
    """When ``error`` is absent, the message falls back to ``stderr``."""
    result = {"success": False, "stderr": "boom"}

    with pytest.raises(TerraformError) as exc_info:
        raise_on_runner_failure(result, provider_name="opnsense", phase="apply")

    assert "boom" in str(exc_info.value)
    assert "opnsense" in str(exc_info.value)
    assert "apply" in str(exc_info.value)


def test_raise_on_runner_failure_handles_missing_keys() -> None:
    """A bare ``success: False`` still raises cleanly with 'Unknown error'."""
    result = {"success": False}

    with pytest.raises(TerraformError) as exc_info:
        raise_on_runner_failure(result, provider_name="esxi", phase="destroy")

    err = exc_info.value
    assert "Unknown error" in str(err)
    assert err.exit_code is None
    assert err.stderr is None
    assert err.stdout is None


def test_raise_on_runner_failure_non_terraform_runner_raises_deployment_error() -> None:
    """A non-Terraform runner raises a plain DeploymentError naming the runner."""
    result = {
        "success": False,
        "error": "component failed",
        "exit_code": 2,
        "stderr": "detail",
    }

    with pytest.raises(DeploymentError) as exc_info:
        raise_on_runner_failure(
            result, provider_name="opnsense", phase="apply", runner_name="opnsense_direct"
        )

    err = exc_info.value
    assert not isinstance(err, TerraformError)
    assert "opnsense_direct apply failed for provider 'opnsense': component failed" in str(err)
    assert "Terraform" not in str(err)
    assert err.context["exit_code"] == 2
    assert err.context["stderr"] == "detail"
    assert "stdout" not in err.context


@pytest.mark.parametrize("runner_name", ["terraform", "opentofu", None])
def test_raise_on_runner_failure_terraform_runners_raise_terraform_error(
    runner_name: str | None,
) -> None:
    """Terraform, OpenTofu and the default keep raising TerraformError."""
    result = {"success": False, "error": "boom", "exit_code": 1}

    with pytest.raises(TerraformError) as exc_info:
        raise_on_runner_failure(
            result, provider_name="proxmox", phase="plan", runner_name=runner_name
        )

    assert "Terraform plan failed for provider 'proxmox': boom" in str(exc_info.value)
