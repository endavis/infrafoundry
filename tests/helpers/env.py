"""Helpers for constructing ``EnvironmentConfig`` instances in tests.

The validation pipeline receives a real ``EnvironmentConfig`` Pydantic model
(as of issue #609), so tests that previously handed in a raw dict should use
``make_env_config`` to build a model with the same fields.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.config.models import EnvironmentConfig


def make_env_config(*, name: str = "test", **overrides: Any) -> EnvironmentConfig:
    """Build an ``EnvironmentConfig`` for tests.

    Args:
        name: Environment name (defaults to ``"test"``).
        **overrides: Any additional ``EnvironmentConfig`` field values
            (e.g. ``provider_settings``, ``secrets``, ``provider_ssh``).

    Returns:
        An ``EnvironmentConfig`` instance populated with the given values.
    """
    return EnvironmentConfig(name=name, **overrides)
