"""Tests for tools/doit/quality.py task wiring around ``bootstrap.py``.

These tests verify that the code-quality tasks include ``bootstrap.py`` when
it exists at the cwd (template repo) and exclude it when it has been removed
(spawned consumer project). Addresses issue #469.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.doit.quality import (
    task_check,
    task_format,
    task_format_check,
    task_lint,
    task_lint_blueprints,
    task_type_check,
)


def _touch(tmp_path: Path, rel: str) -> Path:
    """Create ``rel`` under ``tmp_path`` and return the absolute path."""
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")
    return target


class TestTaskLint:
    """``task_lint`` includes bootstrap.py iff it exists at cwd."""

    def test_includes_bootstrap_py_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "bootstrap.py")

        task = task_lint()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert " bootstrap.py" in action

    def test_excludes_bootstrap_py_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        task = task_lint()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert "bootstrap.py" not in action
        # Sanity check: the ruff invocation is still present.
        assert "ruff check" in action


class TestTaskFormat:
    """``task_format`` has two actions (format + check --fix); both must behave the same."""

    def test_both_actions_include_bootstrap_py_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "bootstrap.py")

        task = task_format()
        for action in task["actions"]:
            assert isinstance(action, str)
            assert " bootstrap.py" in action

    def test_both_actions_exclude_bootstrap_py_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        task = task_format()
        for action in task["actions"]:
            assert isinstance(action, str)
            assert "bootstrap.py" not in action


class TestTaskFormatCheck:
    """``task_format_check`` runs ``ruff format --check``."""

    def test_includes_bootstrap_py_when_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "bootstrap.py")

        task = task_format_check()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert " bootstrap.py" in action

    def test_excludes_bootstrap_py_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        task = task_format_check()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert "bootstrap.py" not in action
        assert "ruff format --check" in action


class TestTaskCheck:
    """``task_check`` aggregates the pre-PR check tasks via ``task_dep``."""

    def test_task_dep_includes_audit(self) -> None:
        """``audit`` must run as part of ``doit check`` so dep CVEs fail locally."""
        task = task_check()
        assert "audit" in task["task_dep"]

    def test_task_dep_covers_full_check_set(self) -> None:
        """``task_check`` must depend on every pre-PR quality/security task."""
        task = task_check()
        assert set(task["task_dep"]) == {
            "format_check",
            "lint",
            "lint_blueprints",
            "type_check",
            "security",
            "audit",
            "spell_check",
            "test",
        }


class TestTaskTypeCheck:
    """``task_type_check`` runs ``mypy``.

    Note (local divergence): unlike upstream, this repo's ``task_type_check``
    targets ``src/ bootstrap.py`` statically rather than using
    ``optional_root_files``. The two upstream conditional tests are replaced
    by a single assertion on the local static action.
    """

    def test_action_targets_src_and_bootstrap(self) -> None:
        """Local action is ``uv run mypy src/ bootstrap.py`` (static, not conditional)."""
        task = task_type_check()
        action = task["actions"][0]
        assert isinstance(action, str)
        assert action == "uv run mypy src/ bootstrap.py"


class TestTaskLintBlueprints:
    """``task_lint_blueprints`` invokes the blueprint portability linter."""

    def test_action_invokes_portability_linter(self) -> None:
        task = task_lint_blueprints()
        actions = task["actions"]
        assert any("tools/lint_blueprint_portability.py" in a for a in actions)

    def test_name_field(self) -> None:
        task = task_lint_blueprints()
        assert task.get("name") == "lint_blueprints" or "name" not in task
