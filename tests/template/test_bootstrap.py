"""Tests for bootstrap.py setup and sync functionality."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bootstrap import (
    SETUP_FILES,
    SYNC_FILES,
    create_settings_file,
    detect_project_settings,
    download_file,
    parse_args,
)


class TestConstants:
    """Tests for file list constants."""

    def test_setup_files_contains_required_modules(self) -> None:
        """Test that SETUP_FILES contains all required setup modules."""
        filenames = [Path(f).name for f in SETUP_FILES]
        assert "__init__.py" in filenames
        assert "utils.py" in filenames
        assert "setup_repo.py" in filenames
        assert "configure.py" in filenames

    def test_sync_files_contains_required_modules(self) -> None:
        """Test that SYNC_FILES contains all required management modules."""
        filenames = [Path(f).name for f in SYNC_FILES]
        assert "__init__.py" in filenames
        assert "utils.py" in filenames
        assert "settings.py" in filenames
        assert "check_template_updates.py" in filenames
        assert "manage.py" in filenames
        assert "configure.py" in filenames
        assert "cleanup.py" in filenames

    def test_sync_files_does_not_contain_setup_only_modules(self) -> None:
        """Test that SYNC_FILES excludes setup-only modules."""
        filenames = [Path(f).name for f in SYNC_FILES]
        assert "setup_repo.py" not in filenames
        assert "repo_settings.py" not in filenames
        assert "migrate_existing_project.py" not in filenames

    def test_setup_files_does_not_contain_sync_only_modules(self) -> None:
        """Test that SETUP_FILES excludes sync-only modules."""
        filenames = [Path(f).name for f in SETUP_FILES]
        assert "settings.py" not in filenames
        assert "check_template_updates.py" not in filenames
        assert "manage.py" not in filenames


class TestParseArgs:
    """Tests for argument parsing."""

    def test_no_args_defaults_to_setup_mode(self) -> None:
        """Test that no arguments means sync=False (setup mode)."""
        args = parse_args([])
        assert args.sync is False

    def test_sync_flag(self) -> None:
        """Test that --sync flag is parsed correctly."""
        args = parse_args(["--sync"])
        assert args.sync is True


class TestDownloadFile:
    """Tests for download_file function."""

    def test_download_file_writes_content(self, tmp_path: Path) -> None:
        """Test that download_file writes fetched content to disk."""
        dest = tmp_path / "test.py"
        mock_response = MagicMock()
        mock_response.read.return_value = b"print('hello')"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("bootstrap.urllib.request.urlopen", return_value=mock_response):
            download_file("https://example.com/test.py", dest)

        assert dest.read_text(encoding="utf-8") == "print('hello')"

    def test_download_file_exits_on_error(self, tmp_path: Path) -> None:
        """Test that download_file exits on network error."""
        dest = tmp_path / "test.py"

        with (
            patch("bootstrap.urllib.request.urlopen", side_effect=Exception("Network error")),
            pytest.raises(SystemExit),
        ):
            download_file("https://example.com/test.py", dest)


class TestDetectProjectSettings:
    """Tests for detect_project_settings function."""

    def test_returns_empty_when_no_pyproject(self, tmp_path: Path) -> None:
        """Test that missing pyproject.toml returns empty settings."""
        result = detect_project_settings(tmp_path)
        assert result == {}

    def test_detects_project_name(self, tmp_path: Path) -> None:
        """Test that project name is detected from pyproject.toml."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "my-cool-project"\n', encoding="utf-8")

        result = detect_project_settings(tmp_path)
        assert result["project_name"] == "my-cool-project"
        assert result["package_name"] == "my_cool_project"
        assert result["pypi_name"] == "my-cool-project"

    def test_detects_description(self, tmp_path: Path) -> None:
        """Test that description is detected."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "test"\ndescription = "A test project"\n', encoding="utf-8"
        )

        result = detect_project_settings(tmp_path)
        assert result["description"] == "A test project"

    def test_detects_author_info(self, tmp_path: Path) -> None:
        """Test that author name and email are detected."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "test"\n'
            '[[project.authors]]\nname = "John Doe"\nemail = "john@example.com"\n',
            encoding="utf-8",
        )

        result = detect_project_settings(tmp_path)
        assert result["author_name"] == "John Doe"
        assert result["author_email"] == "john@example.com"

    def test_detects_github_from_urls(self, tmp_path: Path) -> None:
        """Test that GitHub user/repo are parsed from repository URL."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "test"\n'
            '[project.urls]\nRepository = "https://github.com/myuser/myrepo"\n',
            encoding="utf-8",
        )

        result = detect_project_settings(tmp_path)
        assert result["github_user"] == "myuser"
        assert result["github_repo"] == "myrepo"

    def test_strips_git_suffix_from_repo_url(self, tmp_path: Path) -> None:
        """Test that .git suffix is removed from repository URL."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "test"\n'
            '[project.urls]\nRepository = "https://github.com/user/repo.git"\n',
            encoding="utf-8",
        )

        result = detect_project_settings(tmp_path)
        assert result["github_repo"] == "repo"

    def test_handles_malformed_pyproject(self, tmp_path: Path) -> None:
        """Test that malformed pyproject.toml doesn't crash."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("this is not valid toml [[[", encoding="utf-8")

        result = detect_project_settings(tmp_path)
        assert result == {}

    def test_handles_empty_project_section(self, tmp_path: Path) -> None:
        """Test that empty [project] section returns empty settings."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("[project]\n", encoding="utf-8")

        result = detect_project_settings(tmp_path)
        assert result == {}

    def test_rejects_non_github_url_with_github_in_path(self, tmp_path: Path) -> None:
        """Test that URLs with github.com in path (not host) are rejected."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "test"\n'
            '[project.urls]\nRepository = "https://evil.com/github.com/user/repo"\n',
            encoding="utf-8",
        )

        result = detect_project_settings(tmp_path)
        assert "github_user" not in result
        assert "github_repo" not in result

    def test_accepts_github_subdomain(self, tmp_path: Path) -> None:
        """Test that GitHub subdomain URLs are accepted."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "test"\n'
            '[project.urls]\nRepository = "https://www.github.com/myuser/myrepo"\n',
            encoding="utf-8",
        )

        result = detect_project_settings(tmp_path)
        assert result["github_user"] == "myuser"
        assert result["github_repo"] == "myrepo"

    def test_underscore_name_converted_to_hyphen_for_pypi(self, tmp_path: Path) -> None:
        """Test that underscores in name become hyphens for pypi_name."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "my_project"\n', encoding="utf-8")

        result = detect_project_settings(tmp_path)
        assert result["pypi_name"] == "my-project"
        assert result["package_name"] == "my_project"


class TestCreateSettingsFile:
    """Tests for create_settings_file function."""

    def test_creates_directory_structure(self, tmp_path: Path) -> None:
        """Test that parent directories are created."""
        create_settings_file(tmp_path, {})

        settings_dir = tmp_path / ".config" / "pyproject_template"
        assert settings_dir.exists()

    def test_creates_settings_file(self, tmp_path: Path) -> None:
        """Test that settings.toml is created."""
        result = create_settings_file(tmp_path, {})

        assert result.exists()
        assert result.name == "settings.toml"

    def test_writes_project_section(self, tmp_path: Path) -> None:
        """Test that [project] section is written with settings."""
        settings = {
            "project_name": "my-project",
            "package_name": "my_project",
            "github_user": "testuser",
        }
        result = create_settings_file(tmp_path, settings)

        content = result.read_text(encoding="utf-8")
        assert "[project]" in content
        assert 'project_name = "my-project"' in content
        assert 'package_name = "my_project"' in content
        assert 'github_user = "testuser"' in content

    def test_writes_template_section(self, tmp_path: Path) -> None:
        """Test that [template] section is written with empty values."""
        result = create_settings_file(tmp_path, {})

        content = result.read_text(encoding="utf-8")
        assert "[template]" in content
        assert 'commit = ""' in content
        assert 'commit_date = ""' in content

    def test_empty_settings_writes_empty_strings(self, tmp_path: Path) -> None:
        """Test that missing settings are written as empty strings."""
        result = create_settings_file(tmp_path, {})

        content = result.read_text(encoding="utf-8")
        assert 'project_name = ""' in content
        assert 'author_email = ""' in content

    def test_escapes_special_characters(self, tmp_path: Path) -> None:
        """Test that special characters in values are escaped."""
        settings = {"description": 'A "quoted" project\\path'}
        result = create_settings_file(tmp_path, settings)

        content = result.read_text(encoding="utf-8")
        assert 'description = "A \\"quoted\\" project\\\\path"' in content

    def test_returns_path_to_created_file(self, tmp_path: Path) -> None:
        """Test that the returned path points to the created file."""
        result = create_settings_file(tmp_path, {"project_name": "test"})

        expected = tmp_path / ".config" / "pyproject_template" / "settings.toml"
        assert result == expected


class TestRunSync:
    """Tests for run_sync function."""

    def test_creates_tools_directory(self, tmp_path: Path) -> None:
        """Test that tools/pyproject_template/ is created."""
        from bootstrap import run_sync

        mock_response = MagicMock()
        mock_response.read.return_value = b"# file content"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with (
            patch("bootstrap.urllib.request.urlopen", return_value=mock_response),
            patch("subprocess.run") as mock_subprocess,
        ):
            mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
            run_sync(tmp_path)

        pkg_dir = tmp_path / "tools" / "pyproject_template"
        assert pkg_dir.exists()

    def test_downloads_all_sync_files(self, tmp_path: Path) -> None:
        """Test that all SYNC_FILES are downloaded."""
        from bootstrap import run_sync

        downloaded_urls: list[str] = []

        mock_response = MagicMock()
        mock_response.read.return_value = b"# content"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        def track_downloads(url: str) -> MagicMock:
            downloaded_urls.append(url)
            return mock_response

        with (
            patch("bootstrap.urllib.request.urlopen", side_effect=track_downloads),
            patch("subprocess.run") as mock_subprocess,
        ):
            mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
            run_sync(tmp_path)

        # Verify each sync file was downloaded
        for file_path in SYNC_FILES:
            filename = Path(file_path).name
            expected_url_suffix = f"/{file_path}"
            assert any(url.endswith(expected_url_suffix) for url in downloaded_urls), (
                f"{filename} was not downloaded"
            )

    def test_prompts_if_already_installed(self, tmp_path: Path) -> None:
        """Test that existing installation prompts for confirmation."""
        from bootstrap import run_sync

        pkg_dir = tmp_path / "tools" / "pyproject_template"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "manage.py").write_text("# existing", encoding="utf-8")

        with (
            patch("builtins.input", return_value="n"),
            pytest.raises(SystemExit) as exc_info,
        ):
            run_sync(tmp_path)

        assert exc_info.value.code == 0

    def test_overwrites_if_confirmed(self, tmp_path: Path) -> None:
        """Test that existing installation is overwritten when confirmed."""
        from bootstrap import run_sync

        pkg_dir = tmp_path / "tools" / "pyproject_template"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "manage.py").write_text("# old", encoding="utf-8")

        mock_response = MagicMock()
        mock_response.read.return_value = b"# new content"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with (
            patch("builtins.input", return_value="y"),
            patch("bootstrap.urllib.request.urlopen", return_value=mock_response),
            patch("subprocess.run") as mock_subprocess,
        ):
            mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
            run_sync(tmp_path)

        assert (pkg_dir / "manage.py").read_text(encoding="utf-8") == "# new content"

    def test_creates_settings_file(self, tmp_path: Path) -> None:
        """Test that settings.toml is created during sync."""
        from bootstrap import run_sync

        mock_response = MagicMock()
        mock_response.read.return_value = b"# content"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with (
            patch("bootstrap.urllib.request.urlopen", return_value=mock_response),
            patch("subprocess.run") as mock_subprocess,
        ):
            mock_subprocess.return_value = MagicMock(returncode=0, stderr="")
            run_sync(tmp_path)

        settings_path = tmp_path / ".config" / "pyproject_template" / "settings.toml"
        assert settings_path.exists()


class TestRunSetup:
    """Tests for run_setup function (original behavior)."""

    def test_downloads_setup_files_to_temp_dir(self) -> None:
        """Test that setup mode downloads SETUP_FILES to a temp directory."""
        from bootstrap import run_setup

        downloaded_urls: list[str] = []

        mock_response = MagicMock()
        mock_response.read.return_value = b"# content"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        def track_downloads(url: str) -> MagicMock:
            downloaded_urls.append(url)
            return mock_response

        with (
            patch("bootstrap.urllib.request.urlopen", side_effect=track_downloads),
            pytest.raises(SystemExit),
        ):
            run_setup()

        # Verify setup files were downloaded
        for file_path in SETUP_FILES:
            assert any(url.endswith(f"/{file_path}") for url in downloaded_urls), (
                f"{file_path} was not downloaded"
            )


class TestMain:
    """Tests for main entry point."""

    def test_sync_flag_calls_run_sync(self) -> None:
        """Test that --sync flag routes to run_sync."""
        from bootstrap import main

        with patch("bootstrap.run_sync") as mock_sync:
            main(["--sync"])
            mock_sync.assert_called_once()

    def test_no_flags_calls_run_setup(self) -> None:
        """Test that no flags routes to run_setup."""
        from bootstrap import main

        with patch("bootstrap.run_setup") as mock_setup:
            main([])
            mock_setup.assert_called_once()
