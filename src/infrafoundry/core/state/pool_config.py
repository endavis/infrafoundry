"""Connection pool settings for the InfraFoundry state database engine.

Pool arguments apply to client/server backends such as PostgreSQL. SQLite uses its own
default pool classes, which reject ``pool_size`` and ``max_overflow``, so SQLite gets none.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.engine import make_url

logger = logging.getLogger(__name__)

POOL_ENV_VARS: dict[str, str] = {
    "pool_size": "INFRAFOUNDRY_STATE_POOL_SIZE",
    "max_overflow": "INFRAFOUNDRY_STATE_MAX_OVERFLOW",
    "pool_recycle": "INFRAFOUNDRY_STATE_POOL_RECYCLE",
}

POOL_DEFAULTS: dict[str, int] = {
    "pool_size": 5,
    "max_overflow": 10,
    "pool_recycle": 1800,
}


def _read_int_env(kwarg: str) -> int:
    """Read a non-negative integer pool setting from the environment.

    Args:
        kwarg: The ``create_engine`` keyword (key of ``POOL_ENV_VARS``).

    Returns:
        The configured value, or the default when unset or invalid.
    """
    default = POOL_DEFAULTS[kwarg]
    name = POOL_ENV_VARS[kwarg]
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        value = -1
    if value < 0:
        logger.warning("Invalid %s value %r; using default %d", name, raw, default)
        return default
    return value


def build_engine_kwargs(connection_string: str) -> dict[str, Any]:
    """Build extra ``create_engine`` keyword arguments for a connection string.

    Args:
        connection_string: SQLAlchemy database URL.

    Returns:
        An empty dict for SQLite; pool settings and ``pool_pre_ping`` otherwise.
    """
    if make_url(connection_string).get_backend_name() == "sqlite":
        return {}
    kwargs: dict[str, Any] = {kwarg: _read_int_env(kwarg) for kwarg in POOL_ENV_VARS}
    kwargs["pool_pre_ping"] = True
    return kwargs
