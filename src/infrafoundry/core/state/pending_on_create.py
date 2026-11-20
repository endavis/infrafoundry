"""Ledger of ``on_create`` handler obligations that have not run yet.

An apply that fails after terraform created a resource never fires that
resource's ``on_create`` handlers, and the next apply sees no ``create``
outcome, so they would be lost (#1524). The ledger records the obligation as
append-only ``DeploymentEvent`` rows, with no schema change: ``on_create_pending``
when the create outcome is seen and ``on_create_done`` once the handlers ran
without aborting. A ``(provider, name, kind)`` is pending when its newest row in
the environment is ``on_create_pending``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from infrafoundry.core.state.models import Deployment, DeploymentEvent

EVENT_PENDING = "on_create_pending"
EVENT_DONE = "on_create_done"

PendingKind = Literal["resource", "package"]


@dataclass(frozen=True)
class PendingOnCreate:
    """An ``on_create`` obligation whose handlers have not completed."""

    provider: str
    name: str
    kind: str
    address: str


def _record(
    session_factory: sessionmaker[Session],
    event_type: str,
    deployment_id: int,
    provider: str,
    name: str,
    kind: PendingKind,
    address: str,
) -> None:
    with session_factory() as session:
        session.add(
            DeploymentEvent(
                deployment_id=deployment_id,
                event_type=event_type,
                resource_name=name,
                message=f"{event_type} for {provider}:{name} ({kind})",
                extra_data={"provider": provider, "kind": kind, "address": address},
            )
        )
        session.commit()


def record_pending(
    session_factory: sessionmaker[Session],
    deployment_id: int,
    provider: str,
    name: str,
    kind: PendingKind,
    address: str = "",
) -> None:
    """Append an ``on_create_pending`` row.

    Args:
        session_factory: Session factory bound to the state database.
        deployment_id: Deployment the row belongs to.
        provider: Provider name.
        name: Resource name.
        kind: ``resource`` for the resource's own handlers, ``package`` for the
            aggregate package-level ``RESOURCE_CREATED`` handlers.
        address: Terraform address of the primary create outcome.
    """
    _record(session_factory, EVENT_PENDING, deployment_id, provider, name, kind, address)


def record_done(
    session_factory: sessionmaker[Session],
    deployment_id: int,
    provider: str,
    name: str,
    kind: PendingKind,
    address: str = "",
) -> None:
    """Append an ``on_create_done`` row, clearing the pending obligation.

    Args:
        session_factory: Session factory bound to the state database.
        deployment_id: Deployment the row belongs to.
        provider: Provider name.
        name: Resource name.
        kind: ``resource`` or ``package``.
        address: Terraform address of the create outcome.
    """
    _record(session_factory, EVENT_DONE, deployment_id, provider, name, kind, address)


def get_pending(
    session_factory: sessionmaker[Session],
    environment: str,
    *,
    kind: PendingKind | None = None,
    provider: str | None = None,
) -> list[PendingOnCreate]:
    """List obligations whose newest ledger row is ``on_create_pending``.

    Args:
        session_factory: Session factory bound to the state database.
        environment: Environment to inspect.
        kind: Restrict to one kind.
        provider: Restrict to one provider.

    Returns:
        Pending obligations, oldest first.
    """
    with session_factory() as session:
        rows = session.scalars(
            select(DeploymentEvent)
            .join(Deployment, Deployment.id == DeploymentEvent.deployment_id)
            .where(
                Deployment.environment == environment,
                DeploymentEvent.event_type.in_([EVENT_PENDING, EVENT_DONE]),
            )
            .order_by(DeploymentEvent.id.asc())
        ).all()
        newest: dict[tuple[str, str, str], DeploymentEvent] = {}
        for row in rows:
            data = row.extra_data or {}
            key = (
                str(data.get("provider", "")),
                row.resource_name or "",
                str(data.get("kind", "")),
            )
            newest.pop(key, None)
            newest[key] = row
    pending: list[PendingOnCreate] = []
    for (row_provider, name, row_kind), row in newest.items():
        if row.event_type != EVENT_PENDING:
            continue
        if kind is not None and row_kind != kind:
            continue
        if provider is not None and row_provider != provider:
            continue
        address = str((row.extra_data or {}).get("address", ""))
        pending.append(PendingOnCreate(row_provider, name, row_kind, address))
    return pending
