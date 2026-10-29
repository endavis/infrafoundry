"""Delete one environment's rows from the state database in a single transaction."""

from __future__ import annotations

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from infrafoundry.core.exceptions import StateError
from infrafoundry.core.state.models import (
    Deployment,
    DeploymentEvent,
    DeploymentLock,
    Resource,
    ResourceDependency,
)

# Tables touched by a prune, in the foreign-key-safe order they are deleted.
PRUNE_TABLES: tuple[str, ...] = (
    "resource_dependencies",
    "deployment_events",
    "resources",
    "deployment_locks",
    "deployments",
)


def _env_resource_ids(environment: str) -> object:
    return select(Resource.id).where(Resource.environment == environment)


def _env_deployment_ids(environment: str) -> object:
    return select(Deployment.id).where(Deployment.environment == environment)


def _count(session: Session, stmt: object) -> int:
    return int(session.execute(stmt).scalar_one())  # type: ignore[call-overload]


def _count_rows(session: Session, environment: str) -> dict[str, int]:
    res_ids = _env_resource_ids(environment)
    dep_ids = _env_deployment_ids(environment)
    return {
        "resource_dependencies": _count(
            session,
            select(func.count())
            .select_from(ResourceDependency)
            .where(
                or_(
                    ResourceDependency.resource_id.in_(res_ids),  # type: ignore[arg-type]
                    ResourceDependency.depends_on_id.in_(res_ids),  # type: ignore[arg-type]
                )
            ),
        ),
        "deployment_events": _count(
            session,
            select(func.count())
            .select_from(DeploymentEvent)
            .where(DeploymentEvent.deployment_id.in_(dep_ids)),  # type: ignore[arg-type]
        ),
        "resources": _count(
            session,
            select(func.count()).select_from(Resource).where(Resource.environment == environment),
        ),
        "deployment_locks": _count(
            session,
            select(func.count())
            .select_from(DeploymentLock)
            .where(
                or_(
                    DeploymentLock.environment == environment,
                    DeploymentLock.deployment_id.in_(dep_ids),  # type: ignore[arg-type]
                )
            ),
        ),
        "deployments": _count(
            session,
            select(func.count())
            .select_from(Deployment)
            .where(Deployment.environment == environment),
        ),
    }


def _check_cross_references(session: Session, environment: str) -> None:
    """Raise if another environment's resources point at this environment's deployments."""
    rows = session.execute(
        select(Resource.environment, func.count())
        .where(
            Resource.deployment_id.in_(_env_deployment_ids(environment)),  # type: ignore[arg-type]
            Resource.environment != environment,
        )
        .group_by(Resource.environment)
        .order_by(Resource.environment)
    ).all()
    if rows:
        foreign = sum(count for _, count in rows)
        owners = ", ".join(f"{env} ({count})" for env, count in rows)
        raise StateError(
            f"Cannot prune '{environment}': {foreign} resource(s) in other environments "
            f"reference its deployments: {owners}. Prune those environments first. "
            "Nothing was deleted."
        )


def prune_environment(
    session_factory: sessionmaker[Session], environment: str, dry_run: bool = False
) -> dict[str, int]:
    """Delete (or count, when ``dry_run``) every state row of ``environment``.

    Deletes in foreign-key-safe order inside one transaction, committing once and
    rolling back on any error. ``audit_entries`` is never touched.

    Args:
        session_factory: Session factory bound to the state database.
        environment: Environment whose rows are removed.
        dry_run: Count the rows without deleting.

    Returns:
        Row count per table, keyed by table name.

    Raises:
        StateError: If another environment's resources reference this one's deployments.
    """
    with session_factory() as session:
        counts = _count_rows(session, environment)
        _check_cross_references(session, environment)
        if dry_run or not any(counts.values()):
            return counts

        res_ids = _env_resource_ids(environment)
        dep_ids = _env_deployment_ids(environment)
        try:
            session.execute(
                delete(ResourceDependency).where(
                    or_(
                        ResourceDependency.resource_id.in_(res_ids),  # type: ignore[arg-type]
                        ResourceDependency.depends_on_id.in_(res_ids),  # type: ignore[arg-type]
                    )
                )
            )
            session.execute(
                delete(DeploymentEvent).where(DeploymentEvent.deployment_id.in_(dep_ids))  # type: ignore[arg-type]
            )
            session.execute(delete(Resource).where(Resource.environment == environment))
            session.execute(
                delete(DeploymentLock).where(
                    or_(
                        DeploymentLock.environment == environment,
                        DeploymentLock.deployment_id.in_(dep_ids),  # type: ignore[arg-type]
                    )
                )
            )
            session.execute(delete(Deployment).where(Deployment.environment == environment))
            session.commit()
        except Exception:
            session.rollback()
            raise
        return counts
