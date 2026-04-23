#!/usr/bin/env python3
"""
Claude Code PreToolUse hook to block dangerous command patterns.

This hook intercepts Bash commands before execution and blocks those
containing dangerous flags that could bypass security controls.

Uses shlex to properly parse shell quoting, then checks for dangerous
patterns as standalone tokens (not embedded in quoted argument values).

Exit codes:
  0 - Allow command
  2 - Block command (shows stderr to Claude)

For full documentation, see: docs/development/ai/command-blocking.md
"""

import json
import os
import shlex
import subprocess  # nosec B404 - needed for git branch detection
import sys
from pathlib import Path

# Protected branches - operations on these require extra scrutiny
PROTECTED_BRANCHES = {"main", "master"}

# Dangerous flags that must appear as exact standalone tokens
DANGEROUS_FLAGS = {
    "--admin": "Bypasses branch protection rules",
    "--no-verify": "Skips pre-commit/pre-push hooks",
    "--hard": "Hard reset - can lose uncommitted changes",
}

# Dangerous token sequences (checked in order)
# Format: (token_sequence, description)
DANGEROUS_SEQUENCES = [
    (["rm", "-rf", "/"], "Destructive: removes root filesystem"),
    (["rm", "-rf", "~"], "Destructive: removes home directory"),
    (["sudo", "rm"], "Privileged deletion"),
]

# Force push flags
FORCE_PUSH_FLAGS = {"--force", "-f", "--force-with-lease"}

# Blocked workflow commands - use doit wrappers or require user approval
BLOCKED_WORKFLOW_COMMANDS = {
    ("gh", "issue", "create"): "Use 'doit issue --type=<type>' instead of 'gh issue create'",
    ("gh", "pr", "create"): "Use 'doit pr' instead of 'gh pr create'",
    ("gh", "pr", "merge"): "Use 'doit pr_merge' instead of 'gh pr merge'",
    ("uv", "add"): (
        "Adding dependencies requires user approval. "
        "Suggest the package and let the user run 'uv add <package>' manually."
    ),
    ("doit", "release"): (
        "Releases must be run manually by the user, not by AI agents. "
        "AI can help prepare (update changelog, verify CI) but not execute releases."
    ),
    ("doit", "release_tag"): "Releases must be run manually by the user, not by AI agents.",
}

# Governance labels that require human approval - AI should never add these
GOVERNANCE_LABELS = {
    "ready-to-merge": (
        "The 'ready-to-merge' label is a governance control requiring human approval. "
        "Add this label manually via 'gh pr edit --add-label ready-to-merge' or the GitHub web UI."
    ),
}


def tokenize(command: str) -> list[str]:
    """
    Tokenize command using shlex for proper shell quote handling.

    shlex.split() correctly handles:
    - Double quoted strings: "text with --admin"
    - Single quoted strings: 'text with --force'
    - Embedded quotes: --body="value"
    - Escape sequences

    Returns list of tokens with quotes stripped from values.
    """
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        # Fallback for malformed quotes - try non-POSIX mode
        try:
            return shlex.split(command, posix=False)
        except ValueError:
            # Last resort - simple whitespace split
            return command.split()


def check_dangerous_flags(tokens: list[str]) -> tuple[bool, str]:
    """
    Check if any dangerous flag appears as a standalone token.

    A flag in a quoted argument value (e.g., -m "--admin mentioned")
    becomes part of a larger token and won't match.
    """
    for token in tokens:
        if token in DANGEROUS_FLAGS:
            return True, DANGEROUS_FLAGS[token]
    return False, ""


def check_dangerous_sequences(tokens: list[str]) -> tuple[bool, str]:
    """
    Check if dangerous token sequences appear in the command.

    Looks for consecutive tokens matching dangerous patterns.
    """
    tokens_lower = [t.lower() for t in tokens]

    for sequence, reason in DANGEROUS_SEQUENCES:
        seq_len = len(sequence)
        for i in range(len(tokens_lower) - seq_len + 1):
            if tokens_lower[i : i + seq_len] == [s.lower() for s in sequence]:
                return True, reason
    return False, ""


def check_push_to_protected(tokens: list[str]) -> tuple[bool, str]:
    """
    Check if command is a push (regular or force) while on a protected branch.

    Blocks any git push when the current branch is a protected branch.
    Force pushes to protected branches are also blocked even from feature branches.

    Scans all positions to handle chained commands (e.g., git status; git push --force).
    """
    tokens_lower = [t.lower() for t in tokens]

    # Must be a git push command (not git stash push, etc.)
    if "git" not in tokens_lower or "push" not in tokens_lower:
        return False, ""

    # Find ALL positions where git + push appear as a pair
    for git_idx in range(len(tokens_lower) - 1):
        if tokens_lower[git_idx] != "git":
            continue

        # Ensure "push" is the git subcommand, not part of another command like "git stash push"
        subcommand_idx = git_idx + 1
        if tokens_lower[subcommand_idx] != "push":
            continue

        # Determine the end of this git push command (next git/doit/gh/uv token or end)
        cmd_end = len(tokens)
        for j in range(subcommand_idx + 1, len(tokens_lower)):
            # A new command starts at a token that is a known command root
            # Also handle shell operators that got merged with tokens (e.g., "status;")
            if tokens_lower[j] in ("git", "doit", "gh", "uv"):
                cmd_end = j
                break
        cmd_tokens = tokens[git_idx:cmd_end]

        # Check if any force flag is present in this git push command
        has_force_flag = any(flag in cmd_tokens for flag in FORCE_PUSH_FLAGS)

        # Look for branch name in tokens after 'push'
        # Skip flags (tokens starting with -)
        push_idx = subcommand_idx
        after_push = [t for t in tokens[push_idx + 1 : cmd_end] if not t.startswith("-")]

        # Check if explicitly pushing to a protected branch
        for token in after_push:
            # Handle origin/main format
            branch = token.split("/")[-1] if "/" in token else token

            if branch.lower() in PROTECTED_BRANCHES:
                action = "Force push" if has_force_flag else "Push"
                return True, f"{action} to protected branch '{branch}'"

        # Check if currently on a protected branch (catches bare `git push`)
        current_branch = get_current_branch()
        if (
            current_branch
            and current_branch.lower() in PROTECTED_BRANCHES
            and (not after_push or (len(after_push) == 1 and after_push[0] == "origin"))
        ):
            action = "Force push" if has_force_flag else "Push"
            return True, (
                f"{action} while on protected branch '{current_branch}'. "
                f"Create a feature branch first"
            )

        # Force push without explicit branch from a feature branch — block as safety
        if has_force_flag and (
            not after_push or (len(after_push) == 1 and after_push[0] == "origin")
        ):
            return True, "Force push without explicit branch (could affect protected branch)"

    return False, ""


def check_delete_protected_branch(tokens: list[str]) -> tuple[bool, str]:
    """
    Check if command deletes a protected branch (local or remote).

    Catches:
    - git push origin --delete main
    - git push origin :main
    - git branch -D main
    - git branch -d main

    Scans all positions to handle chained commands (e.g., git log; git push origin --delete main).
    """
    tokens_lower = [t.lower() for t in tokens]

    # Scan for all git token positions
    for git_idx in range(len(tokens_lower)):
        if tokens_lower[git_idx] != "git":
            continue

        if git_idx + 1 >= len(tokens_lower):
            continue

        subcommand = tokens_lower[git_idx + 1]

        # Determine the end of this git command (next command root or end)
        cmd_end = len(tokens)
        for j in range(git_idx + 2, len(tokens_lower)):
            if tokens_lower[j] in ("git", "doit", "gh", "uv"):
                cmd_end = j
                break
        cmd_tokens = tokens[git_idx:cmd_end]
        cmd_tokens_lower = tokens_lower[git_idx:cmd_end]

        # Check for remote branch deletion: git push origin --delete main
        if subcommand == "push" and "--delete" in cmd_tokens_lower:
            for token in cmd_tokens:
                if token.lower() in PROTECTED_BRANCHES:
                    return True, f"Deleting protected remote branch '{token}'"

        # Check for remote branch deletion with colon syntax: git push origin :main
        if subcommand == "push":
            for token in cmd_tokens:
                if token.startswith(":") and token[1:].lower() in PROTECTED_BRANCHES:
                    return True, f"Deleting protected remote branch '{token[1:]}'"

        # Check for local branch deletion: git branch -D main or git branch -d main
        if subcommand == "branch" and ("-d" in cmd_tokens_lower or "-D" in cmd_tokens):
            for token in cmd_tokens:
                if token.lower() in PROTECTED_BRANCHES:
                    return True, f"Deleting protected local branch '{token}'"

    return False, ""


def get_current_branch() -> str | None:
    """
    Get the current git branch name.

    Returns None if not in a git repository or in detached HEAD state.
    """
    try:
        result = subprocess.run(  # nosec B603 B607 - trusted git command
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def check_blocked_workflow_commands(tokens: list[str]) -> tuple[bool, str]:
    """
    Check if command uses blocked workflow commands.

    These commands should use doit wrappers instead of direct gh commands.
    Scans all positions to catch commands chained with && or ;.
    """
    tokens_lower = [t.lower() for t in tokens]

    for cmd_tuple, reason in BLOCKED_WORKFLOW_COMMANDS.items():
        cmd_len = len(cmd_tuple)
        for i in range(len(tokens_lower) - cmd_len + 1):
            if tuple(tokens_lower[i : i + cmd_len]) == cmd_tuple:
                return True, reason
    return False, ""


def check_governance_labels(tokens: list[str]) -> tuple[bool, str]:
    """
    Check if command attempts to add a governance label.

    Governance labels (like 'ready-to-merge') require human approval and
    should never be added by AI agents.
    """
    tokens_lower = [t.lower() for t in tokens]

    # Check for: gh pr edit --add-label <governance-label>
    # or: gh issue edit --add-label <governance-label>
    if "gh" not in tokens_lower:
        return False, ""

    if "edit" not in tokens_lower:
        return False, ""

    if "--add-label" not in tokens_lower:
        return False, ""

    # Check if any governance label is being added
    for label, reason in GOVERNANCE_LABELS.items():
        if label.lower() in tokens_lower:
            return True, reason

    return False, ""


def check_merge_to_protected(tokens: list[str]) -> tuple[bool, str]:
    """
    Check if command is a merge that would create a merge commit on a protected branch.

    Protected branches often require linear history (no merge commits).
    Blocks `git merge` on protected branches unless --ff-only is specified.
    """
    tokens_lower = [t.lower() for t in tokens]

    # Must be a git merge command
    if "git" not in tokens_lower or "merge" not in tokens_lower:
        return False, ""

    # Allow if --ff-only is specified (fast-forward only, no merge commit)
    if "--ff-only" in tokens_lower:
        return False, ""

    # Check if we're on a protected branch
    current_branch = get_current_branch()
    if current_branch and current_branch.lower() in PROTECTED_BRANCHES:
        return True, (
            f"Merge on protected branch '{current_branch}' would create merge commit. "
            f"Use --ff-only for fast-forward merge, or merge via PR"
        )

    return False, ""


def check_command(command: str) -> tuple[bool, str]:
    """
    Check if command contains dangerous patterns.

    Uses shlex to tokenize, then checks for:
    1. Dangerous flags as standalone tokens
    2. Dangerous token sequences
    3. Push to protected branches (regular or force)
    4. Deletion of protected branches
    5. Merge commits on protected branches
    6. Blocked workflow commands
    7. Governance labels

    Returns:
        (is_dangerous, reason)
    """
    tokens = tokenize(command)

    # Check for dangerous standalone flags
    is_dangerous, reason = check_dangerous_flags(tokens)
    if is_dangerous:
        return True, reason

    # Check for dangerous sequences
    is_dangerous, reason = check_dangerous_sequences(tokens)
    if is_dangerous:
        return True, reason

    # Check for push to protected branches (regular or force)
    is_dangerous, reason = check_push_to_protected(tokens)
    if is_dangerous:
        return True, reason

    # Check for deletion of protected branches
    is_dangerous, reason = check_delete_protected_branch(tokens)
    if is_dangerous:
        return True, reason

    # Check for merge commits on protected branches
    is_dangerous, reason = check_merge_to_protected(tokens)
    if is_dangerous:
        return True, reason

    # Check for blocked workflow commands
    is_dangerous, reason = check_blocked_workflow_commands(tokens)
    if is_dangerous:
        return True, reason

    # Check for governance labels
    is_dangerous, reason = check_governance_labels(tokens)
    if is_dangerous:
        return True, reason

    return False, ""


def _parse_input(input_data: dict) -> tuple[str, str]:
    """
    Parse tool name and command from hook input.

    Handles two input formats:
    - Claude/Gemini: {"tool_name": "Bash", "tool_input": {"command": "..."}}
    - Copilot CLI:   {"toolName": "bash", "toolArgs": "{\"command\":\"...\"}"}

    Returns:
        (tool_name, command) tuple
    """
    # Copilot CLI format uses camelCase keys
    if "toolName" in input_data:
        tool_name = input_data.get("toolName", "")
        tool_args_raw = input_data.get("toolArgs", "{}")
        try:
            tool_args = (
                json.loads(tool_args_raw) if isinstance(tool_args_raw, str) else tool_args_raw
            )
        except json.JSONDecodeError:
            tool_args = {}
        return tool_name, tool_args.get("command", "")

    # Claude/Gemini format uses snake_case keys
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    return tool_name, tool_input.get("command", "")


def _is_copilot_format(input_data: dict) -> bool:
    """Return True if input uses Copilot CLI hook format (camelCase keys)."""
    return "toolName" in input_data


LOG_FILE = Path(__file__).parent / "hook-debug.jsonl"


def _log(entry: dict) -> None:
    """Append a JSON log entry. Only active when HOOK_DEBUG=1 is set."""
    if not os.environ.get("HOOK_BLOCKCOMMAND_DEBUG"):
        return
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # Never fail due to logging


def main() -> int:
    """Main entry point."""
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON input: {e}", file=sys.stderr)
        return 1

    tool_name, command = _parse_input(input_data)
    copilot_format = _is_copilot_format(input_data)

    _log(
        {
            "raw_input": input_data,
            "tool_name": tool_name,
            "command": command,
            "copilot_format": copilot_format,
        }
    )

    # Only check shell commands:
    # - "Bash" for Claude
    # - "run_shell_command" for Gemini
    # - "bash" for Copilot CLI
    if tool_name not in ("Bash", "run_shell_command", "bash"):
        return 0

    if not command:
        return 0

    is_dangerous, reason = check_command(command)
    if is_dangerous:
        if copilot_format:
            # Copilot CLI: deny via JSON output to stdout
            output = json.dumps(
                {
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Blocked: {reason}. If intentional, ask the user to run it manually."
                    ),
                }
            )
            print(output)
            return 0
        else:
            # Claude/Gemini: block via exit code 2 + stderr message
            print(
                f"BLOCKED: Command contains dangerous pattern.\n"
                f"Reason: {reason}\n"
                f"Command: {command}\n"
                f"\n"
                f"If this is intentional, ask the user to run it manually.",
                file=sys.stderr,
            )
            return 2  # Exit 2 = Block and show stderr to Claude/Gemini

    return 0


if __name__ == "__main__":
    sys.exit(main())
