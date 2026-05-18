"""Tests for cleanup.py template file cleanup functionality."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


class TestCleanupMode:
    """Tests for CleanupMode enum."""

    def test_cleanup_mode_values(self) -> None:
        """Test that CleanupMode has expected values."""
        from tools.pyproject_template.cleanup import CleanupMode

        assert CleanupMode.SETUP_ONLY.value == "setup"
        assert CleanupMode.ALL.value == "all"


class TestGetFilesToDelete:
    """Tests for get_files_to_delete function."""

    def test_get_files_setup_only(self, tmp_path: Path) -> None:
        """Test get_files_to_delete returns setup files for SETUP_ONLY mode."""
        from tools.pyproject_template.cleanup import CleanupMode, get_files_to_delete

        # Create some setup files
        (tmp_path / "bootstrap.py").touch()
        tools_dir = tmp_path / "tools" / "pyproject_template"
        tools_dir.mkdir(parents=True)
        (tools_dir / "setup_repo.py").touch()
        (tools_dir / "migrate_existing_project.py").touch()
        # This one should NOT be deleted in SETUP_ONLY mode
        (tools_dir / "manage.py").touch()

        files = get_files_to_delete(CleanupMode.SETUP_ONLY, tmp_path)

        file_names = [f.name for f in files]
        assert "bootstrap.py" in file_names
        assert "setup_repo.py" in file_names
        assert "migrate_existing_project.py" in file_names
        assert "manage.py" not in file_names

    def test_get_files_all(self, tmp_path: Path) -> None:
        """Test get_files_to_delete returns all template files for ALL mode."""
        from tools.pyproject_template.cleanup import CleanupMode, get_files_to_delete

        # Create template files
        (tmp_path / "bootstrap.py").touch()
        tools_dir = tmp_path / "tools" / "pyproject_template"
        tools_dir.mkdir(parents=True)
        (tools_dir / "setup_repo.py").touch()
        (tools_dir / "manage.py").touch()
        (tools_dir / "cleanup.py").touch()

        files = get_files_to_delete(CleanupMode.ALL, tmp_path)

        file_names = [f.name for f in files]
        assert "bootstrap.py" in file_names
        assert "setup_repo.py" in file_names
        assert "manage.py" in file_names
        assert "cleanup.py" in file_names

    def test_get_files_nonexistent(self, tmp_path: Path) -> None:
        """Test get_files_to_delete returns empty list when no files exist."""
        from tools.pyproject_template.cleanup import CleanupMode, get_files_to_delete

        files = get_files_to_delete(CleanupMode.SETUP_ONLY, tmp_path)
        assert files == []


class TestGetDirsToDelete:
    """Tests for get_dirs_to_delete function."""

    def test_get_dirs_setup_only(self, tmp_path: Path) -> None:
        """Test get_dirs_to_delete returns empty for SETUP_ONLY mode."""
        from tools.pyproject_template.cleanup import CleanupMode, get_dirs_to_delete

        # Create directories
        (tmp_path / "tools" / "pyproject_template").mkdir(parents=True)

        dirs = get_dirs_to_delete(CleanupMode.SETUP_ONLY, tmp_path)
        assert dirs == []

    def test_get_dirs_all(self, tmp_path: Path) -> None:
        """Test get_dirs_to_delete returns directories for ALL mode."""
        from tools.pyproject_template.cleanup import CleanupMode, get_dirs_to_delete

        # Create directories
        (tmp_path / "tools" / "pyproject_template").mkdir(parents=True)
        (tmp_path / "docs" / "template").mkdir(parents=True)
        (tmp_path / ".config" / "pyproject_template").mkdir(parents=True)

        dirs = get_dirs_to_delete(CleanupMode.ALL, tmp_path)

        dir_names = [d.name for d in dirs]
        assert "pyproject_template" in dir_names


class TestUpdateMkdocsNav:
    """Tests for update_mkdocs_nav function."""

    def test_update_mkdocs_nav_removes_template_section(self, tmp_path: Path) -> None:
        """Test that Template section is removed from mkdocs.yml."""
        from tools.pyproject_template.cleanup import update_mkdocs_nav

        mkdocs_content = """\
nav:
  - Home: index.md
  - Template:
      - Overview: template/index.md
      - Manager: template/manage.md
  - Development:
      - Setup: development/setup.md
"""
        mkdocs_file = tmp_path / "mkdocs.yml"
        mkdocs_file.write_text(mkdocs_content, encoding="utf-8")

        result = update_mkdocs_nav(tmp_path, dry_run=False)

        assert result is True
        new_content = mkdocs_file.read_text(encoding="utf-8")
        assert "Template:" not in new_content
        assert "template/index.md" not in new_content
        assert "Development:" in new_content

    def test_update_mkdocs_nav_no_template_section(self, tmp_path: Path) -> None:
        """Test update_mkdocs_nav when no Template section exists."""
        from tools.pyproject_template.cleanup import update_mkdocs_nav

        mkdocs_content = """\
nav:
  - Home: index.md
  - Development:
      - Setup: development/setup.md
"""
        mkdocs_file = tmp_path / "mkdocs.yml"
        mkdocs_file.write_text(mkdocs_content, encoding="utf-8")

        result = update_mkdocs_nav(tmp_path, dry_run=False)
        assert result is False

    def test_update_mkdocs_nav_dry_run(self, tmp_path: Path) -> None:
        """Test update_mkdocs_nav dry run doesn't modify file."""
        from tools.pyproject_template.cleanup import update_mkdocs_nav

        mkdocs_content = """\
nav:
  - Home: index.md
  - Template:
      - Overview: template/index.md
"""
        mkdocs_file = tmp_path / "mkdocs.yml"
        mkdocs_file.write_text(mkdocs_content, encoding="utf-8")

        result = update_mkdocs_nav(tmp_path, dry_run=True)

        assert result is True
        # Content should be unchanged
        assert mkdocs_file.read_text(encoding="utf-8") == mkdocs_content

    def test_update_mkdocs_nav_no_file(self, tmp_path: Path) -> None:
        """Test update_mkdocs_nav when mkdocs.yml doesn't exist."""
        from tools.pyproject_template.cleanup import update_mkdocs_nav

        result = update_mkdocs_nav(tmp_path, dry_run=False)
        assert result is False


class TestCleanupTemplateFiles:
    """Tests for cleanup_template_files function."""

    def test_cleanup_setup_only(self, tmp_path: Path) -> None:
        """Test cleanup in SETUP_ONLY mode deletes only setup files."""
        from tools.pyproject_template.cleanup import (
            CleanupMode,
            cleanup_template_files,
        )

        # Create files
        (tmp_path / "bootstrap.py").touch()
        tools_dir = tmp_path / "tools" / "pyproject_template"
        tools_dir.mkdir(parents=True)
        (tools_dir / "setup_repo.py").touch()
        (tools_dir / "manage.py").touch()  # Should NOT be deleted

        result = cleanup_template_files(CleanupMode.SETUP_ONLY, tmp_path)

        assert not (tmp_path / "bootstrap.py").exists()
        assert not (tools_dir / "setup_repo.py").exists()
        assert (tools_dir / "manage.py").exists()  # Should still exist
        assert len(result.deleted_files) >= 2
        assert len(result.deleted_dirs) == 0

    def test_cleanup_all(self, tmp_path: Path) -> None:
        """Test cleanup in ALL mode deletes all template files and directories."""
        from tools.pyproject_template.cleanup import (
            CleanupMode,
            cleanup_template_files,
        )

        # Create files and directories
        (tmp_path / "bootstrap.py").touch()
        tools_dir = tmp_path / "tools" / "pyproject_template"
        tools_dir.mkdir(parents=True)
        (tools_dir / "setup_repo.py").touch()
        (tools_dir / "manage.py").touch()
        (tools_dir / "__init__.py").touch()

        # Create mkdocs.yml with Template section
        mkdocs_content = """\
nav:
  - Home: index.md
  - Template:
      - Overview: template/index.md
"""
        (tmp_path / "mkdocs.yml").write_text(mkdocs_content, encoding="utf-8")

        result = cleanup_template_files(CleanupMode.ALL, tmp_path)

        assert not (tmp_path / "bootstrap.py").exists()
        assert not tools_dir.exists()
        assert result.mkdocs_updated is True

    def test_cleanup_dry_run(self, tmp_path: Path) -> None:
        """Test cleanup dry run doesn't delete files."""
        from tools.pyproject_template.cleanup import (
            CleanupMode,
            cleanup_template_files,
        )

        # Create files
        bootstrap = tmp_path / "bootstrap.py"
        bootstrap.touch()

        result = cleanup_template_files(CleanupMode.SETUP_ONLY, tmp_path, dry_run=True)

        # File should still exist
        assert bootstrap.exists()
        # But should be in the list of files that would be deleted
        assert any(f.name == "bootstrap.py" for f in result.deleted_files)

    def test_cleanup_no_files(self, tmp_path: Path) -> None:
        """Test cleanup when no template files exist."""
        from tools.pyproject_template.cleanup import (
            CleanupMode,
            cleanup_template_files,
        )

        result = cleanup_template_files(CleanupMode.SETUP_ONLY, tmp_path)

        assert result.deleted_files == []
        assert result.deleted_dirs == []
        assert result.failed == []


class TestPromptCleanup:
    """Tests for prompt_cleanup function."""

    def test_prompt_cleanup_setup_only(self) -> None:
        """Test prompt_cleanup returns SETUP_ONLY for choice 1."""
        from tools.pyproject_template.cleanup import CleanupMode, prompt_cleanup

        with patch("builtins.input", return_value="1"):
            result = prompt_cleanup()
            assert result == CleanupMode.SETUP_ONLY

    def test_prompt_cleanup_all(self) -> None:
        """Test prompt_cleanup returns ALL for choice 2."""
        from tools.pyproject_template.cleanup import CleanupMode, prompt_cleanup

        with patch("builtins.input", return_value="2"):
            result = prompt_cleanup()
            assert result == CleanupMode.ALL

    def test_prompt_cleanup_keep(self) -> None:
        """Test prompt_cleanup returns None for choice 3."""
        from tools.pyproject_template.cleanup import prompt_cleanup

        with patch("builtins.input", return_value="3"):
            result = prompt_cleanup()
            assert result is None

    def test_prompt_cleanup_invalid_then_valid(self) -> None:
        """Test prompt_cleanup handles invalid input then valid."""
        from tools.pyproject_template.cleanup import CleanupMode, prompt_cleanup

        with patch("builtins.input", side_effect=["invalid", "1"]):
            result = prompt_cleanup()
            assert result == CleanupMode.SETUP_ONLY

    def test_prompt_cleanup_keyboard_interrupt(self) -> None:
        """Test prompt_cleanup handles keyboard interrupt."""
        from tools.pyproject_template.cleanup import prompt_cleanup

        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = prompt_cleanup()
            assert result is None


class TestMain:
    """Tests for main entry point."""

    def test_main_setup_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test main with --setup flag."""
        from tools.pyproject_template.cleanup import main

        monkeypatch.chdir(tmp_path)

        # Create a file to delete
        (tmp_path / "bootstrap.py").touch()

        with patch("sys.argv", ["cleanup.py", "--setup"]):
            result = main()
            assert result == 0

    def test_main_dry_run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test main with --dry-run flag."""
        from tools.pyproject_template.cleanup import main

        monkeypatch.chdir(tmp_path)

        # Create a file
        bootstrap = tmp_path / "bootstrap.py"
        bootstrap.touch()

        with patch("sys.argv", ["cleanup.py", "--setup", "--dry-run"]):
            result = main()
            assert result == 0
            assert bootstrap.exists()  # Should not be deleted

    def test_main_conflicting_flags(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test main with conflicting --setup and --all flags."""
        from tools.pyproject_template.cleanup import main

        monkeypatch.chdir(tmp_path)

        with patch("sys.argv", ["cleanup.py", "--setup", "--all"]):
            result = main()
            assert result == 1


class TestScrubTemplateReferences:
    """Tests for ``scrub_template_references``.

    Verifies each of the three target files gets cleaned up correctly and
    that the scrubber is idempotent. Addresses issue #469.
    """

    _PYPROJECT_WITH_STANZA = """\
[tool.mypy]
strict = true

[[tool.mypy.overrides]]
module = "doit.*"
ignore_missing_imports = true

[[tool.mypy.overrides]]
# Standalone scripts using sys.path manipulation; excluded from discovery
# but still followed via imports from bootstrap.py
module = "tools.pyproject_template.*"
follow_imports = "skip"

[tool.pytest.ini_options]
minversion = "8.0"
"""

    _PYPROJECT_WITHOUT_STANZA = """\
[tool.mypy]
strict = true

[[tool.mypy.overrides]]
module = "doit.*"
ignore_missing_imports = true

[tool.pytest.ini_options]
minversion = "8.0"
"""

    # Mirrors the pyproject.toml state that ``doit fmt_pyproject`` produces
    # before the scrubber runs in the wizard: mypy overrides are normalized
    # into an ``overrides = [...]`` inline array, and the mypy ``exclude``
    # brackets get space-padded. Exercises every new scrub pattern added for
    # the #469 follow-up in one realistic fixture.
    _PYPROJECT_POST_FMT_WITH_TEMPLATE_REFS = """\
[tool.ruff]
line-length = 100

lint.per-file-ignores."tests/benchmarks/*.py" = [
  "ANN401",
]
lint.per-file-ignores."tools/pyproject_template/*.py" = [
  "ANN401",
  "RUF022",
]

[tool.mypy]
strict = true
# tools/pyproject_template/ uses sys.path manipulation for standalone execution
exclude = [ "tools/pyproject_template/", ".claude/", ".gemini/", ".codex/" ]
overrides = [
  { module = "doit.*", ignore_missing_imports = true },
  # Standalone scripts using sys.path manipulation; excluded from discovery
  # but still followed via imports from bootstrap.py
  { module = "tools.pyproject_template.*", follow_imports = "skip" },
]

[tool.pytest.ini_options]
minversion = "8.0"
"""

    _README_WITH_TEMPLATE_SECTIONS = """\
# My Project

Intro text.

## Features

- feature one

## Quick Setup (Automated)

Stuff about bootstrap.py.

## Using This Template (Manual)

Manual instructions about tools/pyproject_template/configure.py.

## Development Setup

Dev instructions.
"""

    _README_WITHOUT_TEMPLATE_SECTIONS = """\
# My Project

Intro text.

## Features

- feature one

## Development Setup

Dev instructions.
"""

    _README_WITH_TEMPLATE_SUBSECTIONS = """\
# My Project

Intro text.

## Versioning & Releases

Commitizen + hatch-vcs.

### Migrating an Existing Project

Bring your existing Python project into this template:

```bash
python tools/pyproject_template/migrate_existing_project.py --target /path/to/your/project
```

### Keeping Up to Date

Already using this template? Stay in sync with improvements:

```bash
python tools/pyproject_template/check_template_updates.py
```

### Creating a Release

```bash
doit release
```
"""

    _DOIT_REF_WITH_TEMPLATE_CLEAN = """\
# Doit Tasks Reference

| Category | Commands | Purpose |
| --- | --- | --- |
| Setup | `install` | Install deps |
| Maintenance | `cleanup`, `template_clean` | Project cleanup |

## Testing Tasks

### `test`

Run tests.

### `template_clean`

Remove template-specific files after project setup.

```bash
doit template_clean --setup
```

**Setup mode (`--setup`)** removes:
- `bootstrap.py`

### `build`

Build the package.
"""

    _DOIT_REF_WITHOUT_TEMPLATE_CLEAN = """\
# Doit Tasks Reference

| Category | Commands | Purpose |
| --- | --- | --- |
| Setup | `install` | Install deps |
| Maintenance | `cleanup` | Project cleanup |

## Testing Tasks

### `test`

Run tests.

### `build`

Build the package.
"""

    # Mirrors the live ``docs/development/github-repository-settings.md`` intro
    # block (lines 14-22): an H1 heading, the three-sentence intro paragraph
    # with the broken ``repo_settings.py`` link in the middle, and the next
    # paragraph that points at the New Project Setup guide.
    _GITHUB_SETTINGS_WITH_TEMPLATE_REFS = """\
# GitHub Repository Settings

Complete reference for the GitHub repository settings this template expects.
New repositories created from the template are configured automatically by
[`repo_settings.py`](../../tools/pyproject_template/repo_settings.py) via
`update_all_repo_settings()`. This page documents what each setting is, why
it is needed, and whether it is set automatically or requires manual action.

For the initial setup workflow, see the [New Project Setup](../template/new-project.md) guide.

## Repository Settings

These are the general repository-level settings applied by
`configure_repository_settings()`.

| Setting | Value | Purpose |
| :--- | :--- | :--- |
| **Default branch** | `main` | Standard branch for PRs and CI |

## Security Settings

Security features are configured by `_configure_security_settings()` in
`repo_settings.py`.

| Setting | Status | Purpose |
| :--- | :--- | :--- |
| **Secret scanning** | Enabled | Detects accidentally committed secrets |
"""

    # Already-scrubbed equivalent of ``_GITHUB_SETTINGS_WITH_TEMPLATE_REFS``.
    # The intro paragraph collapses from three sentences to two (sentence 2 is
    # gone) and the Security Settings introductory paragraph is gone; the
    # surrounding heading and table sit directly together.
    _GITHUB_SETTINGS_WITHOUT_TEMPLATE_REFS = """\
# GitHub Repository Settings

Complete reference for the GitHub repository settings this template expects.
This page documents what each setting is, why
it is needed, and whether it is set automatically or requires manual action.

For the initial setup workflow, see the [New Project Setup](../template/new-project.md) guide.

## Repository Settings

These are the general repository-level settings applied by
`configure_repository_settings()`.

| Setting | Value | Purpose |
| :--- | :--- | :--- |
| **Default branch** | `main` | Standard branch for PRs and CI |

## Security Settings

| Setting | Status | Purpose |
| :--- | :--- | :--- |
| **Secret scanning** | Enabled | Detects accidentally committed secrets |
"""

    # Mirrors the live ``docs/development/release-and-automation.md`` block
    # (lines 88-109): the "Before your first pre-release" subsection plus the
    # full "New projects (bootstrap flow)" paragraph + code block, followed by
    # the still-correct "Existing projects" paragraph + code block.
    _RELEASE_AUTO_WITH_TEMPLATE_REFS = """\
### Before your first pre-release

`doit release --prerelease=alpha|beta|rc` requires a baseline `v*` tag so
commitizen has an anchor version to bump from.

**New projects (bootstrap flow).** `tools/pyproject_template/configure.py`
auto-seeds a `v0.0.0` tag on the root commit, so nothing else is required —
only push it when you're ready:

```bash
git push origin v0.0.0
```

**Existing projects (synced from the template before the auto-seed
landed).** Seed the baseline tag manually, once per project:

```bash
git tag v0.0.0 "$(git rev-list --max-parents=0 HEAD | head -1)"
git push origin v0.0.0
```
"""

    # Already-scrubbed equivalent of ``_RELEASE_AUTO_WITH_TEMPLATE_REFS``: the
    # broken ``configure.py`` link is gone but the lead, the "push it when
    # ready" instruction, and the trailing code block all survive.
    _RELEASE_AUTO_WITHOUT_TEMPLATE_REFS = """\
### Before your first pre-release

`doit release --prerelease=alpha|beta|rc` requires a baseline `v*` tag so
commitizen has an anchor version to bump from.

**New projects (bootstrap flow).** A `v0.0.0` tag is auto-seeded on the
root commit during initial setup, so nothing else is required — only push
it when you're ready:

```bash
git push origin v0.0.0
```

**Existing projects (synced from the template before the auto-seed
landed).** Seed the baseline tag manually, once per project:

```bash
git tag v0.0.0 "$(git rev-list --max-parents=0 HEAD | head -1)"
git push origin v0.0.0
```
"""

    def test_scrubs_pyproject_when_stanza_present(self, tmp_path: Path) -> None:
        """pyproject.toml stanza is removed when present."""
        from tools.pyproject_template.cleanup import scrub_template_references

        (tmp_path / "pyproject.toml").write_text(self._PYPROJECT_WITH_STANZA, encoding="utf-8")

        changed = scrub_template_references(tmp_path)

        new = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
        assert "tools.pyproject_template" not in new
        # The unrelated doit.* override must survive.
        assert 'module = "doit.*"' in new
        assert tmp_path / "pyproject.toml" in changed

    def test_pyproject_noop_when_stanza_absent(self, tmp_path: Path) -> None:
        """Already-scrubbed pyproject.toml is left unchanged."""
        from tools.pyproject_template.cleanup import scrub_template_references

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(self._PYPROJECT_WITHOUT_STANZA, encoding="utf-8")

        changed = scrub_template_references(tmp_path)

        assert pyproject not in changed
        assert pyproject.read_text(encoding="utf-8") == self._PYPROJECT_WITHOUT_STANZA

    def test_scrubs_readme_when_sections_present(self, tmp_path: Path) -> None:
        """Both template sections are removed; surrounding headings survive."""
        from tools.pyproject_template.cleanup import scrub_template_references

        readme = tmp_path / "README.md"
        readme.write_text(self._README_WITH_TEMPLATE_SECTIONS, encoding="utf-8")

        changed = scrub_template_references(tmp_path)

        new = readme.read_text(encoding="utf-8")
        assert "## Quick Setup (Automated)" not in new
        assert "## Using This Template (Manual)" not in new
        # Surrounding headings intact.
        assert "## Features" in new
        assert "## Development Setup" in new
        assert readme in changed

    def test_readme_noop_when_sections_absent(self, tmp_path: Path) -> None:
        """Already-scrubbed README.md is left unchanged."""
        from tools.pyproject_template.cleanup import scrub_template_references

        readme = tmp_path / "README.md"
        readme.write_text(self._README_WITHOUT_TEMPLATE_SECTIONS, encoding="utf-8")

        changed = scrub_template_references(tmp_path)

        assert readme not in changed
        assert readme.read_text(encoding="utf-8") == self._README_WITHOUT_TEMPLATE_SECTIONS

    def test_scrubs_doit_reference_section_and_toc(self, tmp_path: Path) -> None:
        """doit-tasks-reference.md section removed and TOC row rewritten."""
        from tools.pyproject_template.cleanup import scrub_template_references

        doit_ref = tmp_path / "docs" / "development" / "doit-tasks-reference.md"
        doit_ref.parent.mkdir(parents=True)
        doit_ref.write_text(self._DOIT_REF_WITH_TEMPLATE_CLEAN, encoding="utf-8")

        changed = scrub_template_references(tmp_path)

        new = doit_ref.read_text(encoding="utf-8")
        assert "template_clean" not in new
        # The TOC row is rewritten to list only ``cleanup``.
        assert "| Maintenance | `cleanup` | Project cleanup |" in new
        # The surrounding sections still exist.
        assert "### `test`" in new
        assert "### `build`" in new
        assert doit_ref in changed

    def test_doit_reference_noop_when_template_clean_absent(self, tmp_path: Path) -> None:
        """Already-scrubbed doit-tasks-reference.md is left unchanged."""
        from tools.pyproject_template.cleanup import scrub_template_references

        doit_ref = tmp_path / "docs" / "development" / "doit-tasks-reference.md"
        doit_ref.parent.mkdir(parents=True)
        doit_ref.write_text(self._DOIT_REF_WITHOUT_TEMPLATE_CLEAN, encoding="utf-8")

        changed = scrub_template_references(tmp_path)

        assert doit_ref not in changed
        assert doit_ref.read_text(encoding="utf-8") == self._DOIT_REF_WITHOUT_TEMPLATE_CLEAN

    def test_scrubs_pyproject_post_fmt_inline_overrides(self, tmp_path: Path) -> None:
        """Post-fmt inline-array mypy override is scrubbed (#469 follow-up).

        The wizard runs ``doit fmt_pyproject`` before cleanup, which rewrites
        the template's ``[[tool.mypy.overrides]]`` stanza form into an inline
        array entry — the original scrubber only matched the stanza form, so
        the reference survived into spawned projects.
        """
        from tools.pyproject_template.cleanup import scrub_template_references

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(self._PYPROJECT_POST_FMT_WITH_TEMPLATE_REFS, encoding="utf-8")

        changed = scrub_template_references(tmp_path)

        new = pyproject.read_text(encoding="utf-8")
        # Every mention of the template path is gone.
        assert "tools/pyproject_template" not in new
        assert "tools.pyproject_template" not in new
        # Unrelated overrides and excludes survive.
        assert 'module = "doit.*"' in new
        assert '".claude/"' in new
        assert '".gemini/"' in new
        assert '".codex/"' in new
        # The unrelated ruff per-file-ignores block survives.
        assert 'lint.per-file-ignores."tests/benchmarks/*.py"' in new
        assert pyproject in changed

    def test_scrubs_pyproject_ruff_perfile_ignores(self, tmp_path: Path) -> None:
        """Ruff ``per-file-ignores`` block for the template path is removed (#469 follow-up)."""
        from tools.pyproject_template.cleanup import scrub_template_references

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            'lint.per-file-ignores."tools/pyproject_template/*.py" = [\n'
            '  "ANN401",\n'
            '  "RUF022",\n'
            "]\n"
            "\n"
            "[tool.pytest.ini_options]\n"
            'minversion = "8.0"\n',
            encoding="utf-8",
        )

        changed = scrub_template_references(tmp_path)

        new = pyproject.read_text(encoding="utf-8")
        assert 'lint.per-file-ignores."tools/pyproject_template' not in new
        assert "[tool.pytest.ini_options]" in new
        assert pyproject in changed

    def test_scrubs_pyproject_mypy_exclude_entry_and_comment(self, tmp_path: Path) -> None:
        """Mypy ``exclude`` entry and its comment go; other excludes stay (#469 follow-up)."""
        from tools.pyproject_template.cleanup import scrub_template_references

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "[tool.mypy]\n"
            "strict = true\n"
            "# tools/pyproject_template/ uses sys.path manipulation for standalone execution\n"
            'exclude = [ "tools/pyproject_template/", ".claude/", ".gemini/", ".codex/" ]\n',
            encoding="utf-8",
        )

        changed = scrub_template_references(tmp_path)

        new = pyproject.read_text(encoding="utf-8")
        assert "tools/pyproject_template" not in new
        # The comment line is gone (it was specifically about the removed entry).
        assert "uses sys.path manipulation" not in new
        # The remaining AI-config excludes survive intact.
        assert '".claude/"' in new
        assert '".gemini/"' in new
        assert '".codex/"' in new
        assert pyproject in changed

    def test_scrubs_readme_template_subsections(self, tmp_path: Path) -> None:
        """README's ``### Migrating``/``### Keeping Up to Date`` are removed (#469 follow-up).

        Both subsections point at deleted template-management scripts; the
        preceding ``## Versioning & Releases`` heading and the following
        ``### Creating a Release`` subsection must survive.
        """
        from tools.pyproject_template.cleanup import scrub_template_references

        readme = tmp_path / "README.md"
        readme.write_text(self._README_WITH_TEMPLATE_SUBSECTIONS, encoding="utf-8")

        changed = scrub_template_references(tmp_path)

        new = readme.read_text(encoding="utf-8")
        assert "### Migrating an Existing Project" not in new
        assert "### Keeping Up to Date" not in new
        assert "migrate_existing_project.py" not in new
        assert "check_template_updates.py" not in new
        # Surrounding headings survive.
        assert "## Versioning & Releases" in new
        assert "### Creating a Release" in new
        assert readme in changed

    def test_scrub_is_idempotent(self, tmp_path: Path) -> None:
        """Running the scrubber twice must change nothing on the second pass."""
        from tools.pyproject_template.cleanup import scrub_template_references

        # Use the realistic post-``fmt_pyproject`` fixture so the idempotency
        # check exercises every new pattern introduced in the #469 follow-up.
        (tmp_path / "pyproject.toml").write_text(
            self._PYPROJECT_POST_FMT_WITH_TEMPLATE_REFS, encoding="utf-8"
        )
        # README gets both the top-level template sections AND the subsections
        # so the two README patterns are both exercised.
        (tmp_path / "README.md").write_text(
            self._README_WITH_TEMPLATE_SECTIONS + "\n" + self._README_WITH_TEMPLATE_SUBSECTIONS,
            encoding="utf-8",
        )
        doit_ref = tmp_path / "docs" / "development" / "doit-tasks-reference.md"
        doit_ref.parent.mkdir(parents=True)
        doit_ref.write_text(self._DOIT_REF_WITH_TEMPLATE_CLEAN, encoding="utf-8")

        # First pass: changes expected.
        first_changed = scrub_template_references(tmp_path)
        assert first_changed  # non-empty list

        # Snapshot the post-first-pass file contents.
        snapshots = {path: path.read_text(encoding="utf-8") for path in first_changed}

        # Second pass: nothing should change.
        second_changed = scrub_template_references(tmp_path)
        assert second_changed == []

        for path, original in snapshots.items():
            assert path.read_text(encoding="utf-8") == original

    def test_dry_run_does_not_write_files(self, tmp_path: Path) -> None:
        """Under dry_run=True the files are not modified."""
        from tools.pyproject_template.cleanup import scrub_template_references

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(self._PYPROJECT_WITH_STANZA, encoding="utf-8")

        changed = scrub_template_references(tmp_path, dry_run=True)

        # File still has the stanza — nothing was written.
        assert pyproject.read_text(encoding="utf-8") == self._PYPROJECT_WITH_STANZA
        # But the change is still reported.
        assert pyproject in changed

    def test_no_target_files_returns_empty(self, tmp_path: Path) -> None:
        """When none of the three target files exist, return an empty list."""
        from tools.pyproject_template.cleanup import scrub_template_references

        changed = scrub_template_references(tmp_path)
        assert changed == []

    def test_scrubs_github_settings_repo_settings_intro(self, tmp_path: Path) -> None:
        """Intro paragraph: ONLY the broken-link sentence is removed (#474).

        Surgical scrub. The first sentence (``Complete reference for the
        GitHub repository settings...``) and the doc-purpose sentence
        (``This page documents...``) must both survive; only the middle
        sentence pointing at deleted ``repo_settings.py`` goes away.
        """
        from tools.pyproject_template.cleanup import scrub_template_references

        github_settings = tmp_path / "docs" / "development" / "github-repository-settings.md"
        github_settings.parent.mkdir(parents=True)
        github_settings.write_text(self._GITHUB_SETTINGS_WITH_TEMPLATE_REFS, encoding="utf-8")

        changed = scrub_template_references(tmp_path)

        new = github_settings.read_text(encoding="utf-8")
        # The broken-link sentence is gone.
        assert "tools/pyproject_template/repo_settings.py" not in new
        assert "update_all_repo_settings()" not in new
        # The first sentence survives.
        assert "Complete reference for the GitHub repository settings this template expects." in new
        # The doc-purpose sentence survives.
        assert "This page documents what each setting is" in new
        assert github_settings in changed

    def test_scrubs_github_settings_security_paragraph(self, tmp_path: Path) -> None:
        """Security Settings intro paragraph + trailing blank line gone (#474).

        The ``## Security Settings`` heading and the table that follows must
        both survive — the table sits directly under the heading once the
        prose is removed.
        """
        from tools.pyproject_template.cleanup import scrub_template_references

        github_settings = tmp_path / "docs" / "development" / "github-repository-settings.md"
        github_settings.parent.mkdir(parents=True)
        github_settings.write_text(self._GITHUB_SETTINGS_WITH_TEMPLATE_REFS, encoding="utf-8")

        scrub_template_references(tmp_path)

        new = github_settings.read_text(encoding="utf-8")
        # The introductory paragraph is gone.
        assert "_configure_security_settings()" not in new
        assert "Security features are configured by" not in new
        # The heading and the table survive.
        assert "## Security Settings" in new
        assert "**Secret scanning**" in new
        # And the table sits right under the heading (no double blank line).
        assert "## Security Settings\n\n| Setting" in new

    def test_scrubs_release_automation_new_projects_paragraph(self, tmp_path: Path) -> None:
        """release-and-automation.md: paragraph rewritten, surroundings intact (#474).

        The lead ``**New projects (bootstrap flow).**`` and the
        ``git push origin v0.0.0`` code block underneath must survive
        untouched. Only the broken ``configure.py`` link is removed; the
        replacement prose still tells the user the v0.0.0 tag exists.
        """
        from tools.pyproject_template.cleanup import scrub_template_references

        release_auto = tmp_path / "docs" / "development" / "release-and-automation.md"
        release_auto.parent.mkdir(parents=True)
        release_auto.write_text(self._RELEASE_AUTO_WITH_TEMPLATE_REFS, encoding="utf-8")

        changed = scrub_template_references(tmp_path)

        new = release_auto.read_text(encoding="utf-8")
        # The broken link is gone.
        assert "tools/pyproject_template/configure.py" not in new
        # The lead survives (paragraph was rewritten, not stripped).
        assert "**New projects (bootstrap flow).**" in new
        # The trailing code block survives untouched.
        assert "```bash\ngit push origin v0.0.0\n```" in new
        # The user-facing instruction is preserved with the new wording.
        assert "auto-seeded on the" in new
        assert "only push" in new
        # The unrelated "Existing projects" paragraph + code block survive.
        assert "**Existing projects (synced from the template before the auto-seed" in new
        assert release_auto in changed

    def test_scrub_idempotent_for_new_targets(self, tmp_path: Path) -> None:
        """Second pass on already-scrubbed new-target files is a no-op (#474)."""
        from tools.pyproject_template.cleanup import scrub_template_references

        github_settings = tmp_path / "docs" / "development" / "github-repository-settings.md"
        github_settings.parent.mkdir(parents=True)
        github_settings.write_text(self._GITHUB_SETTINGS_WITH_TEMPLATE_REFS, encoding="utf-8")

        release_auto = tmp_path / "docs" / "development" / "release-and-automation.md"
        release_auto.write_text(self._RELEASE_AUTO_WITH_TEMPLATE_REFS, encoding="utf-8")

        # First pass: changes expected on both files.
        first_changed = scrub_template_references(tmp_path)
        assert github_settings in first_changed
        assert release_auto in first_changed

        # Snapshot the post-first-pass file contents.
        snapshots = {path: path.read_text(encoding="utf-8") for path in first_changed}

        # Second pass: nothing changes.
        second_changed = scrub_template_references(tmp_path)
        assert second_changed == []

        for path, original in snapshots.items():
            assert path.read_text(encoding="utf-8") == original

    def test_dry_run_does_not_write_new_targets(self, tmp_path: Path) -> None:
        """Under dry_run=True the new-target files are reported but not written (#474)."""
        from tools.pyproject_template.cleanup import scrub_template_references

        github_settings = tmp_path / "docs" / "development" / "github-repository-settings.md"
        github_settings.parent.mkdir(parents=True)
        github_settings.write_text(self._GITHUB_SETTINGS_WITH_TEMPLATE_REFS, encoding="utf-8")

        release_auto = tmp_path / "docs" / "development" / "release-and-automation.md"
        release_auto.write_text(self._RELEASE_AUTO_WITH_TEMPLATE_REFS, encoding="utf-8")

        changed = scrub_template_references(tmp_path, dry_run=True)

        # Both files are reported as would-change.
        assert github_settings in changed
        assert release_auto in changed
        # But nothing was written.
        assert (
            github_settings.read_text(encoding="utf-8") == self._GITHUB_SETTINGS_WITH_TEMPLATE_REFS
        )
        assert release_auto.read_text(encoding="utf-8") == self._RELEASE_AUTO_WITH_TEMPLATE_REFS


class TestCleanupAllDeletesTemplateCleanTask:
    """Regression test for issue #469: ``tools/doit/template_clean.py`` goes away.

    The doit task file imports the template cleanup module, which is deleted
    under ``CleanupMode.ALL``. Leaving the task behind is misleading because
    it would fail on invocation in a spawned repo.
    """

    def test_cleanup_all_deletes_template_clean_task(self, tmp_path: Path) -> None:
        """template_clean.py is in ALL_TEMPLATE_FILES and gets deleted."""
        from tools.pyproject_template.cleanup import (
            ALL_TEMPLATE_FILES,
            CleanupMode,
            cleanup_template_files,
        )

        # Verify the constant itself lists the file (documents intent).
        assert "tools/doit/template_clean.py" in ALL_TEMPLATE_FILES

        # Create the file and run ALL-mode cleanup.
        template_clean = tmp_path / "tools" / "doit" / "template_clean.py"
        template_clean.parent.mkdir(parents=True)
        template_clean.write_text("# placeholder", encoding="utf-8")

        result = cleanup_template_files(CleanupMode.ALL, tmp_path)

        assert not template_clean.exists()
        # And the deleted_files list reflects the removal.
        assert any(p.name == "template_clean.py" for p in result.deleted_files)

    def test_cleanup_setup_only_leaves_template_clean_task(self, tmp_path: Path) -> None:
        """Under SETUP_ONLY mode, template_clean.py survives (bug-#469 scope)."""
        from tools.pyproject_template.cleanup import (
            CleanupMode,
            cleanup_template_files,
        )

        template_clean = tmp_path / "tools" / "doit" / "template_clean.py"
        template_clean.parent.mkdir(parents=True)
        template_clean.write_text("# placeholder", encoding="utf-8")

        cleanup_template_files(CleanupMode.SETUP_ONLY, tmp_path)

        assert template_clean.exists()


class TestCleanupAllInvokesScrubber:
    """``cleanup_template_files(CleanupMode.ALL)`` calls the scrubber."""

    def test_all_mode_scrubs_pyproject(self, tmp_path: Path) -> None:
        """ALL-mode cleanup removes the tools.pyproject_template mypy override."""
        from tools.pyproject_template.cleanup import (
            CleanupMode,
            cleanup_template_files,
        )

        pyproject_content = (
            "[tool.mypy]\n"
            "strict = true\n"
            "\n"
            "[[tool.mypy.overrides]]\n"
            "# Standalone scripts using sys.path manipulation; excluded from discovery\n"
            "# but still followed via imports from bootstrap.py\n"
            'module = "tools.pyproject_template.*"\n'
            'follow_imports = "skip"\n'
            "\n"
            "[tool.pytest.ini_options]\n"
            'minversion = "8.0"\n'
        )
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(pyproject_content, encoding="utf-8")

        # We need at least one deletable file so ALL-mode has work to do.
        (tmp_path / "bootstrap.py").touch()

        cleanup_template_files(CleanupMode.ALL, tmp_path)

        new = pyproject.read_text(encoding="utf-8")
        assert "tools.pyproject_template" not in new

    def test_setup_only_mode_does_not_scrub(self, tmp_path: Path) -> None:
        """SETUP_ONLY mode leaves scrubber targets untouched."""
        from tools.pyproject_template.cleanup import (
            CleanupMode,
            cleanup_template_files,
        )

        pyproject_content = (
            "[[tool.mypy.overrides]]\n"
            "# guarded\n"
            'module = "tools.pyproject_template.*"\n'
            'follow_imports = "skip"\n'
            "\n"
        )
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(pyproject_content, encoding="utf-8")
        (tmp_path / "bootstrap.py").touch()

        cleanup_template_files(CleanupMode.SETUP_ONLY, tmp_path)

        # Scrubber must not run under SETUP_ONLY.
        assert pyproject.read_text(encoding="utf-8") == pyproject_content

    def test_all_mode_invokes_regenerate_and_check(self, tmp_path: Path) -> None:
        """ALL-mode invokes ``regenerate_doc_toc`` AND ``check_stale_template_references`` (#474).

        Mocks both helpers so we don't depend on the real subprocess; asserts
        that they're each called exactly once. Also asserts the SETUP_ONLY
        path leaves both helpers untouched.
        """
        from tools.pyproject_template import cleanup as cleanup_module
        from tools.pyproject_template.cleanup import (
            CleanupMode,
            cleanup_template_files,
        )

        # ALL-mode needs at least one deletable file so the function reaches
        # the post-cleanup helpers.
        (tmp_path / "bootstrap.py").touch()

        with (
            patch.object(cleanup_module, "regenerate_doc_toc", return_value=False) as mock_regen,
            patch.object(
                cleanup_module, "check_stale_template_references", return_value=[]
            ) as mock_check,
        ):
            cleanup_template_files(CleanupMode.ALL, tmp_path)

        mock_regen.assert_called_once_with(tmp_path, dry_run=False)
        mock_check.assert_called_once_with(tmp_path)

        # SETUP_ONLY mode must NOT call either helper.
        (tmp_path / "bootstrap.py").touch()  # recreate (was deleted above)
        with (
            patch.object(cleanup_module, "regenerate_doc_toc", return_value=False) as mock_regen2,
            patch.object(
                cleanup_module, "check_stale_template_references", return_value=[]
            ) as mock_check2,
        ):
            cleanup_template_files(CleanupMode.SETUP_ONLY, tmp_path)

        mock_regen2.assert_not_called()
        mock_check2.assert_not_called()


class TestRegenerateDocToc:
    """Tests for ``regenerate_doc_toc`` (issue #474)."""

    def test_returns_false_when_script_missing(self, tmp_path: Path) -> None:
        """No ``tools/generate_doc_toc.py`` -> return False, no exception."""
        from tools.pyproject_template.cleanup import regenerate_doc_toc

        # Only a TOC; no generator script.
        toc = tmp_path / "docs" / "TABLE_OF_CONTENTS.md"
        toc.parent.mkdir(parents=True)
        toc.write_text("# TOC\n", encoding="utf-8")

        assert regenerate_doc_toc(tmp_path) is False

    def test_returns_false_when_toc_missing(self, tmp_path: Path) -> None:
        """No ``docs/TABLE_OF_CONTENTS.md`` -> return False."""
        from tools.pyproject_template.cleanup import regenerate_doc_toc

        # Only a script; no TOC.
        script = tmp_path / "tools" / "generate_doc_toc.py"
        script.parent.mkdir(parents=True)
        script.write_text("print('hi')\n", encoding="utf-8")

        assert regenerate_doc_toc(tmp_path) is False

    def test_invokes_subprocess_and_reports_change(self, tmp_path: Path) -> None:
        """Mocked subprocess: exit 1 -> True, exit 0 -> False, exit 2 -> False (warns)."""
        from tools.pyproject_template.cleanup import regenerate_doc_toc

        # Both files must exist for the function to invoke the subprocess.
        script = tmp_path / "tools" / "generate_doc_toc.py"
        script.parent.mkdir(parents=True)
        script.write_text("print('hi')\n", encoding="utf-8")
        toc = tmp_path / "docs" / "TABLE_OF_CONTENTS.md"
        toc.parent.mkdir(parents=True)
        toc.write_text("# TOC\n", encoding="utf-8")

        # Exit 1 = changes written -> True.
        completed_changed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
        with patch("subprocess.run", return_value=completed_changed) as mock_run:
            assert regenerate_doc_toc(tmp_path) is True
            mock_run.assert_called_once()

        # Exit 0 = no change -> False (success path, but nothing happened).
        completed_nochange = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        with patch("subprocess.run", return_value=completed_nochange):
            assert regenerate_doc_toc(tmp_path) is False

        # Exit 2 = real failure -> False (warning logged).
        completed_failed = subprocess.CompletedProcess(
            args=[], returncode=2, stdout="", stderr="boom"
        )
        with patch("subprocess.run", return_value=completed_failed):
            assert regenerate_doc_toc(tmp_path) is False

    def test_dry_run_does_not_invoke_subprocess(self, tmp_path: Path) -> None:
        """Under dry_run=True the subprocess is NOT invoked; returns True."""
        from tools.pyproject_template.cleanup import regenerate_doc_toc

        script = tmp_path / "tools" / "generate_doc_toc.py"
        script.parent.mkdir(parents=True)
        script.write_text("print('hi')\n", encoding="utf-8")
        toc = tmp_path / "docs" / "TABLE_OF_CONTENTS.md"
        toc.parent.mkdir(parents=True)
        toc.write_text("# TOC\n", encoding="utf-8")

        with patch("subprocess.run") as mock_run:
            assert regenerate_doc_toc(tmp_path, dry_run=True) is True
            mock_run.assert_not_called()


class TestCheckStaleTemplateReferences:
    """Tests for ``check_stale_template_references`` (issue #474)."""

    def test_returns_empty_when_docs_clean(self, tmp_path: Path) -> None:
        """Clean docs tree (no markers) -> empty list."""
        from tools.pyproject_template.cleanup import check_stale_template_references

        clean_doc = tmp_path / "docs" / "guide.md"
        clean_doc.parent.mkdir(parents=True)
        clean_doc.write_text("# Guide\n\nNothing template-y here.\n", encoding="utf-8")

        assert check_stale_template_references(tmp_path) == []

    def test_detects_pyproject_template_marker_in_docs(self, tmp_path: Path) -> None:
        """``tools/pyproject_template/`` in a doc -> reported with line number."""
        from tools.pyproject_template.cleanup import check_stale_template_references

        bad_doc = tmp_path / "docs" / "guide.md"
        bad_doc.parent.mkdir(parents=True)
        bad_doc.write_text(
            "# Guide\n\nSee `tools/pyproject_template/foo.py` for details.\n",
            encoding="utf-8",
        )

        survivors = check_stale_template_references(tmp_path)
        assert len(survivors) == 1
        path, line_no, content = survivors[0]
        assert path == bad_doc
        assert line_no == 3
        assert "tools/pyproject_template/foo.py" in content

    def test_detects_template_tools_reference_marker(self, tmp_path: Path) -> None:
        """``template/tools-reference.md`` in a doc -> reported."""
        from tools.pyproject_template.cleanup import check_stale_template_references

        bad_doc = tmp_path / "docs" / "TABLE_OF_CONTENTS.md"
        bad_doc.parent.mkdir(parents=True)
        bad_doc.write_text(
            "# TOC\n\n- [Tools](template/tools-reference.md)\n",
            encoding="utf-8",
        )

        survivors = check_stale_template_references(tmp_path)
        assert len(survivors) == 1
        path, _, content = survivors[0]
        assert path == bad_doc
        assert "template/tools-reference.md" in content

    def test_skips_missing_docs_directory(self, tmp_path: Path) -> None:
        """No ``docs/`` directory -> empty list (and README still scanned if present)."""
        from tools.pyproject_template.cleanup import check_stale_template_references

        # No docs/ at all.
        assert check_stale_template_references(tmp_path) == []

        # Add a clean README to confirm it's scanned without error.
        readme = tmp_path / "README.md"
        readme.write_text("# Hi\nNothing template-y here.\n", encoding="utf-8")
        assert check_stale_template_references(tmp_path) == []

    def test_scans_readme_at_root(self, tmp_path: Path) -> None:
        """``README.md`` with a marker is reported."""
        from tools.pyproject_template.cleanup import check_stale_template_references

        readme = tmp_path / "README.md"
        readme.write_text(
            "# Project\n\nRun `tools/doit/template_clean.py --setup` to clean up.\n",
            encoding="utf-8",
        )

        survivors = check_stale_template_references(tmp_path)
        assert len(survivors) == 1
        path, line_no, content = survivors[0]
        assert path == readme
        assert line_no == 3
        assert "tools/doit/template_clean" in content
