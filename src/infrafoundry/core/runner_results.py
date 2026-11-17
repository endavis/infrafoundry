"""Helpers for interpreting runner result dictionaries.

This module centralizes the logic that converts a runner's result dict
(as returned by ``BaseRunner.plan`` / ``BaseRunner.apply`` /
``BaseRunner.destroy``) into a Python exception when the runner reports
failure. Keeping this in one place ensures that the plan, apply, and
destroy code paths honor the ``success`` flag identically and produce
consistent error messages.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from infrafoundry.core.exceptions import DeploymentError, TerraformError

_TERRAFORM_RUNNERS = frozenset({"terraform", "opentofu"})


def raise_on_runner_failure(
    run_result: Mapping[str, Any],
    *,
    provider_name: str,
    phase: str,
    runner_name: str | None = None,
) -> None:
    """Raise an error when ``run_result['success']`` is False.

    No-op on success. The caller is responsible for emitting
    ``RUNNER_FAILED`` via its existing try/except handler -- this helper
    only converts a result dict into an exception, never emits events.

    Args:
        run_result: The dict returned by a runner's ``plan``, ``apply``,
            or ``destroy`` method. Expected keys include ``success``,
            ``error``, ``stderr``, ``exit_code``, and ``output``.
        provider_name: Name of the provider whose runner produced the
            result. Used in the error message.
        phase: The runner phase that produced the result, e.g.
            ``"plan"``, ``"apply"``, or ``"destroy"``. Used in the error
            message.
        runner_name: Tool name of the runner (e.g. ``"opnsense_direct"``).
            ``None``, ``"terraform"`` and ``"opentofu"`` raise
            ``TerraformError``; any other name raises ``DeploymentError``.

    Raises:
        TerraformError: If ``run_result['success']`` is False and the runner
            is Terraform/OpenTofu (or ``runner_name`` is None). The
            exception carries the runner's ``exit_code``, ``stdout``
            (from ``output``), and ``stderr`` when available.
        DeploymentError: If ``run_result['success']`` is False for any other
            runner. The context carries the same keys when available.
    """
    if run_result.get("success", False):
        return

    error_msg = run_result.get("error") or run_result.get("stderr") or "Unknown error"
    if runner_name is not None and runner_name not in _TERRAFORM_RUNNERS:
        context: dict[str, Any] = {}
        for key, value in (
            ("exit_code", run_result.get("exit_code")),
            ("stdout", run_result.get("output")),
            ("stderr", run_result.get("stderr")),
        ):
            if value is not None:
                context[key] = value
        raise DeploymentError(
            f"{runner_name} {phase} failed for provider '{provider_name}': {error_msg}",
            context,
        )
    raise TerraformError(
        f"Terraform {phase} failed for provider '{provider_name}': {error_msg}",
        exit_code=run_result.get("exit_code"),
        stdout=run_result.get("output"),
        stderr=run_result.get("stderr"),
    )
