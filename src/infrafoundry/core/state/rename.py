"""Rename one environment in the state database in a single transaction."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from infrafoundry.core.exceptions import StateError
from infrafoundry.core.state.models import Deployment, DeploymentLock, Resource

# Tables whose ``environment`` column is rewritten, plus the JSON snapshot in
# ``deployments.rollback_data`` that carries its own ``environment`` key.
RENAME_TABLES: tuple[str, ...] = (
    "resources",
    "deployments",
    "deployment_locks",
    "rollback_data",
)


def _count(session: Session, stmt: object) -> int:
    return int(session.execute(stmt).scalar_one())  # type: ignore[call-overload]


def _rollback_deployments(session: Session, environment: str) -> list[Deployment]:
    """Deployments of ``environment`` whose rollback snapshot names ``environment``."""
    rows = session.execute(
        select(Deployment).where(
            Deployment.environment == environment, Deployment.rollback_data.isnot(None)
        )
    ).scalars()
    return [d for d in rows if (d.rollback_data or {}).get("environment") == environment]


def _count_rows(session: Session, environment: str) -> dict[str, int]:
    return {
        "resources": _count(
            session,
            select(func.count()).select_from(Resource).where(Resource.environment == environment),
        ),
        "deployments": _count(
            session,
            select(func.count())
            .select_from(Deployment)
            .where(Deployment.environment == environment),
        ),
        "deployment_locks": _count(
            session,
            select(func.count())
            .select_from(DeploymentLock)
            .where(DeploymentLock.environment == environment),
        ),
        "rollback_data": len(_rollback_deployments(session, environment)),
    }


def count_environment_rows(
    session_factory: sessionmaker[Session], environment: str
) -> dict[str, int]:
    """Count the rows a rename of ``environment`` would touch.

    Args:
        session_factory: Session factory bound to the state database.
        environment: Environment name.

    Returns:
        Row count per entry of ``RENAME_TABLES``.
    """
    with session_factory() as session:
        return _count_rows(session, environment)


def rename_environment(
    session_factory: sessionmaker[Session], old: str, new: str, dry_run: bool = False
) -> dict[str, int]:
    """Rename (or count, when ``dry_run``) every state row of ``old`` to ``new``.

    Updates the three tables with an ``environment`` column and rewrites the
    ``environment`` key of each ``rollback_data`` snapshot inside one transaction,
    committing once and rolling back on any error. ``audit_entries`` is never touched.

    Args:
        session_factory: Session factory bound to the state database.
        old: Current environment name.
        new: New environment name.
        dry_run: Count the rows without changing them.

    Returns:
        Row count per entry of ``RENAME_TABLES``.

    Raises:
        StateError: If the names are equal, ``old`` has no rows or ``new`` already has rows.
    """
    if old == new:
        raise StateError(f"Cannot rename '{old}' to itself. Nothing was changed.")
    with session_factory() as session:
        counts = _count_rows(session, old)
        if not any(counts.values()):
            raise StateError(f"Environment '{old}' has no state rows. Nothing was changed.")
        if any(_count_rows(session, new).values()):
            raise StateError(f"Environment '{new}' already has state rows. Nothing was changed.")
        if dry_run:
            return counts

        try:
            snapshots = _rollback_deployments(session, old)
            for model in (Resource, Deployment, DeploymentLock):
                session.execute(
                    update(model).where(model.environment == old).values(environment=new)
                )
            for deployment in snapshots:
                # Reassign a new dict so SQLAlchemy sees the JSON column change.
                deployment.rollback_data = {**(deployment.rollback_data or {}), "environment": new}
            session.commit()
        except Exception:
            session.rollback()
            raise
        return counts
