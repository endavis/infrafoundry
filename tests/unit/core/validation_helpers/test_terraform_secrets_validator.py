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


# ---------------------------------------------------------------------------
# package.<key> references (#1565)
# ---------------------------------------------------------------------------


def _pkg_resource(
    refs: list[str],
    *,
    path: str | None = "kubernetes/example-app",
    secrets: dict[str, object] | None = None,
) -> ResourceConfig:
    return ResourceConfig(
        name="demo-vm",
        type="vm",
        provider="proxmox",
        config={"terraform_secrets": refs},
        package_name="example-app",
        package_path=path,
        package_secrets=secrets,
    )


def _errors(report: ValidationReport) -> list[str]:
    return [r.message for r in report.results if not r.passed]


def test_package_ref_resolves_from_package_secrets() -> None:
    report = ValidationReport()
    resource = _pkg_resource(["package.admin_token"], secrets={"admin_token": "not-a-real-secret"})
    validate_terraform_secrets_references(
        "proxmox", [resource], make_env_config(secrets={}), report
    )
    assert not report.has_errors()


def test_package_ref_not_satisfied_by_env_secrets() -> None:
    report = ValidationReport()
    resource = _pkg_resource(["package.admin_token"], secrets={})
    env = make_env_config(secrets={"package": {"admin_token": "not-a-real-secret"}})
    validate_terraform_secrets_references("proxmox", [resource], env, report)
    errors = _errors(report)
    assert len(errors) == 1
    assert "package.admin_token" in errors[0]
    assert "not-a-real-secret" not in errors[0]


def test_package_ref_error_cases() -> None:
    report = ValidationReport()
    resources = [
        _pkg_resource(["package.admin_token"], path=None, secrets=None),
        _pkg_resource(["package.admin_token"], secrets=None),
        _pkg_resource(["package.admin_token"], secrets={"other": "not-a-real-secret"}),
        _pkg_resource(["package."], secrets={"a": "not-a-real-secret"}),
    ]
    validate_terraform_secrets_references("proxmox", resources, make_env_config(secrets={}), report)
    errors = _errors(report)
    assert len(errors) == 4
    assert "does not come from a package" in errors[0]
    assert "no secrets.yaml" in errors[1]
    assert "Available keys" in errors[2]
    assert "empty key" in errors[3]
    assert all("not-a-real-secret" not in e for e in errors)


def test_env_refs_still_checked_next_to_package_refs() -> None:
    report = ValidationReport()
    resource = _pkg_resource(
        ["package.admin_token", "tailscale.missing"], secrets={"admin_token": "x"}
    )
    validate_terraform_secrets_references(
        "proxmox", [resource], make_env_config(secrets={}), report
    )
    errors = _errors(report)
    assert len(errors) == 1
    assert "tailscale.missing" in errors[0]
