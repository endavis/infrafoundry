"""Unit tests for infrafoundry.core.warnings."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from rich.panel import Panel

from infrafoundry.core.warnings import (
    ENV_VAR,
    emit_warning,
    read_warnings,
    render_warnings_panel,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure INFRAFOUNDRY_WARNINGS_FILE doesn't leak between tests."""
    monkeypatch.delenv(ENV_VAR, raising=False)


@pytest.mark.unit
def test_emit_warning_writes_jsonl(tmp_path: Path):
    """A single emit_warning call produces one well-formed JSON line."""
    target = tmp_path / "warnings.jsonl"

    emit_warning("handler:one", "something noisy but survivable", file_path=target)

    content = target.read_text(encoding="utf-8").splitlines()
    assert len(content) == 1
    record = json.loads(content[0])
    assert record == {"source": "handler:one", "message": "something noisy but survivable"}


@pytest.mark.unit
def test_emit_warning_appends_multiple(tmp_path: Path):
    """Repeated calls accumulate, one line each."""
    target = tmp_path / "warnings.jsonl"

    emit_warning("a", "first", file_path=target)
    emit_warning("b", "second", file_path=target)
    emit_warning("a", "third", file_path=target)

    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert [json.loads(line) for line in lines] == [
        {"source": "a", "message": "first"},
        {"source": "b", "message": "second"},
        {"source": "a", "message": "third"},
    ]


@pytest.mark.unit
def test_emit_warning_no_op_when_unset(tmp_path: Path, monkeypatch):
    """With env var unset and no file_path, emit_warning silently no-ops."""
    monkeypatch.delenv(ENV_VAR, raising=False)

    # Should not raise and should not create any stray files.
    emit_warning("handler", "noise")

    # Confirm no files were created in tmp_path (the test's workspace).
    assert list(tmp_path.iterdir()) == []


@pytest.mark.unit
def test_emit_warning_uses_env_var_when_no_file_path(tmp_path: Path, monkeypatch):
    """When file_path is None, the env var is used as the target."""
    target = tmp_path / "env-warnings.jsonl"
    monkeypatch.setenv(ENV_VAR, str(target))

    emit_warning("env-source", "env-driven message")

    content = target.read_text(encoding="utf-8").splitlines()
    assert len(content) == 1
    assert json.loads(content[0]) == {
        "source": "env-source",
        "message": "env-driven message",
    }


@pytest.mark.unit
def test_emit_warning_explicit_path_overrides_env(tmp_path: Path, monkeypatch):
    """An explicit file_path argument wins over the env var."""
    env_target = tmp_path / "env.jsonl"
    explicit_target = tmp_path / "explicit.jsonl"
    monkeypatch.setenv(ENV_VAR, str(env_target))

    emit_warning("s", "m", file_path=explicit_target)

    assert not env_target.exists()
    assert explicit_target.read_text(encoding="utf-8").strip() != ""


@pytest.mark.unit
def test_emit_warning_concurrent_appends_dont_interleave(tmp_path: Path):
    """50 threads emitting 5KB messages each produce 50 intact JSON objects.

    This exercises the fcntl lock: POSIX O_APPEND is only atomic up to
    PIPE_BUF (4096 bytes), so a 5KB payload would interleave without it.
    """
    target = tmp_path / "concurrent.jsonl"
    payload = "x" * 5000  # 5KB, deliberately exceeds PIPE_BUF
    thread_count = 50

    errors: list[BaseException] = []

    def worker(idx: int) -> None:
        try:
            emit_warning(f"t-{idx}", payload, file_path=target)
        except BaseException as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == thread_count
    # Every line must be valid JSON with the expected payload.
    parsed = [json.loads(line) for line in lines]
    sources = sorted(p["source"] for p in parsed)
    assert sources == sorted(f"t-{i}" for i in range(thread_count))
    for p in parsed:
        assert p["message"] == payload


@pytest.mark.unit
def test_read_warnings_returns_empty_for_missing_file(tmp_path: Path):
    """Missing file → empty list; no exception raised."""
    assert read_warnings(tmp_path / "does-not-exist.jsonl") == []


@pytest.mark.unit
def test_read_warnings_returns_empty_for_empty_file(tmp_path: Path):
    """Empty file → empty list."""
    target = tmp_path / "empty.jsonl"
    target.write_text("", encoding="utf-8")

    assert read_warnings(target) == []


@pytest.mark.unit
def test_read_warnings_parses_jsonl(tmp_path: Path):
    """Multi-line file → list of dicts in order."""
    target = tmp_path / "multi.jsonl"
    target.write_text(
        '{"source": "a", "message": "one"}\n'
        '{"source": "b", "message": "two"}\n'
        '{"source": "a", "message": "three"}\n',
        encoding="utf-8",
    )

    result = read_warnings(target)
    assert result == [
        {"source": "a", "message": "one"},
        {"source": "b", "message": "two"},
        {"source": "a", "message": "three"},
    ]


@pytest.mark.unit
def test_read_warnings_skips_malformed_lines(tmp_path: Path, caplog):
    """Malformed JSON lines are skipped; other lines parse; no exception raised."""
    target = tmp_path / "mixed.jsonl"
    target.write_text(
        '{"source": "good", "message": "one"}\n'
        "this-is-not-json\n"
        "\n"
        '{"source": "good", "message": "two"}\n'
        "[1, 2, 3]\n"  # valid JSON but not a dict
        '{"source": "good", "message": "three"}\n',
        encoding="utf-8",
    )

    result = read_warnings(target)
    assert result == [
        {"source": "good", "message": "one"},
        {"source": "good", "message": "two"},
        {"source": "good", "message": "three"},
    ]


@pytest.mark.unit
def test_render_warnings_panel_groups_by_source():
    """Panel body groups messages by their source identifier."""
    console = MagicMock()
    warnings_list = [
        {"source": "handler-a", "message": "first"},
        {"source": "handler-b", "message": "second"},
        {"source": "handler-a", "message": "third"},
    ]

    render_warnings_panel(warnings_list, console)

    console.print.assert_called_once()
    (printed,), _ = console.print.call_args
    assert isinstance(printed, Panel)
    # Title encodes the count.
    title = str(printed.title)
    assert "Warnings" in title
    assert "3" in title
    # Body groups by source. Render the Text object to plain to inspect.
    rendered_body = printed.renderable.plain
    assert "handler-a" in rendered_body
    assert "handler-b" in rendered_body
    assert "first" in rendered_body
    assert "second" in rendered_body
    assert "third" in rendered_body
    # Messages under handler-a should appear together.
    a_idx = rendered_body.index("handler-a")
    b_idx = rendered_body.index("handler-b")
    first_idx = rendered_body.index("first")
    third_idx = rendered_body.index("third")
    # All handler-a messages fall before handler-b.
    assert first_idx > a_idx and first_idx < b_idx
    assert third_idx > a_idx and third_idx < b_idx


@pytest.mark.unit
def test_render_warnings_panel_no_op_when_empty():
    """Empty list → no print call; callers can render unconditionally."""
    console = MagicMock()

    render_warnings_panel([], console)

    console.print.assert_not_called()
