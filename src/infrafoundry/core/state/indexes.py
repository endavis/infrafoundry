"""Create model-declared indexes that an existing state database is missing (#242)."""

from sqlalchemy import Engine, inspect

from infrafoundry.core.state.models import Base


def ensure_indexes(engine: Engine) -> list[str]:
    """Create any named model index that is absent from the database.

    ``Base.metadata.create_all`` skips tables that already exist, so indexes added to a model
    later never reach an existing database. This closes that gap on SQLite and PostgreSQL.

    Args:
        engine: Engine bound to the state database.

    Returns:
        Names of the indexes that were created, in creation order.
    """
    inspector = inspect(engine)
    created: list[str] = []
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {i["name"] for i in inspector.get_indexes(table.name)}
        for index in sorted(table.indexes, key=lambda i: i.name or ""):
            if index.name is None or index.name in existing:
                continue
            index.create(engine)
            created.append(index.name)
    return created
