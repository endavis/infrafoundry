"""Clear stale ``PLANNED`` rows that shadow deployed resources.

Before #1417, ``infra plan`` appended a ``PLANNED`` row for every resource, so a
deployed resource's newest row became ``PLANNED`` and ``infra deployed`` stopped
showing it as ``active``. The ``resources`` table is append-only (ADR-0018), so
the fix appends a fresh ``ACTIVE`` row instead of deleting the ``PLANNED`` rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from infrafoundry.core.state.models import (
    Deployment,
    DeploymentStatus,
    Resource,
    ResourceState,
)

RECONCILE_COMMAND = "reconcile"


@dataclass(frozen=True)
class ReconcileCandidate:
    """A deployed resource whose newest row is a stale ``PLANNED`` row."""

    provider: str
    resource_type: str
    name: str
    active_id: int
    stale_planned: int


def find_stale_planned(session: Session, environment: str) -> list[ReconcileCandidate]:
    """Find resources whose newest non-``PLANNED`` row is ``ACTIVE`` with newer ``PLANNED`` rows.

    Groups are keyed like ``ResourceRepository.get_managed``:
    ``(provider, resource_type, name)`` ordered by ``id``.

    Args:
        session: Open session on the state database.
        environment: Environment to inspect.

    Returns:
        Candidates sorted by provider, resource type and name.
    """
    rows = session.scalars(
        select(Resource).where(Resource.environment == environment).order_by(Resource.id.asc())
    ).all()
    groups: dict[tuple[str, str, str], list[Resource]] = {}
    for row in rows:
        groups.setdefault((row.provider, row.resource_type, row.name), []).append(row)

    candidates: list[ReconcileCandidate] = []
    for (provider, resource_type, name), group in groups.items():
        non_planned = [r for r in group if r.state != ResourceState.PLANNED]
        if not non_planned or non_planned[-1].state != ResourceState.ACTIVE:
            continue
        newest = non_planned[-1]
        stale = sum(1 for r in group if r.state == ResourceState.PLANNED and r.id > newest.id)
        if stale:
            candidates.append(ReconcileCandidate(provider, resource_type, name, newest.id, stale))
    return sorted(candidates, key=lambda c: (c.provider, c.resource_type, c.name))


def reconcile_planned(
    session_factory: sessionmaker[Session],
    environment: str,
    *,
    user: str | None = None,
    dry_run: bool = False,
) -> tuple[list[ReconcileCandidate], int | None]:
    """Append a fresh ``ACTIVE`` row for each candidate in one transaction.

    The copy keeps ``config``, ``terraform_id`` and ``extra_data`` of the last
    ``ACTIVE`` row. ``PLANNED`` rows are left in place. All new rows point at one
    ``reconcile`` deployment, created only when there is something to append.

    Args:
        session_factory: Session factory bound to the state database.
        environment: Environment to reconcile.
        user: User recorded on the ``reconcile`` deployment.
        dry_run: Only report the candidates.

    Returns:
        The candidates and the ``reconcile`` deployment id (``None`` when nothing
        was written).
    """
    with session_factory() as session:
        candidates = find_stale_planned(session, environment)
        if dry_run or not candidates:
            return candidates, None

        try:
            now = datetime.now(UTC)
            deployment = Deployment(
                environment=environment,
                command=RECONCILE_COMMAND,
                status=DeploymentStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                user=user,
            )
            session.add(deployment)
            session.flush()
            for cand in candidates:
                source = session.get(Resource, cand.active_id)
                if source is None:  # pragma: no cover - selected in the same transaction
                    continue
                session.add(
                    Resource(
                        deployment_id=deployment.id,
                        environment=environment,
                        provider=cand.provider,
                        resource_type=cand.resource_type,
                        name=cand.name,
                        state=ResourceState.ACTIVE,
                        config=source.config,
                        terraform_id=source.terraform_id,
                        extra_data=source.extra_data,
                    )
                )
            session.commit()
            return candidates, deployment.id
        except Exception:
            session.rollback()
            raise
