"""Unit tests for ``CronJobsValidator`` (#789).

Covers all static checks:
    - test_valid_passes
    - test_duplicate_names_error
    - test_reserved_description_error
    - test_empty_command_error
    - test_empty_who_error
    - test_schedule_wildcard_valid
    - test_schedule_step_valid
    - test_schedule_range_valid
    - test_schedule_comma_list_valid
    - test_schedule_out_of_range_error
    - test_schedule_minutes_high_boundary
    - test_schedule_hours_high_boundary
    - test_schedule_days_range
    - test_schedule_months_range
    - test_schedule_weekdays_boundary
    - test_empty_resources_no_checks
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.opnsense.validators.cron_jobs_validator import CronJobsValidator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resource(
    name: str = "acme-renew",
    *,
    config: dict[str, Any] | None = None,
) -> ResourceConfig:
    if config is None:
        config = {
            "enabled": True,
            "minutes": "0",
            "hours": "2",
            "days": "*",
            "months": "*",
            "weekdays": "*",
            "who": "root",
            "command": "acmeclient cron-auto-renew",
            "origin": "AcmeClient",
        }
    return ResourceConfig(name=name, type="cron.jobs", provider="opnsense", config=config)


def _failures(report: ValidationReport, check_name: str) -> list[Any]:
    """Return all non-passing entries for a given check_name."""
    return [r for r in report.results if r.check_name == check_name and not r.passed]


def _run(resources: list[ResourceConfig]) -> ValidationReport:
    report = ValidationReport()
    validator = CronJobsValidator(report)
    validator.validate(resources)
    return report


# ---------------------------------------------------------------------------
# Basic pass / fail
# ---------------------------------------------------------------------------


class TestBasicValidation:
    def test_valid_passes(self) -> None:
        report = _run([_resource()])
        assert not report.has_errors()

    def test_empty_resources_no_checks(self) -> None:
        report = _run([])
        assert len(report.results) == 0

    def test_duplicate_names_error(self) -> None:
        report = _run([_resource("dup"), _resource("dup")])
        assert _failures(report, "cron_jobs_unique_names")

    def test_unique_names_pass(self) -> None:
        report = _run([_resource("a"), _resource("b")])
        assert not report.has_errors()


# ---------------------------------------------------------------------------
# Description
# ---------------------------------------------------------------------------


class TestDescriptionValidation:
    def test_reserved_description_error(self) -> None:
        rc = _resource(
            config={
                "enabled": True,
                "minutes": "0",
                "hours": "2",
                "days": "*",
                "months": "*",
                "weekdays": "*",
                "who": "root",
                "command": "acmeclient cron-auto-renew",
                "description": "My job [infrafoundry:acme-renew]",
            }
        )
        report = _run([rc])
        assert _failures(report, "cron_job_acme-renew_description_reserved")

    def test_clean_description_passes(self) -> None:
        rc = _resource(
            config={
                "enabled": True,
                "minutes": "0",
                "hours": "2",
                "days": "*",
                "months": "*",
                "weekdays": "*",
                "who": "root",
                "command": "acmeclient cron-auto-renew",
                "description": "Renews TLS certs via AcmeClient",
            }
        )
        report = _run([rc])
        assert not report.has_errors()

    def test_no_description_passes(self) -> None:
        report = _run([_resource()])
        assert not report.has_errors()


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


class TestCommandValidation:
    def test_empty_command_error(self) -> None:
        cfg: dict[str, Any] = {
            "enabled": True,
            "minutes": "0",
            "hours": "2",
            "days": "*",
            "months": "*",
            "weekdays": "*",
            "who": "root",
            "command": "",
        }
        report = _run([_resource(config=cfg)])
        assert _failures(report, "cron_job_acme-renew_command_empty")

    def test_whitespace_only_command_error(self) -> None:
        cfg: dict[str, Any] = {
            "enabled": True,
            "minutes": "0",
            "hours": "2",
            "days": "*",
            "months": "*",
            "weekdays": "*",
            "who": "root",
            "command": "   ",
        }
        report = _run([_resource(config=cfg)])
        assert _failures(report, "cron_job_acme-renew_command_empty")


# ---------------------------------------------------------------------------
# Who
# ---------------------------------------------------------------------------


class TestWhoValidation:
    def test_empty_who_error(self) -> None:
        cfg: dict[str, Any] = {
            "enabled": True,
            "minutes": "0",
            "hours": "2",
            "days": "*",
            "months": "*",
            "weekdays": "*",
            "who": "",
            "command": "acmeclient cron-auto-renew",
        }
        report = _run([_resource(config=cfg)])
        assert _failures(report, "cron_job_acme-renew_who_empty")

    def test_whitespace_who_error(self) -> None:
        cfg: dict[str, Any] = {
            "enabled": True,
            "minutes": "0",
            "hours": "2",
            "days": "*",
            "months": "*",
            "weekdays": "*",
            "who": "  ",
            "command": "acmeclient cron-auto-renew",
        }
        report = _run([_resource(config=cfg)])
        assert _failures(report, "cron_job_acme-renew_who_empty")


# ---------------------------------------------------------------------------
# Schedule field validation
# ---------------------------------------------------------------------------


def _sched_cfg(**overrides: str) -> dict[str, Any]:
    base: dict[str, Any] = {
        "enabled": True,
        "minutes": "0",
        "hours": "2",
        "days": "*",
        "months": "*",
        "weekdays": "*",
        "who": "root",
        "command": "acmeclient cron-auto-renew",
    }
    base.update(overrides)
    return base


class TestScheduleValidation:
    def test_wildcard_valid(self) -> None:
        report = _run([_resource(config=_sched_cfg(minutes="*"))])
        assert not report.has_errors()

    def test_step_valid(self) -> None:
        report = _run([_resource(config=_sched_cfg(minutes="*/5"))])
        assert not report.has_errors()

    def test_range_valid(self) -> None:
        report = _run([_resource(config=_sched_cfg(hours="8-18"))])
        assert not report.has_errors()

    def test_range_with_step_valid(self) -> None:
        report = _run([_resource(config=_sched_cfg(minutes="0-59/10"))])
        assert not report.has_errors()

    def test_comma_list_valid(self) -> None:
        report = _run([_resource(config=_sched_cfg(minutes="0,15,30,45"))])
        assert not report.has_errors()

    def test_minutes_high_boundary(self) -> None:
        report = _run([_resource(config=_sched_cfg(minutes="59"))])
        assert not report.has_errors()

    def test_minutes_out_of_range_error(self) -> None:
        report = _run([_resource(config=_sched_cfg(minutes="60"))])
        assert _failures(report, "cron_job_acme-renew_minutes_range")

    def test_hours_high_boundary(self) -> None:
        report = _run([_resource(config=_sched_cfg(hours="23"))])
        assert not report.has_errors()

    def test_hours_out_of_range_error(self) -> None:
        report = _run([_resource(config=_sched_cfg(hours="24"))])
        assert _failures(report, "cron_job_acme-renew_hours_range")

    def test_days_low_boundary(self) -> None:
        report = _run([_resource(config=_sched_cfg(days="1"))])
        assert not report.has_errors()

    def test_days_out_of_range_error(self) -> None:
        report = _run([_resource(config=_sched_cfg(days="32"))])
        assert _failures(report, "cron_job_acme-renew_days_range")

    def test_days_zero_error(self) -> None:
        report = _run([_resource(config=_sched_cfg(days="0"))])
        assert _failures(report, "cron_job_acme-renew_days_range")

    def test_months_valid_range(self) -> None:
        report = _run([_resource(config=_sched_cfg(months="6"))])
        assert not report.has_errors()

    def test_months_out_of_range_error(self) -> None:
        report = _run([_resource(config=_sched_cfg(months="13"))])
        assert _failures(report, "cron_job_acme-renew_months_range")

    def test_weekdays_boundary_seven(self) -> None:
        """7 is valid (Sunday alias on OPNsense)."""
        report = _run([_resource(config=_sched_cfg(weekdays="7"))])
        assert not report.has_errors()

    def test_weekdays_out_of_range_error(self) -> None:
        report = _run([_resource(config=_sched_cfg(weekdays="8"))])
        assert _failures(report, "cron_job_acme-renew_weekdays_range")

    def test_invalid_token_format_error(self) -> None:
        report = _run([_resource(config=_sched_cfg(minutes="abc"))])
        assert _failures(report, "cron_job_acme-renew_minutes_range")

    def test_inverted_range_error(self) -> None:
        """L-H where L > H is invalid."""
        report = _run([_resource(config=_sched_cfg(hours="18-8"))])
        assert _failures(report, "cron_job_acme-renew_hours_range")

    def test_step_zero_error(self) -> None:
        """*/0 is invalid — step must be > 0."""
        report = _run([_resource(config=_sched_cfg(minutes="*/0"))])
        assert _failures(report, "cron_job_acme-renew_minutes_range")


# ---------------------------------------------------------------------------
# Origin validation (WARNING level)
# ---------------------------------------------------------------------------


class TestOriginValidation:
    def test_origin_non_cron_emits_warning(self) -> None:
        """A non-'cron' origin in YAML produces a WARNING (not an error).

        InfraFoundry always writes origin='cron' on the wire, so the operator's
        value is silently overridden.  The warning informs them of this.
        """
        cfg: dict[str, Any] = {
            "enabled": True,
            "minutes": "0",
            "hours": "2",
            "days": "*",
            "months": "*",
            "weekdays": "*",
            "who": "root",
            "command": "acmeclient cron-auto-renew",
            "origin": "AcmeClient",
        }
        report = _run([_resource(config=cfg)])
        assert not report.has_errors(), "non-cron origin must produce a WARNING, not an error"
        warnings = [
            r for r in report.results if r.check_name == "cron_job_acme-renew_origin_override"
        ]
        assert warnings, "expected a warning result for non-'cron' origin"

    def test_origin_cron_no_warning(self) -> None:
        """origin='cron' produces no warning — it matches what InfraFoundry writes."""
        cfg: dict[str, Any] = {
            "enabled": True,
            "minutes": "0",
            "hours": "2",
            "days": "*",
            "months": "*",
            "weekdays": "*",
            "who": "root",
            "command": "acmeclient cron-auto-renew",
            "origin": "cron",
        }
        report = _run([_resource(config=cfg)])
        assert not report.has_errors()
        assert not any(
            r.check_name == "cron_job_acme-renew_origin_override" for r in report.results
        )

    def test_origin_absent_no_warning(self) -> None:
        """No origin field in config produces no warning."""
        cfg: dict[str, Any] = {
            "enabled": True,
            "minutes": "0",
            "hours": "2",
            "days": "*",
            "months": "*",
            "weekdays": "*",
            "who": "root",
            "command": "acmeclient cron-auto-renew",
        }
        report = _run([_resource(config=cfg)])
        assert not report.has_errors()
        assert not any(
            r.check_name == "cron_job_acme-renew_origin_override" for r in report.results
        )
