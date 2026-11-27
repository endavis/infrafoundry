"""Tests for ``infrafoundry.core.paths.output_root`` (#1716)."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrafoundry.core.paths import OUTPUT_DIR_ENV, output_root


def test_unset_is_generated_under_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(OUTPUT_DIR_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    assert output_root() == (tmp_path / "generated").resolve()


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_counts_as_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(OUTPUT_DIR_ENV, value)
    monkeypatch.chdir(tmp_path)
    assert output_root() == (tmp_path / "generated").resolve()


def test_relative_value_is_made_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OUTPUT_DIR_ENV, "out/gen")
    monkeypatch.chdir(tmp_path)
    assert output_root() == (tmp_path / "out" / "gen").resolve()


def test_absolute_value_is_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OUTPUT_DIR_ENV, str(tmp_path / "abs"))
    assert output_root() == (tmp_path / "abs").resolve()


def test_tilde_is_expanded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(OUTPUT_DIR_ENV, "~/gen")
    assert output_root() == (tmp_path / "gen").resolve()


def test_symlink_is_resolved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    monkeypatch.setenv(OUTPUT_DIR_ENV, str(link))
    assert output_root() == target.resolve()
