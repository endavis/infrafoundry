"""Delete one environment's (or one provider's) rows from the state database."""

from __future__ import annotations

from collections.abc import Sequence

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


# Tables touched by a provider prune, in the foreign-key-safe order they are deleted.
PROVIDER_PRUNE_TABLES: tuple[str, ...] = ("resource_dependencies", "deployment_events", "resources")


def _provider_resource_ids(environment: str, providers: Sequence[str]) -> object:
    return select(Resource.id).where(
        Resource.environment == environment,
        Resource.provider.in_(list(providers)),
    )


def _provider_event_ids(session: Session, environment: str, providers: Sequence[str]) -> list[int]:
    """Ids of the environment's deployment events stamped with one of ``providers``.

    The provider lives in the event's JSON ``extra_data``, so the match is made in
    Python to stay portable across SQLite and PostgreSQL.
    """
    rows = session.execute(
        select(DeploymentEvent.id, DeploymentEvent.extra_data)
        .where(DeploymentEvent.deployment_id.in_(_env_deployment_ids(environment)))  # type: ignore[arg-type]
        .where(DeploymentEvent.extra_data.is_not(None))
    ).all()
    wanted = set(providers)
    return [
        event_id
        for event_id, extra in rows
        if isinstance(extra, dict) and extra.get("provider") in wanted
    ]


def list_provider_resources(
    session_factory: sessionmaker[Session], environment: str, providers: Sequence[str]
) -> list[tuple[str, str, str]]:
    """Return ``(provider, resource_type, name)`` of each resource a provider prune removes.

    Args:
        session_factory: Session factory bound to the state database.
        environment: Environment the rows belong to.
        providers: Provider ids (``opnsense`` or ``opnsense@fw-b``) to match exactly.

    Returns:
        The rows, sorted by provider, type and name.
    """
    with session_factory() as session:
        rows = session.execute(
            select(Resource.provider, Resource.resource_type, Resource.name)
            .where(
                Resource.environment == environment,
                Resource.provider.in_(list(providers)),
            )
            .order_by(Resource.provider, Resource.resource_type, Resource.name)
        ).all()
        return [(str(p), str(t), str(n)) for p, t, n in rows]


def prune_providers(
    session_factory: sessionmaker[Session],
    environment: str,
    providers: Sequence[str],
    dry_run: bool = False,
) -> dict[str, int]:
    """Delete (or count, when ``dry_run``) the rows of ``providers`` in one environment.

    Removes the providers' resources, the dependencies touching them and the
    deployment events stamped with them, in one transaction. Deployments, locks,
    other providers' rows and other environments are never touched, nor is
    ``audit_entries``.

    Args:
        session_factory: Session factory bound to the state database.
        environment: Environment whose rows are removed.
        providers: Provider ids to match exactly; an instance id matches only itself.
        dry_run: Count the rows without deleting.

    Returns:
        Row count per table in :data:`PROVIDER_PRUNE_TABLES`.
    """
    with session_factory() as session:
        res_ids = _provider_resource_ids(environment, providers)
        event_ids = _provider_event_ids(session, environment, providers)
        dep_where = or_(
            ResourceDependency.resource_id.in_(res_ids),  # type: ignore[arg-type]
            ResourceDependency.depends_on_id.in_(res_ids),  # type: ignore[arg-type]
        )
        counts = {
            "resource_dependencies": _count(
                session, select(func.count()).select_from(ResourceDependency).where(dep_where)
            ),
            "deployment_events": len(event_ids),
            "resources": _count(
                session,
                select(func.count())
                .select_from(Resource)
                .where(
                    Resource.environment == environment,
                    Resource.provider.in_(list(providers)),
                ),
            ),
        }
        if dry_run or not any(counts.values()):
            return counts
        try:
            session.execute(delete(ResourceDependency).where(dep_where))
            for start in range(0, len(event_ids), 500):
                session.execute(
                    delete(DeploymentEvent).where(
                        DeploymentEvent.id.in_(event_ids[start : start + 500])
                    )
                )
            session.execute(
                delete(Resource).where(
                    Resource.environment == environment,
                    Resource.provider.in_(list(providers)),
                )
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return counts
