"""Tests for state database connection pool configuration."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.state import state_manager
from infrafoundry.core.state.pool_config import build_engine_kwargs

PG_URL = "postgresql://user:pass@db.example.com/infrafoundry"
POOL_VARS = (
    "INFRAFOUNDRY_STATE_POOL_SIZE",
    "INFRAFOUNDRY_STATE_MAX_OVERFLOW",
    "INFRAFOUNDRY_STATE_POOL_RECYCLE",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in POOL_VARS:
        monkeypatch.delenv(var, raising=False)


def test_sqlite_gets_no_kwargs() -> None:
    assert build_engine_kwargs("sqlite:///tmp/state.db") == {}


def test_postgresql_defaults() -> None:
    assert build_engine_kwargs(PG_URL) == {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    }


def test_driver_suffix_is_postgresql() -> None:
    assert "pool_size" in build_engine_kwargs("postgresql+psycopg2://u:p@db.example.com/x")


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFRAFOUNDRY_STATE_POOL_SIZE", "20")
    monkeypatch.setenv("INFRAFOUNDRY_STATE_MAX_OVERFLOW", "0")
    monkeypatch.setenv("INFRAFOUNDRY_STATE_POOL_RECYCLE", "300")
    kwargs = build_engine_kwargs(PG_URL)
    assert (kwargs["pool_size"], kwargs["max_overflow"], kwargs["pool_recycle"]) == (20, 0, 300)


@pytest.mark.parametrize("bad", ["abc", "-1", "1.5"])
def test_invalid_value_falls_back_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, bad: str
) -> None:
    monkeypatch.setenv("INFRAFOUNDRY_STATE_POOL_SIZE", bad)
    with caplog.at_level("WARNING"):
        kwargs = build_engine_kwargs(PG_URL)
    assert kwargs["pool_size"] == 5
    assert "INFRAFOUNDRY_STATE_POOL_SIZE" in caplog.text


def _capture_create_engine(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    from sqlalchemy import create_engine as real_create_engine

    calls: list[dict[str, Any]] = []

    def fake(url: str, **kwargs: Any) -> Any:
        calls.append(kwargs)
        # Real engine for a harmless URL; pool kwargs are only recorded.
        return real_create_engine("sqlite://")

    monkeypatch.setattr(state_manager, "create_engine", fake)
    return calls


def test_state_manager_sqlite_has_no_pool_args(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_create_engine(monkeypatch)
    state_manager.StateManager("sqlite:///:memory:")
    assert calls == [{}]


def test_state_manager_postgresql_passes_pool_args(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_create_engine(monkeypatch)
    state_manager.StateManager(PG_URL)
    assert calls[0]["pool_size"] == 5
    assert calls[0]["pool_pre_ping"] is True
