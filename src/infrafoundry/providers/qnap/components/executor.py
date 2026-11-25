"""Runs an ordered list of QNAP writes and stops at the first error (ADR-0039).

A step the switch rejects ends the run: later steps assume the earlier ones took effect.
The result records which steps completed, so the caller can tell the operator where the run
stopped. Logs name the step's type and resource name, never its body.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..client import QnapError, QnapUnreachableError, QnapWriter
from .ordering import Step

logger = logging.getLogger(__name__)


def _object(step: Step) -> dict[str, Any]:
    """Return the step's body as an object; only ``PUT portlist`` takes an array."""
    if not isinstance(step.body, dict):
        raise ValueError(f"a {step.method} step needs an object body")
    return step.body


@dataclass
class ExecutionResult:
    """What happened when a step list ran."""

    completed: list[Step] = field(default_factory=list)
    failed: Step | None = None
    error: str | None = None
    connection_lost: bool = False

    @property
    def success(self) -> bool:
        """True when every step ran."""
        return self.failed is None


def execute_steps(client: QnapWriter, steps: list[Step]) -> ExecutionResult:
    """Run the steps in order and stop at the first error.

    Args:
        client: A QNAP client with write verbs, inside a session.
        steps: Ordered steps from the planner.

    Returns:
        The completed steps, the failed step and its error, if any.
    """
    result = ExecutionResult()
    for step in steps:
        logger.info(
            "qnap %s %s '%s' (phase %s)", step.kind, step.type_name, step.resource_name, step.phase
        )
        try:
            if step.method == "POST":
                client.post(step.path, _object(step))
            elif step.method == "PUT":
                client.put(step.path, step.body, timeout=step.timeout)
            elif step.method == "DELETE":
                client.delete(step.path, _object(step))
            else:
                raise ValueError(f"unknown method '{step.method}'")
        except QnapUnreachableError as exc:
            result.failed, result.error, result.connection_lost = step, str(exc), True
            return result
        except QnapError as exc:
            result.failed, result.error = step, str(exc)
            return result
        result.completed.append(step)
    return result
