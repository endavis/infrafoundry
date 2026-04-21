"""Tests for tools/lint_blueprint_portability.py.

Covers the find_violations() core: detection of disallowed tools,
exemption-marker handling (inline + above-line), comment-line skipping,
and word-boundary correctness.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.lint_blueprint_portability import find_violations, lint_blueprints


class TestFindViolations:
    """Unit tests for the line-level violation detector."""

    def test_clean_script_no_violations(self):
        text = """#!/bin/bash
set -euo pipefail

mapfile -t NAMES < <(python3 -c 'import json,sys
for i in json.load(sys.stdin): print(i)' <<< "$DATA")
"""
        assert find_violations(text) == []

    def test_jq_usage_flagged(self):
        text = """#!/bin/bash
set -euo pipefail

NAMES=$(echo "$DATA" | jq -r '.items[]')
"""
        violations = find_violations(text)
        assert len(violations) == 1
        line_no, tool, content = violations[0]
        assert line_no == 4
        assert tool == "jq"
        assert "jq -r" in content

    def test_yq_usage_flagged(self):
        text = """#!/bin/bash
echo "$DATA" | yq -r '.items'
"""
        violations = find_violations(text)
        assert len(violations) == 1
        assert violations[0][1] == "yq"

    def test_inline_exemption_silences_violation(self):
        text = """#!/bin/bash
NAMES=$(echo "$DATA" | jq -r '.items[]')  # SCRIPT_PORTABILITY_EXEMPT: jq: legacy parser
"""
        assert find_violations(text) == []

    def test_above_line_exemption_silences_violation(self):
        text = """#!/bin/bash
# SCRIPT_PORTABILITY_EXEMPT: jq: installed by step 3
NAMES=$(echo "$DATA" | jq -r '.items[]')
"""
        assert find_violations(text) == []

    def test_exemption_for_wrong_tool_does_not_silence(self):
        text = """#!/bin/bash
# SCRIPT_PORTABILITY_EXEMPT: yq: I meant the other one
NAMES=$(echo "$DATA" | jq -r '.items[]')
"""
        violations = find_violations(text)
        assert len(violations) == 1
        assert violations[0][1] == "jq"

    def test_jq_in_comment_is_not_flagged(self):
        text = """#!/bin/bash
# This script used to use jq but now uses python3
echo "ok"
"""
        assert find_violations(text) == []

    def test_jq_in_indented_comment_is_not_flagged(self):
        text = """#!/bin/bash
if true; then
    # We dropped the jq dependency in PR #646
    echo ok
fi
"""
        assert find_violations(text) == []

    def test_word_boundary_does_not_match_substrings(self):
        text = """#!/bin/bash
# These should NOT trigger:
mkdir jquery_data
PROJ=mkjq
echo $PROJ
"""
        # `jquery` and `mkjq` don't have `jq` as a standalone word.
        assert find_violations(text) == []

    def test_multiple_violations_on_different_lines(self):
        text = """#!/bin/bash
NAMES=$(echo "$DATA" | jq -r '.names[]')
IPS=$(echo "$DATA" | jq -r '.ips[]')
TAGS=$(echo "$DATA" | yq -r '.tags[]')
"""
        violations = find_violations(text)
        assert [(v[0], v[1]) for v in violations] == [(2, "jq"), (3, "jq"), (4, "yq")]

    def test_two_blank_lines_between_marker_and_use_breaks_link(self):
        # The above-line marker only applies to the line *immediately* above.
        text = """#!/bin/bash
# SCRIPT_PORTABILITY_EXEMPT: jq: not adjacent

NAMES=$(echo "$DATA" | jq -r '.items[]')
"""
        violations = find_violations(text)
        assert len(violations) == 1
        assert violations[0][1] == "jq"


class TestLintBlueprintsCurrentTree:
    """Sanity check the lint against the live blueprints/ tree.

    After PR #646 / #648 / #650 the tree should be jq-free, so the lint
    must report zero violations on the current state. Catches regressions
    in the lint script itself (e.g., a flawed regex that triggers false
    positives on an existing exemplar).
    """

    def test_current_blueprints_tree_has_no_violations(self, capsys):
        repo_root = Path(__file__).resolve().parents[2]
        blueprint_dir = repo_root / "blueprints"
        if not blueprint_dir.is_dir():
            pytest.skip("blueprints/ not present in this checkout")
        total_violations, total_scripts = lint_blueprints(blueprint_dir)
        captured = capsys.readouterr()
        assert total_violations == 0, (
            f"expected zero violations, got {total_violations}; output:\n{captured.out}"
        )
        assert total_scripts > 0, "expected to scan at least one script"
