"""Tests for tools/doit/git.py task wiring.

Verifies that ``task_commit``, ``task_bump``, and ``task_changelog`` gate
their ``cz`` invocations on ``uv pip show commitizen`` (via
``install_check_or_skip``) so real failures — pre-commit hook rejections,
tag/version bump failures, changelog generation failures — propagate
instead of being swallowed by the legacy ``|| echo 'not installed'`` pattern.

Addresses issue #527.
"""

from __future__ import annotations

from tools.doit.git import task_bump, task_changelog, task_commit


class TestGitTaskGates:
    """Each git task gates ``cz`` via ``uv pip show commitizen``.

    The package name is ``commitizen`` (CLI is ``cz``). All three tasks
    share the same gating package; the underlying ``cz`` subcommand differs.
    """

    def test_commit_gates_on_commitizen_package(self) -> None:
        action = task_commit()["actions"][0]
        assert isinstance(action, str)
        assert "uv pip show commitizen" in action
        assert "commitizen not installed. Run: uv sync" in action
        assert "uv run cz commit" in action
        # Bug-fix invariant: the bare-swallow pattern must be gone.
        assert "|| echo 'commitizen not installed" not in action

    def test_bump_gates_on_commitizen_package(self) -> None:
        action = task_bump()["actions"][0]
        assert isinstance(action, str)
        assert "uv pip show commitizen" in action
        assert "commitizen not installed. Run: uv sync" in action
        assert "uv run cz bump" in action
        assert "|| echo 'commitizen not installed" not in action

    def test_changelog_gates_on_commitizen_package(self) -> None:
        action = task_changelog()["actions"][0]
        assert isinstance(action, str)
        assert "uv pip show commitizen" in action
        assert "commitizen not installed. Run: uv sync" in action
        assert "uv run cz changelog" in action
        assert "|| echo 'commitizen not installed" not in action
