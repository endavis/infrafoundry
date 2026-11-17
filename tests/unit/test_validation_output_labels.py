"""A ``[fw-a] `` result prefix must survive Rich markup when printed (#1450)."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from infrafoundry.core.orchestrator_workflows import ValidationOrchestrator
from infrafoundry.core.validation import ValidationLevel, ValidationReport


def _print(report: ValidationReport, verbose: bool) -> str:
    buffer = StringIO()
    orchestrator = ValidationOrchestrator.__new__(ValidationOrchestrator)
    orchestrator.console = Console(file=buffer, width=200, force_terminal=False)
    orchestrator._print_detailed_report(report, verbose=verbose)
    return buffer.getvalue()


def test_prefixed_results_are_printed_with_their_label() -> None:
    report = ValidationReport()
    report.add_check("a", True, "[fw-a] connected")
    report.add_check("b", False, "[fw-b] bad vip", level=ValidationLevel.ERROR)
    report.add_check("c", False, "[fw-b] slow", level=ValidationLevel.WARNING)
    output = _print(report, verbose=True)
    assert "[fw-a] connected" in output
    assert "[fw-b] bad vip" in output
    assert "[fw-b] slow" in output


def test_unprefixed_results_print_as_before() -> None:
    report = ValidationReport()
    report.add_check("a", False, "plain failure")
    assert "plain failure" in _print(report, verbose=False)
