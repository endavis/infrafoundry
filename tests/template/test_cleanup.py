"""Tests for cleanup.py template file cleanup functionality."""

from __future__ import annotations

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
