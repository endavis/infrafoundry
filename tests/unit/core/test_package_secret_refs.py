"""Tests for package-scoped ``package.<key>`` secret references (#1565)."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.package_secret_refs import (
    is_package_ref,
    package_ref_key,
    package_ref_problem,
    package_secret_var_name,
    package_var_slug,
    resolve_package_secret,
)
from infrafoundry.core.provider import ResourceConfig

_PLACEHOLDER = "not-a-real-secret"


def _res(
    secrets: dict[str, Any] | None = None,
    *,
    path: str | None = "kubernetes/example-app",
    name: str | None = "example-app",
) -> ResourceConfig:
    return ResourceConfig(
        name="app-admin",
        type="secrets",
        provider="kubernetes",
        config={},
        package_secrets=secrets,
        package_name=name,
        package_path=path,
    )


class TestParsing:
    def test_is_package_ref(self) -> None:
        assert is_package_ref("package.admin_token")
        assert not is_package_ref("packages.admin_token")
        assert not is_package_ref("outputs.x.y")
        assert not is_package_ref("app.admin_token")

    def test_key_keeps_dots_and_may_be_empty(self) -> None:
        assert package_ref_key("package.db.password") == "db.password"
        assert package_ref_key("package.") == ""

    def test_slug_and_var_name(self) -> None:
        assert package_var_slug("kubernetes/Example-App") == "kubernetes_example_app"
        assert (
            package_secret_var_name("kubernetes/example-app", "admin_token")
            == "package_kubernetes_example_app_admin_token"
        )
        assert package_secret_var_name("pkg", "db.password") == "package_pkg_db_password"


class TestResolution:
    def test_resolves_flat_and_nested_keys(self) -> None:
        res = _res({"admin_token": _PLACEHOLDER, "db": {"password": "x-1"}})
        assert resolve_package_secret(res, "package.admin_token") == _PLACEHOLDER
        assert resolve_package_secret(res, "package.db.password") == "x-1"
        assert package_ref_problem(res, "package.admin_token") is None

    def test_non_package_resource(self) -> None:
        res = _res({"admin_token": _PLACEHOLDER}, path=None, name=None)
        problem = package_ref_problem(res, "package.admin_token")
        assert problem is not None
        assert "package.admin_token" in problem
        assert "app-admin" in problem
        with pytest.raises(KeyError):
            resolve_package_secret(res, "package.admin_token")

    def test_missing_secrets_file(self) -> None:
        problem = package_ref_problem(_res(None), "package.admin_token")
        assert problem is not None
        assert "no secrets.yaml" in problem
        assert "example-app" in problem
        assert "kubernetes/example-app" in problem

    def test_missing_key_lists_names_only(self) -> None:
        problem = package_ref_problem(_res({"other": _PLACEHOLDER}), "package.admin_token")
        assert problem is not None
        assert "package.admin_token" in problem
        assert "'other'" in problem
        assert _PLACEHOLDER not in problem

    def test_empty_secrets_variables(self) -> None:
        problem = package_ref_problem(_res({}), "package.admin_token")
        assert problem is not None
        assert "admin_token" in problem

    def test_empty_key(self) -> None:
        problem = package_ref_problem(_res({"a": _PLACEHOLDER}), "package.")
        assert problem is not None
        assert "empty key" in problem
        assert _PLACEHOLDER not in problem


class TestResourceModel:
    def test_secrets_kept_out_of_dump_and_repr(self) -> None:
        res = _res({"admin_token": _PLACEHOLDER})
        assert "package_secrets" not in res.model_dump()
        assert _PLACEHOLDER not in repr(res)
        assert _PLACEHOLDER not in str(res)
        assert _PLACEHOLDER not in res.model_dump_json()
