"""Validate the cross-agent delegation matrix file layout.

Static test only — no CLI or model invocations. Verifies that:

- All 48 source x target x action command/skill files exist at the documented paths.
- `.gemini/settings.json` `skills.disabled` contains all 12 Codex-source delegation
  skill names (preventing Gemini from loading them).
- The matrix documentation page exists.

See `docs/development/ai/cross-agent-delegation.md` and issue #550.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

AGENTS = ("claude", "codex", "gemini", "copilot")
ACTIONS = ("plan", "implement", "review", "adversarial-review")


def _cross_pairs() -> list[tuple[str, str]]:
    """Yield (source, target) pairs where source != target."""
    return [(s, t) for s in AGENTS for t in AGENTS if s != t]


def _expected_path(source: str, target: str, action: str) -> Path:
    """Map a (source, target, action) cell to its on-disk location."""
    if source == "claude":
        return REPO_ROOT / ".claude" / "commands" / target / f"{action}.md"
    if source == "gemini":
        return REPO_ROOT / ".gemini" / "commands" / target / f"{action}.toml"
    if source == "copilot":
        return REPO_ROOT / ".copilot" / "commands" / target / f"{action}.md"
    if source == "codex":
        return REPO_ROOT / ".agents" / "skills" / f"delegate-{target}-{action}" / "SKILL.md"
    raise ValueError(f"unknown source agent: {source}")


@pytest.mark.parametrize(("source", "target"), _cross_pairs())
@pytest.mark.parametrize("action", ACTIONS)
def test_delegation_file_exists(source: str, target: str, action: str) -> None:
    """Every (source, target, action) cell has a corresponding file."""
    path = _expected_path(source, target, action)
    assert path.is_file(), f"missing delegation file: {path.relative_to(REPO_ROOT)}"


def test_total_file_count() -> None:
    """4 sources x 3 targets x 4 actions = 48 files."""
    paths = [_expected_path(s, t, a) for s, t in _cross_pairs() for a in ACTIONS]
    existing = [p for p in paths if p.is_file()]
    assert len(existing) == 48, (
        f"expected 48 delegation files, found {len(existing)}; "
        f"missing: {[str(p.relative_to(REPO_ROOT)) for p in paths if p not in existing]}"
    )


def test_gemini_disabled_list_contains_delegation_skills() -> None:
    """All 12 Codex-source delegation skill names are disabled in .gemini/settings.json.

    Without this, Gemini auto-loads the skills from .agents/skills/ (its docs document
    that path as cross-agent interop) and may mis-activate them. See
    docs/development/ai/cross-agent-delegation.md → "Path conflict between Codex and Gemini".
    """
    settings_path = REPO_ROOT / ".gemini" / "settings.json"
    settings = json.loads(settings_path.read_text())
    disabled = set(settings["skills"]["disabled"])

    expected_skills = {
        f"delegate-{target}-{action}"
        for target in AGENTS
        if target != "codex"
        for action in ACTIONS
    }
    assert len(expected_skills) == 12

    missing = expected_skills - disabled
    assert not missing, (
        f"the following delegation skills must be added to "
        f".gemini/settings.json skills.disabled: {sorted(missing)}"
    )


def test_matrix_doc_exists() -> None:
    """The cross-agent delegation doc page exists."""
    doc = REPO_ROOT / "docs" / "development" / "ai" / "cross-agent-delegation.md"
    assert doc.is_file(), f"missing matrix doc: {doc.relative_to(REPO_ROOT)}"
