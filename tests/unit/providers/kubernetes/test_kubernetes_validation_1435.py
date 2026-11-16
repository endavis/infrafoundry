"""Tests for Kubernetes offline validation, connection probing and cert auth (#1435)."""

import base64
import os
import stat
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator
from infrafoundry.providers.kubernetes.validator import KubernetesValidator
from infrafoundry.providers.kubernetes.validators import (
    CRDValidator,
    HelmValidator,
    KubeconfigValidator,
    NamespaceValidator,
)
from infrafoundry.providers.kubernetes.validators.context import (
    KubeconfigContext,
    KubernetesApiContext,
    KubernetesHelmContext,
)
from infrafoundry.providers.kubernetes.validators.kubeconfig_validator import KubeConnectionInfo
from tests.helpers.env import make_env_config

_B64 = base64.b64encode(b"not-a-real-secret").decode()


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Never read a real kubeconfig."""
    monkeypatch.delenv("KUBECONFIG", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))


def _res(type_: str, name: str, **config: Any) -> ResourceConfig:
    return ResourceConfig(provider="kubernetes", type=type_, name=name, config=config)


def _validator(**settings: Any) -> tuple[KubernetesValidator, ValidationReport]:
    report = ValidationReport()
    env = make_env_config(name="t", provider_settings={"kubernetes": settings})
    return KubernetesValidator(env, report), report


def _errors(report: ValidationReport) -> list[str]:
    return [r.message for r in report.results if not r.passed and r.level == ValidationLevel.ERROR]


# --- offline ----------------------------------------------------------------


class TestOffline:
    def test_makes_no_network_or_kubeconfig_calls(self) -> None:
        v, report = _validator()
        resources = [
            _res("deployments", "web", env_from=[{"configmap": "nope"}]),
            _res("secrets", "s", data={"k": "***"}),
            _res("helm_releases", "h", repository="https://charts.example.com"),
        ]
        with (
            patch.object(KubeconfigValidator, "validate") as kv,
            patch.object(BaseAPIValidator, "check_api_connectivity") as conn,
            patch.object(BaseAPIValidator, "fetch_json") as fetch,
        ):
            v.validate_offline(resources)
        kv.assert_not_called()
        conn.assert_not_called()
        fetch.assert_not_called()
        errors = _errors(report)
        assert any("configmap 'nope'" in m for m in errors)
        assert any("base64" in m for m in errors)
        assert any("'chart'" in m for m in errors)
        assert any(r.check_name == "kubernetes_references" for r in report.results)

    def test_resolves_names_against_reference_resources(self) -> None:
        v, report = _validator()
        dep = _res("deployments", "web", env_from=[{"configmap": "shared"}])
        v.validate_offline([dep], [dep, _res("configmaps", "shared")])
        assert _errors(report) == []

    def test_validate_references_runs_offline_once(self) -> None:
        v, report = _validator()
        v.validate_references([_res("namespaces", "ns")])
        assert [r.check_name for r in report.results].count("kubernetes_references") == 1

    def test_service_string_selector(self) -> None:
        v, report = _validator()
        v.validate_offline([_res("deployments", "web"), _res("services", "svc", selector="web")])
        assert not any(r.check_name == "kubernetes_ref_svc_selector" for r in report.results)
        v2, report2 = _validator()
        v2.validate_offline([_res("services", "svc", selector="other")])
        assert any(r.check_name == "kubernetes_ref_svc_selector" for r in report2.results)

    def test_service_dict_selector(self) -> None:
        v, report = _validator()
        v.validate_offline([_res("services", "svc", selector={"app": "other"})])
        assert any(r.check_name == "kubernetes_ref_svc_selector" for r in report.results)

    def test_non_dict_env_from_entry_does_not_crash(self) -> None:
        v, report = _validator()
        v.validate_offline([_res("deployments", "web", env_from=["oops", None])])
        assert _errors(report) == []

    def test_minio_shaped_set_has_no_errors_or_warnings(self) -> None:
        v, report = _validator()
        v.validate_offline(
            [
                _res("namespaces", "minio"),
                _res(
                    "helm_releases",
                    "operator",
                    chart="operator",
                    repository="https://operator.example.com",
                    namespace="minio-operator",
                    create_namespace=True,
                ),
                _res(
                    "helm_releases",
                    "tenant",
                    chart="tenant",
                    repository="https://operator.example.com",
                    namespace="minio",
                ),
                _res("secrets", "creds", namespace="minio", string_data={"k": "v"}),
                _res(
                    "manifests",
                    "svc",
                    namespace="minio",
                    manifest={"apiVersion": "v1", "kind": "Service"},
                ),
            ]
        )
        assert [r for r in report.results if not r.passed and r.level != ValidationLevel.INFO] == []


# --- connection probe --------------------------------------------------------


def _connected_probe(self_: KubeconfigValidator, ctx: KubeconfigContext) -> None:
    self_._connection_info = KubeConnectionInfo(
        server_url="https://k8s.example.com", connected=True
    )


class TestEnsureConnection:
    def _connected_probe(self, self_: KubeconfigValidator, ctx: KubeconfigContext) -> None:
        self_._connection_info = KubeConnectionInfo(
            server_url="https://k8s.example.com", connected=True
        )

    def test_probe_connects_runs_api_validators_and_keeps_report_clean(self) -> None:
        v, report = _validator()
        v.namespace_validator.validate = MagicMock()  # type: ignore[method-assign]
        v.crd_validator.validate = MagicMock()  # type: ignore[method-assign]
        with patch.object(KubeconfigValidator, "validate", _connected_probe):
            v.validate_references([_res("deployments", "web", namespace="x")])
        v.namespace_validator.validate.assert_called_once()
        v.crd_validator.validate.assert_called_once()
        assert not any(r.check_name.startswith("kubernetes_kubeconfig") for r in report.results)

    def test_probe_failure_skips_api_validators(self) -> None:
        v, _ = _validator()
        v.namespace_validator.validate = MagicMock()  # type: ignore[method-assign]
        v.crd_validator.validate = MagicMock()  # type: ignore[method-assign]
        v.validate_references([_res("deployments", "web", namespace="x")])
        v.namespace_validator.validate.assert_not_called()
        v.crd_validator.validate.assert_not_called()


class TestKubeconfigSourceOrder:
    def test_env_beats_setting_first_entry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KUBECONFIG", os.pathsep.join(["", "/a/one", "/b/two"]))
        v, _ = _validator(kubeconfig_path="/setting")
        assert v._kubeconfig_context().kubeconfig_path == "/a/one"

    def test_setting_when_env_unset(self) -> None:
        v, _ = _validator(kubeconfig_path="/setting")
        assert v._kubeconfig_context().kubeconfig_path == "/setting"

    def test_none_when_neither(self) -> None:
        v, _ = _validator()
        assert v._kubeconfig_context().kubeconfig_path is None


class TestMissingKubeconfig:
    def test_configured_path_missing_is_warning(self, tmp_path: Path) -> None:
        v, report = _validator(kubeconfig_path=str(tmp_path / "absent"))
        v.validate_connectivity()
        missing = [r for r in report.results if "not found" in r.message]
        assert missing
        assert not missing[0].passed
        assert missing[0].level == ValidationLevel.WARNING
        assert not report.has_errors()

    def test_no_kubeconfig_anywhere_is_warning(self) -> None:
        v, report = _validator()
        v.validate_connectivity()
        assert any(r.level == ValidationLevel.WARNING for r in report.results)
        assert not report.has_errors()


# --- helm / crd / namespaces ---------------------------------------------------


class TestHelmRepository:
    @pytest.mark.parametrize("chart", ["oci://registry.example.com/charts/x", "./charts/x"])
    def test_self_contained_chart_needs_no_repository(self, chart: str) -> None:
        report = ValidationReport()
        HelmValidator(report).validate(
            KubernetesHelmContext(helm_releases=[_res("helm_releases", "h", chart=chart)])
        )
        assert _errors(report) == []

    def test_bare_chart_needs_repository(self) -> None:
        report = ValidationReport()
        HelmValidator(report).validate(
            KubernetesHelmContext(helm_releases=[_res("helm_releases", "h", chart="x")])
        )
        assert len(_errors(report)) == 1


class TestCrd:
    def _run(self, helm: bool, installed: list[str]) -> ValidationReport:
        report = ValidationReport()
        api = BaseAPIValidator("kubernetes", make_env_config(), report)
        api.fetch_json = MagicMock(  # type: ignore[method-assign]
            return_value={"items": [{"spec": {"group": g}} for g in installed]}
        )
        CRDValidator(api, report).validate(
            KubernetesApiContext(
                server_url="https://k8s.example.com",
                headers={},
                verify_ssl=False,
                manifests=[
                    _res("manifests", "t", manifest={"apiVersion": "minio.min.io/v2", "kind": "T"})
                ],
                helm_releases_in_config=helm,
            )
        )
        return report

    def test_reads_manifest_api_version(self) -> None:
        report = self._run(False, ["minio.min.io"])
        assert any(
            r.check_name == "kubernetes_crd_minio.min.io" and r.passed for r in report.results
        )

    def test_missing_group_is_warning_with_helm(self) -> None:
        report = self._run(True, [])
        crd = next(r for r in report.results if r.check_name == "kubernetes_crd_minio.min.io")
        assert crd.passed
        assert crd.level == ValidationLevel.WARNING

    def test_missing_group_is_error_without_helm(self) -> None:
        assert len(_errors(self._run(False, []))) == 1


class TestHelmNamespaces:
    def test_helm_created_namespace_is_info(self) -> None:
        v, _ = _validator()
        v.namespace_validator.validate = MagicMock()  # type: ignore[method-assign]
        v.crd_validator.validate = MagicMock()  # type: ignore[method-assign]
        v._validate_api_references(
            [
                _res(
                    "helm_releases",
                    "op",
                    chart="c",
                    repository="r",
                    namespace="minio-operator",
                    create_namespace=True,
                )
            ],
            KubeConnectionInfo(server_url="https://k8s.example.com", connected=True),
        )
        ctx = v.namespace_validator.validate.call_args.args[0]
        assert "minio-operator" in ctx.config_namespaces
        assert ctx.helm_releases_in_config

    def test_namespace_validator_reports_info_for_config_namespace(self) -> None:
        report = ValidationReport()
        api = BaseAPIValidator("kubernetes", make_env_config(), report)
        api.fetch_json = MagicMock(return_value={"items": []})  # type: ignore[method-assign]
        NamespaceValidator(api, report).validate(
            KubernetesApiContext(
                server_url="https://k8s.example.com",
                headers={},
                verify_ssl=False,
                referenced_namespaces={"minio-operator"},
                config_namespaces={"minio-operator"},
            )
        )
        res = next(
            r for r in report.results if r.check_name == "kubernetes_namespace_minio-operator"
        )
        assert res.level == ValidationLevel.INFO


# --- client certificate auth ---------------------------------------------------


def _write_kubeconfig(path: Path, user: dict[str, Any], cluster_extra: dict[str, Any]) -> Path:
    cluster = {"server": "https://k8s.example.com:6443", **cluster_extra}
    path.write_text(
        yaml.dump(
            {
                "current-context": "c",
                "contexts": [{"name": "c", "context": {"cluster": "cl", "user": "u"}}],
                "clusters": [{"name": "cl", "cluster": cluster}],
                "users": [{"name": "u", "user": user}],
            }
        ),
        encoding="utf-8",
    )
    return path


def _kv() -> tuple[KubeconfigValidator, ValidationReport]:
    report = ValidationReport()
    api = BaseAPIValidator("kubernetes", make_env_config(), report)
    return KubeconfigValidator(api, report), report


class TestClientCertAuth:
    def test_inline_data_builds_cert_and_ca_files_with_private_modes(self, tmp_path: Path) -> None:
        cfg = _write_kubeconfig(
            tmp_path / "cfg",
            {"client-certificate-data": _B64, "client-key-data": _B64},
            {"certificate-authority-data": _B64},
        )
        kv, _ = _kv()
        kv.api_validator.check_api_connectivity = MagicMock(return_value=True)  # type: ignore[method-assign]
        kv.api_validator.fetch_json = MagicMock(return_value=None)  # type: ignore[method-assign]
        kv.validate(KubeconfigContext(kubeconfig_path=str(cfg)))
        info = kv.connection_info
        assert kv.is_connected
        assert info.client_cert is not None
        assert info.ca_bundle is not None
        files = [Path(info.client_cert[0]), Path(info.client_cert[1]), Path(info.ca_bundle)]
        for f in files:
            assert stat.S_IMODE(f.stat().st_mode) == 0o600
        assert stat.S_IMODE(files[0].parent.stat().st_mode) == 0o700
        kwargs = kv.api_validator.check_api_connectivity.call_args.kwargs
        assert kwargs["cert"] == info.client_cert
        assert kwargs["verify_ssl"] == info.ca_bundle
        assert kv.api_validator.fetch_json.call_args.kwargs["cert"] == info.client_cert
        kv.cleanup()
        assert not files[0].parent.exists()
        assert not kv.is_connected

    def test_file_form(self, tmp_path: Path) -> None:
        crt = tmp_path / "c.crt"
        key = tmp_path / "c.key"
        ca = tmp_path / "ca.crt"
        for f in (crt, key, ca):
            f.write_text("x")
        cfg = _write_kubeconfig(
            tmp_path / "cfg",
            {"client-certificate": str(crt), "client-key": str(key)},
            {"certificate-authority": str(ca)},
        )
        kv, _ = _kv()
        kv.api_validator.check_api_connectivity = MagicMock(return_value=True)  # type: ignore[method-assign]
        kv.api_validator.fetch_json = MagicMock(return_value=None)  # type: ignore[method-assign]
        kv.validate(KubeconfigContext(kubeconfig_path=str(cfg)))
        assert kv.connection_info.client_cert == (str(crt), str(key))
        assert kv.connection_info.ca_bundle == str(ca)
        kv.cleanup()

    def test_token_wins_over_cert(self, tmp_path: Path) -> None:
        cfg = _write_kubeconfig(
            tmp_path / "cfg",
            {"token": "tok", "client-certificate-data": _B64, "client-key-data": _B64},
            {"insecure-skip-tls-verify": True},
        )
        kv, _ = _kv()
        kv.api_validator.check_api_connectivity = MagicMock(return_value=True)  # type: ignore[method-assign]
        kv.api_validator.fetch_json = MagicMock(return_value=None)  # type: ignore[method-assign]
        kv.validate(KubeconfigContext(kubeconfig_path=str(cfg)))
        assert kv.connection_info.client_cert is None
        assert kv.connection_info.headers["Authorization"] == "Bearer tok"

    def test_no_auth_warns_mentioning_certificate(self, tmp_path: Path) -> None:
        cfg = _write_kubeconfig(tmp_path / "cfg", {}, {"insecure-skip-tls-verify": True})
        kv, report = _kv()
        kv.validate(KubeconfigContext(kubeconfig_path=str(cfg)))
        assert any(
            "client certificate" in r.message and r.level == ValidationLevel.WARNING
            for r in report.results
        )

    def test_validator_cleans_up_when_api_call_raises(self, tmp_path: Path) -> None:
        cfg = _write_kubeconfig(
            tmp_path / "cfg",
            {"client-certificate-data": _B64, "client-key-data": _B64},
            {"certificate-authority-data": _B64},
        )
        v, _ = _validator(kubeconfig_path=str(cfg))
        seen: list[Path] = []

        def boom(*args: Any, **kwargs: Any) -> bool:
            seen.append(Path(kwargs["cert"][0]).parent)
            raise RuntimeError("boom")

        v.kubeconfig_validator.api_validator.check_api_connectivity = boom  # type: ignore[method-assign]
        with pytest.raises(RuntimeError):
            v.validate_connectivity()
        assert seen
        assert not seen[0].exists()

    def test_probe_dir_removed_after_validate_references(self, tmp_path: Path) -> None:
        cfg = _write_kubeconfig(
            tmp_path / "cfg",
            {"client-certificate-data": _B64, "client-key-data": _B64},
            {"certificate-authority-data": _B64},
        )
        v, _ = _validator(kubeconfig_path=str(cfg))
        seen: list[Path] = []

        def check(*args: Any, **kwargs: Any) -> bool:
            seen.append(Path(kwargs["cert"][0]).parent)
            return False

        with patch.object(BaseAPIValidator, "check_api_connectivity", side_effect=check):
            v.validate_references([_res("namespaces", "n")])
        assert seen
        assert not seen[0].exists()


class TestRequestsPassThrough:
    def test_fetch_json_forwards_cert_and_ca_path(self) -> None:
        report = ValidationReport()
        api = BaseAPIValidator("kubernetes", make_env_config(), report)
        response = MagicMock(status_code=200)
        response.json.return_value = {}
        with patch("requests.request", return_value=response) as req:
            api.fetch_json(
                url="https://k8s.example.com/api",
                check_name="x",
                verify_ssl="/tmp/ca.pem",
                cert=("/tmp/c", "/tmp/k"),
            )
        assert req.call_args.kwargs["verify"] == "/tmp/ca.pem"
        assert req.call_args.kwargs["cert"] == ("/tmp/c", "/tmp/k")

    def test_connectivity_forwards_cert(self) -> None:
        report = ValidationReport()
        api = BaseAPIValidator("kubernetes", make_env_config(), report)
        response = MagicMock(status_code=200)
        with patch("requests.request", return_value=response) as req:
            assert api.check_api_connectivity(
                url="https://k8s.example.com/api", verify_ssl="/tmp/ca.pem", cert=("/c", "/k")
            )
        assert req.call_args.kwargs["cert"] == ("/c", "/k")
        assert req.call_args.kwargs["verify"] == "/tmp/ca.pem"
