#!/usr/bin/env python3
"""
Test suite for the dangerous command blocking hook.

Run this after making changes to the lexer or patterns to verify behavior.

Usage (from any directory):
    python3 /path/to/project/tools/hooks/ai/test_hook.py
"""

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

# Test cases: (command, expected_result, description)
# expected_result: 'ALLOW' or 'BLOCK'
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
    ("doit release_dev", "BLOCK", "doit release_dev"),
    ("doit release_tag", "BLOCK", "doit release_tag"),
    ("doit release_pr", "BLOCK", "doit release_pr"),
    # === SHOULD ALLOW - Other doit commands ===
    ("doit check", "ALLOW", "doit check"),
    ("doit test", "ALLOW", "doit test"),
    ("doit pr", "ALLOW", "doit pr"),
    ("doit issue --type=bug", "ALLOW", "doit issue"),
    # === SHOULD BLOCK - Governance labels ===
    ("gh pr edit 123 --add-label ready-to-merge", "BLOCK", "add ready-to-merge"),
    ("gh pr edit --add-label ready-to-merge", "BLOCK", "add ready-to-merge no PR"),
    ("gh issue edit 45 --add-label ready-to-merge", "BLOCK", "issue ready-to-merge"),
    # === SHOULD ALLOW - Other labels ===
    ("gh pr edit 123 --add-label bug", "ALLOW", "add bug label"),
    ("gh pr edit 123 --add-label enhancement", "ALLOW", "add enhancement label"),
    # === SHOULD ALLOW - Other gh commands ===
    ("gh issue list", "ALLOW", "gh issue list"),
    ("gh pr list", "ALLOW", "gh pr list"),
    ("gh issue view 123", "ALLOW", "gh issue view"),
    ("gh pr view 456", "ALLOW", "gh pr view"),
    ("gh issue close 123", "ALLOW", "gh issue close"),
    ("gh pr close 123", "ALLOW", "gh pr close"),
]


def run_test(cmd: str, expected: str, desc: str) -> bool:
    """Run a single test and return True if it passed."""
    import json

    json_input = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
    result = subprocess.run(
        ["python3", str(HOOK_PATH)], input=json_input, capture_output=True, text=True
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


def main() -> int:
    """Run all tests and return exit code."""
    print(f"Testing hook: {HOOK_PATH}\n")
    print("=" * 80)

    passed = 0
    failed = 0

    for cmd, expected, desc in TESTS:
        if run_test(cmd, expected, desc):
            passed += 1
        else:
            failed += 1

    print("=" * 80)
    result_color = GREEN if failed == 0 else RED
    print(f"\n{result_color}Results: {passed} passed, {failed} failed{RESET}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
