"""Unit tests for the infra doctor secret-sources helpers (#1567)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.cli.commands.infra._secret_sources import (
    SecretSourceRow,
    SourceStatus,
    collect_secret_sources,
    print_secret_sources,
    secret_sources_json,
)
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation_helpers.terraform_secrets_validator import output_ref_problem

PLACEHOLDER = "PLACEHOLDER-SECRET-VALUE-1567"


def _res(
    config: dict[str, Any] | None = None,
    *,
    name: str = "example-app",
    rtype: str = "vm",
    provider: str = "proxmox",
    package_path: str | None = "apps/example-app",
    package_secrets: dict[str, Any] | None = None,
) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type=rtype,
        provider=provider,
        config=config or {},
        package_path=package_path,
        package_name="example-app" if package_path else None,
        package_secrets=package_secrets,
    )


def _collect(
    resources: list[ResourceConfig], secrets: dict[str, Any] | None = None
) -> list[SecretSourceRow]:
    return collect_secret_sources(resources, "test", lambda: secrets)


@pytest.mark.unit
class TestCollect:
    """collect_secret_sources classifies each reference."""

    def test_package_ref_resolved(self) -> None:
        rows = _collect(
            [
                _res(
                    {"terraform_secrets": ["package.admin_token"]},
                    package_secrets={"admin_token": PLACEHOLDER},
                )
            ]
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.status is SourceStatus.RESOLVED
        assert row.field == "terraform_secrets[0]"
        assert row.source == "envs/test/apps/example-app/secrets.yaml"
        assert PLACEHOLDER not in repr(rows)

    def test_package_ref_missing_key(self) -> None:
        rows = _collect(
            [_res({"terraform_secrets": ["package.nope"]}, package_secrets={"admin_token": "x"})]
        )
        assert rows[0].status is SourceStatus.UNRESOLVED
        assert "nope" in (rows[0].reason or "")

    def test_package_ref_no_package_secrets(self) -> None:
        rows = _collect([_res({"terraform_secrets": ["package.admin_token"]})])
        assert rows[0].status is SourceStatus.UNRESOLVED
        assert "no secrets.yaml" in (rows[0].reason or "")

    def test_package_ref_empty_key(self) -> None:
        rows = _collect([_res({"terraform_secrets": ["package."]}, package_secrets={"a": "b"})])
        assert rows[0].status is SourceStatus.UNRESOLVED
        assert "empty key" in (rows[0].reason or "")

    def test_package_ref_without_package(self) -> None:
        rows = _collect([_res({"terraform_secrets": ["package.a"]}, package_path=None)])
        assert rows[0].status is SourceStatus.UNRESOLVED
        assert rows[0].source == "-"
        assert "needs a package" in (rows[0].reason or "")

    def test_unprefixed_present_and_missing(self) -> None:
        rows = _collect(
            [_res({"terraform_secrets": ["db.password", "db.missing"]})],
            {"db": {"password": PLACEHOLDER}},
        )
        assert [r.status for r in rows] == [SourceStatus.RESOLVED, SourceStatus.UNRESOLVED]
        assert rows[0].source == "envs/test/secrets.yaml"
        assert "unknown secret key 'db.missing'" in (rows[1].reason or "")
        assert PLACEHOLDER not in repr(rows)

    def test_unprefixed_with_no_env_secrets(self) -> None:
        rows = _collect([_res({"terraform_secrets": ["db.password"]})], None)
        assert rows[0].status is SourceStatus.UNRESOLVED

    def test_env_secrets_loaded_lazily(self) -> None:
        loader = MagicMock(return_value={})
        collect_secret_sources(
            [
                _res(
                    {"terraform_secrets": ["package.a", "outputs.opnsense.token"]},
                    provider="kubernetes",
                    package_secrets={"a": "b"},
                )
            ],
            "test",
            loader,
        )
        loader.assert_not_called()

    def test_env_secrets_loaded_once(self) -> None:
        loader = MagicMock(return_value={"a": "x", "b": "y"})
        collect_secret_sources([_res({"terraform_secrets": ["a", "b", "c"]})], "test", loader)
        loader.assert_called_once()

    def test_outputs_ok_is_apply_time(self) -> None:
        rows = _collect(
            [_res({"terraform_secrets": ["outputs.opnsense.api_key"]}, provider="kubernetes")]
        )
        assert rows[0].status is SourceStatus.APPLY_TIME
        assert rows[0].source == "outputs of opnsense (apply time)"

    @pytest.mark.parametrize(
        ("provider", "ref", "needle"),
        [
            ("proxmox", "outputs.opnsense.key", "kubernetes provider only"),
            ("kubernetes", "outputs.bad", "must look like"),
            ("kubernetes", "outputs.kubernetes.key", "own outputs"),
        ],
    )
    def test_outputs_bad(self, provider: str, ref: str, needle: str) -> None:
        rows = _collect([_res({"terraform_secrets": [ref]}, provider=provider)])
        assert rows[0].status is SourceStatus.UNRESOLVED
        assert rows[0].source == "-"
        assert needle in (rows[0].reason or "")

    def test_kubernetes_secret_field_paths(self) -> None:
        resource = _res(
            {
                "string_data_secrets": {"token": "package.admin_token"},
                "data_secrets": {"blob": "db.blob"},
            },
            rtype="secrets",
            provider="kubernetes",
            package_secrets={"admin_token": "x"},
        )
        rows = _collect([resource], {"db": {"blob": "x"}})
        assert [r.field for r in rows] == ["string_data_secrets.token", "data_secrets.blob"]
        assert all(r.status is SourceStatus.RESOLVED for r in rows)

    def test_helm_set_sensitive_keeps_raw_index(self) -> None:
        resource = _res(
            {
                "set_sensitive": [
                    {"name": "a", "value": "literal"},
                    {"name": "b", "value_secret": "package.admin_token"},
                ]
            },
            rtype="helm_releases",
            provider="kubernetes@edge",
            package_secrets={"admin_token": "x"},
        )
        rows = _collect([resource])
        assert [r.field for r in rows] == ["set_sensitive[1].value_secret"]

    def test_kubernetes_shape_errors(self) -> None:
        resource = _res(
            {"string_data_secrets": {"k": "db.x"}, "string_data": {"k": "v"}},
            rtype="secrets",
            provider="kubernetes",
        )
        rows = _collect([resource], {"db": {"x": "y"}})
        assert len(rows) == 1
        assert rows[0].status is SourceStatus.UNRESOLVED
        assert rows[0].field == "secrets fields"
        assert "both" in (rows[0].reason or "")

    def test_non_kubernetes_ignores_value_secret_fields(self) -> None:
        resource = _res({"string_data_secrets": {"k": "db.x"}}, rtype="secrets")
        assert _collect([resource]) == []

    def test_non_list_terraform_secrets(self) -> None:
        rows = _collect([_res({"terraform_secrets": "db.password"})])
        assert len(rows) == 1
        assert rows[0].status is SourceStatus.UNRESOLVED
        assert rows[0].field == "terraform_secrets"
        assert "non-list terraform_secrets value: str" in (rows[0].reason or "")

    def test_non_string_entry_never_shows_value(self) -> None:
        rows = _collect([_res({"terraform_secrets": [{"token": PLACEHOLDER}]})])
        assert rows[0].status is SourceStatus.UNRESOLVED
        assert rows[0].ref == "<non-string: dict>"
        assert PLACEHOLDER not in repr(rows)


@pytest.mark.unit
class TestPrintAndJson:
    """Rendering never shows a value and keeps brackets."""

    def test_print_rows_and_summary(self, capsys: pytest.CaptureFixture[str]) -> None:
        rows = _collect(
            [
                _res(
                    {"terraform_secrets": ["package.a", "package.b", "outputs.x.y"]},
                    provider="kubernetes",
                    package_secrets={"a": PLACEHOLDER},
                )
            ]
        )
        print_secret_sources(rows, "package example-app")
        out = capsys.readouterr().out
        assert "Secret sources (package example-app):" in out
        assert "terraform_secrets[0]" in out
        assert "terraform_secrets[1]" in out
        assert "->envs/test/apps/example-app/secrets.yaml" in "".join(out.split())
        assert "Secret sources: 1 resolved, 1 at apply time, 1 unresolved" in out
        assert PLACEHOLDER not in out

    def test_print_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        print_secret_sources([], "resource(s) a")
        out = capsys.readouterr().out
        assert "no secret references" in out
        assert "Secret sources:" not in out.replace("Secret sources (", "")

    def test_json_shape(self) -> None:
        rows = _collect([_res({"terraform_secrets": ["db.x"]})], {"db": {"x": PLACEHOLDER}})
        data = secret_sources_json(rows, "package example-app")
        assert data["scope"] == "package example-app"
        assert data["rows"][0]["status"] == "resolved"
        assert data["rows"][0]["reason"] is None
        assert PLACEHOLDER not in repr(data)


@pytest.mark.unit
class TestOutputRefProblem:
    """output_ref_problem is the per-ref form of the validator's check."""

    def test_ok(self) -> None:
        assert output_ref_problem("kubernetes", "outputs.opnsense.key", True) is None

    def test_not_allowed(self) -> None:
        assert "kubernetes provider only" in (
            output_ref_problem("proxmox", "outputs.opnsense.key", False) or ""
        )

    def test_malformed(self) -> None:
        assert "must look like" in (output_ref_problem("kubernetes", "outputs.x", True) or "")

    def test_own_provider(self) -> None:
        assert "own outputs" in (
            output_ref_problem("kubernetes", "outputs.kubernetes.key", True) or ""
        )
