"""Tests for github.py doit tasks.

Focused on `_extract_linked_issues`, which `doit pr_merge` uses to parse
``Addresses #N`` tokens from a PR body. The parser is intentionally strict:
only ``Addresses`` (capitalized) at the start of a line is matched. This
prevents mid-sentence references and prose mentions from polluting the
merge-commit subject or auto-close list.
"""

from __future__ import annotations

from tools.doit.github import _extract_linked_issues


class TestExtractLinkedIssues:
    """Tests for `_extract_linked_issues` strict line-start matching."""

    def test_addresses_issue(self) -> None:
        """A bare ``Addresses #N`` at line start is matched."""
        body = "Addresses #123"
        result = _extract_linked_issues(body)
        assert result == ["123"]

    def test_addresses_lowercase_ignored(self) -> None:
        """Lowercase ``addresses #N`` is ignored (case-sensitive)."""
        body = "addresses #456"
        result = _extract_linked_issues(body)
        assert result == []

    def test_addresses_uppercase_ignored(self) -> None:
        """All-caps ``ADDRESSES #N`` is ignored (case-sensitive)."""
        body = "ADDRESSES #789"
        result = _extract_linked_issues(body)
        assert result == []

    def test_mid_sentence_ignored(self) -> None:
        """``Addresses #N`` mid-line is ignored (must be at line start)."""
        body = "This PR Addresses #123"
        result = _extract_linked_issues(body)
        assert result == []

    def test_multiple_addresses(self) -> None:
        """Multiple line-start matches are all returned, in order."""
        body = "Addresses #123\nAddresses #456"
        result = _extract_linked_issues(body)
        assert result == ["123", "456"]

    def test_duplicate_issues(self) -> None:
        """Duplicate issue numbers are de-duplicated, preserving first occurrence."""
        body = "Addresses #123\nAddresses #123"
        result = _extract_linked_issues(body)
        assert result == ["123"]

    def test_no_issues(self) -> None:
        """A body with no ``Addresses`` references returns an empty list."""
        body = "This PR adds a new feature"
        result = _extract_linked_issues(body)
        assert result == []

    def test_issue_in_code_block_still_matched(self) -> None:
        """A line-start match inside a fenced code block is still matched.

        Distinguishing real references from code-block content would require
        a full markdown parser; the cheap parser opts to match by line
        position and rely on convention. Authors who want to mention
        ``Addresses #N`` without linking should indent or prose-wrap it.
        """
        body = "```\nAddresses #123\n```"
        result = _extract_linked_issues(body)
        assert result == ["123"]

    def test_old_closes_keyword_not_matched(self) -> None:
        """``Closes #N`` is intentionally not matched.

        The project standardized on ``Addresses #N`` to keep
        github-auto-close OFF and force explicit closing via PR merge.
        Other keywords (Closes/Fixes/Part of) must not trigger the parser.
        """
        body = "Closes #123"
        result = _extract_linked_issues(body)
        assert result == []

    def test_old_fixes_keyword_not_matched(self) -> None:
        """``Fixes #N`` is intentionally not matched (see ``Closes``)."""
        body = "Fixes #456"
        result = _extract_linked_issues(body)
        assert result == []
