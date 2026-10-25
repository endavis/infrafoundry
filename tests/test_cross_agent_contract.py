"""The cross-agent workflow files must agree, not merely exist.

`test_delegation_matrix.py` checks that every command/skill file is present.
Presence is not agreement: the files encode a shared workflow contract — the plan
comment header, the branch-name pattern, the finalize handoff — that lets a user
switch agents mid-workflow without losing state. Until now nothing checked that
they still said the same things, so the contract held only by manual discipline
across 74 files (#692).

The contract itself is documented in
``docs/development/ai/cross-agent-delegation.md``; this module is its enforcement.
When the two disagree, the doc is the specification and this file is the bug.

Per-agent exemptions are declared in `EXEMPTIONS` with a reason, because uniform
prose is not the goal — agreement on the contract is. Claude's `implement`
command legitimately omits `doit check` because it delegates to
`.claude/agents/implement-worker.md`, which runs it.

Assertions are scoped to the agents a project actually wires, following the
convention in `tests/agent_roster.py` (#690).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_roster import agent_is_present, present_agents

REPO_ROOT = Path(__file__).resolve().parents[1]

# Where each agent keeps its self-action workflow file for a given action.
SELF_ACTION_LAYOUTS = {
    "claude": lambda action: REPO_ROOT / ".claude" / "commands" / "claude" / f"{action}.md",
    "copilot": lambda action: REPO_ROOT / ".github" / "skills" / f"copilot-{action}" / "SKILL.md",
    "codex": lambda action: REPO_ROOT / ".agents" / "skills" / f"codex-{action}" / "SKILL.md",
    "antigravity": (
        lambda action: REPO_ROOT / ".agents" / "skills" / f"antigravity-{action}" / "SKILL.md"
    ),
}

# The finalize step is host-agnostic: Claude has its own copy, and every other
# host reaches the `.agents/skills/` one (Copilot reads that directory too).
FINALIZE_FILES = (
    REPO_ROOT / ".claude" / "commands" / "ghi-finalize.md",
    REPO_ROOT / ".agents" / "skills" / "ghi-finalize" / "SKILL.md",
)

# Contract elements, by the action whose files must carry them. Each entry is
# (label, substring). Substrings rather than regexes: the contract is a literal
# string the agents must reproduce, so a literal check is the honest test.
CONTRACT = {
    "plan": [
        ("plan-comment header", "Implementation Plan for"),
    ],
    "implement": [
        ("branch-name pattern", "<type>/"),
        ("validation command", "doit check"),
        ("finalize handoff", "ghi-finalize"),
    ],
    "review": [
        ("read-only constraint", "**Read-only.**"),
    ],
    "adversarial-review": [
        ("read-only constraint", "**Read-only.**"),
    ],
}

# (action, agent) pairs that legitimately omit an element, with the reason.
# An exemption is a documented architectural difference, not a licence to drift.
EXEMPTIONS: dict[tuple[str, str, str], str] = {
    ("implement", "claude", "validation command"): (
        "Claude delegates implementation to .claude/agents/implement-worker.md, "
        "which runs `doit check` itself"
    ),
}

# The identical sentence every review file must carry, so the constraint cannot
# be reworded into something weaker on one surface.
READ_ONLY_SENTENCE = (
    "**Read-only.** Review and report — do not edit files, commit, or push. "
    "Findings go to the user and the PR; any fix is a separate change the user asks for."
)


def _self_action_files(action: str) -> list[tuple[str, Path]]:
    """Return (agent, path) for each wired agent's file for *action*."""
    return [(agent, SELF_ACTION_LAYOUTS[agent](action)) for agent in present_agents()]


def _contract_violations(action: str, agent: str, text: str) -> list[str]:
    """Return the contract elements *text* is missing for (*action*, *agent*).

    Shared by the real check and its non-vacuity companion, so the companion
    exercises the logic that actually runs rather than a restatement of it.
    """
    return [
        f"{agent}/{action} is missing the {label} ({needle!r})"
        for label, needle in CONTRACT[action]
        if needle not in text and (action, agent, label) not in EXEMPTIONS
    ]


@pytest.mark.parametrize("action", sorted(CONTRACT))
def test_self_action_files_carry_the_contract(action: str) -> None:
    """Every wired agent's file for *action* contains that action's contract elements."""
    missing: list[str] = []

    for agent, path in _self_action_files(action):
        if not path.is_file():
            missing.append(f"{agent}: {path.relative_to(REPO_ROOT)} does not exist")
            continue
        missing += _contract_violations(action, agent, path.read_text(encoding="utf-8"))

    assert not missing, (
        "cross-agent contract violations:\n  "
        + "\n  ".join(missing)
        + "\n\nThe contract is specified in docs/development/ai/cross-agent-delegation.md. "
        "If an agent legitimately differs, declare it in EXEMPTIONS with a reason."
    )


def test_read_only_constraint_is_worded_identically() -> None:
    """The review constraint must be the same sentence everywhere.

    A constraint that is paraphrased per host drifts into a weaker version on one
    surface, and whichever agent is driving decides which version applies — the
    same failure mode the rule-file mirror guards against.
    """
    divergent = []
    for action in ("review", "adversarial-review"):
        for agent, path in _self_action_files(action):
            if not path.is_file():
                continue
            if READ_ONLY_SENTENCE not in path.read_text(encoding="utf-8"):
                divergent.append(f"{agent}/{action}")

    assert not divergent, (
        f"these files do not carry the exact read-only sentence: {divergent}. "
        "Reword all of them together or none."
    )


def test_finalize_files_carry_the_issue_reference_contract() -> None:
    """`Addresses #` lives in the finalize step, which is what opens the PR.

    Asserted here rather than on `implement` because no implement file opens a
    PR — a distinction #692 originally had the other way round.
    """
    missing = [
        str(path.relative_to(REPO_ROOT))
        for path in FINALIZE_FILES
        if path.is_file() and "Addresses #" not in path.read_text(encoding="utf-8")
    ]
    assert not missing, f"finalize files missing the 'Addresses #' contract: {missing}"


def test_at_least_one_finalize_file_exists() -> None:
    """Guard the check above against silently passing on an empty set."""
    assert any(path.is_file() for path in FINALIZE_FILES), (
        "no ghi-finalize file found; the contract check above would be vacuous"
    )


def test_the_contract_scanner_detects_a_violation() -> None:
    """Feeding the checker a file with none of the contract must flag every element.

    Without this, `test_self_action_files_carry_the_contract` could pass because
    the checker finds nothing to complain about rather than because the files
    comply. Uses an agent with no exemptions so nothing is silently skipped.
    """
    empty = "an unrelated document with none of the contract in it"

    for action, elements in CONTRACT.items():
        violations = _contract_violations(action, "copilot", empty)
        assert len(violations) == len(elements), (
            f"scanner found {len(violations)} of {len(elements)} missing elements "
            f"for {action!r}; the needles are too weak to assert on"
        )


def test_declared_exemptions_actually_suppress() -> None:
    """An exemption must change the outcome, or it is decoration.

    Claude's implement file is exempt from `doit check`; the same empty text
    scored against Copilot must therefore yield one more violation.
    """
    empty = "an unrelated document with none of the contract in it"
    claude = _contract_violations("implement", "claude", empty)
    copilot = _contract_violations("implement", "copilot", empty)

    assert len(claude) == len(copilot) - 1, (
        "the Claude implement exemption did not suppress anything; "
        f"claude={claude} copilot={copilot}"
    )


def test_exemptions_are_real_and_documented() -> None:
    """Every exemption must name a live agent/action and actually be needed.

    Stops the exemption table from outliving the difference it excuses — the way
    an allowlist quietly becomes a list of things nobody checks.
    """
    stale: list[str] = []
    for (action, agent, label), reason in EXEMPTIONS.items():
        assert reason.strip(), f"exemption ({action}, {agent}, {label}) needs a reason"
        if not agent_is_present(agent):
            continue
        path = SELF_ACTION_LAYOUTS[agent](action)
        needle = next(n for lbl, n in CONTRACT[action] if lbl == label)
        if path.is_file() and needle in path.read_text(encoding="utf-8"):
            stale.append(f"({action}, {agent}, {label}) — the file now carries {needle!r}")

    assert not stale, f"these exemptions are no longer needed and should be removed: {stale}"
