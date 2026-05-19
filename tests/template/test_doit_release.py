"""Tests for tools/doit/release.py — local-flow adaptation.

Covers the six local-relevant functions that diverge from upstream:
``validate_merge_commits``, ``validate_issue_links``,
``_get_pypi_name_from_pyproject``, ``task_release_pr``,
``task_release_tag``, and ``task_release_dev``.

Upstream's ``test_doit_release.py`` targets a different ``task_release``
shape (``_extract_version_from_release_pr``, ``_build_cz_get_next_cmd``,
``_repo_has_version_tags``, ``_extract_next_version_from_cz_output``) that
does not exist in this fork.  See docs/development/pyproject-template-divergences.md
for the category-3 entry.

Subprocess stubbing uses ``monkeypatch.setattr("tools.doit.release.subprocess.run",
fake)`` — NOT the shared ``mock_subprocess`` fixture — because ``release.py``
imports ``subprocess`` at its own module top, and the shared fixture patches
``tools.doit.github.subprocess.run`` which does not intercept calls made here.
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from tools.doit.release import (
    _get_pypi_name_from_pyproject,
    task_release_dev,
    task_release_pr,
    task_release_tag,
    validate_issue_links,
    validate_merge_commits,
)

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _silent_console() -> Console:
    """Return a Console that discards all output (suitable for tests)."""
    return Console(file=io.StringIO(), force_terminal=False)


def _make_completed(
    cmd: list[str],
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=cmd, returncode=returncode, stdout=stdout, stderr=stderr
    )


# ---------------------------------------------------------------------------
# TestGetPypiNameFromPyproject — ported verbatim from upstream
# ---------------------------------------------------------------------------


class TestGetPypiNameFromPyproject:
    """Tests for ``_get_pypi_name_from_pyproject`` (issue #478).

    The helper reads ``[project].name`` from ``pyproject.toml`` in the current
    working directory at runtime.  Each test uses ``monkeypatch.chdir(tmp_path)``
    so the helper reads a synthetic ``pyproject.toml`` instead of the repo's
    real one.
    """

    def test_returns_project_name(self, tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
        """Happy path: ``[project].name = "my-pkg"`` → ``"my-pkg"``."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "my-pkg"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        assert _get_pypi_name_from_pyproject() == "my-pkg"

    def test_returns_none_when_pyproject_missing(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """No ``pyproject.toml`` in the cwd → ``None`` (caller falls back)."""
        monkeypatch.chdir(tmp_path)
        assert _get_pypi_name_from_pyproject() is None

    def test_returns_none_when_project_table_missing(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """Valid TOML without a ``[project]`` table → ``None``."""
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "irrelevant"\n',
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        assert _get_pypi_name_from_pyproject() is None

    def test_returns_none_when_name_key_missing(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """``[project]`` table present but no ``name`` key → ``None``."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        assert _get_pypi_name_from_pyproject() is None

    def test_returns_none_for_malformed_toml(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """Malformed TOML → ``None`` (the ``TOMLDecodeError`` is swallowed)."""
        (tmp_path / "pyproject.toml").write_text(
            "this is = = not valid toml [[",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        assert _get_pypi_name_from_pyproject() is None


# ---------------------------------------------------------------------------
# TestValidateMergeCommits — ported from upstream with local regex adaptation
# ---------------------------------------------------------------------------


class TestValidateMergeCommits:
    """Tests for ``validate_merge_commits``.

    The helper shells out to ``git describe`` then ``git log --merges``.
    Tests monkeypatch ``tools.doit.release.subprocess.run`` so git calls
    return canned results.

    Local adaptation: the local regex allows ``release:`` as a valid type
    (so release-PR merges pass governance validation on the next cut).
    """

    @staticmethod
    def _fake_run(
        describe_returncode: int,
        describe_stdout: str,
        log_stdout: str,
    ) -> tuple[list[list[str]], object]:
        """Build a fake ``subprocess.run`` that captures calls.

        Returns ``(captured_calls, fake_run)``.  The first git-describe call
        yields the given returncode/stdout; the second git-log call yields
        ``log_stdout`` with returncode 0.
        """
        calls: list[list[str]] = []

        def fake(
            cmd: list[str],
            *_args: object,
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            calls.append(list(cmd))
            if "describe" in cmd:
                return _make_completed(cmd, returncode=describe_returncode, stdout=describe_stdout)
            return _make_completed(cmd, returncode=0, stdout=log_stdout)

        return calls, fake

    def test_no_tags_falls_back_to_last_10_commits(self, monkeypatch: MonkeyPatch) -> None:
        """When ``git describe`` fails (no tags), range_spec is ``HEAD~10..HEAD``.

        Regression for the previous ``HEAD`` fallback that walked full history
        and surfaced merges from unrelated pre-project ancestors.
        """
        calls, fake = self._fake_run(describe_returncode=128, describe_stdout="", log_stdout="")
        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        assert validate_merge_commits(_silent_console()) is True

        log_cmds = [c for c in calls if "log" in c]
        assert len(log_cmds) == 1
        assert log_cmds[0][-1] == "HEAD~10..HEAD"

    def test_with_tag_uses_tag_range(self, monkeypatch: MonkeyPatch) -> None:
        """When a tag exists, range_spec is ``<last_tag>..HEAD``."""
        calls, fake = self._fake_run(
            describe_returncode=0, describe_stdout="v0.1.0\n", log_stdout=""
        )
        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        assert validate_merge_commits(_silent_console()) is True

        log_cmds = [c for c in calls if "log" in c]
        assert len(log_cmds) == 1
        assert log_cmds[0][-1] == "v0.1.0..HEAD"

    def test_valid_merge_commit_passes(self, monkeypatch: MonkeyPatch) -> None:
        """A merge commit matching the convention returns True."""
        _, fake = self._fake_run(
            describe_returncode=0,
            describe_stdout="v0.1.0\n",
            log_stdout="abc1234 fix: handle null (merges PR #42, addresses #41)",
        )
        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        assert validate_merge_commits(_silent_console()) is True

    def test_invalid_merge_commit_fails(self, monkeypatch: MonkeyPatch) -> None:
        """A merge commit not matching the convention returns False."""
        _, fake = self._fake_run(
            describe_returncode=0,
            describe_stdout="v0.1.0\n",
            log_stdout="abc1234 Merge branch 'master' of https://example.com/repo",
        )
        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        assert validate_merge_commits(_silent_console()) is False


# ---------------------------------------------------------------------------
# TestValidateIssueLinks — fresh tests (no upstream equivalent)
# ---------------------------------------------------------------------------


class TestValidateIssueLinks:
    """Tests for ``validate_issue_links``.

    The helper calls ``git describe`` then ``git log`` and warns (but does NOT
    block) when non-docs, non-merge commits lack ``#N`` references.
    ``validate_issue_links`` always returns ``True``.
    """

    @staticmethod
    def _fake_run_for_issue_links(
        log_stdout: str,
        describe_returncode: int = 0,
        describe_stdout: str = "v0.1.0\n",
    ) -> object:
        def fake(
            cmd: list[str],
            *_args: object,
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            if "describe" in cmd:
                return _make_completed(cmd, returncode=describe_returncode, stdout=describe_stdout)
            return _make_completed(cmd, returncode=0, stdout=log_stdout)

        return fake

    def test_all_commits_with_issue_refs_returns_true(self, monkeypatch: MonkeyPatch) -> None:
        """Happy path: every non-docs commit references an issue → True."""
        log = "abc1234 feat: add new feature #42\ndef5678 fix: handle null values #43\n"
        monkeypatch.setattr(
            "tools.doit.release.subprocess.run",
            self._fake_run_for_issue_links(log_stdout=log),
        )
        assert validate_issue_links(_silent_console()) is True

    def test_commits_without_issue_refs_still_returns_true(self, monkeypatch: MonkeyPatch) -> None:
        """Warning path: commits lacking ``#N`` refs trigger a warning but return True.

        ``validate_issue_links`` is non-blocking by design.
        """
        log = "abc1234 feat: add new feature\ndef5678 chore: bump deps\n"
        monkeypatch.setattr(
            "tools.doit.release.subprocess.run",
            self._fake_run_for_issue_links(log_stdout=log),
        )
        # Still True even though no issue refs are present.
        assert validate_issue_links(_silent_console()) is True

    def test_docs_and_merge_commits_are_skipped(self, monkeypatch: MonkeyPatch) -> None:
        """``docs:`` commits and commits containing "merge" are excluded from the check."""
        log = "abc1234 docs: update README\ndef5678 Merge pull request #50 from feature/foo\n"
        monkeypatch.setattr(
            "tools.doit.release.subprocess.run",
            self._fake_run_for_issue_links(log_stdout=log),
        )
        assert validate_issue_links(_silent_console()) is True


# ---------------------------------------------------------------------------
# TestTaskReleasePr — fresh tests (light hybrid coverage)
# ---------------------------------------------------------------------------


class TestTaskReleasePr:
    """Tests for the action inside ``task_release_pr``.

    Light / hybrid coverage: happy path + four critical error branches.
    The action closes over the inner ``create_release_pr`` function; we call
    ``task_release_pr()["actions"][0]`` to reach it.
    """

    @staticmethod
    def _build_happy_fake_run(
        next_version: str = "1.2.3",
    ) -> tuple[list[list[str]], object]:
        """Build a ``subprocess.run`` stub for the happy-path sequence.

        Sequence (in order):
        1. ``git branch --show-current`` → "main"
        2. ``git status -s`` → "" (clean)
        3. ``git pull`` → success
        4. ``git describe --tags --abbrev=0`` → "v0.1.0" (validate_merge_commits)
        5. ``git log --merges ...`` → "" (no merges to validate)
        6. ``git describe --tags --abbrev=0`` → "v0.1.0" (validate_issue_links)
        7. ``git log --pretty=format ...`` → "" (no commits)
        8. ``doit check`` → success
        9. ``uv run cz bump --get-next`` → next_version
        10. ``git checkout -b release/v{next_version}`` → success
        11. ``uv run cz changelog --incremental`` → success
        12. ``git add CHANGELOG.md`` → success
        13. ``git commit -m ...`` → success
        14. ``git push -u origin release/v{next_version}`` → success
        15. ``gh pr create ...`` → success
        """
        calls: list[list[str]] = []

        def fake(
            cmd: list[str],
            *_args: object,
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            calls.append(list(cmd))
            stdout = ""
            if cmd[:3] == ["git", "branch", "--show-current"]:
                stdout = "main\n"
            elif cmd[:2] == ["git", "status"]:
                stdout = ""
            elif cmd[:2] == ["git", "describe"]:
                stdout = "v0.1.0\n"
            elif "--get-next" in cmd:
                stdout = f"{next_version}\n"
            return _make_completed(cmd, returncode=0, stdout=stdout)

        return calls, fake

    def test_happy_path_creates_pr(self, monkeypatch: MonkeyPatch) -> None:
        """Happy path: all subprocesses succeed → PR is created."""
        calls, fake = self._build_happy_fake_run(next_version="1.2.3")
        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        action = task_release_pr()["actions"][0]
        action()  # must not raise or sys.exit

        # Verify a gh pr create call was made.
        gh_calls = [c for c in calls if c[:3] == ["gh", "pr", "create"]]
        assert len(gh_calls) == 1

        # Verify the PR title contains the version.
        title_idx = gh_calls[0].index("--title") + 1
        assert "1.2.3" in gh_calls[0][title_idx]

        # Verify a release branch was checked out.
        checkout_calls = [c for c in calls if "checkout" in c and "-b" in c]
        assert len(checkout_calls) == 1
        assert checkout_calls[0][-1] == "release/v1.2.3"

    def test_not_on_main_exits(self, monkeypatch: MonkeyPatch) -> None:
        """When not on main, the action calls ``sys.exit(1)``."""

        def fake(
            cmd: list[str],
            *_args: object,
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            if cmd[:3] == ["git", "branch", "--show-current"]:
                return _make_completed(cmd, returncode=0, stdout="feature/foo\n")
            return _make_completed(cmd)

        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        action = task_release_pr()["actions"][0]
        with pytest.raises(SystemExit) as exc_info:
            action()
        assert exc_info.value.code == 1

    def test_dirty_tree_exits(self, monkeypatch: MonkeyPatch) -> None:
        """Uncommitted changes in the working tree → ``sys.exit(1)``."""

        def fake(
            cmd: list[str],
            *_args: object,
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            if cmd[:3] == ["git", "branch", "--show-current"]:
                return _make_completed(cmd, stdout="main\n")
            if cmd[:2] == ["git", "status"]:
                return _make_completed(cmd, stdout=" M tools/doit/release.py\n")
            return _make_completed(cmd)

        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        action = task_release_pr()["actions"][0]
        with pytest.raises(SystemExit) as exc_info:
            action()
        assert exc_info.value.code == 1

    def test_invalid_merge_commits_exits(self, monkeypatch: MonkeyPatch) -> None:
        """``validate_merge_commits`` returning False → ``sys.exit(1)``."""

        def fake(
            cmd: list[str],
            *_args: object,
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            if cmd[:3] == ["git", "branch", "--show-current"]:
                return _make_completed(cmd, stdout="main\n")
            if cmd[:2] == ["git", "status"]:
                return _make_completed(cmd, stdout="")
            if cmd[:2] == ["git", "pull"]:
                return _make_completed(cmd)
            if cmd[:2] == ["git", "describe"]:
                return _make_completed(cmd, stdout="v0.1.0\n")
            if "log" in cmd and "--merges" in cmd:
                # Return an invalid merge commit to fail validation.
                return _make_completed(cmd, stdout="abc1234 Bad commit message without pattern")
            return _make_completed(cmd)

        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        action = task_release_pr()["actions"][0]
        with pytest.raises(SystemExit) as exc_info:
            action()
        assert exc_info.value.code == 1

    def test_cz_get_next_failure_exits(self, monkeypatch: MonkeyPatch) -> None:
        """``cz bump --get-next`` non-zero exit → ``sys.exit(1)``."""

        def fake(
            cmd: list[str],
            *_args: object,
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            if cmd[:3] == ["git", "branch", "--show-current"]:
                return _make_completed(cmd, stdout="main\n")
            if cmd[:2] == ["git", "status"]:
                return _make_completed(cmd, stdout="")
            if cmd[:2] == ["git", "pull"]:
                return _make_completed(cmd)
            if cmd[:2] == ["git", "describe"]:
                return _make_completed(cmd, stdout="v0.1.0\n")
            if "log" in cmd and "--merges" in cmd:
                return _make_completed(cmd, stdout="")
            if "log" in cmd:
                return _make_completed(cmd, stdout="")
            if cmd[:2] == ["doit", "check"]:
                return _make_completed(cmd)
            if "--get-next" in cmd:
                raise subprocess.CalledProcessError(1, cmd, "", "no commits")
            return _make_completed(cmd)

        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        action = task_release_pr()["actions"][0]
        with pytest.raises(SystemExit) as exc_info:
            action()
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# TestTaskReleaseTag — fresh tests (light hybrid coverage)
# ---------------------------------------------------------------------------


class TestTaskReleaseTag:
    """Tests for the action inside ``task_release_tag``.

    Light / hybrid coverage: happy path + three critical error branches.
    """

    @staticmethod
    def _build_happy_fake_run(
        version: str = "1.2.3",
    ) -> tuple[list[list[str]], object]:
        """Build a ``subprocess.run`` stub for the happy-path sequence.

        Sequence:
        1. ``git branch --show-current`` → "main"
        2. ``git pull`` → success
        3. ``gh pr list ...`` → JSON with one release PR
        4. ``git tag -l v{version}`` → "" (tag not yet present)
        5. ``git tag v{version}`` → success
        6. ``git push origin v{version}`` → success
        """
        import json as _json

        calls: list[list[str]] = []
        pr_payload = _json.dumps(
            [
                {
                    "title": f"release: v{version}",
                    "mergedAt": "2026-01-01",
                    "headRefName": f"release/v{version}",
                }
            ]
        )

        def fake(
            cmd: list[str],
            *_args: object,
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            calls.append(list(cmd))
            if cmd[:3] == ["git", "branch", "--show-current"]:
                return _make_completed(cmd, stdout="main\n")
            if cmd[:2] == ["git", "pull"]:
                return _make_completed(cmd)
            if cmd[:2] == ["gh", "pr"]:
                return _make_completed(cmd, stdout=pr_payload)
            if cmd[:3] == ["git", "tag", "-l"]:
                return _make_completed(cmd, stdout="")  # tag absent
            return _make_completed(cmd)

        return calls, fake

    def test_happy_path_tags_and_pushes(self, monkeypatch: MonkeyPatch) -> None:
        """Happy path: creates tag v1.2.3 and pushes to origin."""
        calls, fake = self._build_happy_fake_run(version="1.2.3")
        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        action = task_release_tag()["actions"][0]
        action()  # must not raise

        tag_create = [c for c in calls if c[:2] == ["git", "tag"] and len(c) == 3]
        assert len(tag_create) == 1
        assert tag_create[0][2] == "v1.2.3"

        push_calls = [c for c in calls if c[:2] == ["git", "push"] and "v1.2.3" in c]
        assert len(push_calls) == 1

    def test_no_release_pr_found_exits(self, monkeypatch: MonkeyPatch) -> None:
        """Empty ``gh pr list`` result → ``sys.exit(1)``."""
        import json as _json

        def fake(
            cmd: list[str],
            *_args: object,
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            if cmd[:3] == ["git", "branch", "--show-current"]:
                return _make_completed(cmd, stdout="main\n")
            if cmd[:2] == ["git", "pull"]:
                return _make_completed(cmd)
            if cmd[:2] == ["gh", "pr"]:
                return _make_completed(cmd, stdout=_json.dumps([]))
            return _make_completed(cmd)

        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        action = task_release_tag()["actions"][0]
        with pytest.raises(SystemExit) as exc_info:
            action()
        assert exc_info.value.code == 1

    def test_version_not_extractable_exits(self, monkeypatch: MonkeyPatch) -> None:
        """PR title/branch without a version pattern → ``sys.exit(1)``."""
        import json as _json

        pr_payload = _json.dumps(
            [
                {
                    "title": "fix: some unrelated PR",
                    "mergedAt": "2026-01-01",
                    "headRefName": "fix/42-thing",
                }
            ]
        )

        def fake(
            cmd: list[str],
            *_args: object,
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            if cmd[:3] == ["git", "branch", "--show-current"]:
                return _make_completed(cmd, stdout="main\n")
            if cmd[:2] == ["git", "pull"]:
                return _make_completed(cmd)
            if cmd[:2] == ["gh", "pr"]:
                return _make_completed(cmd, stdout=pr_payload)
            return _make_completed(cmd)

        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        action = task_release_tag()["actions"][0]
        with pytest.raises(SystemExit) as exc_info:
            action()
        assert exc_info.value.code == 1

    def test_tag_already_exists_exits(self, monkeypatch: MonkeyPatch) -> None:
        """``git tag -l`` returning the tag name → ``sys.exit(1)``."""
        import json as _json

        pr_payload = _json.dumps(
            [
                {
                    "title": "release: v2.0.0",
                    "mergedAt": "2026-01-01",
                    "headRefName": "release/v2.0.0",
                }
            ]
        )

        def fake(
            cmd: list[str],
            *_args: object,
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            if cmd[:3] == ["git", "branch", "--show-current"]:
                return _make_completed(cmd, stdout="main\n")
            if cmd[:2] == ["git", "pull"]:
                return _make_completed(cmd)
            if cmd[:2] == ["gh", "pr"]:
                return _make_completed(cmd, stdout=pr_payload)
            if cmd[:3] == ["git", "tag", "-l"]:
                return _make_completed(cmd, stdout="v2.0.0\n")  # tag exists!
            return _make_completed(cmd)

        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        action = task_release_tag()["actions"][0]
        with pytest.raises(SystemExit) as exc_info:
            action()
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# TestTaskReleaseDev — fresh tests (light hybrid coverage)
# ---------------------------------------------------------------------------


class TestTaskReleaseDev:
    """Tests for the action inside ``task_release_dev``.

    Light / hybrid coverage: happy path + dirty-tree error + off-main warning
    (user accepts with ``"y"``).
    """

    @staticmethod
    def _build_happy_fake_run(
        branch: str = "main",
    ) -> tuple[list[list[str]], object]:
        """Build a ``subprocess.run`` stub for the happy-path sequence.

        Sequence:
        1. ``git branch --show-current`` → branch (default "main")
        2. ``git status -s`` → "" (clean)
        3. ``git pull`` → success
        4. ``doit check`` → success
        5. ``uv run cz bump --prerelease alpha --changelog`` → success
        6. ``git push --follow-tags origin main`` → success
        """
        calls: list[list[str]] = []

        def fake(
            cmd: list[str],
            *_args: object,
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            calls.append(list(cmd))
            stdout = ""
            if cmd[:3] == ["git", "branch", "--show-current"]:
                stdout = f"{branch}\n"
            elif cmd[:2] == ["git", "status"]:
                stdout = ""
            elif "bump" in cmd and "--prerelease" in cmd:
                stdout = "Bumping to version 0.2.0a0\n"
            return _make_completed(cmd, returncode=0, stdout=stdout)

        return calls, fake

    def test_happy_path_bumps_and_pushes(self, monkeypatch: MonkeyPatch) -> None:
        """Happy path: cz bump with prerelease type and push --follow-tags."""
        calls, fake = self._build_happy_fake_run()
        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        action = task_release_dev()["actions"][0]
        action()  # must not raise

        bump_calls = [c for c in calls if "bump" in c and "--prerelease" in c]
        assert len(bump_calls) == 1
        assert "--prerelease" in bump_calls[0]
        assert "alpha" in bump_calls[0]

        push_calls = [c for c in calls if c[:2] == ["git", "push"] and "--follow-tags" in c]
        assert len(push_calls) == 1

    def test_dirty_tree_exits(self, monkeypatch: MonkeyPatch) -> None:
        """Uncommitted changes → ``sys.exit(1)`` before any release work."""

        def fake(
            cmd: list[str],
            *_args: object,
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            if cmd[:3] == ["git", "branch", "--show-current"]:
                return _make_completed(cmd, stdout="main\n")
            if cmd[:2] == ["git", "status"]:
                return _make_completed(cmd, stdout=" M tools/doit/release.py\n")
            return _make_completed(cmd)

        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)

        action = task_release_dev()["actions"][0]
        with pytest.raises(SystemExit) as exc_info:
            action()
        assert exc_info.value.code == 1

    def test_off_main_branch_with_yes_continues(self, monkeypatch: MonkeyPatch) -> None:
        """User enters ``"y"`` at the off-main warning prompt → flow continues."""
        calls, fake = self._build_happy_fake_run(branch="feat/foo")
        monkeypatch.setattr("tools.doit.release.subprocess.run", fake)
        # Patch builtins.input to simulate the user accepting the warning.
        monkeypatch.setattr("builtins.input", lambda _prompt: "y")

        action = task_release_dev()["actions"][0]
        action()  # must not raise — user said "y"

        push_calls = [c for c in calls if c[:2] == ["git", "push"] and "--follow-tags" in c]
        assert len(push_calls) == 1
