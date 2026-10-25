"""Tests for AI agent workflow assets checked into the template."""

from __future__ import annotations

import json
from pathlib import Path

from agent_roster import agent_is_present, present_agents, skip_if_absent

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_codex_workflow_skills_exist() -> None:
    """Codex workflow skills should be present in the repo skills directory."""
    skip_if_absent("codex")

    skill_paths = [
        REPO_ROOT / ".agents" / "skills" / "codex-plan" / "SKILL.md",
        REPO_ROOT / ".agents" / "skills" / "codex-implement" / "SKILL.md",
        REPO_ROOT / ".agents" / "skills" / "codex-review" / "SKILL.md",
        REPO_ROOT / ".agents" / "skills" / "codex-adversarial-review" / "SKILL.md",
        REPO_ROOT / ".agents" / "skills" / "ghi-finalize" / "SKILL.md",
    ]

    for skill_path in skill_paths:
        assert skill_path.exists(), f"Missing Codex skill: {skill_path}"


def test_multi_orchestrator_files_exist() -> None:
    """multi-* orchestrators exist for every host this project wires.

    The template wires all four hosts (9 files); a project that keeps fewer is
    checked against the hosts it kept (#690).
    """
    actions = ("plan", "review", "adversarial-review")
    paths: list[Path] = []
    if agent_is_present("claude"):
        paths += [REPO_ROOT / ".claude" / "commands" / f"multi-{a}.md" for a in actions]
    if agent_is_present("copilot"):
        paths += [REPO_ROOT / ".copilot" / "commands" / f"multi-{a}.md" for a in actions]
    # Codex and Antigravity share the .agents/skills/ orchestrators.
    if agent_is_present("codex") or agent_is_present("antigravity"):
        paths += [REPO_ROOT / ".agents" / "skills" / f"multi-{a}" / "SKILL.md" for a in actions]

    for path in paths:
        assert path.exists(), f"Missing multi-orchestrator file: {path}"


def test_self_action_grid_exists() -> None:
    """Every wired agent has its four self-action files.

    The template wires four agents x four actions = 16 files. The grid is built
    from the agents this project keeps rather than pinned at the template's
    roster (#690).
    """
    actions = ("plan", "implement", "review", "adversarial-review")
    # Where each host keeps its self-action files. Copilot uses .github/skills/
    # rather than .claude/skills/ — see tests/test_delegation_matrix.py
    # ::_expected_path for why.
    layouts = {
        "claude": lambda a: REPO_ROOT / ".claude" / "commands" / "claude" / f"{a}.md",
        "copilot": lambda a: REPO_ROOT / ".github" / "skills" / f"copilot-{a}" / "SKILL.md",
        "codex": lambda a: REPO_ROOT / ".agents" / "skills" / f"codex-{a}" / "SKILL.md",
        "antigravity": lambda a: REPO_ROOT / ".agents" / "skills" / f"antigravity-{a}" / "SKILL.md",
    }

    for agent in present_agents():
        for action in actions:
            path = layouts[agent](action)
            assert path.exists(), f"Missing self-action file: {path}"


def test_retired_self_action_aliases_are_removed() -> None:
    """The old ghissue-plan/implement/close self-action aliases should be gone."""
    removed = [
        REPO_ROOT / ".claude" / "commands" / "ghissue-plan.md",
        REPO_ROOT / ".claude" / "commands" / "ghissue-implement.md",
        REPO_ROOT / ".claude" / "commands" / "ghissue-close.md",
        REPO_ROOT / ".agents" / "skills" / "ghissue-plan" / "SKILL.md",
        REPO_ROOT / ".agents" / "skills" / "ghissue-implement" / "SKILL.md",
    ]

    for path in removed:
        assert not path.exists(), f"Retired self-action file should not exist: {path}"


def test_retired_dual_agent_files_are_removed() -> None:
    """The old hardcoded dual-agent commands should be gone, replaced by multi-* orchestrators."""
    removed = [
        REPO_ROOT / ".claude" / "commands" / "ghissue-plan-both.md",
        REPO_ROOT / ".claude" / "commands" / "ghissue-review-both.md",
    ]

    for path in removed:
        assert not path.exists(), f"Retired file should not exist: {path}"


def test_retired_workflow_step_aliases_are_removed() -> None:
    """The old ghissue-finalize/ghissue-status workflow steps should be renamed to ghi-*."""
    removed = [
        REPO_ROOT / ".claude" / "commands" / "ghissue-finalize.md",
        REPO_ROOT / ".claude" / "commands" / "ghissue-status.md",
        REPO_ROOT / ".agents" / "skills" / "ghissue-finalize" / "SKILL.md",
    ]

    for path in removed:
        assert not path.exists(), f"Retired workflow step file should not exist: {path}"


def test_codex_config_keeps_shared_dangerous_command_hook() -> None:
    """Codex config should keep the shared dangerous-command hook wired."""
    skip_if_absent("codex")

    config = (REPO_ROOT / ".codex" / "config.toml").read_text(encoding="utf-8")

    # `codex_hooks` is the deprecated spelling; Codex warns on it and would
    # silently stop running the hook if it were removed (#681).
    assert "hooks = true" in config
    # Match the assignment, not the bare word: the config explains the rename
    # in a comment, which a substring check would trip over.
    assert "codex_hooks = true" not in config
    assert "[[hooks.PreToolUse]]" in config
    assert "block-dangerous-commands.py" in config


def test_codex_config_uses_current_schema() -> None:
    """Codex config should avoid obsolete keys from older Codex releases."""
    skip_if_absent("codex")

    config = (REPO_ROOT / ".codex" / "config.toml").read_text(encoding="utf-8")

    assert 'approval_policy = "on-request"' in config
    assert "default_policy" not in config
    assert "[[approval_policy]]" not in config
    assert "[shell_env_policy]" not in config


def test_ai_setup_documents_codex_skills_workflow() -> None:
    """AI setup docs should describe the Codex skills-based workflow."""
    content = (REPO_ROOT / "docs" / "development" / "AI_SETUP.md").read_text(encoding="utf-8")

    assert ".agents/skills" in content
    assert "$codex-plan" in content
    assert "shared dangerous-command hook" in content


def test_slash_commands_doc_mentions_codex_skills_instead_of_custom_commands() -> None:
    """Workflow docs should describe Codex via skills rather than custom slash commands."""
    content = (REPO_ROOT / "docs" / "development" / "ai" / "slash-commands.md").read_text(
        encoding="utf-8"
    )

    assert "repo-scoped skills" in content
    assert "/skills" in content
    assert "$codex-implement" in content


def test_enforcement_principles_document_codex_hook_support() -> None:
    """Enforcement docs should reflect current Codex hook support."""
    content = (REPO_ROOT / "docs" / "development" / "ai" / "enforcement-principles.md").read_text(
        encoding="utf-8"
    )

    assert "Codex uses the shared hook" in content
    assert "no hook support" not in content


def test_antigravity_workflow_skills_exist() -> None:
    """Antigravity self-action skills should be present in the shared .agents/skills directory."""
    skip_if_absent("antigravity")

    for action in ("plan", "implement", "review", "adversarial-review"):
        skill_path = REPO_ROOT / ".agents" / "skills" / f"antigravity-{action}" / "SKILL.md"
        assert skill_path.exists(), f"Missing Antigravity skill: {skill_path}"


def test_antigravity_hooks_json_wires_shared_hook() -> None:
    """.agents/hooks.json should wire the shared dangerous-command hook on PreToolUse."""
    skip_if_absent("antigravity")

    hooks_path = REPO_ROOT / ".agents" / "hooks.json"
    assert hooks_path.exists(), f"Missing Antigravity hooks config: {hooks_path}"

    config = json.loads(hooks_path.read_text(encoding="utf-8"))
    commands = [
        handler.get("command", "")
        for group in config.values()
        for entry in group.get("PreToolUse", [])
        for handler in entry.get("hooks", [])
    ]
    assert any("block-dangerous-commands" in c for c in commands), (
        "Antigravity .agents/hooks.json must wire the shared dangerous-command hook on PreToolUse"
    )
    # The hook is agy's only gate (delegated invocations pass
    # --dangerously-skip-permissions), so its path must not depend on the CWD
    # agy happens to run handlers from. A bare "../tools/..." satisfied the
    # assertion above while resolving outside the repo from any other CWD.
    assert any("$(git rev-parse --show-toplevel)" in c for c in commands), (
        "Antigravity hook path must resolve independently of the handler CWD"
    )

    matchers = [
        entry.get("matcher", "")
        for group in config.values()
        for entry in group.get("PreToolUse", [])
    ]
    assert any("run_command" in m for m in matchers), (
        "Antigravity hook matcher must target the run_command tool"
    )


def test_copilot_hooks_json_pins_its_hook_path() -> None:
    """Copilot's wiring must keep an explicit cwd so its relative path resolves."""
    hooks_path = REPO_ROOT / ".github" / "hooks" / "copilot-hooks.json"
    assert hooks_path.exists(), f"Missing Copilot hooks config: {hooks_path}"

    config = json.loads(hooks_path.read_text(encoding="utf-8"))
    entries = config.get("hooks", {}).get("preToolUse", [])
    assert entries, "Copilot config must define a preToolUse hook"

    for entry in entries:
        assert "block-dangerous-commands" in entry.get("bash", ""), (
            "Copilot preToolUse hook must wire the shared dangerous-command hook"
        )
        # The path is relative, so the cwd pin is what makes it resolve.
        assert entry.get("cwd"), (
            "Copilot hook uses a relative path and must pin cwd, or it resolves "
            "against an unstated working directory"
        )


def test_stdout_contract_wirings_route_through_the_launcher() -> None:
    """Antigravity and Copilot must invoke the launcher, not the .py directly.

    Both block only on a stdout deny payload, so a hook that cannot start reads
    as "allow". The launcher denies in that case; calling the .py directly does
    not, because a script that never runs cannot emit its own deny.

    Only the hosts this project wires are checked (#690); the launcher itself is
    asserted either way, since it is what makes the contract fail closed.
    """
    wirings: list[tuple[str, list[str]]] = []

    if agent_is_present("antigravity"):
        agy = json.loads((REPO_ROOT / ".agents" / "hooks.json").read_text(encoding="utf-8"))
        wirings.append(
            (
                "Antigravity",
                [
                    handler.get("command", "")
                    for group in agy.values()
                    for entry in group.get("PreToolUse", [])
                    for handler in entry.get("hooks", [])
                ],
            )
        )

    if agent_is_present("copilot"):
        copilot = json.loads(
            (REPO_ROOT / ".github" / "hooks" / "copilot-hooks.json").read_text(encoding="utf-8")
        )
        wirings.append(
            (
                "Copilot",
                [e.get("bash", "") for e in copilot.get("hooks", {}).get("preToolUse", [])],
            )
        )

    for label, commands in wirings:
        assert any("block-dangerous-commands.sh" in c for c in commands), (
            f"{label} must route through the fail-closed launcher"
        )

    launcher = REPO_ROOT / "tools" / "hooks" / "ai" / "block-dangerous-commands.sh"
    assert launcher.exists(), f"Missing launcher: {launcher}"


def test_docs_document_antigravity_agent() -> None:
    """AI setup and command-blocking docs should register Antigravity as a supported agent."""
    ai_setup = (REPO_ROOT / "docs" / "development" / "AI_SETUP.md").read_text(encoding="utf-8")
    assert "Antigravity" in ai_setup
    assert ".agents/hooks.json" in ai_setup

    blocking = (REPO_ROOT / "docs" / "development" / "ai" / "command-blocking.md").read_text(
        encoding="utf-8"
    )
    assert ".agents/hooks.json" in blocking
    assert "write_to_file" in blocking


def test_multi_orchestrators_recognize_antigravity() -> None:
    """Every wired host's multi-* orchestrators offer antigravity as an agent.

    Skipped when the project does not wire Antigravity — there is nothing for the
    orchestrators to offer (#690).
    """
    skip_if_absent("antigravity")

    actions = ("plan", "review", "adversarial-review")
    multi_files: list[Path] = []
    if agent_is_present("claude"):
        multi_files += [REPO_ROOT / ".claude" / "commands" / f"multi-{a}.md" for a in actions]
    if agent_is_present("copilot"):
        multi_files += [REPO_ROOT / ".copilot" / "commands" / f"multi-{a}.md" for a in actions]
    multi_files += [REPO_ROOT / ".agents" / "skills" / f"multi-{a}" / "SKILL.md" for a in actions]

    for f in multi_files:
        content = f.read_text(encoding="utf-8")
        assert "`antigravity`" in content, f"{f} does not list antigravity as an allowed agent"
        assert "agy -p" in content, f"{f} has no agy invocation block"
