"""Regression tests for ``validate_terraform_secrets_references``.

Guards against the regression in issue #609 where a dict was passed in place
of ``EnvironmentConfig``, causing ``getattr(env_config, "secrets", None)`` to
silently return ``None`` and every ``terraform_secrets`` reference to be
reported as "unknown".
"""

from __future__ import annotations

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.core.validation_helpers.terraform_secrets_validator import (
    validate_terraform_secrets_references,
)
from tests.helpers.env import make_env_config


def _resource(terraform_secrets: list[str]) -> ResourceConfig:
    return ResourceConfig(
        name="demo-vm",
        type="vm",
        provider="proxmox",
        config={"terraform_secrets": terraform_secrets},
    )


def test_references_resolve_against_env_config_secrets() -> None:
    """Declared terraform_secrets that exist in env.secrets pass validation."""
    env_config = make_env_config(
        secrets={"tailscale": {"oauth_client_id": "xxxx"}},
    )
    report = ValidationReport()
    resources = [_resource(["tailscale.oauth_client_id"])]

    validate_terraform_secrets_references("proxmox", resources, env_config, report)

    assert not report.has_errors()
    results = [r for r in report.results if r.check_name == "proxmox_terraform_secrets_demo-vm"]
    assert len(results) == 1
    assert results[0].passed


def test_missing_reference_reports_error() -> None:
    """Missing keys produce an error listing the unknown reference."""
    env_config = make_env_config(secrets={})
    report = ValidationReport()
    resources = [_resource(["tailscale.oauth_client_id"])]

    validate_terraform_secrets_references("proxmox", resources, env_config, report)

    assert report.has_errors()
    failures = [r for r in report.results if not r.passed]
    assert len(failures) == 1
    assert "tailscale.oauth_client_id" in failures[0].message
