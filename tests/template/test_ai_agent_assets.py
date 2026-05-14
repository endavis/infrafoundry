"""Tests for AI agent workflow assets checked into the template."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_codex_workflow_skills_exist() -> None:
    """Codex workflow skills should be present in the repo skills directory."""
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
    """multi-* orchestrators (plan, review, adversarial-review) should exist for all 4 hosts."""
    paths = [
        # Claude
        REPO_ROOT / ".claude" / "commands" / "multi-plan.md",
        REPO_ROOT / ".claude" / "commands" / "multi-review.md",
        REPO_ROOT / ".claude" / "commands" / "multi-adversarial-review.md",
        # Gemini
        REPO_ROOT / ".gemini" / "commands" / "multi-plan.toml",
        REPO_ROOT / ".gemini" / "commands" / "multi-review.toml",
        REPO_ROOT / ".gemini" / "commands" / "multi-adversarial-review.toml",
        # Copilot
        REPO_ROOT / ".copilot" / "commands" / "multi-plan.md",
        REPO_ROOT / ".copilot" / "commands" / "multi-review.md",
        REPO_ROOT / ".copilot" / "commands" / "multi-adversarial-review.md",
        # Codex
        REPO_ROOT / ".agents" / "skills" / "multi-plan" / "SKILL.md",
        REPO_ROOT / ".agents" / "skills" / "multi-review" / "SKILL.md",
        REPO_ROOT / ".agents" / "skills" / "multi-adversarial-review" / "SKILL.md",
    ]

    for path in paths:
        assert path.exists(), f"Missing multi-orchestrator file: {path}"


def test_self_action_grid_exists() -> None:
    """All 16 self-action files (4 agents x 4 actions) should exist."""
    paths = [
        # Claude self-action
        REPO_ROOT / ".claude" / "commands" / "claude" / "plan.md",
        REPO_ROOT / ".claude" / "commands" / "claude" / "implement.md",
        REPO_ROOT / ".claude" / "commands" / "claude" / "review.md",
        REPO_ROOT / ".claude" / "commands" / "claude" / "adversarial-review.md",
        # Gemini self-action
        REPO_ROOT / ".gemini" / "commands" / "gemini" / "plan.toml",
        REPO_ROOT / ".gemini" / "commands" / "gemini" / "implement.toml",
        REPO_ROOT / ".gemini" / "commands" / "gemini" / "review.toml",
        REPO_ROOT / ".gemini" / "commands" / "gemini" / "adversarial-review.toml",
        # Copilot self-action
        REPO_ROOT / ".copilot" / "commands" / "copilot" / "plan.md",
        REPO_ROOT / ".copilot" / "commands" / "copilot" / "implement.md",
        REPO_ROOT / ".copilot" / "commands" / "copilot" / "review.md",
        REPO_ROOT / ".copilot" / "commands" / "copilot" / "adversarial-review.md",
        # Codex self-action (skills)
        REPO_ROOT / ".agents" / "skills" / "codex-plan" / "SKILL.md",
        REPO_ROOT / ".agents" / "skills" / "codex-implement" / "SKILL.md",
        REPO_ROOT / ".agents" / "skills" / "codex-review" / "SKILL.md",
        REPO_ROOT / ".agents" / "skills" / "codex-adversarial-review" / "SKILL.md",
    ]

    for path in paths:
        assert path.exists(), f"Missing self-action file: {path}"


def test_retired_self_action_aliases_are_removed() -> None:
    """The old ghissue-plan/implement/close self-action aliases should be gone."""
    removed = [
        REPO_ROOT / ".claude" / "commands" / "ghissue-plan.md",
        REPO_ROOT / ".claude" / "commands" / "ghissue-implement.md",
        REPO_ROOT / ".claude" / "commands" / "ghissue-close.md",
        REPO_ROOT / ".gemini" / "commands" / "ghissue-plan.toml",
        REPO_ROOT / ".gemini" / "commands" / "ghissue-implement.toml",
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
        REPO_ROOT / ".claude" / "commands" / "ghissue-gemini-review.md",
        REPO_ROOT / ".gemini" / "commands" / "ghissue-plan-stdout.toml",
        REPO_ROOT / ".gemini" / "commands" / "ghissue-review-pr.toml",
    ]

    for path in removed:
        assert not path.exists(), f"Retired file should not exist: {path}"


def test_retired_workflow_step_aliases_are_removed() -> None:
    """The old ghissue-finalize/ghissue-status workflow steps should be renamed to ghi-*."""
    removed = [
        REPO_ROOT / ".claude" / "commands" / "ghissue-finalize.md",
        REPO_ROOT / ".claude" / "commands" / "ghissue-status.md",
        REPO_ROOT / ".gemini" / "commands" / "ghissue-finalize.toml",
        REPO_ROOT / ".agents" / "skills" / "ghissue-finalize" / "SKILL.md",
    ]

    for path in removed:
        assert not path.exists(), f"Retired workflow step file should not exist: {path}"


def test_codex_config_keeps_shared_dangerous_command_hook() -> None:
    """Codex config should keep the shared dangerous-command hook wired."""
    config = (REPO_ROOT / ".codex" / "config.toml").read_text(encoding="utf-8")

    assert "codex_hooks = true" in config
    assert "[[hooks.PreToolUse]]" in config
    assert "block-dangerous-commands.py" in config


def test_codex_config_uses_current_schema() -> None:
    """Codex config should avoid obsolete keys from older Codex releases."""
    config = (REPO_ROOT / ".codex" / "config.toml").read_text(encoding="utf-8")

    assert 'approval_policy = "untrusted"' in config
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
