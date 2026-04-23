"""Tests for the unified pyproject-template management tool."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.pyproject_template.settings import (
    PreflightWarning,
    ProjectContext,
    ProjectSettings,
    SettingsManager,
    TemplateState,
    get_template_commits_since,
    get_template_latest_commit,
)


class TestProjectSettings:
    """Tests for ProjectSettings dataclass."""

    def test_is_configured_with_valid_settings(self) -> None:
        """Test that is_configured returns True for valid settings."""
        settings = ProjectSettings(
            project_name="My Project",
            package_name="my_project",
            pypi_name="my-project",
            description="A test project",
            author_name="Test Author",
            author_email="test@example.com",
            github_user="testuser",
            github_repo="my-project",
        )
        assert settings.is_configured() is True

    def test_is_configured_with_placeholder_name(self) -> None:
        """Test that is_configured returns False for placeholder values."""
        settings = ProjectSettings(
            project_name="Package Name",  # placeholder
            package_name="package_name",  # placeholder
            description="A test project",
            author_name="Your Name",  # placeholder
            author_email="your.email@example.com",  # placeholder
            github_user="username",  # placeholder
        )
        assert settings.is_configured() is False

    def test_is_configured_with_empty_values(self) -> None:
        """Test that is_configured returns False for empty values."""
        settings = ProjectSettings()
        assert settings.is_configured() is False

    def test_has_placeholder_values_returns_fields(self) -> None:
        """Test that has_placeholder_values returns list of placeholder fields."""
        settings = ProjectSettings(
            project_name="Package Name",
            package_name="my_project",
            author_name="Your Name",
            author_email="test@example.com",
            github_user="testuser",
        )
        placeholders = settings.has_placeholder_values()
        assert "project_name" in placeholders
        assert "author_name" in placeholders
        assert "package_name" not in placeholders


class TestProjectContext:
    """Tests for ProjectContext dataclass."""

    def test_is_fresh_clone(self) -> None:
        """Test is_fresh_clone property."""
        context = ProjectContext(has_git=True, has_pyproject=False)
        assert context.is_fresh_clone is True

        context = ProjectContext(has_git=True, has_pyproject=True)
        assert context.is_fresh_clone is False

    def test_is_existing_repo(self) -> None:
        """Test is_existing_repo property."""
        context = ProjectContext(has_git=True, has_pyproject=True)
        assert context.is_existing_repo is True

        context = ProjectContext(has_git=False, has_pyproject=True)
        assert context.is_existing_repo is False


class TestTemplateState:
    """Tests for TemplateState dataclass."""

    def test_is_synced_with_commit(self) -> None:
        """Test is_synced returns True when commit is set."""
        state = TemplateState(commit="abc123", commit_date="2025-01-15")
        assert state.is_synced() is True

    def test_is_synced_without_commit(self) -> None:
        """Test is_synced returns False when commit is not set."""
        state = TemplateState()
        assert state.is_synced() is False


class TestPreflightWarning:
    """Tests for PreflightWarning dataclass."""

    def test_warning_with_suggestion(self) -> None:
        """Test warning creation with suggestion."""
        warning = PreflightWarning(
            message="GitHub CLI not authenticated",
            suggestion="Run: gh auth login",
        )
        assert warning.message == "GitHub CLI not authenticated"
        assert warning.suggestion == "Run: gh auth login"

    def test_warning_without_suggestion(self) -> None:
        """Test warning creation without suggestion."""
        warning = PreflightWarning(message="Not a git repository")
        assert warning.message == "Not a git repository"
        assert warning.suggestion == ""


class TestSettingsManager:
    """Tests for SettingsManager class."""

    def test_init_creates_default_context(self, tmp_path: Path) -> None:
        """Test that SettingsManager initializes with detected context."""
        # Create a minimal directory structure
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"', encoding="utf-8")
        (tmp_path / ".git").mkdir()

        with patch("subprocess.run") as mock_run:
            # Mock git config calls
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

            manager = SettingsManager(root=tmp_path)

            assert manager.context.has_pyproject is True
            assert manager.context.has_git is True

    def test_load_from_pyproject(self, tmp_path: Path) -> None:
        """Test loading settings from pyproject.toml."""
        pyproject_content = """
[project]
name = "test-project"
description = "A test project"
authors = [{name = "Test Author", email = "test@example.com"}]

[project.urls]
Repository = "https://github.com/testuser/test-project"
"""
        (tmp_path / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

            manager = SettingsManager(root=tmp_path)

            assert manager.settings.project_name == "test-project"
            assert manager.settings.description == "A test project"
            assert manager.settings.author_name == "Test Author"
            assert manager.settings.author_email == "test@example.com"
            assert manager.settings.github_user == "testuser"
            assert manager.settings.github_repo == "test-project"

    def test_load_from_settings_file(self, tmp_path: Path) -> None:
        """Test loading settings from settings.toml."""
        settings_dir = tmp_path / ".config" / "pyproject_template"
        settings_dir.mkdir(parents=True)

        settings_content = """
[project]
name = "My Project"
package_name = "my_project"
pypi_name = "my-project"
description = "A great project"
author_name = "Author Name"
author_email = "author@example.com"
github_user = "authoruser"
github_repo = "my-project"

[template]
commit = "abc123def456"
commit_date = "2025-01-15"
"""
        (settings_dir / "settings.toml").write_text(settings_content, encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "other"', encoding="utf-8")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

            manager = SettingsManager(root=tmp_path)

            # Settings file values should take precedence
            assert manager.settings.project_name == "My Project"
            assert manager.settings.package_name == "my_project"
            assert manager.template_state.commit == "abc123def456"
            assert manager.template_state.commit_date == "2025-01-15"

    def test_save_creates_settings_file(self, tmp_path: Path) -> None:
        """Test that save creates the settings file with template state."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"', encoding="utf-8")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

            manager = SettingsManager(root=tmp_path)
            # save() only saves when there's template state
            manager.template_state.commit = "abc123"
            manager.template_state.commit_date = "2025-01-17"
            manager.save()

            settings_file = tmp_path / ".config" / "pyproject_template" / "settings.toml"
            assert settings_file.exists()
            content = settings_file.read_text(encoding="utf-8")
            assert "abc123" in content

    def test_update_template_state(self, tmp_path: Path) -> None:
        """Test updating template state."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"', encoding="utf-8")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

            manager = SettingsManager(root=tmp_path)
            manager.update_template_state("newcommit123", "2025-01-20")

            assert manager.template_state.commit == "newcommit123"
            assert manager.template_state.commit_date == "2025-01-20"

            # Verify it was saved
            settings_file = tmp_path / ".config" / "pyproject_template" / "settings.toml"
            content = settings_file.read_text(encoding="utf-8")
            assert "newcommit123" in content


class TestGetTemplateLatestCommit:
    """Tests for get_template_latest_commit function."""

    def test_returns_commit_info_on_success(self) -> None:
        """Test that function returns commit SHA and date on success."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"""
{
    "sha": "abc123def456789",
    "commit": {
        "committer": {
            "date": "2025-01-15T10:30:00Z"
        }
    }
}
"""
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = get_template_latest_commit()

            assert result is not None
            commit_sha, commit_date = result
            assert commit_sha == "abc123def456789"  # Full SHA for GitHub compare
            assert commit_date == "2025-01-15"

    def test_returns_none_on_error(self) -> None:
        """Test that function returns None on network error."""
        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            result = get_template_latest_commit()
            assert result is None


class TestGetTemplateCommitsSince:
    """Tests for get_template_commits_since function."""

    def test_returns_commits_since_sha(self) -> None:
        """Test that function returns commits since the given SHA."""
        mock_response = MagicMock()
        # Use 12-char SHAs to match the truncation in the function
        mock_response.read.return_value = b"""
[
    {
        "sha": "newest123456",
        "commit": {
            "message": "Latest commit",
            "committer": {"date": "2025-01-20T10:00:00Z"}
        }
    },
    {
        "sha": "middle123456",
        "commit": {
            "message": "Middle commit",
            "committer": {"date": "2025-01-18T10:00:00Z"}
        }
    },
    {
        "sha": "known1234567",
        "commit": {
            "message": "Known commit",
            "committer": {"date": "2025-01-15T10:00:00Z"}
        }
    }
]
"""
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            # Pass the exact truncated SHA that will match
            result = get_template_commits_since("known1234567")

            assert result is not None
            assert len(result) == 2
            assert result[0]["sha"] == "newest123456"
            assert result[0]["message"] == "Latest commit"
            assert result[1]["sha"] == "middle123456"

    def test_returns_none_on_error(self) -> None:
        """Test that function returns None on error."""
        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            result = get_template_commits_since("abc123")
            assert result is None


class TestMainModule:
    """Tests for the manage module."""

    def test_parse_args_no_args(self) -> None:
        """Test parsing with no arguments."""
        from tools.pyproject_template.manage import parse_args

        args = parse_args([])
        assert args.command is None
        assert args.yes is False
        assert args.dry_run is False

    def test_parse_args_with_command(self) -> None:
        """Test parsing with command."""
        from tools.pyproject_template.manage import parse_args

        args = parse_args(["create"])
        assert args.command == "create"

        args = parse_args(["configure"])
        assert args.command == "configure"

        args = parse_args(["check"])
        assert args.command == "check"

        args = parse_args(["repo"])
        assert args.command == "repo"

    def test_parse_args_with_flags(self) -> None:
        """Test parsing with flags."""
        from tools.pyproject_template.manage import parse_args

        args = parse_args(["--yes", "--dry-run"])
        assert args.yes is True
        assert args.dry_run is True

        args = parse_args(["-y"])
        assert args.yes is True

    def test_parse_args_update_only(self) -> None:
        """Test parsing --update-only flag."""
        from tools.pyproject_template.manage import parse_args

        args = parse_args(["--update-only"])
        assert args.update_only is True

    def test_get_recommended_action_fresh_clone(self) -> None:
        """Test recommended action for fresh clone."""
        from tools.pyproject_template.manage import get_recommended_action

        context = ProjectContext(has_git=True, has_pyproject=False)
        settings = ProjectSettings()
        template_state = TemplateState()

        result = get_recommended_action(context, settings, template_state, None)
        assert result == 2  # Configure project (has placeholders)

    def test_get_recommended_action_placeholder_values(self) -> None:
        """Test recommended action when placeholders exist."""
        from tools.pyproject_template.manage import get_recommended_action

        context = ProjectContext(has_git=True, has_pyproject=True)
        settings = ProjectSettings(
            project_name="Package Name",  # placeholder
            author_name="Your Name",  # placeholder
        )
        template_state = TemplateState()

        result = get_recommended_action(context, settings, template_state, None)
        assert result == 2  # Re-run configuration

    def test_get_recommended_action_outdated_template(self) -> None:
        """Test recommended action when template is outdated."""
        from tools.pyproject_template.manage import get_recommended_action

        context = ProjectContext(has_git=True, has_pyproject=True)
        settings = ProjectSettings(
            project_name="My Project",
            package_name="my_project",
            pypi_name="my-project",
            author_name="Test Author",
            author_email="test@example.com",
            github_user="testuser",
            github_repo="my-project",
            description="A project",
        )
        template_state = TemplateState(commit="oldcommit123", commit_date="2025-01-01")

        result = get_recommended_action(
            context, settings, template_state, ("newcommit456", "2025-01-15")
        )
        assert result == 3  # Check for template updates

    def test_get_recommended_action_up_to_date(self) -> None:
        """Test recommended action when everything is up to date."""
        from tools.pyproject_template.manage import get_recommended_action

        context = ProjectContext(has_git=True, has_pyproject=True)
        settings = ProjectSettings(
            project_name="My Project",
            package_name="my_project",
            pypi_name="my-project",
            author_name="Test Author",
            author_email="test@example.com",
            github_user="testuser",
            github_repo="my-project",
            description="A project",
        )
        template_state = TemplateState(commit="samecommit12", commit_date="2025-01-15")

        result = get_recommended_action(
            context, settings, template_state, ("samecommit12", "2025-01-15")
        )
        assert result is None  # No recommendation, up to date


class TestConfigureModule:
    """Tests for the configure module refactoring."""

    def test_parse_args_accepts_argv(self) -> None:
        """Test that parse_args accepts argv parameter."""
        from tools.pyproject_template.configure import parse_args

        args = parse_args(["--auto", "--yes"])
        assert args.auto is True
        assert args.yes is True

    def test_parse_args_dry_run(self) -> None:
        """Test that parse_args accepts --dry-run."""
        from tools.pyproject_template.configure import parse_args

        args = parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_run_configure_replaces_owner_repo_placeholders(self, tmp_path: Path) -> None:
        """Test that {owner} and {repo} placeholders are replaced."""
        from tools.pyproject_template.configure import run_configure

        # Create minimal project structure
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"', encoding="utf-8")
        (tmp_path / "src" / "test_pkg").mkdir(parents=True)
        (tmp_path / "src" / "test_pkg" / "__init__.py").write_text("", encoding="utf-8")

        # Create issue template with {owner}/{repo} placeholders
        issue_template_dir = tmp_path / ".github" / "ISSUE_TEMPLATE"
        issue_template_dir.mkdir(parents=True)
        config_yml = issue_template_dir / "config.yml"
        config_yml.write_text(
            "contact_links:\n  - url: https://github.com/{owner}/{repo}/discussions\n",
            encoding="utf-8",
        )

        import os

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            # Mock Path.unlink to prevent configure.py self-destruct
            with patch.object(Path, "unlink"):
                result = run_configure(
                    auto=True,
                    yes=True,
                    defaults={
                        "project_name": "Test Project",
                        "package_name": "test_pkg",
                        "pypi_name": "test-pkg",
                        "description": "A test project",
                        "author_name": "Test Author",
                        "author_email": "test@example.com",
                        "github_user": "testuser",
                    },
                )
            assert result == 0

            # Verify {owner} and {repo} were replaced
            content = config_yml.read_text(encoding="utf-8")
            assert "{owner}" not in content
            assert "{repo}" not in content
            assert "testuser" in content
            assert "test_pkg" in content
        finally:
            os.chdir(old_cwd)

    def test_run_configure_replaces_security_email(self, tmp_path: Path) -> None:
        """Test that security@example.com placeholder is replaced."""
        from tools.pyproject_template.configure import run_configure

        # Create minimal project structure
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"', encoding="utf-8")
        (tmp_path / "src" / "test_pkg").mkdir(parents=True)
        (tmp_path / "src" / "test_pkg" / "__init__.py").write_text("", encoding="utf-8")

        # Create SECURITY.md with placeholder email
        github_dir = tmp_path / ".github"
        github_dir.mkdir(parents=True)
        security_md = github_dir / "SECURITY.md"
        security_md.write_text("Contact: security@example.com\n", encoding="utf-8")

        import os

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            # Mock Path.unlink to prevent configure.py self-destruct
            with patch.object(Path, "unlink"):
                result = run_configure(
                    auto=True,
                    yes=True,
                    defaults={
                        "project_name": "Test Project",
                        "package_name": "test_pkg",
                        "pypi_name": "test-pkg",
                        "description": "A test project",
                        "author_name": "Test Author",
                        "author_email": "author@myproject.com",
                        "github_user": "testuser",
                    },
                )
            assert result == 0

            # Verify security@example.com was replaced
            content = security_md.read_text(encoding="utf-8")
            assert "security@example.com" not in content
            assert "author@myproject.com" in content
        finally:
            os.chdir(old_cwd)

    def test_run_configure_replaces_insert_contact_email(self, tmp_path: Path) -> None:
        """Test that [INSERT CONTACT EMAIL] placeholder is replaced."""
        from tools.pyproject_template.configure import run_configure

        # Create minimal project structure
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"', encoding="utf-8")
        (tmp_path / "src" / "test_pkg").mkdir(parents=True)
        (tmp_path / "src" / "test_pkg" / "__init__.py").write_text("", encoding="utf-8")

        # Create CODE_OF_CONDUCT.md with placeholder
        github_dir = tmp_path / ".github"
        github_dir.mkdir(parents=True)
        coc_md = github_dir / "CODE_OF_CONDUCT.md"
        coc_md.write_text("Report issues to [INSERT CONTACT EMAIL].\n", encoding="utf-8")

        import os

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            # Mock Path.unlink to prevent configure.py self-destruct
            with patch.object(Path, "unlink"):
                result = run_configure(
                    auto=True,
                    yes=True,
                    defaults={
                        "project_name": "Test Project",
                        "package_name": "test_pkg",
                        "pypi_name": "test-pkg",
                        "description": "A test project",
                        "author_name": "Test Author",
                        "author_email": "contact@myproject.com",
                        "github_user": "testuser",
                    },
                )
            assert result == 0

            # Verify [INSERT CONTACT EMAIL] was replaced
            content = coc_md.read_text(encoding="utf-8")
            assert "[INSERT CONTACT EMAIL]" not in content
            assert "contact@myproject.com" in content
        finally:
            os.chdir(old_cwd)

    def test_run_configure_replaces_mkdocs_placeholders(self, tmp_path: Path) -> None:
        """Test that mkdocs.yml placeholders (GitHub Pages URL, repo_name) are replaced."""
        from tools.pyproject_template.configure import run_configure

        # Create minimal project structure
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"', encoding="utf-8")
        (tmp_path / "src" / "test_pkg").mkdir(parents=True)
        (tmp_path / "src" / "test_pkg" / "__init__.py").write_text("", encoding="utf-8")

        # Create mkdocs.yml with placeholders
        mkdocs_yml = tmp_path / "mkdocs.yml"
        mkdocs_yml.write_text(
            "site_url: https://username.github.io/package_name\nrepo_name: username/package_name\n",
            encoding="utf-8",
        )

        import os

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            # Mock Path.unlink to prevent configure.py self-destruct
            with patch.object(Path, "unlink"):
                result = run_configure(
                    auto=True,
                    yes=True,
                    defaults={
                        "project_name": "Test Project",
                        "package_name": "test_pkg",
                        "pypi_name": "test-pkg",
                        "description": "A test project",
                        "author_name": "Test Author",
                        "author_email": "test@example.com",
                        "github_user": "myuser",
                    },
                )
            assert result == 0

            # Verify mkdocs.yml placeholders were replaced
            content = mkdocs_yml.read_text(encoding="utf-8")
            assert "username.github.io" not in content
            assert "https://myuser.github.io/test_pkg" in content
            assert "username/package_name" not in content
            assert "myuser/test_pkg" in content
        finally:
            os.chdir(old_cwd)

    def test_run_configure_removes_template_tests_directory(self, tmp_path: Path) -> None:
        """Test that tests/template/ is removed during configure."""
        from tools.pyproject_template.configure import run_configure

        # Create minimal project structure
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"', encoding="utf-8")
        (tmp_path / "src" / "test_pkg").mkdir(parents=True)
        (tmp_path / "src" / "test_pkg" / "__init__.py").write_text("", encoding="utf-8")

        # Create template-only tests directory that should be removed
        template_tests_dir = tmp_path / "tests" / "template"
        template_tests_dir.mkdir(parents=True)
        (template_tests_dir / "__init__.py").write_text("", encoding="utf-8")
        (template_tests_dir / "test_utils.py").write_text("# test file", encoding="utf-8")

        import os

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            # Mock Path.unlink to prevent configure.py self-destruct
            with patch.object(Path, "unlink"):
                result = run_configure(
                    auto=True,
                    yes=True,
                    defaults={
                        "project_name": "Test Project",
                        "package_name": "test_pkg",
                        "pypi_name": "test-pkg",
                        "description": "A test project",
                        "author_name": "Test Author",
                        "author_email": "test@example.com",
                        "github_user": "testuser",
                    },
                )
            assert result == 0

            # Verify template-only tests directory was removed
            assert not template_tests_dir.exists()
            # But tests directory itself should still exist
            assert (tmp_path / "tests").exists()
        finally:
            os.chdir(old_cwd)


class TestSeedBaselineTag:
    """Tests for ``seed_baseline_tag`` (issue #447).

    Exercises the auto-seed of ``v0.0.0`` on the bootstrap root commit. The
    function powers the fix for the papercut introduced by the ``--prerelease``
    guard from issue #448: without a baseline tag, cz bump refuses to compute
    a pre-release on a fresh repo.
    """

    @staticmethod
    def _init_repo(repo: Path) -> str:
        """Initialize a git repo in ``repo`` with one empty root commit.

        Returns the SHA of the root commit.
        """
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "root", "--no-verify"],
            cwd=repo,
            check=True,
            capture_output=True,
            env=env,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    @staticmethod
    def _list_tags(repo: Path) -> list[str]:
        result = subprocess.run(
            ["git", "tag", "--list"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def test_no_tags_creates_v0_0_0_on_root_commit(self, tmp_path: Path) -> None:
        """With no existing v* tags, seed_baseline_tag creates v0.0.0 on the root commit."""
        from tools.pyproject_template.configure import seed_baseline_tag

        root_sha = self._init_repo(tmp_path)

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            seed_baseline_tag()

            assert self._list_tags(tmp_path) == ["v0.0.0"]

            # Verify the tag points at the root commit
            tagged_sha = subprocess.run(
                ["git", "rev-list", "-n", "1", "v0.0.0"],
                cwd=tmp_path,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            assert tagged_sha == root_sha
        finally:
            os.chdir(old_cwd)

    def test_existing_version_tag_is_preserved(self, tmp_path: Path) -> None:
        """When a v* tag already exists, seed_baseline_tag is a no-op (idempotent)."""
        from tools.pyproject_template.configure import seed_baseline_tag

        self._init_repo(tmp_path)
        subprocess.run(
            ["git", "tag", "v0.1.0"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            seed_baseline_tag()

            # v0.1.0 preserved, v0.0.0 NOT added.
            assert self._list_tags(tmp_path) == ["v0.1.0"]
        finally:
            os.chdir(old_cwd)

    def test_not_a_git_repo_is_safe_no_op(self, tmp_path: Path) -> None:
        """Outside a git repo, seed_baseline_tag skips without raising."""
        from tools.pyproject_template.configure import seed_baseline_tag

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            seed_baseline_tag()  # Must not raise.
            # No .git, no tags, nothing to observe — just reaching this line
            # proves the function returned cleanly.
            assert not (tmp_path / ".git").exists()
        finally:
            os.chdir(old_cwd)


class TestCheckUpdatesModule:
    """Tests for the check_template_updates module refactoring."""

    def test_parse_args_accepts_argv(self) -> None:
        """Test that parse_args accepts argv parameter."""
        from tools.pyproject_template.check_template_updates import parse_args

        args = parse_args(["--skip-changelog", "--keep-template"])
        assert args.skip_changelog is True
        assert args.keep_template is True

    def test_parse_args_dry_run(self) -> None:
        """Test that parse_args accepts --dry-run."""
        from tools.pyproject_template.check_template_updates import parse_args

        args = parse_args(["--dry-run"])
        assert args.dry_run is True


class TestYesFlagBehavior:
    """Tests for --yes flag threading through subcommands."""

    def test_yes_flag_passed_to_run_action(self) -> None:
        """Verify main(["--yes", "sync"]) passes yes=True through to run_action."""
        from tools.pyproject_template.manage import main

        with (
            patch("tools.pyproject_template.manage.SettingsManager") as mock_manager_cls,
            patch("tools.pyproject_template.manage.run_action", return_value=0) as mock_run_action,
        ):
            mock_manager = MagicMock()
            mock_manager_cls.return_value = mock_manager

            main(["--yes", "sync"])

            mock_run_action.assert_called_once_with(
                5, mock_manager, False, yes=True, cleanup_mode=None
            )

    def test_sync_with_yes_skips_prompt(self, tmp_path: Path) -> None:
        """Verify action_mark_synced() with yes=True skips the confirmation prompt."""
        from tools.pyproject_template.manage import action_mark_synced

        # Set up template commit file
        template_dir = tmp_path / "tmp" / "extracted" / "pyproject-template-main"
        template_dir.mkdir(parents=True)
        commit_file = template_dir / ".template_commit"
        commit_file.write_text("abc123newcommit\n2025-06-15\n", encoding="utf-8")

        mock_manager = MagicMock()
        mock_manager.template_state.commit = "oldcommit000"

        with (
            patch("tools.pyproject_template.manage.Path") as mock_path_cls,
            patch("tools.pyproject_template.manage.prompt") as mock_prompt,
            patch("subprocess.run") as mock_subprocess,
        ):
            # Make Path("tmp/extracted/...") resolve to our tmp_path
            def path_side_effect(arg: str = "") -> Path:
                if arg == "tmp/extracted/pyproject-template-main":
                    return template_dir
                return Path(arg)

            mock_path_cls.side_effect = path_side_effect

            # subprocess calls succeed
            mock_subprocess.return_value = MagicMock(returncode=0)

            action_mark_synced(mock_manager, dry_run=False, yes=True)

            # prompt should NOT have been called
            mock_prompt.assert_not_called()
            # update_template_state should have been called
            mock_manager.update_template_state.assert_called_once_with(
                "abc123newcommit", "2025-06-15"
            )

    def test_cleanup_with_yes_skips_prompt(self) -> None:
        """Verify action_template_cleanup() with yes=True skips prompt_cleanup."""
        from tools.pyproject_template.manage import action_template_cleanup

        mock_manager = MagicMock()

        with patch("tools.pyproject_template.manage.prompt_cleanup") as mock_prompt_cleanup:
            result = action_template_cleanup(mock_manager, dry_run=False, yes=True)

            assert result == 0
            mock_prompt_cleanup.assert_not_called()

    def test_configure_with_yes_uses_auto_mode(self) -> None:
        """Verify action_configure() with yes=True calls run_configure with auto=True."""
        from tools.pyproject_template.manage import action_configure

        mock_manager = MagicMock()
        mock_manager.settings.project_name = "test"
        mock_manager.settings.package_name = "test"
        mock_manager.settings.pypi_name = "test"
        mock_manager.settings.description = "test"
        mock_manager.settings.author_name = "test"
        mock_manager.settings.author_email = "test@test.com"
        mock_manager.settings.github_user = "test"

        with (
            patch("tools.pyproject_template.manage.run_configure", return_value=0) as mock_run,
            patch("tools.pyproject_template.manage.load_defaults", return_value={}),
        ):
            result = action_configure(mock_manager, dry_run=False, yes=True)

            assert result == 0
            mock_run.assert_called_once()
            _, kwargs = mock_run.call_args
            assert kwargs["auto"] is True
            assert kwargs["yes"] is True

    def test_cleanup_with_cleanup_mode_setup(self) -> None:
        """Verify action_template_cleanup() with cleanup_mode='setup' uses that mode."""
        from tools.pyproject_template.manage import action_template_cleanup

        mock_manager = MagicMock()

        with (
            patch("tools.pyproject_template.manage.cleanup_template_files") as mock_cleanup,
            patch("tools.pyproject_template.manage.prompt_cleanup"),
        ):
            mock_result = MagicMock()
            mock_result.failed = []
            mock_cleanup.return_value = mock_result

            result = action_template_cleanup(mock_manager, dry_run=False, cleanup_mode="setup")

            assert result == 0
            mock_cleanup.assert_called_once()

    def test_cleanup_with_invalid_mode_fails(self) -> None:
        """Verify action_template_cleanup() with invalid cleanup_mode returns error."""
        from tools.pyproject_template.manage import action_template_cleanup

        mock_manager = MagicMock()

        with patch("tools.pyproject_template.manage.prompt_cleanup"):
            result = action_template_cleanup(mock_manager, dry_run=False, cleanup_mode="invalid")

            assert result == 1


class TestMigrateModule:
    """Tests for the migrate_existing_project module refactoring."""

    def test_parse_args_accepts_argv(self) -> None:
        """Test that parse_args accepts argv parameter."""
        from tools.pyproject_template.migrate_existing_project import parse_args

        args = parse_args(["--target", "/some/path", "--download"])
        assert args.target == Path("/some/path")
        assert args.download is True

    def test_parse_args_dry_run(self) -> None:
        """Test that parse_args accepts --dry-run."""
        from tools.pyproject_template.migrate_existing_project import parse_args

        args = parse_args(["--target", "/some/path", "--dry-run"])
        assert args.dry_run is True
