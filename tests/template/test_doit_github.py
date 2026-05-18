"""Tests for github.py doit tasks."""

import io
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

import tools.doit.github as github_mod
from tools.doit.github import (
    _PR_TITLE_PATTERN,
    _check_branch_up_to_date,
    _close_linked_issues,
    _ensure_branch_pushed,
    _extract_linked_issues,
    _fetch_github_labels,
    _format_merge_subject,
    _gh_env_create,
    _gh_env_exists,
    _gh_env_list,
    _gh_repo_slug,
    _is_transient_gh_error,
    _load_labels_file,
    _reconcile_labels,
    _run_gh_with_retry,
    task_env_create,
    task_env_list,
    task_labels_sync,
    task_publish_setup,
)


class TestExtractLinkedIssues:
    """Tests for _extract_linked_issues function."""

    def test_addresses_issue(self) -> None:
        """Test extraction of 'Addresses #XX' pattern."""
        body = "Addresses #123"
        result = _extract_linked_issues(body)
        assert result == ["123"]

    def test_addresses_lowercase_ignored(self) -> None:
        """Test that lowercase 'addresses #XX' is ignored."""
        body = "addresses #456"
        result = _extract_linked_issues(body)
        assert result == []

    def test_addresses_uppercase_ignored(self) -> None:
        """Test that uppercase 'ADDRESSES #XX' is ignored."""
        body = "ADDRESSES #789"
        result = _extract_linked_issues(body)
        assert result == []

    def test_mid_sentence_ignored(self) -> None:
        """Test that mid-sentence 'Addresses #XX' is ignored."""
        body = "This PR Addresses #123"
        result = _extract_linked_issues(body)
        assert result == []

    def test_multiple_addresses(self) -> None:
        """Test extraction of multiple addresses patterns at line starts."""
        body = "Addresses #123\nAddresses #456"
        result = _extract_linked_issues(body)
        assert result == ["123", "456"]

    def test_duplicate_issues(self) -> None:
        """Test that duplicate issues are removed."""
        body = "Addresses #123\nAddresses #123"
        result = _extract_linked_issues(body)
        assert result == ["123"]

    def test_no_issues(self) -> None:
        """Test handling of body with no issues."""
        body = "This PR adds a new feature"
        result = _extract_linked_issues(body)
        assert result == []

    def test_issue_in_code_block_still_matched(self) -> None:
        """Test that issues in code blocks are still matched (by design)."""
        body = "```\nAddresses #123\n```"
        result = _extract_linked_issues(body)
        assert result == ["123"]

    def test_old_closes_keyword_not_matched(self) -> None:
        """Test that old 'Closes' keyword is not matched."""
        body = "Closes #123"
        result = _extract_linked_issues(body)
        assert result == []

    def test_old_fixes_keyword_not_matched(self) -> None:
        """Test that old 'Fixes' keyword is not matched."""
        body = "Fixes #456"
        result = _extract_linked_issues(body)
        assert result == []

    def test_old_part_of_keyword_not_matched(self) -> None:
        """Test that old 'Part of' keyword is not matched."""
        body = "Part of #101"
        result = _extract_linked_issues(body)
        assert result == []


class TestFormatMergeSubject:
    """Tests for _format_merge_subject function."""

    def test_with_single_issue(self) -> None:
        """Test formatting with a single addressed issue."""
        result = _format_merge_subject("feat: add feature", 18, ["42"])
        assert result == "feat: add feature (merges PR #18, addresses #42)"

    def test_with_multiple_issues(self) -> None:
        """Test formatting with multiple addressed issues."""
        result = _format_merge_subject("fix: bug fix", 23, ["19", "20"])
        assert result == "fix: bug fix (merges PR #23, addresses #19, #20)"

    def test_without_issues(self) -> None:
        """Test formatting without linked issues."""
        result = _format_merge_subject("docs: update readme", 29, [])
        assert result == "docs: update readme (merges PR #29)"

    def test_with_scope(self) -> None:
        """Test formatting with scoped title."""
        result = _format_merge_subject("feat(api): add endpoint", 50, ["100"])
        assert result == "feat(api): add endpoint (merges PR #50, addresses #100)"

    def test_preserves_title_exactly(self) -> None:
        """Test that PR title is preserved exactly."""
        title = "refactor: simplify complex logic"
        result = _format_merge_subject(title, 99, ["55"])
        assert result.startswith(title)


class TestCloseLinkedIssues:
    """Tests for _close_linked_issues helper."""

    def test_closes_single_linked_issue(self, mock_subprocess: MagicMock) -> None:
        """Single issue results in one gh issue close invocation."""
        console = Console()
        mock_subprocess.register({("gh", "issue", "close"): {}})
        _close_linked_issues(["123"], 45, console)

        assert mock_subprocess.call_count == 1
        args, kwargs = mock_subprocess.call_args
        assert args[0] == [
            "gh",
            "issue",
            "close",
            "123",
            "--comment",
            "Addressed in PR #45",
        ]
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True

    def test_closes_multiple_linked_issues(self, mock_subprocess: MagicMock) -> None:
        """Multiple issues result in multiple calls in order."""
        console = Console()
        mock_subprocess.register({("gh", "issue", "close"): {}})
        _close_linked_issues(["10", "20", "30"], 7, console)

        assert mock_subprocess.call_count == 3
        called_issues = [call.args[0][3] for call in mock_subprocess.call_args_list]
        assert called_issues == ["10", "20", "30"]

    def test_no_issues_is_noop(self, mock_subprocess: MagicMock) -> None:
        """Empty issue list results in no subprocess calls."""
        console = Console()
        _close_linked_issues([], 99, console)

        mock_subprocess.assert_not_called()

    def test_partial_failure_continues(self, mock_subprocess: MagicMock) -> None:
        """A failure on one issue does not stop subsequent closes."""
        console = Console()

        def spec(cmd: list[str]) -> MagicMock | BaseException:
            if cmd[3] == "20":
                return subprocess.CalledProcessError(returncode=1, cmd=cmd, stderr="boom")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_subprocess.register({("gh", "issue", "close"): spec})
        # Should not raise.
        _close_linked_issues(["10", "20", "30"], 7, console)

        assert mock_subprocess.call_count == 3
        called_issues = [call.args[0][3] for call in mock_subprocess.call_args_list]
        assert called_issues == ["10", "20", "30"]

    def test_close_comment_format(self, mock_subprocess: MagicMock) -> None:
        """The close comment must be exactly 'Addressed in PR #<n>'."""
        console = Console()
        mock_subprocess.register({("gh", "issue", "close"): {}})
        _close_linked_issues(["5"], 123, console)

        cmd = mock_subprocess.call_args.args[0]
        assert cmd[4] == "--comment"
        assert cmd[5] == "Addressed in PR #123"


class TestCheckBranchUpToDate:
    """Tests for _check_branch_up_to_date helper."""

    @staticmethod
    def _make_console() -> Console:
        return Console(file=io.StringIO(), width=200)

    def test_up_to_date_branch_passes(self, mock_subprocess: MagicMock) -> None:
        """rev-list --count == 0 → helper returns cleanly."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "rev-list", "--count"): {"stdout": "0\n"},
                ("git", "fetch"): {},
            }
        )
        _check_branch_up_to_date("feat/x", console)

        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "up to date" in output.lower()

    def test_behind_branch_aborts(self, mock_subprocess: MagicMock) -> None:
        """rev-list --count > 0 → SystemExit(1) with remediation message."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "rev-list", "--count"): {"stdout": "3\n"},
                ("git", "fetch"): {},
                ("git", "log"): {"stdout": "abc1 one\n"},
            }
        )

        with pytest.raises(SystemExit) as excinfo:
            _check_branch_up_to_date("feat/x", console)

        assert excinfo.value.code == 1
        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "3 commit" in output
        assert "git rebase origin/main" in output
        assert "feat/x" in output

    def test_fetch_failure_warns_and_proceeds(self, mock_subprocess: MagicMock) -> None:
        """git fetch failure → warning printed, helper returns."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "fetch"): subprocess.CalledProcessError(
                    returncode=128, cmd=["git", "fetch"], stderr="could not resolve host"
                ),
            }
        )
        _check_branch_up_to_date("feat/x", console)

        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "warning" in output.lower()
        assert "could not resolve host" in output

    def test_behind_branch_lists_missing_commits(self, mock_subprocess: MagicMock) -> None:
        """Missing commit SHAs from `git log` appear in the output."""
        console = self._make_console()
        log_out = "abc1234 feat: one\ndef5678 fix: two\n"
        mock_subprocess.register(
            {
                ("git", "rev-list", "--count"): {"stdout": "2\n"},
                ("git", "fetch"): {},
                ("git", "log"): {"stdout": log_out},
            }
        )

        with pytest.raises(SystemExit):
            _check_branch_up_to_date("feat/x", console)

        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "abc1234" in output
        assert "def5678" in output


class TestEnsureBranchPushed:
    """Tests for _ensure_branch_pushed helper."""

    @staticmethod
    def _make_console() -> Console:
        return Console(file=io.StringIO(), width=200)

    def test_existing_upstream_is_noop(self, mock_subprocess: MagicMock) -> None:
        """rev-parse @{u} succeeds → no push, helper returns."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "rev-parse"): {"stdout": "origin/feat/x\n"},
            }
        )
        _ensure_branch_pushed("feat/x", console, no_push=False)

        assert mock_subprocess.call_count == 1

    def test_no_upstream_pushes(self, mock_subprocess: MagicMock) -> None:
        """rev-parse @{u} fails → git push -u origin is called."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "rev-parse"): subprocess.CalledProcessError(
                    returncode=128, cmd=["git", "rev-parse"], stderr="no upstream configured"
                ),
                ("git", "push", "-u"): {},
            }
        )
        _ensure_branch_pushed("feat/x", console, no_push=False)

        assert mock_subprocess.call_count == 2
        push_cmd = mock_subprocess.call_args_list[1].args[0]
        assert push_cmd == ["git", "push", "-u", "origin", "feat/x"]

    def test_push_failure_aborts(self, mock_subprocess: MagicMock) -> None:
        """rev-parse @{u} fails and git push fails → SystemExit(1)."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "rev-parse"): subprocess.CalledProcessError(
                    returncode=128, cmd=["git", "rev-parse"], stderr="no upstream"
                ),
                ("git", "push", "-u"): subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["git", "push", "-u"],
                    stderr="remote rejected: protected branch",
                ),
            }
        )

        with pytest.raises(SystemExit) as excinfo:
            _ensure_branch_pushed("feat/x", console, no_push=False)

        assert excinfo.value.code == 1
        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "Failed to push" in output
        assert "remote rejected" in output

    def test_no_push_flag_and_no_upstream_aborts(self, mock_subprocess: MagicMock) -> None:
        """no_push=True with missing upstream → SystemExit(1), no push."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "rev-parse"): subprocess.CalledProcessError(
                    returncode=128, cmd=["git", "rev-parse"], stderr="no upstream"
                ),
            }
        )

        with pytest.raises(SystemExit) as excinfo:
            _ensure_branch_pushed("feat/x", console, no_push=True)

        assert excinfo.value.code == 1
        assert mock_subprocess.call_count == 1
        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert "no upstream" in output.lower()
        assert "--no-push" in output

    def test_no_push_flag_with_upstream_passes(self, mock_subprocess: MagicMock) -> None:
        """no_push=True with an upstream → returns, no push."""
        console = self._make_console()
        mock_subprocess.register(
            {
                ("git", "rev-parse"): {"stdout": "origin/feat/x\n"},
            }
        )
        _ensure_branch_pushed("feat/x", console, no_push=True)

        assert mock_subprocess.call_count == 1


class TestLabelsSync:
    """Tests for the ``labels_sync`` doit task and its helpers."""

    @staticmethod
    def _make_console() -> Console:
        return Console(file=io.StringIO(), width=200)

    @staticmethod
    def _labels_file(tmp_path: Path, body: str) -> Path:
        path = tmp_path / "labels.yml"
        path.write_text(body, encoding="utf-8")
        return path

    @staticmethod
    def _register_list(mock_subprocess: MagicMock, current: list[dict[str, str]]) -> None:
        """Wire `gh label list` to return ``current`` as JSON."""
        mock_subprocess.register({("gh", "label", "list"): {"stdout": json.dumps(current)}})

    def _run_task(
        self,
        dry_run: bool = False,
        prune: bool = False,
        file: str = "",
    ) -> None:
        action = task_labels_sync()["actions"][0]
        action(dry_run=dry_run, prune=prune, file=file)

    def test_creates_missing_labels(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """File has 'foo', GH has none → one gh label create call."""
        labels_file = self._labels_file(
            tmp_path,
            "- name: foo\n  color: aaa111\n  description: Foo label\n",
        )
        self._register_list(mock_subprocess, [])
        mock_subprocess.register({("gh", "label", "create"): {}})

        self._run_task(file=str(labels_file))

        create_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:3] == ["gh", "label", "create"]
        ]
        assert len(create_calls) == 1
        assert create_calls[0].args[0] == [
            "gh",
            "label",
            "create",
            "foo",
            "--color",
            "aaa111",
            "--description",
            "Foo label",
        ]

    def test_updates_mismatched_labels(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """File has 'foo' color aaa111, GH has color bbb222 → one gh label edit call."""
        labels_file = self._labels_file(
            tmp_path,
            "- name: foo\n  color: aaa111\n  description: Foo label\n",
        )
        self._register_list(
            mock_subprocess,
            [{"name": "foo", "color": "bbb222", "description": "Foo label"}],
        )
        mock_subprocess.register({("gh", "label", "edit"): {}})

        self._run_task(file=str(labels_file))

        edit_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:3] == ["gh", "label", "edit"]
        ]
        assert len(edit_calls) == 1
        assert edit_calls[0].args[0] == [
            "gh",
            "label",
            "edit",
            "foo",
            "--color",
            "aaa111",
            "--description",
            "Foo label",
        ]

    def test_no_change_when_match(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """File and GH identical → no mutating calls."""
        labels_file = self._labels_file(
            tmp_path,
            "- name: foo\n  color: aaa111\n  description: Foo label\n",
        )
        self._register_list(
            mock_subprocess,
            [{"name": "foo", "color": "aaa111", "description": "Foo label"}],
        )

        self._run_task(file=str(labels_file))

        mutating = [
            c
            for c in mock_subprocess.call_args_list
            if c.args[0][:3]
            in (["gh", "label", "create"], ["gh", "label", "edit"], ["gh", "label", "delete"])
        ]
        assert mutating == []

    def test_prune_deletes_extras(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """With --prune, GH has a label not in file → gh label delete is called."""
        labels_file = self._labels_file(
            tmp_path,
            "- name: foo\n  color: aaa111\n  description: Foo label\n",
        )
        self._register_list(
            mock_subprocess,
            [
                {"name": "foo", "color": "aaa111", "description": "Foo label"},
                {"name": "old-label", "color": "cccccc", "description": "legacy"},
            ],
        )
        mock_subprocess.register({("gh", "label", "delete"): {}})

        self._run_task(file=str(labels_file), prune=True)

        delete_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:3] == ["gh", "label", "delete"]
        ]
        assert len(delete_calls) == 1
        assert delete_calls[0].args[0] == ["gh", "label", "delete", "old-label", "--yes"]

    def test_no_prune_by_default(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """GH has extra label, no --prune → no delete call; extra is reported as skipped."""
        labels_file = self._labels_file(
            tmp_path,
            "- name: foo\n  color: aaa111\n  description: Foo label\n",
        )
        self._register_list(
            mock_subprocess,
            [
                {"name": "foo", "color": "aaa111", "description": "Foo label"},
                {"name": "old-label", "color": "cccccc", "description": "legacy"},
            ],
        )

        self._run_task(file=str(labels_file))

        delete_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:3] == ["gh", "label", "delete"]
        ]
        assert delete_calls == []

    def test_dry_run_makes_no_mutations(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """With --dry-run, only gh label list is called; no create/edit/delete."""
        labels_file = self._labels_file(
            tmp_path,
            "- name: foo\n  color: aaa111\n  description: Foo label\n"
            "- name: bar\n  color: bbb222\n  description: Bar label\n",
        )
        self._register_list(
            mock_subprocess,
            [
                {"name": "bar", "color": "999999", "description": "Bar label"},
                {"name": "legacy", "color": "cccccc", "description": "to prune"},
            ],
        )

        self._run_task(file=str(labels_file), prune=True, dry_run=True)

        mutating = [
            c
            for c in mock_subprocess.call_args_list
            if c.args[0][:3]
            in (["gh", "label", "create"], ["gh", "label", "edit"], ["gh", "label", "delete"])
        ]
        assert mutating == []

    def test_malformed_yaml_raises_clear_error(
        self, tmp_path: Path, mock_subprocess: MagicMock
    ) -> None:
        """Entry without a 'name' field → SystemExit(1) naming the offending entry."""
        labels_file = self._labels_file(tmp_path, "- color: red\n")

        with pytest.raises(SystemExit) as excinfo:
            self._run_task(file=str(labels_file))

        assert excinfo.value.code == 1
        mock_subprocess.assert_not_called()

    def test_missing_file_raises(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """--file pointing at a nonexistent path → SystemExit(1)."""
        missing = tmp_path / "does-not-exist.yml"

        with pytest.raises(SystemExit) as excinfo:
            self._run_task(file=str(missing))

        assert excinfo.value.code == 1
        mock_subprocess.assert_not_called()

    def test_color_comparison_case_insensitive(
        self, tmp_path: Path, mock_subprocess: MagicMock
    ) -> None:
        """File 'FBCA04', GH 'fbca04' → no update."""
        labels_file = self._labels_file(
            tmp_path,
            "- name: needs-triage\n  color: FBCA04\n  description: triage\n",
        )
        self._register_list(
            mock_subprocess,
            [{"name": "needs-triage", "color": "fbca04", "description": "triage"}],
        )

        self._run_task(file=str(labels_file))

        mutating = [
            c
            for c in mock_subprocess.call_args_list
            if c.args[0][:3]
            in (["gh", "label", "create"], ["gh", "label", "edit"], ["gh", "label", "delete"])
        ]
        assert mutating == []

    def test_empty_description_handled(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """File entry with empty description → create call uses --description ''."""
        labels_file = self._labels_file(
            tmp_path,
            '- name: foo\n  color: aaa111\n  description: ""\n',
        )
        self._register_list(mock_subprocess, [])
        mock_subprocess.register({("gh", "label", "create"): {}})

        self._run_task(file=str(labels_file))

        create_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:3] == ["gh", "label", "create"]
        ]
        assert len(create_calls) == 1
        cmd = create_calls[0].args[0]
        assert cmd[-2:] == ["--description", ""]

    def test_summary_counts_correct(self, tmp_path: Path, mock_subprocess: MagicMock) -> None:
        """Mixed scenario (create + update + no-change + skipped) → counters correct."""
        labels_file = self._labels_file(
            tmp_path,
            "\n".join(
                [
                    "- name: new-one",
                    "  color: aaa111",
                    "  description: new",
                    "- name: updated",
                    "  color: bbb222",
                    "  description: updated desc",
                    "- name: same",
                    "  color: cccccc",
                    "  description: same",
                    "",
                ]
            ),
        )
        self._register_list(
            mock_subprocess,
            [
                {"name": "updated", "color": "999999", "description": "old"},
                {"name": "same", "color": "cccccc", "description": "same"},
                {"name": "extra", "color": "111111", "description": "extra"},
            ],
        )
        mock_subprocess.register(
            {
                ("gh", "label", "create"): {},
                ("gh", "label", "edit"): {},
            }
        )

        counters = _reconcile_labels(
            _load_labels_file(labels_file, self._make_console()),
            _fetch_github_labels(self._make_console()),
            prune=False,
            dry_run=False,
            console=self._make_console(),
        )

        assert counters["created"] == 1
        assert counters["updated"] == 1
        assert counters["unchanged"] == 1
        assert counters["deleted"] == 0
        assert counters["skipped"] == 1

    def test_labels_file_parses(self) -> None:
        """The actual .github/labels.yml parses and has non-empty entries."""
        repo_labels = Path(__file__).resolve().parent.parent.parent / ".github" / "labels.yml"
        assert repo_labels.exists(), f"{repo_labels} is missing"

        entries = _load_labels_file(repo_labels, self._make_console())
        assert entries, "labels.yml should not be empty"

        names = {entry["name"] for entry in entries}
        # Two labels the issue highlighted as missing on the repo must be present.
        assert "automerge-blocked" in names
        assert "do-not-merge" in names
        # Every entry must have a 6-char hex color.
        for entry in entries:
            assert len(entry["color"]) == 6, f"bad color for {entry['name']}: {entry['color']!r}"


class TestPrTitlePattern:
    """Tests for ``_PR_TITLE_PATTERN`` (issue #655).

    The pattern gates whether ``doit pr_merge`` accepts a PR title. All eight
    standard conventional-commit types must pass; ``release`` must pass too
    (machine-generated by ``doit release``) so the release PR can be merged
    via the standard flow. Arbitrary titles must be rejected.
    """

    @pytest.mark.parametrize(
        "title",
        [
            "feat: add thing",
            "fix: bug fix",
            "refactor: restructure",
            "docs: update",
            "test: add case",
            "chore: bump dep",
            "ci: add workflow",
            "perf: speed it up",
            "release: v0.1.0a0",
            "release: v1.2.3",
            "release: v0.1.0-alpha.0",
            "fix(api): scope ok",
            "release(hotfix): v1.2.3",
        ],
    )
    def test_valid_titles_match(self, title: str) -> None:
        assert _PR_TITLE_PATTERN.match(title), f"should match: {title!r}"

    @pytest.mark.parametrize(
        "title",
        [
            "no type prefix",
            "Release: wrong case",
            "feat add colon",
            "bump: wrong type",
            "release v0.1.0a0",  # missing colon
            "",
        ],
    )
    def test_invalid_titles_reject(self, title: str) -> None:
        assert not _PR_TITLE_PATTERN.match(title), f"should not match: {title!r}"


class TestGhRepoSlug:
    """Tests for the ``_gh_repo_slug`` helper."""

    def test_returns_name_with_owner(self, mock_subprocess: MagicMock) -> None:
        """gh repo view output is stripped and returned verbatim."""
        mock_subprocess.register({("gh", "repo", "view"): {"stdout": "acme/widgets\n"}})
        assert _gh_repo_slug() == "acme/widgets"

    def test_uses_json_and_jq(self, mock_subprocess: MagicMock) -> None:
        """The command uses ``--json nameWithOwner`` and ``--jq .nameWithOwner``."""
        mock_subprocess.register({("gh", "repo", "view"): {"stdout": "o/r\n"}})
        _gh_repo_slug()

        cmd = mock_subprocess.call_args.args[0]
        assert cmd == [
            "gh",
            "repo",
            "view",
            "--json",
            "nameWithOwner",
            "--jq",
            ".nameWithOwner",
        ]


class TestGhEnvExists:
    """Tests for the ``_gh_env_exists`` helper."""

    def test_returns_true_on_200(self, mock_subprocess: MagicMock) -> None:
        """HTTP 200 (returncode 0) → True."""
        mock_subprocess.register(
            {("gh", "api", "repos/acme/widgets/environments/pypi"): {"returncode": 0}}
        )
        assert _gh_env_exists("acme/widgets", "pypi") is True

    def test_returns_false_on_404(self, mock_subprocess: MagicMock) -> None:
        """Non-zero exit (e.g., 404) → False."""
        mock_subprocess.register(
            {
                ("gh", "api", "repos/acme/widgets/environments/pypi"): {
                    "returncode": 1,
                    "stderr": "HTTP 404: Not Found",
                }
            }
        )
        assert _gh_env_exists("acme/widgets", "pypi") is False

    def test_uses_silent_flag(self, mock_subprocess: MagicMock) -> None:
        """The GET includes ``--silent`` so the response body is discarded."""
        mock_subprocess.register(
            {("gh", "api", "repos/acme/widgets/environments/pypi"): {"returncode": 0}}
        )
        _gh_env_exists("acme/widgets", "pypi")

        cmd = mock_subprocess.call_args.args[0]
        assert cmd == ["gh", "api", "repos/acme/widgets/environments/pypi", "--silent"]


class TestGhEnvCreate:
    """Tests for the ``_gh_env_create`` helper."""

    def test_sends_put(self, mock_subprocess: MagicMock) -> None:
        """The call is a ``PUT`` to the environments endpoint."""
        mock_subprocess.register({("gh", "api", "-X", "PUT"): {}})
        _gh_env_create("acme/widgets", "pypi")

        cmd = mock_subprocess.call_args.args[0]
        assert cmd == ["gh", "api", "-X", "PUT", "repos/acme/widgets/environments/pypi"]
        assert mock_subprocess.call_args.kwargs["check"] is True

    def test_propagates_failure(self, mock_subprocess: MagicMock) -> None:
        """A failed API call propagates as CalledProcessError."""
        mock_subprocess.register(
            {
                ("gh", "api", "-X", "PUT"): subprocess.CalledProcessError(
                    returncode=1, cmd=["gh"], stderr="boom"
                )
            }
        )
        with pytest.raises(subprocess.CalledProcessError):
            _gh_env_create("acme/widgets", "pypi")


class TestGhEnvList:
    """Tests for the ``_gh_env_list`` helper."""

    def test_parses_and_sorts(self, mock_subprocess: MagicMock) -> None:
        """Newline-separated names are parsed and sorted alphabetically."""
        mock_subprocess.register(
            {("gh", "api", "repos/acme/widgets/environments"): {"stdout": "testpypi\npypi\n"}}
        )
        result = _gh_env_list("acme/widgets")
        assert result == ["pypi", "testpypi"]

    def test_handles_empty(self, mock_subprocess: MagicMock) -> None:
        """Empty output yields an empty list."""
        mock_subprocess.register({("gh", "api", "repos/acme/widgets/environments"): {"stdout": ""}})
        assert _gh_env_list("acme/widgets") == []

    def test_ignores_blank_lines(self, mock_subprocess: MagicMock) -> None:
        """Blank lines and extra whitespace are ignored."""
        mock_subprocess.register(
            {
                ("gh", "api", "repos/acme/widgets/environments"): {
                    "stdout": "  pypi\n\n  testpypi  \n"
                }
            }
        )
        assert _gh_env_list("acme/widgets") == ["pypi", "testpypi"]


class TestTaskEnvCreate:
    """Tests for the ``env_create`` doit task."""

    @staticmethod
    def _action() -> "Callable[..., None]":
        action = task_env_create()["actions"][0]
        return action  # type: ignore[no-any-return]

    def test_empty_name_exits(self, mock_subprocess: MagicMock) -> None:
        """Empty ``--name`` aborts with exit 1 and no API calls."""
        with pytest.raises(SystemExit) as excinfo:
            self._action()(name="")

        assert excinfo.value.code == 1
        mock_subprocess.assert_not_called()

    def test_shortcircuits_on_existing(self, mock_subprocess: MagicMock) -> None:
        """Existing environment → no PUT is issued."""
        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api", "repos/acme/widgets/environments/pypi"): {"returncode": 0},
            }
        )

        self._action()(name="pypi")

        put_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:4] == ["gh", "api", "-X", "PUT"]
        ]
        assert put_calls == []

    def test_creates_when_missing(self, mock_subprocess: MagicMock) -> None:
        """Missing environment → exactly one PUT is issued to the right path."""
        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api", "repos/acme/widgets/environments/pypi"): {
                    "returncode": 1,
                    "stderr": "HTTP 404",
                },
                ("gh", "api", "-X", "PUT"): {},
            }
        )

        self._action()(name="pypi")

        put_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:4] == ["gh", "api", "-X", "PUT"]
        ]
        assert len(put_calls) == 1
        assert put_calls[0].args[0] == [
            "gh",
            "api",
            "-X",
            "PUT",
            "repos/acme/widgets/environments/pypi",
        ]


class TestTaskEnvList:
    """Tests for the ``env_list`` doit task."""

    @staticmethod
    def _action() -> "Callable[..., None]":
        action = task_env_list()["actions"][0]
        return action  # type: ignore[no-any-return]

    def test_lists_environments(self, mock_subprocess: MagicMock) -> None:
        """A populated repo prints a bulleted list and issues no writes."""
        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api", "repos/acme/widgets/environments"): {"stdout": "pypi\ntestpypi\n"},
            }
        )

        self._action()()

        put_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:4] == ["gh", "api", "-X", "PUT"]
        ]
        assert put_calls == []
        assert mock_subprocess.call_count == 2

    def test_handles_empty_repo(self, mock_subprocess: MagicMock) -> None:
        """No environments → helper returns cleanly (no SystemExit, no writes)."""
        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api", "repos/acme/widgets/environments"): {"stdout": ""},
            }
        )

        # Must not raise.
        self._action()()

        put_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:4] == ["gh", "api", "-X", "PUT"]
        ]
        assert put_calls == []


class TestTaskPublishSetup:
    """Tests for the ``publish_setup`` doit task."""

    @staticmethod
    def _action() -> "Callable[..., None]":
        action = task_publish_setup()["actions"][0]
        return action  # type: ignore[no-any-return]

    def test_creates_both_when_missing(self, mock_subprocess: MagicMock) -> None:
        """Both ``testpypi`` and ``pypi`` are PUT when neither exists."""

        def api_spec(cmd: list[str]) -> MagicMock:
            # PUT requests succeed with 200.
            if cmd[:4] == ["gh", "api", "-X", "PUT"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            # GET environment-exists checks always 404 for this test.
            return MagicMock(returncode=1, stdout="", stderr="HTTP 404")

        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api"): api_spec,
            }
        )

        self._action()()

        put_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:4] == ["gh", "api", "-X", "PUT"]
        ]
        assert len(put_calls) == 2
        put_paths = [c.args[0][4] for c in put_calls]
        assert put_paths == [
            "repos/acme/widgets/environments/testpypi",
            "repos/acme/widgets/environments/pypi",
        ]

    def test_idempotent_when_both_exist(self, mock_subprocess: MagicMock) -> None:
        """When both environments exist, no PUT is issued."""
        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api", "repos/acme/widgets/environments/testpypi"): {"returncode": 0},
                ("gh", "api", "repos/acme/widgets/environments/pypi"): {"returncode": 0},
            }
        )

        self._action()()

        put_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:4] == ["gh", "api", "-X", "PUT"]
        ]
        assert put_calls == []

    def test_creates_only_missing(self, mock_subprocess: MagicMock) -> None:
        """Only the missing environment is PUT; existing one is skipped."""

        def api_spec(cmd: list[str]) -> MagicMock:
            if cmd[:4] == ["gh", "api", "-X", "PUT"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            # testpypi exists, pypi does not.
            if cmd[2] == "repos/acme/widgets/environments/testpypi":
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="HTTP 404")

        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api"): api_spec,
            }
        )

        self._action()()

        put_calls = [
            c for c in mock_subprocess.call_args_list if c.args[0][:4] == ["gh", "api", "-X", "PUT"]
        ]
        assert len(put_calls) == 1
        assert put_calls[0].args[0][4] == "repos/acme/widgets/environments/pypi"

    def test_output_lists_all_three_trusted_publishers(
        self, mock_subprocess: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Panel output enumerates all three (workflow, env) registrations."""
        mock_subprocess.register(
            {
                ("gh", "repo", "view"): {"stdout": "acme/widgets\n"},
                ("gh", "api", "repos/acme/widgets/environments/testpypi"): {"returncode": 0},
                ("gh", "api", "repos/acme/widgets/environments/pypi"): {"returncode": 0},
            }
        )

        self._action()()

        # Collapse all whitespace so assertions are robust against any
        # rich-driven line wrapping inside the Panel.fit output.
        captured = capsys.readouterr().out
        collapsed = " ".join(captured.split())

        # All three (workflow, env) pairs must be mentioned.
        assert "workflow=testpypi.yml, env=testpypi" in collapsed
        assert "workflow=release.yml, env=testpypi" in collapsed
        assert "workflow=release.yml, env=pypi" in collapsed

        # Both publishing URLs must appear. The TestPyPI URL must appear
        # at least twice (once per TestPyPI registration).
        assert "https://pypi.org/manage/account/publishing/" in collapsed
        assert "https://test.pypi.org/manage/account/publishing/" in collapsed
        assert collapsed.count("https://test.pypi.org/manage/account/publishing/") >= 2

        # The owner/repo values from _gh_repo_slug must appear.
        assert "acme" in collapsed
        assert "widgets" in collapsed


class TestIsTransientGhError:
    """Tests for _is_transient_gh_error string classifier."""

    def test_5xx_gateway_timeout(self) -> None:
        """HTTP 504 Gateway Timeout is classified as transient."""
        result = _is_transient_gh_error("non-200 OK status code: 504 Gateway Timeout")
        assert result is not None

    def test_503_service_unavailable(self) -> None:
        """503 Service Unavailable substring is classified as transient."""
        result = _is_transient_gh_error("503 Service Unavailable")
        assert result is not None

    def test_unicorn_marker(self) -> None:
        """GitHub's 'Unicorn!' error page is classified as transient."""
        result = _is_transient_gh_error("Unicorn!")
        assert result is not None

    def test_connection_refused(self) -> None:
        """'connection refused' is classified as transient."""
        result = _is_transient_gh_error("connection refused")
        assert result is not None

    def test_io_timeout(self) -> None:
        """'i/o timeout' is classified as transient."""
        result = _is_transient_gh_error("i/o timeout")
        assert result is not None

    def test_http_404_not_transient(self) -> None:
        """HTTP 404 Not Found is NOT transient."""
        result = _is_transient_gh_error("HTTP 404 Not Found")
        assert result is None

    def test_validation_error_not_transient(self) -> None:
        """Validation errors are NOT transient."""
        result = _is_transient_gh_error("Validation Failed: title required")
        assert result is None

    def test_empty_string_not_transient(self) -> None:
        """Empty string returns None (not transient)."""
        result = _is_transient_gh_error("")
        assert result is None


class TestRunGhWithRetry:
    """Tests for _run_gh_with_retry retry logic."""

    def test_success_on_first_attempt(
        self, mock_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Successful first attempt returns result without calling sleep."""
        sleep_mock = MagicMock()
        monkeypatch.setattr(github_mod.time, "sleep", sleep_mock)
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)

        mock_subprocess.register({("gh", "issue"): {"returncode": 0, "stdout": "ok"}})
        result = _run_gh_with_retry(["gh", "issue", "list"], check=True)

        assert result.stdout == "ok"
        sleep_mock.assert_not_called()

    def test_success_after_one_transient_retry(
        self, mock_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """First attempt raises transient 504, second attempt succeeds."""
        sleep_mock = MagicMock()
        monkeypatch.setattr(github_mod.time, "sleep", sleep_mock)
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)
        monkeypatch.setenv("DOIT_GH_RETRIES", "3")

        call_count = 0

        def spec(cmd: list[str]) -> MagicMock | BaseException:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CalledProcessError(
                    returncode=1,
                    cmd=cmd,
                    stderr="non-200 OK status code: 504 Gateway Timeout",
                )
            return MagicMock(returncode=0, stdout="merged", stderr="")

        mock_subprocess.register({("gh", "pr"): spec})
        result = _run_gh_with_retry(["gh", "pr", "merge", "42"], check=True)

        assert result.stdout == "merged"
        assert sleep_mock.call_count == 1

    def test_all_retries_exhausted_check_true(
        self, mock_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All retries exhausted with check=True raises CalledProcessError."""
        sleep_mock = MagicMock()
        monkeypatch.setattr(github_mod.time, "sleep", sleep_mock)
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)
        monkeypatch.setenv("DOIT_GH_RETRIES", "2")

        mock_subprocess.register(
            {
                ("gh", "api"): subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["gh", "api"],
                    stderr="503 Service Unavailable",
                )
            }
        )

        with pytest.raises(subprocess.CalledProcessError):
            _run_gh_with_retry(["gh", "api", "/repos"], check=True)

        # 2 retries means 3 total attempts → 2 sleeps
        assert sleep_mock.call_count == 2

    def test_non_retryable_4xx_raises_immediately(
        self, mock_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-transient (4xx) failure with check=True raises without sleeping."""
        sleep_mock = MagicMock()
        monkeypatch.setattr(github_mod.time, "sleep", sleep_mock)
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)

        mock_subprocess.register(
            {
                ("gh", "issue"): subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["gh", "issue"],
                    stderr="HTTP 422 Validation Failed: title required",
                )
            }
        )

        with pytest.raises(subprocess.CalledProcessError):
            _run_gh_with_retry(["gh", "issue", "create"], check=True)

        sleep_mock.assert_not_called()

    def test_check_false_transient_returns_after_exhaustion(
        self, mock_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """check=False with transient errors retries then returns CompletedProcess."""
        sleep_mock = MagicMock()
        monkeypatch.setattr(github_mod.time, "sleep", sleep_mock)
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)
        monkeypatch.setenv("DOIT_GH_RETRIES", "2")

        mock_subprocess.register(
            {
                ("gh", "api"): subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["gh", "api"],
                    stderr="503 Service Unavailable",
                )
            }
        )

        result = _run_gh_with_retry(["gh", "api", "/test"], check=False)

        assert result.returncode == 1
        assert "503" in result.stderr
        assert sleep_mock.call_count == 2

    def test_check_false_non_transient_returns_immediately(
        self, mock_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """check=False with non-transient error returns immediately without retry."""
        sleep_mock = MagicMock()
        monkeypatch.setattr(github_mod.time, "sleep", sleep_mock)
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)

        mock_subprocess.register(
            {
                ("gh", "api"): subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["gh", "api"],
                    stderr="HTTP 404 Not Found",
                )
            }
        )

        result = _run_gh_with_retry(["gh", "api", "/missing"], check=False)

        assert result.returncode == 1
        sleep_mock.assert_not_called()

    def test_doit_gh_retries_zero_no_sleep(
        self, mock_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DOIT_GH_RETRIES=0 means single attempt — failure raises, no sleep."""
        sleep_mock = MagicMock()
        monkeypatch.setattr(github_mod.time, "sleep", sleep_mock)
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)
        monkeypatch.setenv("DOIT_GH_RETRIES", "0")

        mock_subprocess.register(
            {
                ("gh", "label"): subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["gh", "label"],
                    stderr="503 Service Unavailable",
                )
            }
        )

        with pytest.raises(subprocess.CalledProcessError):
            _run_gh_with_retry(["gh", "label", "list"])

        sleep_mock.assert_not_called()

    def test_doit_gh_backoff_base_zero_sleep_near_zero(
        self, mock_subprocess: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DOIT_GH_BACKOFF_BASE=0.0 results in sleep called with ~0.0 delay."""
        sleep_calls: list[float] = []
        monkeypatch.setattr(github_mod.time, "sleep", lambda s: sleep_calls.append(s))
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)
        monkeypatch.setenv("DOIT_GH_RETRIES", "1")
        monkeypatch.setenv("DOIT_GH_BACKOFF_BASE", "0.0")

        call_count = 0

        def spec(cmd: list[str]) -> MagicMock | BaseException:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CalledProcessError(
                    returncode=1, cmd=cmd, stderr="503 Service Unavailable"
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_subprocess.register({("gh", "repo"): spec})
        _run_gh_with_retry(["gh", "repo", "view"])

        assert len(sleep_calls) == 1
        assert sleep_calls[0] == pytest.approx(0.0, abs=1e-9)

    def test_retry_banner_printed(
        self,
        mock_subprocess: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Retry banner is printed to console on transient failure."""
        monkeypatch.setattr(github_mod.time, "sleep", lambda *_: None)
        monkeypatch.setattr(github_mod.random, "uniform", lambda *_: 0.0)
        monkeypatch.setenv("DOIT_GH_RETRIES", "1")

        call_count = 0

        def spec(cmd: list[str]) -> MagicMock | BaseException:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CalledProcessError(
                    returncode=1, cmd=cmd, stderr="503 Service Unavailable"
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_subprocess.register({("gh", "pr"): spec})

        with patch("tools.doit.github.Console") as mock_console_cls:
            mock_console = MagicMock()
            mock_console_cls.return_value = mock_console
            _run_gh_with_retry(["gh", "pr", "view"])

        printed = " ".join(str(call.args[0]) for call in mock_console.print.call_args_list)
        assert "Retry" in printed
        assert "1/1" in printed
