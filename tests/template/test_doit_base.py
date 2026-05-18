"""Tests for tools/doit/base.py helpers."""

from __future__ import annotations

import os
import shlex
import subprocess  # nosec B404 - test invokes bash deliberately to verify shell-snippet behaviour
import sys
from pathlib import Path

import pytest

from tools.doit.base import install_check_or_skip, optional_root_files


def _touch(tmp_path: Path, rel: str) -> Path:
    """Create ``rel`` under ``tmp_path`` and return the absolute path."""
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")
    return target


class TestOptionalRootFiles:
    """Tests for the ``optional_root_files`` helper."""

    def test_empty_input_returns_empty_string(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No names -> empty string (safe to concatenate)."""
        monkeypatch.chdir(tmp_path)
        assert optional_root_files() == ""

    def test_missing_file_returns_empty_string(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Absent candidate -> empty string."""
        monkeypatch.chdir(tmp_path)
        assert optional_root_files("bootstrap.py") == ""

    def test_present_file_returns_space_prefixed_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Existing file -> ``' bootstrap.py'`` (single leading space)."""
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "bootstrap.py")

        result = optional_root_files("bootstrap.py")
        assert result == " bootstrap.py"
        # Exactly one leading space.
        assert result.startswith(" ")
        assert not result.startswith("  ")

    def test_two_present_files_preserve_argument_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Multiple present names -> argument order preserved, single space separators."""
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "a.py")
        _touch(tmp_path, "b.py")

        assert optional_root_files("a.py", "b.py") == " a.py b.py"
        # Swapping the argument order swaps the output order too.
        assert optional_root_files("b.py", "a.py") == " b.py a.py"

    def test_mix_of_present_and_absent_filters_out_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only the present names survive; missing ones are silently skipped."""
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "a.py")

        assert optional_root_files("a.py", "missing.py") == " a.py"
        assert optional_root_files("missing.py", "a.py") == " a.py"

    def test_single_leading_space_and_separator(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Output uses exactly one leading space and one separator between names."""
        monkeypatch.chdir(tmp_path)
        _touch(tmp_path, "x.py")
        _touch(tmp_path, "y.py")

        result = optional_root_files("x.py", "y.py")
        # No double-spaces anywhere in the output.
        assert "  " not in result
        # Exactly two names separated by exactly one space.
        assert result == " x.py y.py"

    def test_directory_with_matching_name_is_not_treated_as_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A directory named ``bootstrap.py`` must not satisfy the is_file() guard."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "bootstrap.py").mkdir()

        assert optional_root_files("bootstrap.py") == ""


# ---------------------------------------------------------------------------
# install_check_or_skip
# ---------------------------------------------------------------------------


def _write_fake_uv(tmp_path: Path) -> Path:
    """Write a fake ``uv`` shim that gates ``pip show`` on the FAKE_INSTALLED env var.

    Returns the directory containing the shim (suitable for prepending to PATH).
    The shim accepts ``pip show <pkg>`` and exits 0 iff ``FAKE_INSTALLED=1``.
    All other invocations exit 0 (we never actually run ``uv run`` in these
    tests — the gate either skips or hands off to ``true`` / ``false``).
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shim = bindir / "uv"
    shim.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "pip" ] && [ "$2" = "show" ]; then\n'
        '  [ "$FAKE_INSTALLED" = "1" ] && exit 0 || exit 1\n'
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return bindir


def _run_bash(action: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run ``bash -c <action>`` with a deliberately minimal env. Used by the
    shell-level behavioural tests below."""
    return subprocess.run(  # nosec B603 B607
        ["bash", "-c", action],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


class TestInstallCheckOrSkip:
    """Structural tests for ``install_check_or_skip`` (cross-platform).

    Asserts the generated snippet's shape: gate command, redirection, hint,
    exit-0 branch, separator, and shell-safe quoting. Behavioural assertions
    (snippet driven through ``bash``) live in
    ``TestInstallCheckOrSkipShellBehavior`` below — those are POSIX-shell
    specific and skipped on Windows.
    """

    def test_snippet_contains_uv_pip_show_with_package(self) -> None:
        """The gate uses ``uv pip show <package>`` to detect installation."""
        snippet = install_check_or_skip("bandit", "bandit not installed.")
        assert "uv pip show bandit" in snippet

    def test_snippet_silences_pip_show_output(self) -> None:
        """The gate must redirect ``uv pip show`` output so it doesn't pollute task logs."""
        snippet = install_check_or_skip("bandit", "bandit not installed.")
        assert ">/dev/null 2>&1" in snippet

    def test_snippet_contains_hint(self) -> None:
        """The hint is embedded in the not-installed branch."""
        snippet = install_check_or_skip(
            "bandit", "bandit not installed. Run: uv sync --extra security"
        )
        assert "bandit not installed. Run: uv sync --extra security" in snippet

    def test_snippet_exits_zero_in_not_installed_branch(self) -> None:
        """The not-installed branch must exit 0 so doit ticks green for missing extras."""
        snippet = install_check_or_skip("bandit", "bandit not installed.")
        assert "exit 0" in snippet

    def test_snippet_ends_with_separator_for_concatenation(self) -> None:
        """The snippet ends with ``; `` so callers can plain-concatenate the rest of the action."""
        snippet = install_check_or_skip("bandit", "bandit not installed.")
        assert snippet.endswith("; ")

    def test_hint_with_special_chars_is_shell_quoted(self) -> None:
        """Hints containing single quotes / spaces are quoted via ``shlex.quote``.

        Without quoting, an embedded ``'`` would terminate the shell-quoted
        string and either break the snippet or, worse, allow injection.
        """
        hint = "don't break: run `uv sync --extra security`"
        snippet = install_check_or_skip("bandit", hint)
        # The hint is included via shlex.quote(); whatever its quoted form is,
        # bash must echo back the original hint verbatim when the snippet runs.
        assert shlex.quote(hint) in snippet


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "Behavioural tests drive the snippet through bash -c with a fake "
        "``uv`` shim on PATH. On GitHub's Windows runners, ``bash`` resolves "
        "to ``wsl.exe`` and fails before the snippet is reached. The doit "
        "task action only runs through POSIX shell in real use, so this "
        "platform restriction matches reality."
    ),
)
class TestInstallCheckOrSkipShellBehavior:
    """Behavioural tests for ``install_check_or_skip`` (POSIX shells only).

    Drive the snippet through ``bash -c`` against a fake ``uv`` shim on PATH
    to verify that the three relevant branches behave correctly. The
    "installed + tool fails -> action exits non-zero" case is the bug fix
    being verified (issue #527).
    """

    def _build_env(self, bindir: Path, *, installed: bool) -> dict[str, str]:
        """Build a minimal child env with the fake-uv directory ahead of system bins."""
        # /usr/bin and /bin keep ``bash``, ``echo``, etc. resolvable; the fake
        # ``uv`` wins because its directory comes first.
        path = f"{bindir}:/usr/bin:/bin"
        env = {"PATH": path, "FAKE_INSTALLED": "1" if installed else "0"}
        # ``bash`` itself sometimes needs ``HOME`` etc; keep it minimal but viable.
        if "HOME" in os.environ:
            env["HOME"] = os.environ["HOME"]
        return env

    def test_not_installed_branch_exits_zero_and_prints_hint(self, tmp_path: Path) -> None:
        """When ``uv pip show`` fails, the snippet prints the hint and exits 0."""
        bindir = _write_fake_uv(tmp_path)
        env = self._build_env(bindir, installed=False)

        snippet = install_check_or_skip(
            "bandit", "bandit not installed. Run: uv sync --extra security"
        )
        # The user's real command is ``false`` — if the gate failed to short
        # the shell on the not-installed branch, the action would exit 1.
        action = snippet + "false"

        result = _run_bash(action, env)
        assert result.returncode == 0
        assert "bandit not installed. Run: uv sync --extra security" in result.stdout

    def test_installed_and_tool_succeeds_exits_zero(self, tmp_path: Path) -> None:
        """When ``uv pip show`` succeeds and the tool succeeds, the action exits 0."""
        bindir = _write_fake_uv(tmp_path)
        env = self._build_env(bindir, installed=True)

        snippet = install_check_or_skip("bandit", "bandit not installed.")
        action = snippet + "true"

        result = _run_bash(action, env)
        assert result.returncode == 0
        # The hint must NOT appear on the happy path.
        assert "not installed" not in result.stdout

    def test_installed_and_tool_fails_propagates_nonzero(self, tmp_path: Path) -> None:
        """When ``uv pip show`` succeeds and the tool fails, the action exits non-zero.

        This is the bug fix from issue #527: previously the ``|| echo 'not
        installed'`` form swallowed real failures by exiting 0. The gate must
        let real failures through unmasked.
        """
        bindir = _write_fake_uv(tmp_path)
        env = self._build_env(bindir, installed=True)

        snippet = install_check_or_skip("bandit", "bandit not installed.")
        action = snippet + "false"

        result = _run_bash(action, env)
        assert result.returncode != 0
        # The "not installed" hint must NOT appear when the failure is real.
        assert "not installed" not in result.stdout
