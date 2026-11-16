"""Shared marking of resources as failed after a failed apply or destroy."""

import logging

from infrafoundry.core.events import EventManager, EventType
from infrafoundry.core.state import ResourceState, StateManager
from infrafoundry.core.types import ResourceEventData

logger = logging.getLogger(__name__)


def mark_resources_failed(
    state_manager: StateManager,
    event_manager: EventManager,
    env_name: str,
    provider_name: str,
    resource_ids: dict[str, int],
    *,
    phase: str,
    package_filter: str | None = None,
) -> None:
    """Mark this run's in-flight rows ``ERROR`` after a failed apply or destroy.

    Rows from earlier runs are untouched. Failures here are logged and
    swallowed so the runner's original exception is the one that propagates.

    Args:
        state_manager: State manager used to update the resource rows.
        event_manager: Event manager used to emit ``RESOURCE_FAILED``.
        env_name: Environment name.
        provider_name: Provider name.
        resource_ids: Resource name to state-row id for this run.
        phase: Phase that failed (``"apply"`` or ``"destroy"``), used in the log.
        package_filter: Package filter forwarded to the emitted events.
    """
    try:
        for name, db_id in resource_ids.items():
            state_manager.update_resource_state(
                resource_id=db_id,
                state=ResourceState.ERROR,
            )
            failed_resource_event: ResourceEventData = {
                "resource_id": db_id,
                "provider": provider_name,
                "name": name,
                "terraform_id": None,
            }
            event_manager.emit_event(
                EventType.RESOURCE_FAILED,
                env_name,
                failed_resource_event,
                target_resources=[name],
                package_filter=package_filter,
                resource_scoped=True,
            )
    except Exception:
        logger.warning(
            "Could not mark resources ERROR after failed %s for provider %s",
            phase,
            provider_name,
            exc_info=True,
        )
