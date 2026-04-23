"""Tests for pyproject_template utility functions."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tools.pyproject_template.utils import (
    FILES_TO_UPDATE,
    Colors,
    GitHubCLI,
    Logger,
    command_exists,
    get_first_author,
    get_git_config,
    is_github_url,
    load_toml_file,
    parse_github_url,
    update_file,
    update_test_files,
    validate_email,
    validate_package_name,
    validate_pypi_name,
)


class TestValidatePackageName:
    """Tests for validate_package_name function."""

    def test_lowercase_conversion(self) -> None:
        """Test that names are converted to lowercase."""
        assert validate_package_name("MyPackage") == "mypackage"

    def test_invalid_chars_replaced(self) -> None:
        """Test that invalid characters are replaced with underscores."""
        assert validate_package_name("my-package") == "my_package"
        assert validate_package_name("my.package") == "my_package"
        assert validate_package_name("my package") == "my_package"

    def test_leading_trailing_underscores_stripped(self) -> None:
        """Test that leading/trailing underscores are stripped."""
        assert validate_package_name("_mypackage_") == "mypackage"
        assert validate_package_name("__my__") == "my"

    def test_leading_number_prefixed(self) -> None:
        """Test that leading numbers get underscore prefix."""
        assert validate_package_name("123package") == "_123package"

    def test_valid_name_unchanged(self) -> None:
        """Test that valid names remain unchanged."""
        assert validate_package_name("my_package") == "my_package"
        assert validate_package_name("package123") == "package123"


class TestValidatePypiName:
    """Tests for validate_pypi_name function."""

    def test_lowercase_conversion(self) -> None:
        """Test that names are converted to lowercase."""
        assert validate_pypi_name("MyPackage") == "mypackage"

    def test_invalid_chars_replaced(self) -> None:
        """Test that invalid characters are replaced with hyphens."""
        assert validate_pypi_name("my_package") == "my-package"
        assert validate_pypi_name("my.package") == "my-package"
        assert validate_pypi_name("my package") == "my-package"

    def test_leading_trailing_hyphens_stripped(self) -> None:
        """Test that leading/trailing hyphens are stripped."""
        assert validate_pypi_name("-mypackage-") == "mypackage"

    def test_multiple_hyphens_collapsed(self) -> None:
        """Test that multiple hyphens are collapsed to one."""
        assert validate_pypi_name("my--package") == "my-package"
        assert validate_pypi_name("my___package") == "my-package"

    def test_valid_name_unchanged(self) -> None:
        """Test that valid names remain unchanged."""
        assert validate_pypi_name("my-package") == "my-package"


class TestValidateEmail:
    """Tests for validate_email function."""

    def test_valid_emails(self) -> None:
        """Test that valid emails pass validation."""
        assert validate_email("user@example.com") is True
        assert validate_email("user.name@example.com") is True
        assert validate_email("user+tag@example.co.uk") is True
        assert validate_email("user123@sub.domain.com") is True

    def test_invalid_emails(self) -> None:
        """Test that invalid emails fail validation."""
        assert validate_email("notanemail") is False
        assert validate_email("@example.com") is False
        assert validate_email("user@") is False
        assert validate_email("user@.com") is False
        assert validate_email("") is False


class TestCommandExists:
    """Tests for command_exists function."""

    def test_existing_command(self) -> None:
        """Test that existing commands are detected."""
        # 'which' should exist on Linux/macOS
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert command_exists("python") is True

    def test_nonexistent_command(self) -> None:
        """Test that non-existent commands return False."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert command_exists("nonexistent_command_xyz") is False

    def test_handles_exception(self) -> None:
        """Test that exceptions are handled gracefully."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert command_exists("anything") is False


class TestGetGitConfig:
    """Tests for get_git_config function."""

    def test_returns_config_value(self) -> None:
        """Test that git config values are returned."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Test User\n")
            result = get_git_config("user.name")
            assert result == "Test User"

    def test_returns_default_on_failure(self) -> None:
        """Test that default is returned when config not found."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = get_git_config("nonexistent.key", "default_value")
            assert result == "default_value"

    def test_handles_exception(self) -> None:
        """Test that exceptions return default value."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = get_git_config("user.name", "fallback")
            assert result == "fallback"

    def test_falls_back_to_global_when_unscoped_fails(self) -> None:
        """Unscoped lookup failure triggers ``--global`` retry (#470)."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout=""),
                MagicMock(returncode=0, stdout="Global User\n"),
            ]
            result = get_git_config("user.name")
            assert result == "Global User"
            assert mock_run.call_count == 2
            # Second call must include the --global flag.
            second_call_argv = mock_run.call_args_list[1].args[0]
            assert "--global" in second_call_argv

    def test_returns_default_when_both_scopes_fail(self) -> None:
        """Both unscoped and global lookups failing yields the default (#470)."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout=""),
                MagicMock(returncode=1, stdout=""),
            ]
            result = get_git_config("nonexistent.key", "default_value")
            assert result == "default_value"
            assert mock_run.call_count == 2

    def test_fallback_exception_returns_default(self) -> None:
        """Exception on the ``--global`` retry falls back to default (#470)."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout=""),
                FileNotFoundError,
            ]
            result = get_git_config("user.name", "fallback")
            assert result == "fallback"
            assert mock_run.call_count == 2


class TestIsGithubUrl:
    """Tests for is_github_url function."""

    def test_valid_github_urls(self) -> None:
        """Test that valid GitHub URLs are recognized."""
        assert is_github_url("https://github.com/owner/repo") is True
        assert is_github_url("https://github.com/owner/repo.git") is True
        assert is_github_url("http://github.com/owner/repo") is True

    def test_github_subdomains(self) -> None:
        """Test that GitHub subdomains are recognized."""
        assert is_github_url("https://raw.github.com/owner/repo/main/file") is True

    def test_non_github_urls(self) -> None:
        """Test that non-GitHub URLs are rejected."""
        assert is_github_url("https://gitlab.com/owner/repo") is False
        assert is_github_url("https://bitbucket.org/owner/repo") is False

    def test_url_manipulation_attack(self) -> None:
        """Test that URL manipulation attacks are rejected."""
        # This should NOT match - github.com is in the path, not the host
        assert is_github_url("https://evil.com/github.com/owner/repo") is False
        assert is_github_url("https://evil.com?redirect=github.com") is False

    def test_invalid_urls(self) -> None:
        """Test that invalid URLs return False."""
        assert is_github_url("") is False
        assert is_github_url("not-a-url") is False


class TestParseGithubUrl:
    """Tests for parse_github_url function."""

    def test_https_url(self) -> None:
        """Test parsing HTTPS GitHub URL."""
        owner, repo = parse_github_url("https://github.com/owner/repo")
        assert owner == "owner"
        assert repo == "repo"

    def test_https_url_with_git_suffix(self) -> None:
        """Test parsing HTTPS URL with .git suffix."""
        owner, repo = parse_github_url("https://github.com/owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"

    def test_ssh_url(self) -> None:
        """Test parsing SSH GitHub URL."""
        owner, repo = parse_github_url("git@github.com:owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"

    def test_trailing_slash(self) -> None:
        """Test parsing URL with trailing slash."""
        owner, repo = parse_github_url("https://github.com/owner/repo/")
        assert owner == "owner"
        assert repo == "repo"

    def test_empty_url(self) -> None:
        """Test that empty URL returns empty tuple."""
        owner, repo = parse_github_url("")
        assert owner == ""
        assert repo == ""

    def test_non_github_url(self) -> None:
        """Test that non-GitHub URL returns empty tuple."""
        owner, repo = parse_github_url("https://gitlab.com/owner/repo")
        assert owner == ""
        assert repo == ""


class TestLoadTomlFile:
    """Tests for load_toml_file function."""

    def test_loads_valid_toml(self, tmp_path: Path) -> None:
        """Test loading a valid TOML file."""
        toml_file = tmp_path / "test.toml"
        toml_file.write_text('[section]\nkey = "value"\nnumber = 42', encoding="utf-8")

        result = load_toml_file(toml_file)
        assert result == {"section": {"key": "value", "number": 42}}

    def test_returns_empty_dict_for_missing_file(self, tmp_path: Path) -> None:
        """Test that missing file returns empty dict."""
        result = load_toml_file(tmp_path / "nonexistent.toml")
        assert result == {}

    def test_returns_empty_dict_for_invalid_toml(self, tmp_path: Path) -> None:
        """Test that invalid TOML returns empty dict."""
        toml_file = tmp_path / "invalid.toml"
        toml_file.write_text("this is not valid toml [[[", encoding="utf-8")

        result = load_toml_file(toml_file)
        assert result == {}


class TestGetFirstAuthor:
    """Tests for get_first_author function."""

    def test_extracts_first_author(self) -> None:
        """Test extracting first author from pyproject data."""
        data = {
            "project": {
                "authors": [
                    {"name": "First Author", "email": "first@example.com"},
                    {"name": "Second Author", "email": "second@example.com"},
                ]
            }
        }
        name, email = get_first_author(data)
        assert name == "First Author"
        assert email == "first@example.com"

    def test_returns_empty_for_no_authors(self) -> None:
        """Test that empty tuple is returned when no authors."""
        data: dict[str, Any] = {"project": {}}
        name, email = get_first_author(data)
        assert name == ""
        assert email == ""

    def test_returns_empty_for_missing_project(self) -> None:
        """Test that empty tuple is returned when no project section."""
        data: dict[str, Any] = {}
        name, email = get_first_author(data)
        assert name == ""
        assert email == ""

    def test_handles_partial_author_info(self) -> None:
        """Test handling author with only name or email."""
        data = {"project": {"authors": [{"name": "Only Name"}]}}
        name, email = get_first_author(data)
        assert name == "Only Name"
        assert email == ""


class TestUpdateFile:
    """Tests for update_file function."""

    def test_replaces_strings(self, tmp_path: Path) -> None:
        """Test basic string replacement."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello old_value, goodbye old_value", encoding="utf-8")

        update_file(test_file, {"old_value": "new_value"})

        assert test_file.read_text(encoding="utf-8") == "Hello new_value, goodbye new_value"

    def test_package_name_preserves_kwargs(self, tmp_path: Path) -> None:
        """Test that package_name replacement preserves keyword arguments."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            'from package_name import module\nfunc(package_name="value")\n',
            encoding="utf-8",
        )

        update_file(test_file, {"package_name": "my_pkg"})

        content = test_file.read_text(encoding="utf-8")
        assert "from my_pkg import module" in content
        # The kwarg should be preserved
        assert 'package_name="value"' in content

    def test_package_name_preserves_toml_keys(self, tmp_path: Path) -> None:
        """``package_name = "value"`` form is preserved inside Python source.

        The ``(?!\\s*=)`` guard protects both kwargs and TOML-key forms when
        the file is a ``.py`` module. Non-Python files receive a blind
        replace and are covered by
        :class:`TestUpdateFileModes` (see commit-3 additions for this fix).
        """
        test_file = tmp_path / "settings.py"
        test_file.write_text('package_name = "value"\nname = "package_name"\n', encoding="utf-8")

        update_file(test_file, {"package_name": "my_pkg"})

        content = test_file.read_text(encoding="utf-8")
        assert 'package_name = "value"' in content
        assert 'name = "my_pkg"' in content

    def test_skips_missing_file(self, tmp_path: Path) -> None:
        """Test that missing files are skipped without error."""
        update_file(tmp_path / "nonexistent.txt", {"old": "new"})
        # Should not raise

    def test_skips_binary_files(self, tmp_path: Path) -> None:
        """Test that binary files are skipped."""
        binary_file = tmp_path / "test.bin"
        binary_file.write_bytes(b"\x00\x01\x02\xff\xfe")

        # Should not raise
        update_file(binary_file, {"old": "new"})


class TestUpdateTestFiles:
    """Tests for update_test_files function."""

    def test_updates_imports(self, tmp_path: Path) -> None:
        """Test that imports are updated in test files."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_example.py"
        test_file.write_text("from package_name import core\n", encoding="utf-8")

        update_test_files(test_dir, "my_package")

        assert "from my_package import core" in test_file.read_text(encoding="utf-8")

    def test_skips_missing_directory(self, tmp_path: Path) -> None:
        """Test that missing directory is handled gracefully."""
        update_test_files(tmp_path / "nonexistent", "my_package")
        # Should not raise


class TestUpdateFileModes:
    """Tests for update_file's three replacement modes (#464).

    1. Marker tokens (``__FOO__``): blind replace; collision-proof.
    2. Identifier-like literals in ``.py`` files: word-boundary regex,
       so ``validate_package_name`` survives replacement of ``package_name``.
    3. Everything else: blind replace.
    """

    def test_marker_replacement_is_blind(self, tmp_path: Path) -> None:
        """``__PACKAGE_NAME__`` marker is replaced regardless of surrounding chars."""
        test_file = tmp_path / "readme.md"
        test_file.write_text(
            "Install `__PACKAGE_NAME__`. See docs at __PACKAGE_NAME__.\n",
            encoding="utf-8",
        )

        update_file(test_file, {"__PACKAGE_NAME__": "my_pkg"})

        content = test_file.read_text(encoding="utf-8")
        assert "Install `my_pkg`" in content
        assert "See docs at my_pkg" in content

    def test_literal_in_python_code_protects_identifiers(self, tmp_path: Path) -> None:
        """``validate_package_name`` survives replacement of the ``package_name`` literal."""
        test_file = tmp_path / "mod.py"
        test_file.write_text(
            "from tools.utils import validate_package_name\nfrom package_name import core\n",
            encoding="utf-8",
        )

        update_file(test_file, {"package_name": "my_pkg"})

        content = test_file.read_text(encoding="utf-8")
        assert "validate_package_name" in content  # identifier preserved
        assert "from my_pkg import core" in content  # standalone replaced

    def test_literal_username_in_python_code_protects_identifiers(self, tmp_path: Path) -> None:
        """``my_username`` survives; bare ``username`` is replaced."""
        test_file = tmp_path / "mod.py"
        test_file.write_text(
            "my_username = config['user']\nprint(username)\n",
            encoding="utf-8",
        )

        update_file(test_file, {"username": "testuser"})

        content = test_file.read_text(encoding="utf-8")
        assert "my_username" in content
        assert "print(testuser)" in content

    def test_literal_in_non_python_file_is_blind(self, tmp_path: Path) -> None:
        """Prose files still get blind replace for literal tokens (no word boundary)."""
        test_file = tmp_path / "guide.md"
        test_file.write_text("Run `my_package_name` to install.\n", encoding="utf-8")

        update_file(test_file, {"package_name": "pyprojecttest"})

        # Blind replace corrupts identifiers in non-Python files by design;
        # callers should migrate prose files to marker tokens (see #464 commit 2).
        content = test_file.read_text(encoding="utf-8")
        assert "my_pyprojecttest" in content

    def test_python_identifier_hyphen_case(self, tmp_path: Path) -> None:
        """``\\b`` boundaries work around hyphen since ``-`` is non-word."""
        test_file = tmp_path / "mod.py"
        test_file.write_text(
            "# doc: package-name and somepackage-name and package-nameish\n",
            encoding="utf-8",
        )

        update_file(test_file, {"package-name": "my-pkg"})

        content = test_file.read_text(encoding="utf-8")
        assert "# doc: my-pkg and somepackage-name and package-nameish" in content

    def test_marker_does_not_interfere_with_literal(self, tmp_path: Path) -> None:
        """Marker and literal replacements for the same concept coexist cleanly."""
        test_file = tmp_path / "mixed.md"
        test_file.write_text(
            "New marker: __PACKAGE_NAME__. Old literal: package_name.\n",
            encoding="utf-8",
        )

        update_file(
            test_file,
            {"__PACKAGE_NAME__": "my_pkg", "package_name": "my_pkg"},
        )

        content = test_file.read_text(encoding="utf-8")
        assert "New marker: my_pkg" in content
        assert "Old literal: my_pkg" in content


class TestColors:
    """Tests for Colors class."""

    def test_color_codes_defined(self) -> None:
        """Test that all color codes are defined."""
        assert Colors.RED.startswith("\033[")
        assert Colors.GREEN.startswith("\033[")
        assert Colors.YELLOW.startswith("\033[")
        assert Colors.BLUE.startswith("\033[")
        assert Colors.CYAN.startswith("\033[")
        assert Colors.BOLD.startswith("\033[")
        assert Colors.NC == "\033[0m"


class TestLogger:
    """Tests for Logger class."""

    def test_info_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test info message output."""
        Logger.info("Test message")
        captured = capsys.readouterr()
        assert "Test message" in captured.out
        assert "i" in captured.out

    def test_success_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test success message output."""
        Logger.success("Success message")
        captured = capsys.readouterr()
        assert "Success message" in captured.out

    def test_warning_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test warning message output."""
        Logger.warning("Warning message")
        captured = capsys.readouterr()
        assert "Warning message" in captured.out

    def test_error_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test error message output to stderr."""
        Logger.error("Error message")
        captured = capsys.readouterr()
        assert "Error message" in captured.err

    def test_step_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test step message output."""
        Logger.step("Step message")
        captured = capsys.readouterr()
        assert "Step message" in captured.out

    def test_header_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test header message output."""
        Logger.header("Header message")
        captured = capsys.readouterr()
        assert "Header message" in captured.out
        assert "━" in captured.out  # Check for separator line


class TestGitHubCLI:
    """Tests for GitHubCLI class."""

    def test_run_success(self) -> None:
        """Test successful gh command execution."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="output", stderr="")
            result = GitHubCLI.run(["repo", "view"])
            assert result.stdout == "output"
            mock_run.assert_called_once()

    def test_run_failure_raises(self) -> None:
        """Test that failed gh command raises exception."""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "gh")
            with pytest.raises(subprocess.CalledProcessError):
                GitHubCLI.run(["repo", "view"])

    def test_is_authenticated_true(self) -> None:
        """Test is_authenticated returns True when authenticated."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert GitHubCLI.is_authenticated() is True

    def test_is_authenticated_false(self) -> None:
        """Test is_authenticated returns False when not authenticated."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert GitHubCLI.is_authenticated() is False

    def test_is_authenticated_no_gh(self) -> None:
        """Test is_authenticated returns False when gh not installed."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert GitHubCLI.is_authenticated() is False


class TestFilesToUpdate:
    """Tests for FILES_TO_UPDATE constant."""

    def test_is_tuple(self) -> None:
        """Test that FILES_TO_UPDATE is a tuple (immutable)."""
        assert isinstance(FILES_TO_UPDATE, tuple)

    def test_contains_core_files(self) -> None:
        """Test that essential files are included."""
        core_files = [
            "pyproject.toml",
            "README.md",
            "LICENSE",
            "dodo.py",
            "mkdocs.yml",
            "AGENTS.md",
        ]
        for f in core_files:
            assert f in FILES_TO_UPDATE, f"Missing core file: {f}"

    def test_contains_github_workflows(self) -> None:
        """Test that GitHub workflow files are included."""
        workflow_files = [
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
            ".github/workflows/testpypi.yml",
            ".github/workflows/breaking-change-detection.yml",
        ]
        for f in workflow_files:
            assert f in FILES_TO_UPDATE, f"Missing workflow: {f}"

    def test_contains_github_files(self) -> None:
        """Test that GitHub config files are included."""
        github_files = [
            ".github/CONTRIBUTING.md",
            ".github/SECURITY.md",
            ".github/CODE_OF_CONDUCT.md",
            ".github/CODEOWNERS",
            ".github/pull_request_template.md",
        ]
        for f in github_files:
            assert f in FILES_TO_UPDATE, f"Missing GitHub file: {f}"

    def test_contains_claude_files(self) -> None:
        """Test that Claude config files are included."""
        claude_files = [
            ".claude/CLAUDE.md",
            ".claude/lsp-setup.md",
        ]
        for f in claude_files:
            assert f in FILES_TO_UPDATE, f"Missing Claude file: {f}"

    def test_contains_config_files(self) -> None:
        """Test that config files are included."""
        config_files = [
            ".envrc",
            ".pre-commit-config.yaml",
        ]
        for f in config_files:
            assert f in FILES_TO_UPDATE, f"Missing config file: {f}"

    def test_no_duplicates(self) -> None:
        """Test that there are no duplicate entries."""
        assert len(FILES_TO_UPDATE) == len(set(FILES_TO_UPDATE))
