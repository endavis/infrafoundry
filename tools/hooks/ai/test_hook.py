#!/usr/bin/env python3
"""
Test suite for the dangerous command blocking hook.

Run this after making changes to the lexer or patterns to verify behavior.

Usage (from any directory):
    python3 /path/to/project/tools/hooks/ai/test_hook.py

Pass ALLOW_AI_READY_TO_MERGE=1 to exercise the bypass path:
    ALLOW_AI_READY_TO_MERGE=1 python3 /path/to/project/tools/hooks/ai/test_hook.py
"""

import json
import os
import subprocess  # nosec B404 - needed to run hook for testing
import sys
from pathlib import Path

# ANSI color codes
RED = "\033[91m"
GREEN = "\033[92m"
RESET = "\033[0m"

# Find the hook to test (same directory as this test file)
# Use resolve() to get absolute path so it works from any directory
HOOK_PATH = (Path(__file__).parent / "block-dangerous-commands.py").resolve()

# ---------------------------------------------------------------------------
# Bash test cases: (command, expected_result, description)
# expected_result: 'ALLOW' or 'BLOCK'
# ---------------------------------------------------------------------------
TESTS = [
    # === SHOULD ALLOW - Safe commands ===
    ("git status", "ALLOW", "safe command"),
    ("git log --oneline", "ALLOW", "safe with flag"),
    # === SHOULD ALLOW - Dangerous patterns in quoted text ===
    ('git commit -m "text with --admin"', "ALLOW", "double quoted"),
    ('echo "--force flag"', "ALLOW", "double quoted 2"),
    ("echo '--no-verify test'", "ALLOW", "single quoted"),
    ('git commit -m "do not use --force"', "ALLOW", "flag in message"),
    # === SHOULD ALLOW - Heredocs (content inside quotes) ===
    (
        """git commit -m "$(cat <<'EOF'
--admin mentioned in docs
EOF
)\"""",
        "ALLOW",
        "heredoc with --admin",
    ),
    (
        '''doit pr --body="$(cat <<'EOF'
## Blocked Patterns
- `--admin` (bypasses branch protection)
- `rm -rf ~` (destructive)
EOF
)"''',
        "ALLOW",
        "heredoc with markdown",
    ),
    # === SHOULD ALLOW - Force push to feature branches ===
    ("git push --force origin feat/my-feature", "ALLOW", "force push feature branch"),
    ("git push -f origin fix/bugfix", "ALLOW", "-f push feature branch"),
    ("git push --force-with-lease origin dev", "ALLOW", "force-with-lease feature"),
    # === SHOULD BLOCK - Always dangerous flags ===
    ("gh pr merge --admin", "BLOCK", "actual --admin flag"),
    ("git commit --no-verify", "BLOCK", "actual --no-verify"),
    ("git reset --hard HEAD", "BLOCK", "git reset --hard"),
    # === SHOULD BLOCK - Force push to protected branches ===
    ("git push --force origin main", "BLOCK", "force push to main"),
    ("git push --force origin master", "BLOCK", "force push to master"),
    ("git push -f origin main", "BLOCK", "force push -f to main"),
    ("git push --force-with-lease origin main", "BLOCK", "force-with-lease to main"),
    ("git push --force", "BLOCK", "force push no branch"),
    ("git push -f", "BLOCK", "-f push no branch"),
    ("git push --force origin", "BLOCK", "force push origin only"),
    # === SHOULD BLOCK - Delete protected branches ===
    ("git push origin --delete main", "BLOCK", "delete remote main"),
    ("git push origin :main", "BLOCK", "delete main colon syntax"),
    ("git branch -D main", "BLOCK", "force delete local main"),
    ("git branch -d master", "BLOCK", "delete local master"),
    # === SHOULD ALLOW - Delete feature branches ===
    ("git push origin --delete feat/old-feature", "ALLOW", "delete remote feature"),
    ("git branch -D feat/old-feature", "ALLOW", "delete local feature"),
    # === SHOULD ALLOW - Merge with --ff-only (always safe) ===
    ("git merge --ff-only some-branch", "ALLOW", "merge --ff-only"),
    ("git merge --ff-only origin/main", "ALLOW", "merge --ff-only origin"),
    # === SHOULD ALLOW - Merge on feature branch (not protected) ===
    # Note: These tests assume we're NOT on main/master. If run on a protected
    # branch, these would be BLOCK instead. The hook checks current branch.
    ("git merge some-branch", "ALLOW", "merge on feature branch"),
    ("git merge origin/main", "ALLOW", "merge origin/main on feat"),
    # === SHOULD BLOCK - Direct gh issue/pr create/merge (use doit wrappers) ===
    ("gh issue create --title 'test'", "BLOCK", "gh issue create"),
    ("gh pr create --title 'test'", "BLOCK", "gh pr create"),
    ('gh issue create --title "test" --body "body"', "BLOCK", "gh issue create full"),
    ("gh pr create --fill", "BLOCK", "gh pr create fill"),
    ("gh pr merge 123", "BLOCK", "gh pr merge"),
    ("gh pr merge --squash", "BLOCK", "gh pr merge squash"),
    ("gh pr merge 123 --squash --delete-branch", "BLOCK", "gh pr merge full"),
    # === SHOULD BLOCK - uv add (dependencies require user approval) ===
    ("uv add requests", "BLOCK", "uv add single package"),
    ("uv add requests httpx", "BLOCK", "uv add multiple packages"),
    ("uv add 'requests>=2.0'", "BLOCK", "uv add with version"),
    ("uv add --dev pytest", "BLOCK", "uv add dev dependency"),
    # === SHOULD ALLOW - Other uv commands ===
    ("uv sync", "ALLOW", "uv sync"),
    ("uv run pytest", "ALLOW", "uv run"),
    ("uv pip list", "ALLOW", "uv pip list"),
    ("uv remove requests", "ALLOW", "uv remove"),
    # === SHOULD BLOCK - doit release (releases require user to run manually) ===
    ("doit release", "BLOCK", "doit release"),
    ("doit release --dry-run", "BLOCK", "doit release dry-run"),
    ("doit release_tag", "BLOCK", "doit release_tag"),
    # === SHOULD ALLOW - Other doit commands ===
    ("doit check", "ALLOW", "doit check"),
    ("doit test", "ALLOW", "doit test"),
    ("doit pr", "ALLOW", "doit pr"),
    ("doit issue --type=bug", "ALLOW", "doit issue"),
    # === SHOULD BLOCK - Governance labels (no env var) ===
    ("gh pr edit 123 --add-label ready-to-merge", "BLOCK", "add ready-to-merge"),
    ("gh pr edit --add-label ready-to-merge", "BLOCK", "add ready-to-merge no PR"),
    ("gh issue edit 45 --add-label ready-to-merge", "BLOCK", "issue ready-to-merge"),
    # === SHOULD ALLOW - Other labels ===
    ("gh pr edit 123 --add-label bug", "ALLOW", "add bug label"),
    ("gh pr edit 123 --add-label enhancement", "ALLOW", "add enhancement label"),
    # === SHOULD BLOCK - Nested/chained commands ===
    ("cd /path && doit release", "BLOCK", "chained doit release"),
    ("cd /path && gh pr create --fill", "BLOCK", "chained gh pr create"),
    ("cd /path && uv add requests", "BLOCK", "chained uv add"),
    ("cd /path && git push --force origin main", "BLOCK", "chained force push main"),
    ("git status; git push --force origin main", "BLOCK", "semicolon force push main"),
    ("git status; git push origin --delete main", "BLOCK", "semicolon delete main"),
    ("git log; git branch -D main", "BLOCK", "semicolon branch -D main"),
    # === SHOULD ALLOW - Nested/chained safe commands ===
    ("cd /path && doit check", "ALLOW", "chained doit check"),
    ("cd /path && git status", "ALLOW", "chained git status"),
    ("git status; git push origin feat/branch", "ALLOW", "semicolon push feature"),
    # === SHOULD ALLOW - Other gh commands ===
    ("gh issue list", "ALLOW", "gh issue list"),
    ("gh pr list", "ALLOW", "gh pr list"),
    ("gh issue view 123", "ALLOW", "gh issue view"),
    ("gh pr view 456", "ALLOW", "gh pr view"),
    ("gh issue close 123", "ALLOW", "gh issue close"),
    ("gh pr close 123", "ALLOW", "gh pr close"),
    # === SHOULD BLOCK - Bash env-var persistence (no env var) ===
    (
        'echo "ALLOW_AI_READY_TO_MERGE=1" >> ~/.bashrc',
        "BLOCK",
        "persist rtm var to .bashrc",
    ),
    (
        "tee -a ~/.zshrc <<< 'export ALLOW_AI_READY_TO_MERGE=1'",
        "BLOCK",
        "persist rtm var to .zshrc",
    ),
    # === SHOULD ALLOW - Bash write to non-protected target ===
    (
        'echo "ALLOW_AI_READY_TO_MERGE=1" >> /tmp/notes.txt',
        "ALLOW",
        "rtm var to non-protected file",
    ),
    # === SHOULD ALLOW - Bash write to protected file but no var name ===
    (
        'echo "PATH=/foo" >> ~/.bashrc',
        "ALLOW",
        "no var name write to .bashrc",
    ),
    # === SHOULD ALLOW - var name appears but no write to a protected target ===
    # `git add` lists protected files as positional args and the commit message
    # mentions the var name; this is staging code + composing a commit, not a
    # write that persists the var into the file system.
    (
        'git add .claude/settings.json && git commit -m "doc: mention ALLOW_AI_READY_TO_MERGE"',
        "ALLOW",
        "git add + commit message mentions var",
    ),
    (
        'echo "ALLOW_AI_READY_TO_MERGE is the env var" ',
        "ALLOW",
        "var name in echo without redirect",
    ),
    (
        "grep ALLOW_AI_READY_TO_MERGE .claude/settings.json",
        "ALLOW",
        "grep var name in protected file",
    ),
    (
        "cat .claude/settings.json | head -5 # ALLOW_AI_READY_TO_MERGE",
        "ALLOW",
        "read protected file with var in comment",
    ),
    # === SHOULD BLOCK - Additional persistence write patterns ===
    (
        "sed -i 's/X/ALLOW_AI_READY_TO_MERGE=1/' ~/.bashrc",
        "BLOCK",
        "sed -i in-place edit on .bashrc",
    ),
    (
        "python -c \"open('/home/me/.bashrc','a').write('ALLOW_AI_READY_TO_MERGE=1')\"",
        "BLOCK",
        "python -c writing var to .bashrc",
    ),
    (
        'echo "ALLOW_AI_READY_TO_MERGE=1" >>~/.bashrc',
        "BLOCK",
        "no-space redirect to .bashrc",
    ),
    # === SHOULD ALLOW - similar but not actually writing ===
    (
        "sed 's/X/ALLOW_AI_READY_TO_MERGE=1/' ~/.bashrc",
        "ALLOW",
        "sed without -i (read-only) on .bashrc",
    ),
    (
        "python script.py # ALLOW_AI_READY_TO_MERGE",
        "ALLOW",
        "python without -c flag",
    ),
    (
        "python -c \"print('ALLOW_AI_READY_TO_MERGE')\"",
        "ALLOW",
        "python -c print var name only",
    ),
]

# ---------------------------------------------------------------------------
# Governance label bypass tests — run with ALLOW_AI_READY_TO_MERGE=1 in env
# ---------------------------------------------------------------------------
# These are like TESTS but the bypass env var is injected per subprocess call.
BYPASS_TESTS = [
    # === SHOULD ALLOW when env var is set ===
    (
        "gh pr edit 123 --add-label ready-to-merge",
        "ALLOW",
        "rtm label with bypass var",
    ),
    (
        "gh pr edit --add-label ready-to-merge",
        "ALLOW",
        "rtm label no PR with bypass var",
    ),
    (
        "gh issue edit 45 --add-label ready-to-merge",
        "ALLOW",
        "issue rtm label with bypass var",
    ),
]

# ---------------------------------------------------------------------------
# File-edit test cases: (tool_name, tool_input_dict, expected, description)
# expected: 'ALLOW' or 'BLOCK'
# ---------------------------------------------------------------------------
EDIT_TESTS = [
    # Edit ~/.bashrc adding the env var name → BLOCK
    (
        "Edit",
        {
            "file_path": "~/.bashrc",
            "old_string": "",
            "new_string": "export ALLOW_AI_READY_TO_MERGE=1",
        },
        "BLOCK",
        "Edit .bashrc adding rtm var",
    ),
    # Edit .envrc adding the var → BLOCK
    (
        "Edit",
        {
            "file_path": ".envrc",
            "old_string": "",
            "new_string": "export ALLOW_AI_READY_TO_MERGE=1",
        },
        "BLOCK",
        "Edit .envrc adding rtm var",
    ),
    # Write .claude/settings.local.json containing the var → BLOCK
    (
        "Write",
        {
            "file_path": ".claude/settings.local.json",
            "content": '{"env": {"ALLOW_AI_READY_TO_MERGE": "1"}}',
        },
        "BLOCK",
        "Write claude settings.local.json with rtm var",
    ),
    # Edit ~/.bashrc with unrelated content (no env var name) → ALLOW
    (
        "Edit",
        {
            "file_path": "~/.bashrc",
            "old_string": "",
            "new_string": "export PATH=$PATH:/usr/local/bin",
        },
        "ALLOW",
        "Edit .bashrc unrelated content",
    ),
    # Edit /tmp/scratch.txt adding the var (target not protected) → ALLOW
    (
        "Edit",
        {
            "file_path": "/tmp/scratch.txt",  # nosec B108 - test data, not a real tmp file
            "old_string": "",
            "new_string": "export ALLOW_AI_READY_TO_MERGE=1",
        },
        "ALLOW",
        "Edit non-protected file with rtm var",
    ),
    # MultiEdit on ~/.zshrc where one edit adds the var → BLOCK
    (
        "MultiEdit",
        {
            "file_path": "~/.zshrc",
            "edits": [
                {"old_string": "# aliases", "new_string": "# aliases\nalias ll='ls -la'"},
                {
                    "old_string": "# env",
                    "new_string": "# env\nexport ALLOW_AI_READY_TO_MERGE=1",
                },
            ],
        },
        "BLOCK",
        "MultiEdit .zshrc one edit has rtm var",
    ),
    # Gemini write_file to .envrc → BLOCK
    (
        "write_file",
        {
            "file_path": ".envrc",
            "content": "export ALLOW_AI_READY_TO_MERGE=1\n",
        },
        "BLOCK",
        "Gemini write_file to .envrc with rtm var",
    ),
    # Gemini replace on ~/.bashrc → BLOCK
    (
        "replace",
        {
            "file_path": "~/.bashrc",
            "old_string": "",
            "new_string": "export ALLOW_AI_READY_TO_MERGE=1",
        },
        "BLOCK",
        "Gemini replace .bashrc with rtm var",
    ),
    # Gemini write_file to unprotected file → ALLOW
    (
        "write_file",
        {
            "file_path": "/tmp/scratch.txt",  # nosec B108 - test data, not a real tmp file
            "content": "export ALLOW_AI_READY_TO_MERGE=1\n",
        },
        "ALLOW",
        "Gemini write_file non-protected with rtm var",
    ),
    # Copilot format: Edit via toolName/toolArgs → BLOCK
    # (tested in run_edit_test via copilot_format flag)
]

# Copilot-format file-edit tests: same shape but using camelCase hook input
# (tool_name, tool_input_dict, expected, description)
COPILOT_EDIT_TESTS = [
    (
        "Edit",
        {
            "file_path": "~/.bashrc",
            "old_string": "",
            "new_string": "export ALLOW_AI_READY_TO_MERGE=1",
        },
        "BLOCK",
        "Copilot Edit .bashrc adding rtm var",
    ),
    (
        "Edit",
        {
            "file_path": "~/.bashrc",
            "old_string": "",
            "new_string": "export PATH=$PATH:/usr/local/bin",
        },
        "ALLOW",
        "Copilot Edit .bashrc unrelated content",
    ),
]


def run_test(
    cmd: str,
    expected: str,
    desc: str,
    extra_env: dict[str, str] | None = None,
) -> bool:
    """Run a single Bash-tool test and return True if it passed."""
    json_input = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
    env = {**os.environ, **(extra_env or {})}
    result = subprocess.run(
        ["python3", str(HOOK_PATH)],
        input=json_input,
        capture_output=True,
        text=True,
        env=env,
    )
    actual = "BLOCK" if result.returncode == 2 else "ALLOW"
    passed = actual == expected
    mark = "+" if passed else "X"
    color = GREEN if passed else RED

    # Truncate command for display
    cmd_display = cmd.replace("\n", "\\n")
    if len(cmd_display) > 50:
        cmd_display = cmd_display[:47] + "..."

    print(f"{color}{mark} {actual:5} (expected {expected:5}) | {desc:25} | {cmd_display}{RESET}")

    if not passed:
        print(f"{RED}  stderr: {result.stderr[:200] if result.stderr else '(none)'}{RESET}")

    return passed


def run_edit_test(
    tool_name: str,
    tool_input: dict,
    expected: str,
    desc: str,
    copilot_format: bool = False,
    extra_env: dict[str, str] | None = None,
) -> bool:
    """Run a single file-edit-tool test and return True if it passed."""
    if copilot_format:
        json_input = json.dumps(
            {
                "toolName": tool_name,
                "toolArgs": json.dumps(tool_input),
            }
        )
    else:
        json_input = json.dumps(
            {
                "tool_name": tool_name,
                "tool_input": tool_input,
            }
        )

    env = {**os.environ, **(extra_env or {})}
    result = subprocess.run(
        ["python3", str(HOOK_PATH)],
        input=json_input,
        capture_output=True,
        text=True,
        env=env,
    )
    # Copilot denials return exit 0 with JSON stdout; non-copilot denials return exit 2
    if copilot_format:
        try:
            out = json.loads(result.stdout)
            actual = "BLOCK" if out.get("permissionDecision") == "deny" else "ALLOW"
        except (json.JSONDecodeError, AttributeError):
            actual = "ALLOW"
    else:
        actual = "BLOCK" if result.returncode == 2 else "ALLOW"

    passed = actual == expected
    mark = "+" if passed else "X"
    color = GREEN if passed else RED

    label = f"[copilot] {desc}" if copilot_format else desc
    print(f"{color}{mark} {actual:5} (expected {expected:5}) | {label:35} | {tool_name}{RESET}")

    if not passed:
        print(f"{RED}  stderr: {result.stderr[:200] if result.stderr else '(none)'}{RESET}")
        if copilot_format and result.stdout:
            print(f"{RED}  stdout: {result.stdout[:200]}{RESET}")

    return passed


def main() -> int:
    """Run all tests and return exit code."""
    print(f"Testing hook: {HOOK_PATH}\n")
    print("=" * 80)

    passed = 0
    failed = 0

    # --- Bash command tests (no env var) ---
    print("\n[Bash command tests — no bypass env var]")
    for cmd, expected, desc in TESTS:
        if run_test(cmd, expected, desc):
            passed += 1
        else:
            failed += 1

    # --- Governance label bypass tests (env var injected per test) ---
    print("\n[Governance label bypass tests — ALLOW_AI_READY_TO_MERGE=1 injected]")
    bypass_env = {"ALLOW_AI_READY_TO_MERGE": "1"}
    for cmd, expected, desc in BYPASS_TESTS:
        if run_test(cmd, expected, desc, extra_env=bypass_env):
            passed += 1
        else:
            failed += 1

    # --- File-edit tests (Claude/Codex/Gemini format) ---
    print("\n[File-edit tests — Claude/Codex/Gemini format]")
    for tool_name, tool_input, expected, desc in EDIT_TESTS:
        if run_edit_test(tool_name, tool_input, expected, desc):
            passed += 1
        else:
            failed += 1

    # --- File-edit tests (Copilot format) ---
    print("\n[File-edit tests — Copilot format]")
    for tool_name, tool_input, expected, desc in COPILOT_EDIT_TESTS:
        if run_edit_test(tool_name, tool_input, expected, desc, copilot_format=True):
            passed += 1
        else:
            failed += 1

    print("=" * 80)
    result_color = GREEN if failed == 0 else RED
    print(f"\n{result_color}Results: {passed} passed, {failed} failed{RESET}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
