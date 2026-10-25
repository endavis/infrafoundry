"""Property-based tests for tools.pyproject_template.utils (template-owned).

These tests are template-owned: they run in the template's own CI, are
excluded from the drift checker, and are shed from downstreams via cleanup.
Only tooling assertions live here.  Skeleton assertions (greet, etc.) live in
the downstream-owned ``tests/template/test_properties.py``.
"""

from __future__ import annotations

import re

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from tools.pyproject_template.utils import (
    is_github_url,
    validate_email,
    validate_package_name,
    validate_pypi_name,
)

# ---------------------------------------------------------------------------
# validate_package_name
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestValidatePackageNameProperties:
    """Property-based tests for validate_package_name."""

    @given(name=st.text(min_size=1))
    @example("MyPackage")
    @example("123start")
    @example("hello-world")
    @example("__leading__")
    def test_output_contains_only_valid_chars(self, name: str) -> None:
        """Output must only contain lowercase letters, digits, and underscores."""
        result = validate_package_name(name)
        if result:
            assert re.fullmatch(r"[a-z0-9_]+", result), f"Invalid chars in output: {result!r}"

    @given(name=st.text(min_size=1))
    @example("9lives")
    def test_output_never_starts_with_digit(self, name: str) -> None:
        """Output must never start with a digit (Python identifier rule)."""
        result = validate_package_name(name)
        if result:
            assert not result[0].isdigit(), f"Output starts with digit: {result!r}"

    @given(name=st.from_regex(r"[a-zA-Z][a-zA-Z0-9_]*", fullmatch=True))
    @example("valid_name")
    def test_valid_input_produces_nonempty_output(self, name: str) -> None:
        """Input with at least one alpha char produces non-empty output."""
        result = validate_package_name(name)
        assert result, f"Expected non-empty output for input: {name!r}"

    @given(name=st.text(min_size=1))
    def test_output_has_no_leading_trailing_underscores(self, name: str) -> None:
        """Output must not have leading or trailing underscores (after strip).

        Exception: a leading underscore is added when the result starts with a digit.
        """
        result = validate_package_name(name)
        if result:
            # If it starts with _, the next char must be a digit (the prefix case)
            if result.startswith("_"):
                assert len(result) > 1 and result[1].isdigit(), (
                    f"Unexpected leading underscore: {result!r}"
                )
            assert not result.endswith("_"), f"Trailing underscore in output: {result!r}"


# ---------------------------------------------------------------------------
# validate_pypi_name
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestValidatePypiNameProperties:
    """Property-based tests for validate_pypi_name."""

    @given(name=st.text(min_size=1))
    @example("My--Package")
    @example("--leading")
    @example("trailing--")
    def test_output_contains_only_valid_chars(self, name: str) -> None:
        """Output must only contain lowercase letters, digits, and hyphens."""
        result = validate_pypi_name(name)
        if result:
            assert re.fullmatch(r"[a-z0-9-]+", result), f"Invalid chars in output: {result!r}"

    @given(name=st.text(min_size=1))
    @example("a--b--c")
    def test_no_consecutive_hyphens(self, name: str) -> None:
        """Output must not contain consecutive hyphens."""
        result = validate_pypi_name(name)
        assert "--" not in result, f"Consecutive hyphens in output: {result!r}"

    @given(name=st.text(min_size=1))
    @example("-leading")
    @example("trailing-")
    def test_no_leading_or_trailing_hyphens(self, name: str) -> None:
        """Output must not start or end with a hyphen."""
        result = validate_pypi_name(name)
        if result:
            assert not result.startswith("-"), f"Leading hyphen: {result!r}"
            assert not result.endswith("-"), f"Trailing hyphen: {result!r}"


# ---------------------------------------------------------------------------
# validate_email
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestValidateEmailProperties:
    """Property-based tests for validate_email."""

    def test_empty_string_returns_false(self) -> None:
        """Empty string must not be considered a valid email."""
        assert validate_email("") is False

    @given(text=st.text(alphabet=st.characters(blacklist_characters="@"), min_size=1))
    def test_string_without_at_returns_false(self, text: str) -> None:
        """A string without '@' cannot be a valid email."""
        assert validate_email(text) is False

    @given(
        local=st.from_regex(r"[a-zA-Z0-9._%+-]+", fullmatch=True),
        domain=st.from_regex(r"[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", fullmatch=True),
    )
    @example(local="user", domain="example.com")
    def test_well_formed_email_returns_true(self, local: str, domain: str) -> None:
        """Well-formed local@domain emails must validate as true."""
        email = f"{local}@{domain}"
        assert validate_email(email) is True, f"Expected valid: {email!r}"


# ---------------------------------------------------------------------------
# is_github_url
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestIsGithubUrlProperties:
    """Property-based tests for is_github_url."""

    @given(
        domain=st.from_regex(r"[a-z]{3,12}\.(com|org|net|io)", fullmatch=True).filter(
            lambda d: "github" not in d
        )
    )
    def test_non_github_domains_return_false(self, domain: str) -> None:
        """URLs with non-github domains must return False."""
        url = f"https://{domain}/owner/repo"
        assert is_github_url(url) is False, f"Expected False for: {url!r}"

    @given(path=st.from_regex(r"/[a-z]+/[a-z]+", fullmatch=True))
    @example(path="/owner/repo")
    def test_github_com_returns_true(self, path: str) -> None:
        """URLs with github.com domain must return True."""
        url = f"https://github.com{path}"
        assert is_github_url(url) is True, f"Expected True for: {url!r}"

    @given(text=st.text(min_size=0, max_size=50))
    def test_never_raises(self, text: str) -> None:
        """is_github_url must never raise an exception for any input."""
        result = is_github_url(text)
        assert isinstance(result, bool)
