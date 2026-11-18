"""Runs an ordered list of RouterOS writes and stops at the first error.

The steps come from :func:`ordering.order_changes`. A step the device rejects ends the
run: later steps assume the earlier ones took effect (a bridge must exist before its
ports do), so carrying on would build on a partial state. The result records which steps
completed, so the caller can tell the operator where the run stopped.

Logs name the step's type and resource name, never its body.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..client import RouterOSAPIError, RouterOSConnectionError, RouterOSWriter
from ..schema import SPECS, key_of
from .diff import CREATE, DELETE, UPDATE
from .ordering import Step

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """What happened when a step list ran."""

    completed: list[Step] = field(default_factory=list)
    failed: Step | None = None
    error: str | None = None
    connection_lost: bool = False
    created_ids: dict[tuple[str, tuple[Any, ...]], str] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """True when every step ran."""
        return self.failed is None


def _resolve_id(
    client: RouterOSWriter,
    step: Step,
    created_ids: dict[tuple[str, tuple[Any, ...]], str],
) -> str | None:
    """Return the ``.id`` a step acts on: the planned one, a created one, else a re-read."""
    if step.live_id:
        return step.live_id
    known = created_ids.get((step.type_name, step.key))
    if known:
        return known
    spec = SPECS[step.type_name]
    for row in client.get(spec.path):
        if key_of(spec, row) == step.key and row.get(".id"):
            return row[".id"]
    return None


def execute_steps(client: RouterOSWriter, steps: list[Step]) -> ExecutionResult:
    """Run the steps in order and stop at the first error.

    Args:
        client: A RouterOS client with write verbs.
        steps: Ordered steps from the planner.

    Returns:
        The completed steps, the failed step and its error, if any.
    """
    result = ExecutionResult()
    for step in steps:
        spec = SPECS[step.type_name]
        logger.info(
            "mikrotik %s %s '%s' (phase %s)",
            step.kind,
            step.type_name,
            step.resource_name,
            step.phase,
        )
        try:
            if step.kind == CREATE:
                row = client.put(spec.path, step.body)
                if row.get(".id"):
                    result.created_ids[(step.type_name, step.key)] = row[".id"]
            else:
                row_id = _resolve_id(client, step, result.created_ids)
                if row_id is None:
                    raise RouterOSAPIError(
                        f"cannot find the {step.type_name} row '{step.resource_name}' on the device"
                    )
                if step.kind == UPDATE:
                    client.patch(spec.path, row_id, step.body)
                elif step.kind == DELETE:
                    client.delete(spec.path, row_id)
                else:
                    raise ValueError(f"unknown step kind '{step.kind}'")
        except RouterOSConnectionError as exc:
            result.failed, result.error, result.connection_lost = step, str(exc), True
            return result
        except RouterOSAPIError as exc:
            result.failed, result.error = step, str(exc)
            return result
        result.completed.append(step)
    return result
