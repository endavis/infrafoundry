"""Validator helpers for ``secret://`` URIs in ``provider_settings``.

Live validator hooks (connectivity, references) call :func:`resolved_env_or_report` to get an
environment whose provider settings are resolved, or a reported failure. Offline hooks and
presence-only validators call :func:`report_settings_secret_problems`, which checks shape and
the configured backend only and never contacts a vault. Messages carry the URI, never a value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from infrafoundry.core.provider_instances import split_provider_id
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
        report: Report that receives an ERROR check when a URI cannot be resolved.

    Returns:
        A resolved copy, or ``None`` when resolution failed (the failure is on the report).
    """
    base, _ = split_provider_id(provider_name)
    try:
        return with_resolved_provider_settings(env_config, base)
    except SecretResolutionError as exc:
        report.add_check(
            check_name=f"{base}_settings_secrets",
            passed=False,
            message=f"provider_settings.{base}: {exc}",
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
