"""Tests for the system users/groups validators (#805)."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators import (
    SystemGroupValidator,
    SystemUserValidator,
    build_xref_index,
)
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext
from tests.helpers.opnsense_auth import BCRYPT, PUBKEY


def _usr(name: str, /, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type="system.users", provider="opnsense", config=config)


def _grp(name: str, /, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type="system.groups", provider="opnsense", config=config)


def _errors(report: ValidationReport) -> list[Any]:
    return [r for r in report.results if not r.passed and r.level == ValidationLevel.ERROR]


def _run_users(resources: list[ResourceConfig]) -> list[Any]:
    report = ValidationReport()
    SystemUserValidator(report).validate(OPNsenseValidationContext(resources=resources))
    return _errors(report)


def _run_groups(groups: list[ResourceConfig], users: list[ResourceConfig]) -> list[Any]:
    report = ValidationReport()
    ctx = OPNsenseValidationContext(resources=groups, index=build_xref_index(groups + users))
    SystemGroupValidator(report).validate(ctx)
    return _errors(report)


@pytest.mark.parametrize("field", ["password", "authorizedkeys", "otp_seed", "apikeys"])
def test_literal_secret_is_error_without_echo(field: str) -> None:
    errors = _run_users([_usr("u", **{field: BCRYPT if field == "password" else PUBKEY})])
    assert len(errors) == 1
    assert errors[0].check_name == f"system_user_u_{field}_literal_secret"
    assert BCRYPT not in errors[0].message and "AAAAFAKE" not in errors[0].message


def test_secret_uri_and_absent_and_empty_pass() -> None:
    users = [
        _usr("a", password="secret://env_secrets/users/a/password", authorizedkeys=""),
        _usr("b"),
    ]
    assert _run_users(users) == []


def test_duplicate_names_and_uids() -> None:
    errors = _run_users([_usr("a", uid=2000), _usr("b", uid=2000), _usr("c", name="a")])
    checks = {e.check_name for e in errors}
    assert "system_user_unique_uids" in checks
    assert "system_user_unique_names" in checks


def test_bad_scope_uid_priv() -> None:
    errors = _run_users([_usr("a", scope="x", uid="abc", priv="not-a-list")])
    assert len(errors) == 3


@pytest.mark.parametrize("ref", ["a", "users.a", "system.users.a"])
def test_member_ref_forms_resolve(ref: str) -> None:
    assert _run_groups([_grp("g", member_refs=[ref])], [_usr("a")]) == []


def test_member_ref_miss_is_error() -> None:
    errors = _run_groups([_grp("g", member_refs=["nobody"])], [_usr("a")])
    assert len(errors) == 1


def test_member_ref_without_index_is_error() -> None:
    report = ValidationReport()
    ctx = OPNsenseValidationContext(resources=[_grp("g", member_refs=["a"])])
    SystemGroupValidator(report).validate(ctx)
    assert len(_errors(report)) == 1


def test_group_duplicates_and_shapes() -> None:
    errors = _run_groups(
        [_grp("a", gid=1), _grp("b", gid=1), _grp("c", member_refs="a", scope="q")], []
    )
    checks = {e.check_name for e in errors}
    assert "system_group_unique_gids" in checks
    assert "system_group_c_member_refs" in checks
    assert "system_group_c_scope" in checks
