"""Property-based tests using Hypothesis.

Tests invariant properties of validation framework classes
using randomly generated inputs rather than hand-picked examples.
"""

from __future__ import annotations

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from infrafoundry.core.validation import ValidationLevel, ValidationReport, ValidationResult

# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestValidationResultProperties:
    """Property-based tests for ValidationResult."""

    @given(
        check_name=st.text(min_size=1),
        message=st.text(min_size=1),
        passed=st.booleans(),
        level=st.sampled_from(ValidationLevel),
    )
    @example(check_name="test", message="ok", passed=True, level=ValidationLevel.ERROR)
    def test_repr_contains_check_name(
        self,
        check_name: str,
        message: str,
        passed: bool,
        level: ValidationLevel,
    ) -> None:
        """The repr must contain the check name."""
        result = ValidationResult(
            check_name=check_name, level=level, passed=passed, message=message
        )
        text = repr(result)
        assert check_name in text

    @given(
        check_name=st.text(min_size=1),
        message=st.text(min_size=1),
        passed=st.booleans(),
        level=st.sampled_from(ValidationLevel),
    )
    def test_repr_shows_pass_or_fail_symbol(
        self,
        check_name: str,
        message: str,
        passed: bool,
        level: ValidationLevel,
    ) -> None:
        """The repr must show a pass or fail symbol."""
        result = ValidationResult(
            check_name=check_name, level=level, passed=passed, message=message
        )
        text = repr(result)
        if passed:
            assert "\u2713" in text  # checkmark
        else:
            assert "\u2717" in text  # cross


# ---------------------------------------------------------------------------
# ValidationReport
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestValidationReportProperties:
    """Property-based tests for ValidationReport."""

    @given(
        results=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=20),
                st.booleans(),
                st.sampled_from(ValidationLevel),
            ),
            min_size=0,
            max_size=50,
        )
    )
    def test_summary_total_equals_result_count(
        self,
        results: list[tuple[str, bool, ValidationLevel]],
    ) -> None:
        """Summary total must equal the number of results added."""
        report = ValidationReport()
        for name, passed, level in results:
            report.add_check(name, passed, "msg", level)
        summary = report.get_summary()
        assert summary["total"] == len(results)

    @given(
        results=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=20),
                st.booleans(),
                st.sampled_from(ValidationLevel),
            ),
            min_size=0,
            max_size=50,
        )
    )
    def test_summary_counts_are_consistent(
        self,
        results: list[tuple[str, bool, ValidationLevel]],
    ) -> None:
        """Summary passed + errors + warnings + info must equal total."""
        report = ValidationReport()
        for name, passed, level in results:
            report.add_check(name, passed, "msg", level)
        summary = report.get_summary()
        assert (
            summary["passed"] + summary["errors"] + summary["warnings"] + summary["info"]
            == summary["total"]
        )

    @given(
        results=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=20),
                st.just(True),
                st.sampled_from(ValidationLevel),
            ),
            min_size=1,
            max_size=20,
        )
    )
    def test_all_passed_means_no_errors(
        self,
        results: list[tuple[str, bool, ValidationLevel]],
    ) -> None:
        """When all checks pass, has_errors and has_warnings must be False."""
        report = ValidationReport()
        for name, passed, level in results:
            report.add_check(name, passed, "msg", level)
        assert not report.has_errors()
        assert not report.has_warnings()

    @given(check_name=st.text(min_size=1, max_size=20))
    def test_single_error_means_has_errors(self, check_name: str) -> None:
        """A single failed ERROR check means has_errors returns True."""
        report = ValidationReport()
        report.add_check(check_name, False, "fail", ValidationLevel.ERROR)
        assert report.has_errors()

    @given(check_name=st.text(min_size=1, max_size=20))
    def test_single_warning_means_has_warnings(self, check_name: str) -> None:
        """A single failed WARNING check means has_warnings returns True."""
        report = ValidationReport()
        report.add_check(check_name, False, "warn", ValidationLevel.WARNING)
        assert report.has_warnings()
        assert not report.has_errors()
