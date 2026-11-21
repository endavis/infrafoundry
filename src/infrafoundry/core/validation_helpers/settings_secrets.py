"""Validator helpers for ``secret://`` URIs in ``provider_settings``.

Live validator hooks (connectivity, references) call :func:`resolved_env_or_report` to get an
environment whose provider settings are resolved, or a reported failure. Offline hooks and
presence-only validators call :func:`report_settings_secret_problems`, which checks shape and
the configured backend only and never contacts a vault. Messages carry the URI, never a value.
A resolution failure is reported once per report, labelled with the instance name when the
provider has instances.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from infrafoundry.core.provider_instances import (
    instance_label,
    instance_spec,
    split_provider_id,
)
from infrafoundry.core.validation import ValidationLevel
from infrafoundry.secrets.environment import (
    provider_settings_secret_problems,
    with_resolved_provider_settings,
)
from infrafoundry.secrets.resolver import SecretResolutionError

if TYPE_CHECKING:
    from infrafoundry.core.config.models import EnvironmentConfig
    from infrafoundry.core.validation import ValidationReport


def resolved_env_or_report(
    env_config: EnvironmentConfig, provider_name: str, report: ValidationReport
) -> EnvironmentConfig | None:
    """Return ``env_config`` with the provider's settings resolved, or ``None`` after reporting.

    Args:
        env_config: The environment under validation.
        provider_name: Provider id, with or without an ``@instance`` suffix.
        report: Report that receives an ERROR check when a URI cannot be resolved. The same
            failure is added once per report, however many hooks hit it.

    Returns:
        A resolved copy, or ``None`` when resolution failed (the failure is on the report).
    """
    base, _ = split_provider_id(provider_name)
    try:
        return with_resolved_provider_settings(env_config, provider_name)
    except SecretResolutionError as exc:
        label = (
            instance_label(base, env_config, provider_name)
            if instance_spec(base) is not None
            else None
        )
        prefix = f"[{label}] " if label else ""
        check_name = f"{base}_settings_secrets"
        message = f"{prefix}provider_settings.{base}: {exc}"
        already = any(
            not r.passed and r.check_name == check_name and r.message == message
            for r in report.results
        )
        if not already:
            report.add_check(
                check_name=check_name,
                passed=False,
                message=message,
                level=ValidationLevel.ERROR,
            )
        return None


def report_settings_secret_problems(
    env_config: EnvironmentConfig,
    provider_name: str,
    report: ValidationReport,
    *,
    check_presence: bool = True,
) -> None:
    """Report offline problems with the provider's settings URIs (shape and backend only).

    ``check_presence`` False also skips the lookup of an ``env_secrets`` path.
    """
    base, _ = split_provider_id(provider_name)
    problems = provider_settings_secret_problems(env_config, base, check_presence=check_presence)
    if problems:
        report.add_check(
            check_name=f"{base}_settings_secrets",
            passed=False,
            message="; ".join(problems),
            level=ValidationLevel.ERROR,
        )
