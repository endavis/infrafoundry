"""Cron-jobs validator for OPNsense (#789).

Plan-time validation for the ``cron.jobs`` dotted resource type — a
list-shape resource where each entry is an OPNsense scheduled task.

Static checks only (no live-box access):

- Schedule field range validation (``minutes``, ``hours``, ``days``,
  ``months``, ``weekdays``) using the standard cron value grammar.
- Unique names within the submitted resource list.
- ``description`` must not contain the reserved ``[infrafoundry:`` prefix
  (the identity suffix is appended automatically at apply time).
- ``command`` must be non-empty.
- ``who`` must be non-empty.
"""

from __future__ import annotations

import re
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# ---------------------------------------------------------------------------
# Schedule value grammar
# ---------------------------------------------------------------------------

# Cron valid value ranges per field.
_SCHEDULE_RANGES: dict[str, tuple[int, int]] = {
    "minutes": (0, 59),
    "hours": (0, 23),
    "days": (1, 31),
    "months": (1, 12),
    "weekdays": (0, 7),
}

# Single token regex: ``*``, a plain integer, or a ``*/N`` step expression.
# We validate range in a second pass rather than inline in the regex.
_TOKEN_RE = re.compile(r"^\*(?:/(\d+))?$|^(\d+)$|^(\d+)-(\d+)(?:/(\d+))?$")

# Reserved identity prefix — must NOT appear in the operator-supplied description.
_IDENTITY_PROBE = re.compile(r"\[infrafoundry:[^\]]*\]")


class CronJobsValidator:
    """Validates OPNsense cron-job resource definitions at plan time.

    Performs static checks only: no live-box access occurs in this class.
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ``ValidationReport`` to add results to.
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate all cron-job resources.

        Args:
            resources: ``cron.jobs`` ``ResourceConfig`` entries.
        """
        if not resources:
            return
        self._check_unique_names(resources)
        for resource in resources:
            self._validate_one(resource)

    def _check_unique_names(self, resources: list[ResourceConfig]) -> None:
        seen: set[str] = set()
        duplicates: list[str] = []
        for resource in resources:
            name = resource.name
            if name in seen:
                duplicates.append(name)
            seen.add(name)
        if duplicates:
            self.report.add_check(
                check_name="cron_jobs_unique_names",
                passed=False,
                message=(
                    f"Duplicate cron_job resource names: {sorted(duplicates)!r}. "
                    f"Each cron_job must have a unique name within the environment."
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_one(self, resource: ResourceConfig) -> None:
        name = resource.name
        config = resource.config
        self._validate_description(name, config)
        self._validate_command(name, config)
        self._validate_who(name, config)
        self._validate_origin(name, config)
        for field_name, (low, high) in _SCHEDULE_RANGES.items():
            self._validate_schedule_field(name, config, field_name, low, high)

    def _validate_description(self, name: str, config: dict[str, Any]) -> None:
        description = config.get("description", "")
        if not isinstance(description, str):
            self.report.add_check(
                check_name=f"cron_job_{name}_description_type",
                passed=False,
                message=(
                    f"cron_job '{name}' description must be a string, "
                    f"got {type(description).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if _IDENTITY_PROBE.search(description):
            self.report.add_check(
                check_name=f"cron_job_{name}_description_reserved",
                passed=False,
                message=(
                    f"cron_job '{name}' description must not contain "
                    f"'[infrafoundry:<name>]' — that tag is reserved for the "
                    f"InfraFoundry identity suffix, which is added automatically "
                    f"at apply time"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_command(self, name: str, config: dict[str, Any]) -> None:
        command = config.get("command", "")
        if not isinstance(command, str):
            self.report.add_check(
                check_name=f"cron_job_{name}_command_type",
                passed=False,
                message=(
                    f"cron_job '{name}' command must be a string, got {type(command).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if not command.strip():
            self.report.add_check(
                check_name=f"cron_job_{name}_command_empty",
                passed=False,
                message=(f"cron_job '{name}' command must not be empty"),
                level=ValidationLevel.ERROR,
            )

    def _validate_who(self, name: str, config: dict[str, Any]) -> None:
        who = config.get("who", "root")
        if not isinstance(who, str):
            self.report.add_check(
                check_name=f"cron_job_{name}_who_type",
                passed=False,
                message=(f"cron_job '{name}' who must be a string, got {type(who).__name__}"),
                level=ValidationLevel.ERROR,
            )
            return
        if not who.strip():
            self.report.add_check(
                check_name=f"cron_job_{name}_who_empty",
                passed=False,
                message=(f"cron_job '{name}' who must not be empty"),
                level=ValidationLevel.ERROR,
            )

    def _validate_origin(self, name: str, config: dict[str, Any]) -> None:
        """Warn when the operator sets a non-``"cron"`` origin.

        InfraFoundry always writes ``origin="cron"`` on the wire regardless
        of the YAML value, so a non-``"cron"`` origin is silently overridden
        at apply time.  This warning tells the operator so they understand
        why their value doesn't appear on the box.

        Args:
            name: Resource name.
            config: Resource config dict.
        """
        origin = config.get("origin", "")
        if not isinstance(origin, str):
            return
        if origin and origin != "cron":
            self.report.add_check(
                check_name=f"cron_job_{name}_origin_override",
                passed=True,
                message=(
                    f"cron_job '{name}' has origin={origin!r} in YAML. "
                    f'InfraFoundry always writes origin="cron" on the wire so that '
                    f"delJob can delete the job. The YAML value will be ignored at "
                    f"apply time."
                ),
                level=ValidationLevel.WARNING,
            )

    def _validate_schedule_field(
        self,
        name: str,
        config: dict[str, Any],
        field_name: str,
        low: int,
        high: int,
    ) -> None:
        raw = config.get(field_name, "*")
        if not isinstance(raw, str):
            self.report.add_check(
                check_name=f"cron_job_{name}_{field_name}_type",
                passed=False,
                message=(
                    f"cron_job '{name}' {field_name} must be a string, got {type(raw).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        # Multi-token: comma-separated list of tokens.
        tokens = [t.strip() for t in raw.split(",")]
        for token in tokens:
            if not _validate_cron_token(token, low, high):
                self.report.add_check(
                    check_name=f"cron_job_{name}_{field_name}_range",
                    passed=False,
                    message=(
                        f"cron_job '{name}' {field_name}={raw!r} is not valid. "
                        f"Expected '*', '*/N', a comma-separated list, or values "
                        f"in the range [{low}-{high}]"
                    ),
                    level=ValidationLevel.ERROR,
                )
                return  # report once per field, not once per token


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_cron_token(token: str, low: int, high: int) -> bool:
    """Return True if *token* is a valid cron field token within [low, high].

    Args:
        token: A single cron token (e.g. ``"*"``, ``"*/5"``, ``"3"``,
            ``"1-5"``, ``"0-59/10"``).
        low: Minimum valid value for the field.
        high: Maximum valid value for the field.

    Returns:
        True if the token is syntactically valid and numerically in range.
    """
    if not token:
        return False
    match = _TOKEN_RE.match(token)
    if not match:
        return False
    step_str, single_str, range_low_str, range_high_str, range_step_str = match.groups()

    # "*/N" — step on wildcard
    if step_str is not None:
        step = int(step_str)
        return step > 0

    # Plain integer
    if single_str is not None:
        value = int(single_str)
        return low <= value <= high

    # "L-H" or "L-H/N" — range
    if range_low_str is not None and range_high_str is not None:
        range_low = int(range_low_str)
        range_high = int(range_high_str)
        if not (low <= range_low <= high and low <= range_high <= high):
            return False
        if range_low > range_high:
            return False
        if range_step_str is not None:
            step = int(range_step_str)
            return step > 0
        return True

    # Bare "*" (step_str is None, match group(1) is None — captured by first branch with None)
    # The regex matches bare "*" with all five groups = None.
    return True
