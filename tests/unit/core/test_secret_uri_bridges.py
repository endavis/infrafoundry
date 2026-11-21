"""``secret://`` URIs in the Terraform and Ansible secret bridges (#1520).

Covers ``terraform_secrets`` (variable naming, env-var build, plan-time validation, the
``infra doctor`` secret sources, the Kubernetes value-secret fields), the host Tailscale auth ref
and the destroy-time tailnet cleanup. A stub ``bw`` on ``PATH`` stands in for the vault.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.cli.commands.infra._secret_sources import SourceStatus, collect_secret_sources
from infrafoundry.core.config.models import (
    BitwardenBackendConfig,
    EnvironmentConfig,
    SecretBackendsConfig,
)
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_mixins import (
    TerraformGeneratorMixin,
    collect_terraform_secret_vars,
    sanitize_secret_ref_to_tf_var,
    secret_ref_tf_var,
    secret_uri_tf_var,
)
from infrafoundry.core.tailscale import (
    TailnetDeviceCleanup,
    process_tailscale_config,
    remove_tailnet_devices,
)
from infrafoundry.core.validation import ValidationReport
from infrafoundry.core.validation_helpers import validate_terraform_secrets_references
from infrafoundry.providers.host import HostProvider
from infrafoundry.providers.kubernetes.secret_refs import shape_errors, with_terraform_secrets
from infrafoundry.secrets.backends.bitwarden import close_bitwarden_sessions
from tests.unit.secrets.bw_stub import FIXTURE_VALUE, SERVER, StubBw, install_stub

VAULT_URI = "secret://bitwarden/Router Admin/password"
SOPS_URI = "secret://env_secrets/db/password"
SOPS_VALUE = "from-sops-value"
CANARY = "canary-secret-value-777"


@pytest.fixture(autouse=True)
def _close_sessions() -> Iterator[None]:
    close_bitwarden_sessions()
    yield
    close_bitwarden_sessions()


@pytest.fixture
def stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StubBw:
    return install_stub(tmp_path, monkeypatch)


def make_env(*, vault: bool = True, secrets: dict[str, Any] | None = None) -> EnvironmentConfig:
    backends = (
        SecretBackendsConfig(bitwarden=BitwardenBackendConfig(server=SERVER)) if vault else None
    )
    return EnvironmentConfig(
        name="test",
        secrets=secrets if secrets is not None else {"db": {"password": SOPS_VALUE}},
        secret_backends=backends,
    )


def res(name: str, refs: list[str], rtype: str = "instance", **config: Any) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type=rtype,
        provider="test",
        config={"terraform_secrets": refs, **config},
        package_path="apps/example",
        package_secrets={"k": "pkg-value"},
    )


class _Harness(TerraformGeneratorMixin):
    name = "test"

    def __init__(self) -> None:
        self.config_dir = Path("/nonexistent")
        self.terraform_dir = Path("/nonexistent/terraform")

    def _load_environment_config(self) -> EnvironmentConfig | None:  # pragma: no cover
        return None

    def _write_terraform_file(self, filename: str, content: str) -> None:  # pragma: no cover
        raise AssertionError("not called")


class TestVariableNaming:
    def test_uri_name(self) -> None:
        assert (
            secret_uri_tf_var("secret://bitwarden/Router Admin/password")
            == "secret_bitwarden_router_admin_password"
        )
        assert secret_ref_tf_var(SOPS_URI) == "secret_env_secrets_db_password"

    def test_key_with_slashes_and_dashes(self) -> None:
        assert (
            secret_uri_tf_var("secret://bitwarden/a-b/c d/user") == "secret_bitwarden_a_b_c_d_user"
        )

    @pytest.mark.parametrize("bad", ["secret://bitwarden", "secret://bitwarden/", "plain"])
    def test_malformed_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError, match="valid secret://"):
            secret_uri_tf_var(bad)

    def test_dotted_and_package_naming_unchanged(self) -> None:
        assert secret_ref_tf_var("a.b") == "a_b"
        assert sanitize_secret_ref_to_tf_var("a.b") == "a_b"
        r = res("one", ["package.k"])
        assert secret_ref_tf_var("package.k", r) == "package_apps_example_k"

    def test_same_slug_collision_names_only_refs(self) -> None:
        a = res("a", ["secret://bitwarden/x y/password"])
        b = res("b", ["secret://bitwarden/x-y/password"])
        with pytest.raises(ValueError, match="both map to Terraform variable") as exc:
            collect_terraform_secret_vars([a, b])
        assert CANARY not in str(exc.value)

    def test_declared_vars_for_uri(self) -> None:
        assert collect_terraform_secret_vars([res("a", [SOPS_URI])]) == [
            {"name": "secret_env_secrets_db_password", "source": SOPS_URI}
        ]


class TestEnvVarBuild:
    def test_env_secrets_uri_and_dotted_distinct_same_value(self, stub: StubBw) -> None:
        out = _Harness()._build_terraform_secret_env_vars(
            make_env(), [res("a", [SOPS_URI, "db.password"])]
        )
        assert out == {
            "TF_VAR_secret_env_secrets_db_password": SOPS_VALUE,
            "TF_VAR_db_password": SOPS_VALUE,
        }
        assert stub.calls() == []

    def test_bitwarden_uri_and_mixed_refs(self, stub: StubBw) -> None:
        resource = res("a", [VAULT_URI, "db.password", "package.k", "outputs.other.thing"])
        out = _Harness()._build_terraform_secret_env_vars(make_env(), [resource])
        assert out == {
            "TF_VAR_secret_bitwarden_router_admin_password": FIXTURE_VALUE,
            "TF_VAR_db_password": SOPS_VALUE,
            "TF_VAR_package_apps_example_k": "pkg-value",
        }

    def test_dotted_only_runs_no_bw(self, stub: StubBw) -> None:
        _Harness()._build_terraform_secret_env_vars(make_env(), [res("a", ["db.password"])])
        assert stub.calls() == []

    def test_unresolvable_uri_keyerror_names_resource_and_uri(
        self, stub: StubBw, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        uri = "secret://bitwarden/Nope/password"
        with pytest.raises(KeyError) as exc:
            _Harness()._build_terraform_secret_env_vars(make_env(), [res("web", [uri])])
        message = exc.value.args[0]
        assert uri in message
        assert "'web'" in message
        assert FIXTURE_VALUE not in message + caplog.text

    def test_unconfigured_backend(self) -> None:
        with pytest.raises(KeyError, match="not configured"):
            _Harness()._build_terraform_secret_env_vars(
                make_env(vault=False), [res("a", [VAULT_URI])]
            )
        with pytest.raises(ValueError, match="valid secret://"):
            _Harness()._build_terraform_secret_env_vars(
                make_env(), [res("a", ["secret://bitwarden"])]
            )
        with pytest.raises(KeyError, match="not configured"):
            _Harness()._build_terraform_secret_env_vars(make_env(), [res("a", ["secret://file/x"])])

    def test_value_never_logged(self, stub: StubBw, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.DEBUG)
        _Harness()._build_terraform_secret_env_vars(make_env(), [res("a", [VAULT_URI])])
        assert FIXTURE_VALUE not in caplog.text


class TestValidator:
    def _run(self, env: EnvironmentConfig, refs: list[str]) -> ValidationReport:
        report = ValidationReport()
        validate_terraform_secrets_references("test", [res("a", refs)], env, report)
        return report

    def test_env_secrets_uri_present_and_missing(self) -> None:
        assert not self._run(make_env(), [SOPS_URI]).has_errors()
        report = self._run(make_env(), ["secret://env_secrets/db/missing"])
        assert report.has_errors()
        assert "secret://env_secrets/db/missing" in report.results[-1].message

    def test_bitwarden_uri_offline(self, stub: StubBw) -> None:
        assert not self._run(make_env(), [VAULT_URI]).has_errors()
        assert stub.calls() == []

    def test_bitwarden_not_configured(self, stub: StubBw) -> None:
        report = self._run(make_env(vault=False), [VAULT_URI])
        assert report.has_errors()
        assert "not configured" in report.results[-1].message
        assert stub.calls() == []

    def test_unknown_backend_named(self) -> None:
        report = self._run(make_env(), ["secret://nosuch/x/y"])
        assert "nosuch" in report.results[-1].message

    def test_uri_not_reported_as_missing_dotted_key(self) -> None:
        report = self._run(make_env(), [VAULT_URI, "db.password"])
        assert not report.has_errors()


class TestDoctorSources:
    def _rows(self, env: EnvironmentConfig, refs: list[str]) -> list[Any]:
        return collect_secret_sources(
            [res("a", refs)], "test", lambda: env.secrets, env_config=lambda: env
        )

    def test_env_secrets_resolved_and_unresolved(self) -> None:
        rows = self._rows(make_env(), [SOPS_URI, "secret://env_secrets/db/missing"])
        assert [r.status for r in rows] == [SourceStatus.RESOLVED, SourceStatus.UNRESOLVED]
        assert rows[0].source == "envs/test/secrets.yaml"

    def test_bitwarden_apply_time_no_bw(self, stub: StubBw) -> None:
        (row,) = self._rows(make_env(), [VAULT_URI])
        assert row.status is SourceStatus.APPLY_TIME
        assert row.source == "bitwarden (apply time)"
        assert stub.calls() == []

    def test_unconfigured_backend_unresolved_no_value(self) -> None:
        (row,) = self._rows(make_env(vault=False), [VAULT_URI])
        assert row.status is SourceStatus.UNRESOLVED
        assert "bitwarden" in (row.reason or "")
        assert FIXTURE_VALUE not in repr(row)

    def test_without_env_config_loader_only_env_secrets(self) -> None:
        rows = collect_secret_sources(
            [res("a", [SOPS_URI, VAULT_URI])], "test", lambda: {"db": {"password": "x"}}
        )
        assert [r.status for r in rows] == [SourceStatus.RESOLVED, SourceStatus.UNRESOLVED]


class TestKubernetesFolding:
    def _secret(self, ref: str) -> ResourceConfig:
        return ResourceConfig(
            name="app-secret",
            type="secrets",
            provider="kubernetes",
            config={"string_data_secrets": {"token": ref}},
        )

    def test_value_secret_uri_folded_validated_and_emitted(self, stub: StubBw) -> None:
        resource = with_terraform_secrets(self._secret(VAULT_URI))
        assert resource.config["terraform_secrets"] == [VAULT_URI]
        report = ValidationReport()
        validate_terraform_secrets_references("kubernetes", [resource], make_env(), report)
        assert not report.has_errors()
        out = _Harness()._build_terraform_secret_env_vars(make_env(), [resource])
        assert out == {"TF_VAR_secret_bitwarden_router_admin_password": FIXTURE_VALUE}

    def test_shape_message_wording(self) -> None:
        bad = ResourceConfig(
            name="s",
            type="secrets",
            provider="kubernetes",
            config={"string_data_secrets": {"k": 1}},
        )
        (message,) = shape_errors(bad)
        assert "secret reference strings" in message
        assert "dotted" not in message


class TestHostTailscaleAuth:
    @pytest.fixture
    def provider(self, tmp_path: Path) -> HostProvider:
        p = HostProvider(tmp_path / "envs", tmp_path / "output")
        p.set_environment("test")
        return p

    def _resolve(self, provider: HostProvider, env: EnvironmentConfig | None, ref: str) -> str:
        with patch.object(HostProvider, "_load_environment_config", return_value=env):
            return provider.resolve_tailscale_auth(ref)

    def test_env_secrets_uri(self, provider: HostProvider) -> None:
        assert self._resolve(provider, make_env(), SOPS_URI) == SOPS_VALUE

    def test_bitwarden_uri(self, provider: HostProvider, stub: StubBw) -> None:
        assert self._resolve(provider, make_env(), VAULT_URI) == FIXTURE_VALUE

    def test_unresolvable_uri_names_ref_not_value(
        self, provider: HostProvider, stub: StubBw
    ) -> None:
        ref = "secret://bitwarden/Nope/password"
        with pytest.raises(ValueError, match="Tailscale auth secret") as exc:
            self._resolve(provider, make_env(), ref)
        assert ref in str(exc.value)
        assert FIXTURE_VALUE not in str(exc.value)

    def test_no_environment_still_value_error(self, provider: HostProvider) -> None:
        with pytest.raises(ValueError, match="Tailscale auth secret"):
            self._resolve(provider, None, VAULT_URI)

    def test_process_tailscale_config_uri_auth_key(self) -> None:
        resource = ResourceConfig(
            name="node-a",
            type="instance",
            provider="oci",
            config={
                "tailscale": {
                    "auth": {"auth_key_secret": VAULT_URI},
                    "advertise_tags": ["tag:example"],
                }
            },
        )
        cfg = process_tailscale_config(resource, base64_encode=True)
        assert cfg is not None
        assert cfg["auth_key_var"] == secret_uri_tf_var(VAULT_URI)
        assert VAULT_URI in resource.config["terraform_secrets"]


CLIENT_ID_REF = "secret://env_secrets/tailscale/oauth_client_id"
CLIENT_SECRET_REF = "secret://bitwarden/Tailnet/password"


def _target() -> TailnetDeviceCleanup:
    return TailnetDeviceCleanup(
        resource_name="node-a",
        hostname="node-a",
        tags=("tag:example",),
        client_id_ref=CLIENT_ID_REF,
        client_secret_ref=CLIENT_SECRET_REF,
    )


def _session() -> MagicMock:
    session = MagicMock()
    session.post.return_value = MagicMock(status_code=200, json=lambda: {"access_token": "tok"})
    session.get.return_value = MagicMock(status_code=200, json=lambda: {"devices": []})
    return session


class TestTailnetCleanup:
    def test_lookup_resolves_uri_refs(self) -> None:
        values = {CLIENT_ID_REF: "the-id", CLIENT_SECRET_REF: "the-secret"}
        session = _session()
        report = remove_tailnet_devices([_target()], None, lookup=values.get, session=session)
        assert report.warnings == []
        assert session.post.call_args.kwargs["data"] == {
            "client_id": "the-id",
            "client_secret": "the-secret",
        }

    def test_lookup_none_gives_existing_warning_without_values(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        session = _session()
        values: dict[str, str | None] = {CLIENT_ID_REF: CANARY}
        report = remove_tailnet_devices([_target()], None, lookup=values.get, session=session)
        assert report.warnings == [
            f"Tailnet cleanup skipped: secret not found: {CLIENT_SECRET_REF}"
        ]
        assert CANARY not in " ".join(report.warnings) + caplog.text
        session.post.assert_not_called()
