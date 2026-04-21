#!/usr/bin/env python3
"""Lint blueprint scripts for portability contract violations.

Scans ``blueprints/**/*.sh`` for tools that
``docs/development/blueprint-script-portability.md`` calls out as
not-recommended (currently ``jq`` and ``yq``). False positives can be
silenced with an inline marker on the violating line:

.. code-block:: bash

    foo | jq -r '.bar'  # SCRIPT_PORTABILITY_EXEMPT: jq: <reason>

Or on the line directly above:

.. code-block:: bash

    # SCRIPT_PORTABILITY_EXEMPT: jq: <reason>
    foo | jq -r '.bar'

Comment-only lines are ignored unconditionally so headers, docstrings,
and prose can freely discuss the tools without tripping the lint.

Exits 0 if no unexempted violations were found, 1 otherwise.

Usage:
    python tools/lint_blueprint_portability.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DISALLOWED_TOOLS: tuple[str, ...] = ("jq", "yq")
EXEMPT_MARKER_RE = re.compile(r"#\s*SCRIPT_PORTABILITY_EXEMPT:\s*(\w+)\s*:")
COMMENT_LINE_RE = re.compile(r"^\s*#")
TOOL_RES: dict[str, re.Pattern[str]] = {
    tool: re.compile(rf"\b{tool}\b") for tool in DISALLOWED_TOOLS
}


def find_violations(text: str) -> list[tuple[int, str, str]]:
    """Return a list of (line_number, tool, line_content) violations.

    A violation is a non-comment line that matches one of the disallowed
    tool patterns and is not silenced by an inline or above-line
    SCRIPT_PORTABILITY_EXEMPT marker for the same tool.

    Args:
        text: Full contents of the script file.

    Returns:
        List of (1-based line number, tool name, stripped line content).
    """
    lines = text.splitlines()
    violations: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines, start=1):
        if COMMENT_LINE_RE.match(line):
            continue
        for tool, pattern in TOOL_RES.items():
            if not pattern.search(line):
                continue
            if _is_exempted(tool, line, lines, i):
                continue
            violations.append((i, tool, line.rstrip()))
    return violations


def _is_exempted(tool: str, line: str, all_lines: list[str], line_no: int) -> bool:
    """Check inline and above-line exemption markers for the given tool."""
    inline = EXEMPT_MARKER_RE.search(line)
    if inline and inline.group(1) == tool:
        return True
    if line_no >= 2:
        prev = all_lines[line_no - 2]
        prev_match = EXEMPT_MARKER_RE.search(prev)
        if prev_match and prev_match.group(1) == tool:
            return True
    return False


def lint_blueprints(blueprint_dir: Path) -> tuple[int, int]:
    """Lint all .sh files under blueprint_dir.

    Returns:
        Tuple of (total_violations, total_scripts_scanned).
    """
    scripts = sorted(blueprint_dir.rglob("*.sh"))
    total_violations = 0
    repo_root = blueprint_dir.parent
    for script in scripts:
        violations = find_violations(script.read_text())
        if not violations:
            continue
        rel = script.relative_to(repo_root)
        for line_no, tool, content in violations:
            print(f"{rel}:{line_no}: uses '{tool}' (not recommended)")
            print(f"    {content}")
        total_violations += len(violations)
    return total_violations, len(scripts)


def main() -> int:
    repo_root = Path(__file__).parent.parent
    blueprint_dir = repo_root / "blueprints"
    if not blueprint_dir.is_dir():
        print(f"ERROR: blueprints/ not found at {blueprint_dir}", file=sys.stderr)
        return 1

    total_violations, total_scripts = lint_blueprints(blueprint_dir)

    if total_violations:
        print(file=sys.stderr)
        print(
            f"Found {total_violations} portability violation(s) across "
            f"{total_scripts} blueprint script(s).",
            file=sys.stderr,
        )
        print(
            "See docs/development/blueprint-script-portability.md for guidance.",
            file=sys.stderr,
        )
        print(
            "To silence a justified use, add an inline or above-line marker:",
            file=sys.stderr,
        )
        print("    # SCRIPT_PORTABILITY_EXEMPT: <tool>: <reason>", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
