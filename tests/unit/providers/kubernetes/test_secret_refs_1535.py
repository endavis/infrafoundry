"""Tests for secret-backed values in the Kubernetes provider (#1535)."""

import base64
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.kubernetes import KubernetesProvider
from infrafoundry.providers.kubernetes.secret_refs import (
    collect_value_secret_refs,
    shape_errors,
    with_terraform_secrets,
)
from infrafoundry.providers.kubernetes.validator import KubernetesValidator
from tests.helpers.env import make_env_config

_PLACEHOLDER = "not-a-real-secret"
_B64 = base64.b64encode(_PLACEHOLDER.encode()).decode()


def _res(type_: str, name: str, **config: Any) -> ResourceConfig:
    return ResourceConfig(provider="kubernetes", type=type_, name=name, config=config)


def _secret(**config: Any) -> ResourceConfig:
    return _res("secrets", "creds", **config)


def _helm(**config: Any) -> ResourceConfig:
    return _res("helm_releases", "rel", **config)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("KUBECONFIG", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))


# --- helpers ----------------------------------------------------------------


class TestHelpers:
    def test_collect_refs_in_order_ignoring_literals(self) -> None:
        secret = _secret(
            string_data={"a": "literal"},
            string_data_secrets={"pw": "app.admin_token"},
            data_secrets={"tls": "app.tls_key_b64"},
        )
        assert collect_value_secret_refs(secret) == ["app.admin_token", "app.tls_key_b64"]
        helm = _helm(
            set_sensitive=[
                {"name": "x", "value": "lit"},
                {"name": "y", "value_secret": "app.oauth"},
            ]
        )
        assert collect_value_secret_refs(helm) == ["app.oauth"]

    def test_with_terraform_secrets_merges_dedups_and_does_not_mutate(self) -> None:
        secret = _secret(
            terraform_secrets=["app.admin_token", "app.other"],
            string_data_secrets={"pw": "app.admin_token", "x": "app.third"},
        )
        result = with_terraform_secrets(secret)
        assert result.config["terraform_secrets"] == ["app.admin_token", "app.other", "app.third"]
        assert secret.config["terraform_secrets"] == ["app.admin_token", "app.other"]

    def test_with_terraform_secrets_rejects_non_list(self) -> None:
        with pytest.raises(TypeError, match="non-list"):
            with_terraform_secrets(_secret(terraform_secrets="app.x"))

    def test_with_terraform_secrets_without_refs_adds_nothing(self) -> None:
        assert "terraform_secrets" not in with_terraform_secrets(_secret(data={"a": _B64})).config

    @pytest.mark.parametrize(
        "resource",
        [
            _secret(string_data_secrets=["app.x"]),
            _secret(data_secrets={"k": 5}),
            _secret(string_data={"k": "v"}, string_data_secrets={"k": "app.x"}),
            _secret(data={"k": _B64}, data_secrets={"k": "app.x"}),
            _helm(set_sensitive=[{"name": "n", "value": "v", "value_secret": "app.x"}]),
            _helm(set_sensitive=[{"name": "n"}]),
            _helm(set_sensitive=[{"name": "n", "value_secret": 3}]),
        ],
    )
    def test_shape_errors_detected(self, resource: ResourceConfig) -> None:
        assert len(shape_errors(resource)) == 1

    def test_shape_errors_clean(self) -> None:
        assert shape_errors(_secret(string_data_secrets={"k": "app.x"})) == []
        assert shape_errors(_helm(set_sensitive=[{"name": "n", "value_secret": "app.x"}])) == []


# --- rendering ----------------------------------------------------------------


@pytest.fixture
def provider(tmp_path: Path) -> KubernetesProvider:
    (tmp_path / "config").mkdir()
    (tmp_path / "output").mkdir()
    prov = KubernetesProvider(tmp_path / "config", tmp_path / "output")
    prov.set_environment("test")
    return prov


def _tf_dir(provider: KubernetesProvider) -> Path:
    return provider.output_dir / "terraform" / "kubernetes"


class TestRendering:
    def test_string_data_secrets_render_as_var(self, provider: KubernetesProvider) -> None:
        provider.generate_terraform([_secret(string_data_secrets={"password": "app.admin_token"})])
        content = (_tf_dir(provider) / "secrets.tf").read_text()
        assert "data = {" in content
        assert '"password" = var.app_admin_token' in content
        for tf in _tf_dir(provider).glob("*.tf"):
            assert _PLACEHOLDER not in tf.read_text()

    def test_data_secrets_render_in_binary_data_and_precedence(
        self, provider: KubernetesProvider
    ) -> None:
        provider.generate_terraform(
            [
                _secret(
                    string_data_secrets={"dup": "app.a"},
                    data_secrets={"tls": "app.tls_key_b64", "dup": "app.b"},
                )
            ]
        )
        content = (_tf_dir(provider) / "secrets.tf").read_text()
        binary = content.split("binary_data = {")[1].split("}")[0]
        assert '"tls" = var.app_tls_key_b64' in binary
        assert "dup" not in binary

    def test_helm_set_sensitive_value_secret(self, provider: KubernetesProvider) -> None:
        provider.generate_terraform(
            [
                _helm(
                    chart="c",
                    repository="https://charts.example.com",
                    namespace="default",
                    set_sensitive=[
                        {"name": "a", "value_secret": "app.oauth"},
                        {"name": "b", "value": "literal"},
                    ],
                )
            ]
        )
        content = (_tf_dir(provider) / "helm_releases.tf").read_text()
        assert "value = var.app_oauth\n" in content
        assert 'value = "literal"' in content

    def test_variables_declared_once_per_ref(self, provider: KubernetesProvider) -> None:
        provider.generate_terraform(
            [
                _secret(string_data_secrets={"pw": "app.shared"}),
                _helm(
                    chart="c",
                    repository="https://charts.example.com",
                    namespace="default",
                    set_sensitive=[{"name": "a", "value_secret": "app.shared"}],
                ),
            ]
        )
        content = (_tf_dir(provider) / "variables.tf").read_text()
        assert 'variable "kubeconfig_path"' in content
        assert content.count('variable "app_shared"') == 1
        assert "sensitive   = true" in content

    def test_literal_secret_unchanged(self, provider: KubernetesProvider) -> None:
        provider.generate_terraform([_secret(string_data={"u": "admin"}, data={"d": _B64})])
        content = (_tf_dir(provider) / "secrets.tf").read_text()
        assert '"u" = "admin"' in content
        assert f'"d" = "{_B64}"' in content
        assert "var." not in content


class TestEnvVars:
    def test_injects_after_generate_only(
        self, provider: KubernetesProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = make_env_config(
            name="test",
            secrets={"app": {"admin_token": _PLACEHOLDER}},
            provider_settings={"kubernetes": {"kubeconfig_path": "/k/config"}},
        )
        monkeypatch.setattr(provider, "_load_environment_config", lambda: env)
        assert "TF_VAR_app_admin_token" not in provider.get_terraform_env_vars()
        provider.generate_terraform([_secret(string_data_secrets={"pw": "app.admin_token"})])
        result = provider.get_terraform_env_vars()
        assert result["TF_VAR_app_admin_token"] == _PLACEHOLDER
        assert result["TF_VAR_kubeconfig_path"] == "/k/config"


# --- validation ---------------------------------------------------------------


def _validate(resources: list[ResourceConfig], secrets: dict[str, Any]) -> ValidationReport:
    report = ValidationReport()
    env = make_env_config(name="t", secrets=secrets)
    KubernetesValidator(env, report).validate_offline(resources)
    return report


def _errors(report: ValidationReport) -> list[str]:
    return [r.message for r in report.results if not r.passed and r.level == ValidationLevel.ERROR]


class TestValidation:
    def test_unresolved_ref_errors_naming_path(self) -> None:
        report = _validate([_secret(string_data_secrets={"pw": "app.missing"})], {})
        errors = _errors(report)
        assert any("app.missing" in e for e in errors)
        assert any(r.check_name == "kubernetes_terraform_secrets_creds" for r in report.results)

    def test_resolved_ref_passes(self) -> None:
        report = _validate(
            [_secret(string_data_secrets={"pw": "app.token"})], {"app": {"token": _PLACEHOLDER}}
        )
        assert _errors(report) == []

    def test_data_secrets_non_base64_errors_without_value(self) -> None:
        report = _validate(
            [_secret(data_secrets={"tls": "app.key"})], {"app": {"key": "!!not base64!!"}}
        )
        errors = _errors(report)
        assert len(errors) == 1
        assert "tls" in errors[0]
        assert "app.key" in errors[0]
        assert "!!not base64!!" not in errors[0]

    def test_data_secrets_base64_passes(self) -> None:
        report = _validate([_secret(data_secrets={"tls": "app.key"})], {"app": {"key": _B64}})
        assert _errors(report) == []

    def test_shape_errors_reported_without_exception(self) -> None:
        report = _validate(
            [
                _secret(string_data_secrets=["x"]),
                _helm(
                    chart="c",
                    repository="https://charts.example.com",
                    set_sensitive=[{"name": "n"}],
                ),
            ],
            {},
        )
        assert len(_errors(report)) == 2

    def test_no_network_calls(self) -> None:
        with (
            patch("subprocess.run") as run,
            patch("infrafoundry.providers.kubernetes.validator.KubeconfigValidator.validate") as v,
        ):
            _validate([_secret(string_data_secrets={"pw": "app.x"})], {"app": {"x": "y"}})
        run.assert_not_called()
        v.assert_not_called()
