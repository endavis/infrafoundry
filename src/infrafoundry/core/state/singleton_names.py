"""One-time state migration for OPNsense singleton resource names (#1237).

Before #1237 every dict-shaped OPNsense resource was recorded in the
``resources`` table under the name ``settings``. The loader now names each
singleton by its dotted type, so legacy rows are rewritten to match.
"""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from infrafoundry.core.state.models import Resource


def rename_legacy_singleton_rows(session_factory: sessionmaker[Session]) -> int:
    """Rename legacy ``settings`` singleton rows to their dotted resource type.

    Only ``resources`` rows of the OPNsense provider whose name is ``settings``
    and whose type is a dict-shaped (singleton) type are touched. History
    (``deployment_events``, rollback snapshots, audit entries) is left alone.
    The update is idempotent.

    Args:
        session_factory: Session factory bound to the state database.

    Returns:
        Number of rows renamed.
    """
    # Lazy import: ``package_loader`` imports ``infrafoundry.core.state.*``, so a
    # module-level import here would create an import cycle.
    from infrafoundry.core.config.package_loader import (
        LEGACY_SINGLETON_RESOURCE_NAME,
        NESTED_PROVIDER_NAMESPACE,
        SINGLETON_RESOURCE_TYPES,
    )

    with session_factory() as session:
        try:
            result = session.execute(
                update(Resource)
                .where(
                    Resource.provider == NESTED_PROVIDER_NAMESPACE,
                    Resource.name == LEGACY_SINGLETON_RESOURCE_NAME,
                    Resource.resource_type.in_(SINGLETON_RESOURCE_TYPES),
                )
                .values(name=Resource.resource_type)
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return int(getattr(result, "rowcount", 0) or 0)
