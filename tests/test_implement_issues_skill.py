"""The `implement-issues` skill runs several issues in parallel worktrees (#1097, ADR-9028)."""

from __future__ import annotations

import re
from pathlib import Path

from tools.doit.skills import SHARED_SKILLS

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / ".agents" / "skills" / "implement-issues" / "SKILL.md"
IMPLEMENT_ISSUE = REPO_ROOT / ".agents" / "skills" / "implement-issue" / "SKILL.md"
AI_DOCS = REPO_ROOT / "docs" / "development" / "ai"
AGENTS_MD = REPO_ROOT / "AGENTS.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _frontmatter() -> dict[str, str]:
    match = re.match(r"---\n(.*?)\n---\n", _text(), re.DOTALL)
    assert match, "SKILL.md has no frontmatter"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _section(start: str, end: str) -> str:
    text = _text()
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def test_frontmatter_and_registration() -> None:
    fm = _frontmatter()
    assert fm["name"] == "implement-issues"
    assert "implement issues" in fm["description"]
    assert "implement-issues" in SHARED_SKILLS


def test_preflight_comes_before_worktree_creation() -> None:
    text = _text()
    create = text.index("uv run doit worktree --branch=<type>/<n>-")
    assert text.index("gh issue view") < create
    assert text.index("overlap") < create
    assert text.index("check only") < create


def test_check_only_stops_before_step_2() -> None:
    step1 = _section("### Step 1:", "### Step 2:")
    assert "`check only`" in step1
    assert "no worktree is created" in step1


def test_worktrees_are_created_in_sequence_from_the_main_checkout() -> None:
    step2 = _section("### Step 2:", "### Step 3:")
    assert "one after another" in step2
    assert "main checkout" in step2


def test_main_checkout_is_never_switched_or_inspected_except_with_git_c() -> None:
    text = _text()
    assert "git checkout" not in text
    assert "git pull" not in text
    assert "--active" not in text
    assert "git -C" in text
    for match in re.finditer(r"git stash", text):
        assert text[: match.start()].endswith("bare `"), "bare git stash rule only"


def test_one_background_agent_per_issue_with_the_absolute_worktree() -> None:
    step3 = _section("### Step 3:", "### Step 4:")
    assert "run_in_background: true" in step3
    assert "general-purpose" in step3
    assert 'cd "<WORKTREE>" &&' in step3
    assert "never edit files" in step3


def test_concurrency_cap() -> None:
    text = _text()
    assert "default 2" in text
    assert "--max=" in text


def test_ask_first_contract() -> None:
    step3 = _section("### Step 3:", "### Step 4:")
    assert "ASK-FIRST:" in step3
    assert "that issue only" in step3
    assert "the others continue" in step3


def test_merge_gate_stays_with_the_user() -> None:
    text = _text()
    never = text[text.index("## Never") :]
    assert "--add-label" not in text
    assert "gh pr merge" not in text
    assert re.search(r"[Nn]ever apply the `ready-to-merge` label, merge a PR, or close", never)
    assert "merge-pr" in text


def test_host_support_names_every_host() -> None:
    host = _text()[_text().index("## Host support") :]
    for name in ("Claude Code", "Codex", "Copilot", "Antigravity"):
        assert name in host
    assert "one after another" in host


def test_docs_register_the_skill() -> None:
    slash = (AI_DOCS / "slash-commands.md").read_text(encoding="utf-8")
    assert "### implement issues A, B" in slash
    assert "Twenty workflow skills" in slash
    assert "implement issues" in (AI_DOCS / "first-5-minutes.md").read_text(encoding="utf-8")
    delegation = (AI_DOCS / "cross-agent-delegation.md").read_text(encoding="utf-8")
    assert "## Parallel issues (`implement-issues`)" in delegation
    assert "slash-commands.md#implement-issues-a-b" in AGENTS_MD.read_text(encoding="utf-8")


def test_implement_issue_points_at_implement_issues() -> None:
    text = IMPLEMENT_ISSUE.read_text(encoding="utf-8")
    assert "use `implement-issues`" in text
    assert "../implement-issues/SKILL.md" in text


def test_step_3_prompt_names_the_plan_review_brief() -> None:
    step3 = _section("### Step 3:", "### Step 4:")
    assert "Plan-review brief" in step3
