"""Tests for sync-exclude support in ``check_template_updates``."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.pyproject_template.check_template_updates import (
    compare_files,
    load_sync_excludes,
)


def _make_template(
    template_root: Path, files: dict[str, str], *, base: str = "pyproject-template-main"
) -> Path:
    """Create a fake extracted template tree under ``template_root/<base>``.

    Mirrors the directory shape produced by ``download_and_extract_archive``.
    """
    root = template_root / base
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def _write_exclude_file(project_root: Path, patterns: list[str]) -> None:
    settings_dir = project_root / ".config" / "pyproject_template"
    settings_dir.mkdir(parents=True, exist_ok=True)
    body = "exclude = [\n" + "".join(f'    "{p}",\n' for p in patterns) + "]\n"
    (settings_dir / "sync-exclude.toml").write_text(body, encoding="utf-8")


class TestLoadSyncExcludes:
    """Direct tests of the ``load_sync_excludes`` loader."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert load_sync_excludes(tmp_path) == []

    def test_valid_file_returns_patterns(self, tmp_path: Path) -> None:
        _write_exclude_file(tmp_path, ["examples/api/**", "src/foo.py"])
        assert load_sync_excludes(tmp_path) == ["examples/api/**", "src/foo.py"]

    def test_missing_exclude_key_returns_empty(self, tmp_path: Path) -> None:
        settings_dir = tmp_path / ".config" / "pyproject_template"
        settings_dir.mkdir(parents=True)
        (settings_dir / "sync-exclude.toml").write_text("# no exclude key\n", encoding="utf-8")
        assert load_sync_excludes(tmp_path) == []

    def test_malformed_toml_returns_empty(self, tmp_path: Path) -> None:
        settings_dir = tmp_path / ".config" / "pyproject_template"
        settings_dir.mkdir(parents=True)
        (settings_dir / "sync-exclude.toml").write_text("not = valid toml [[\n", encoding="utf-8")
        assert load_sync_excludes(tmp_path) == []

    def test_non_list_exclude_returns_empty(self, tmp_path: Path) -> None:
        settings_dir = tmp_path / ".config" / "pyproject_template"
        settings_dir.mkdir(parents=True)
        (settings_dir / "sync-exclude.toml").write_text('exclude = "oops"\n', encoding="utf-8")
        assert load_sync_excludes(tmp_path) == []

    def test_non_string_entries_dropped(self, tmp_path: Path) -> None:
        settings_dir = tmp_path / ".config" / "pyproject_template"
        settings_dir.mkdir(parents=True)
        (settings_dir / "sync-exclude.toml").write_text(
            'exclude = ["keep.py", 42, "also.py"]\n', encoding="utf-8"
        )
        assert load_sync_excludes(tmp_path) == ["keep.py", "also.py"]


class TestCompareFilesWithExcludes:
    """``compare_files`` returns ``(different_files, excluded_files)``."""

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        project = tmp_path / "project"
        project.mkdir()
        return project

    @pytest.fixture
    def template(self, tmp_path: Path) -> Path:
        return tmp_path / "template"

    def test_no_exclude_file_is_noop(self, project: Path, template: Path) -> None:
        template_root = _make_template(
            template,
            {"docs/index.md": "upstream", "src/main.py": "upstream"},
        )
        # Project has neither file; both should appear in different_files.
        diff, excluded = compare_files(project, template_root)
        assert excluded == []
        assert sorted(p.as_posix() for p in diff) == ["docs/index.md", "src/main.py"]

    def test_glob_match_lands_in_excluded(self, project: Path, template: Path) -> None:
        template_root = _make_template(
            template,
            {"examples/api/foo.py": "x", "examples/api/sub/bar.py": "y", "src/main.py": "z"},
        )
        _write_exclude_file(project, ["examples/api/**"])
        diff, excluded = compare_files(project, template_root)
        assert sorted(p.as_posix() for p in diff) == ["src/main.py"]
        assert sorted(p.as_posix() for p in excluded) == [
            "examples/api/foo.py",
            "examples/api/sub/bar.py",
        ]

    def test_exact_path_match(self, project: Path, template: Path) -> None:
        template_root = _make_template(
            template,
            {"src/package_name/core.py": "x", "src/package_name/cli.py": "y"},
        )
        _write_exclude_file(project, ["src/package_name/core.py"])
        diff, excluded = compare_files(project, template_root)
        assert [p.as_posix() for p in diff] == ["src/package_name/cli.py"]
        assert [p.as_posix() for p in excluded] == ["src/package_name/core.py"]

    def test_unmatched_file_still_flagged(self, project: Path, template: Path) -> None:
        template_root = _make_template(
            template,
            {"README.md": "x", "examples/api/foo.py": "y"},
        )
        _write_exclude_file(project, ["examples/api/**"])
        diff, excluded = compare_files(project, template_root)
        assert [p.as_posix() for p in diff] == ["README.md"]
        assert [p.as_posix() for p in excluded] == ["examples/api/foo.py"]

    def test_hardcoded_skip_takes_precedence(self, project: Path, template: Path) -> None:
        # __pycache__ is in the hardcoded skip set; user excludes should not
        # override that, and __pycache__ should not appear in either bucket.
        template_root = _make_template(
            template,
            {"__pycache__/cached.pyc": "x", "src/main.py": "y"},
        )
        _write_exclude_file(project, ["__pycache__/**"])
        diff, excluded = compare_files(project, template_root)
        assert [p.as_posix() for p in diff] == ["src/main.py"]
        assert excluded == []

    def test_matching_file_not_reported(self, project: Path, template: Path) -> None:
        # If the project file matches the template, neither bucket should contain it
        # — even if it would otherwise match an exclude pattern.
        template_root = _make_template(template, {"src/main.py": "same"})
        (project / "src").mkdir()
        (project / "src" / "main.py").write_text("same", encoding="utf-8")
        _write_exclude_file(project, ["src/main.py"])
        diff, excluded = compare_files(project, template_root)
        assert diff == []
        assert excluded == []

    def test_excludes_param_overrides_file(self, project: Path, template: Path) -> None:
        # Passing ``excludes=`` explicitly bypasses the on-disk loader, which is
        # how callers (and tests) inject patterns without a TOML file on disk.
        template_root = _make_template(template, {"a.py": "x", "b.py": "y"})
        diff, excluded = compare_files(project, template_root, excludes=["a.py"])
        assert [p.as_posix() for p in diff] == ["b.py"]
        assert [p.as_posix() for p in excluded] == ["a.py"]
