"""Tests for tools/doit/git.py task wiring.

Verifies that ``task_commit``, ``task_bump``, and ``task_changelog`` gate
their ``cz`` invocations on ``uv pip show commitizen`` (via
``install_check_or_skip``) so real failures — pre-commit hook rejections,
tag/version bump failures, changelog generation failures — propagate
instead of being swallowed by the legacy ``|| echo 'not installed'`` pattern.

Addresses issue #527.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tools.doit.git import task_bump, task_changelog, task_commit, task_pre_commit_install

REPO_ROOT = Path(__file__).resolve().parents[2]


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


class TestPreCommitInstall:
    """`pre_commit_install` and the config must agree on the hook set (#749 D1).

    The task installs whatever `default_install_hook_types` declares. That is the
    right design — one source for the set — but it couples two files silently:
    remove the declaration and the task keeps passing while `commit-msg` stops
    being installed, which is the #741 failure exactly. These tests hold the two
    together.
    """

    @staticmethod
    def _declared_hook_types() -> list[str]:
        config = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
        return list(config.get("default_install_hook_types") or [])

    def test_task_delegates_the_hook_set_to_the_config(self) -> None:
        """A single bare install, so the config decides which types are installed."""
        actions = task_pre_commit_install()["actions"]
        assert actions == ["uv run pre-commit install"], (
            "Enumerating --hook-type here re-creates the bug this fixed: the list "
            "drifts from `default_install_hook_types` and describes a hook set that "
            "is no longer the hook set."
        )

    def test_config_declares_the_hook_types_the_task_relies_on(self) -> None:
        """The bare install is only sufficient while the config declares the set."""
        declared = self._declared_hook_types()
        assert declared, (
            "`default_install_hook_types` is gone from .pre-commit-config.yaml, so "
            "`pre-commit install` now installs only `pre-commit` and every other hook "
            "type stops running. Restore it, or make the task enumerate the set again."
        )

    def test_commit_msg_is_among_them(self) -> None:
        """`commit-msg` carries conventional commits and the branch/issue check."""
        assert "commit-msg" in self._declared_hook_types(), (
            "Without `commit-msg`, neither conventional-commit validation nor the "
            "commit/branch issue check runs -- silently, because a hook that was "
            "never installed cannot fail (#741)."
        )
