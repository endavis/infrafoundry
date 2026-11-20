"""Tests for ``outputs.<provider>.<output>`` references in the Kubernetes provider (#1536)."""

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.kubernetes import KubernetesProvider
from infrafoundry.providers.kubernetes.secret_refs import shape_errors
from infrafoundry.providers.kubernetes.validator import KubernetesValidator
from tests.helpers.env import make_env_config

REF = "outputs.tailscale.oauth_client_k8s_operator_secret"
VAR = "outputs_tailscale_oauth_client_k8s_operator_secret"


def _res(type_: str, name: str, **config: Any) -> ResourceConfig:
    return ResourceConfig(provider="kubernetes", type=type_, name=name, config=config)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("KUBECONFIG", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))


@pytest.fixture
def provider(tmp_path: Path) -> KubernetesProvider:
    (tmp_path / "config").mkdir()
    (tmp_path / "output").mkdir()
    prov = KubernetesProvider(tmp_path / "config", tmp_path / "output")
    prov.set_environment("test")
    return prov


def _validate(*resources: ResourceConfig) -> ValidationReport:
    report = ValidationReport()
    KubernetesValidator(make_env_config(secrets={}), report).validate_offline(list(resources))
    return report


def _errors(report: ValidationReport) -> list[str]:
    return [r.message for r in report.results if not r.passed and r.level == ValidationLevel.ERROR]


class TestOutputRefs:
    def test_collects_from_all_three_fields(self, provider: KubernetesProvider) -> None:
        resources = [
            _res("secrets", "s", string_data_secrets={"k": REF}),
            _res("helm_releases", "h", set_sensitive=[{"name": "n", "value_secret": REF}]),
            _res("configmaps", "c", terraform_secrets=["outputs.tailscale.other", "app.x"]),
        ]
        assert provider.get_terraform_output_refs(resources) == [
            REF,
            "outputs.tailscale.other",
        ]

    def test_defaults_to_last_generation(self, provider: KubernetesProvider) -> None:
        assert provider.get_terraform_output_refs() == []
        provider.generate_terraform([_res("secrets", "s", string_data_secrets={"k": REF})])
        assert provider.get_terraform_output_refs() == [REF]

    def test_variable_declared_sensitive_and_no_value_rendered(
        self, provider: KubernetesProvider
    ) -> None:
        provider.generate_terraform([_res("secrets", "s", string_data_secrets={"k": REF})])
        tf_dir = provider.output_dir / "terraform" / "kubernetes"
        variables = (tf_dir / "variables.tf").read_text()
        block = variables.split(f'variable "{VAR}"')[1].split("}")[0]
        assert "sensitive" in block
        assert f"var.{VAR}" in (tf_dir / "secrets.tf").read_text()

    def test_provider_env_vars_skip_output_refs(self, provider: KubernetesProvider) -> None:
        provider.generate_terraform([_res("secrets", "s", string_data_secrets={"k": REF})])
        assert f"TF_VAR_{VAR}" not in provider.get_terraform_env_vars()


class TestValidation:
    def test_output_ref_not_reported_as_missing_secret(self) -> None:
        report = _validate(_res("secrets", "s", string_data_secrets={"k": REF}))
        assert _errors(report) == []

    def test_malformed_ref_errors(self) -> None:
        report = _validate(_res("secrets", "s", string_data_secrets={"k": "outputs.tailscale"}))
        assert any("outputs.<provider>.<output>" in m for m in _errors(report))

    def test_self_ref_errors(self) -> None:
        report = _validate(
            _res("secrets", "s", string_data_secrets={"k": "outputs.kubernetes.thing"})
        )
        assert any("own outputs" in m for m in _errors(report))

    def test_data_secrets_output_ref_errors(self) -> None:
        resource = _res("secrets", "s", data_secrets={"k": REF})
        assert len(shape_errors(resource)) == 1
        assert any("string_data_secrets" in m for m in _errors(_validate(resource)))
