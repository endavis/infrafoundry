"""Provider settings ``secret://`` URIs resolve at every reader (#1594)."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.config.models import (
    BitwardenBackendConfig,
    EnvironmentConfig,
    SecretBackendsConfig,
)
from infrafoundry.core.provider_mixins import TerraformGeneratorMixin
from infrafoundry.core.validation import ValidationReport
from infrafoundry.core.validation_helpers import (
    report_settings_secret_problems,
    resolved_env_or_report,
)
from infrafoundry.secrets.backends.bitwarden import close_bitwarden_sessions
from infrafoundry.secrets.environment import (
    provider_settings_secret_problems,
    resolve_secret_settings,
    resolved_environment_data,
    resolved_provider_settings,
    with_resolved_provider_settings,
)
from infrafoundry.secrets.resolver import SecretResolutionError
from tests.unit.secrets.bw_stub import FIXTURE_VALUE, SERVER, StubBw, install_stub

PW_URI = "secret://bitwarden/Router Admin/password"
KEY_URI = "secret://bitwarden/Router Admin/api_key"
KEY_VALUE = "fixture-api-456"


@pytest.fixture(autouse=True)
def _close_sessions() -> Iterator[None]:
    close_bitwarden_sessions()
    yield
    close_bitwarden_sessions()


@pytest.fixture
def stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StubBw:
    return install_stub(tmp_path, monkeypatch)


def make_env(provider_settings: dict[str, Any], **extra: Any) -> EnvironmentConfig:
    return EnvironmentConfig(
        name="test",
        secrets={"db": {"password": "from-sops"}},
        secret_backends=SecretBackendsConfig(bitwarden=BitwardenBackendConfig(server=SERVER)),
        provider_settings=provider_settings,
        **extra,
    )


class TestResolveSecretSettings:
    def test_no_uri_is_independent_copy_and_no_bw_call(self, stub: StubBw) -> None:
        settings = {"a": {"b": [1, {"c": "plain"}]}}
        out = resolve_secret_settings(make_env({}), settings)
        assert out == settings
        assert out is not settings
        assert out is not None
        out["a"]["b"].append(2)
        assert settings["a"]["b"] == [1, {"c": "plain"}]
        assert stub.calls() == []

    def test_none_in_none_out(self) -> None:
        assert resolve_secret_settings(make_env({}), None) is None

    def test_nested_dicts_and_lists(self, stub: StubBw) -> None:
        settings = {
            "firewalls": {"fw-b": {"api_key": KEY_URI, "api_url": "https://fw-b.example.com"}},
            "items": [PW_URI, {"k": PW_URI}],
        }
        out = resolve_secret_settings(make_env({}), settings)
        assert out == {
            "firewalls": {"fw-b": {"api_key": KEY_VALUE, "api_url": "https://fw-b.example.com"}},
            "items": [FIXTURE_VALUE, {"k": FIXTURE_VALUE}],
        }
        assert settings["items"] == [PW_URI, {"k": PW_URI}]

    def test_error_names_uri_not_value(self) -> None:
        env = make_env({})
        with pytest.raises(SecretResolutionError) as exc:
            resolve_secret_settings(env, {"x": "secret://env_secrets/db/missing"})
        assert "secret://env_secrets/db/missing" in str(exc.value)
        assert "from-sops" not in str(exc.value)


class TestProviderAccessors:
    def test_instance_id_reads_base_block(self, stub: StubBw) -> None:
        env = make_env({"opnsense": {"api_key": KEY_URI}})
        assert resolved_provider_settings(env, "opnsense@fw-b") == {"api_key": KEY_VALUE}

    def test_missing_provider_is_none(self) -> None:
        assert resolved_provider_settings(make_env({}), "oci") is None

    def test_with_resolved_leaves_original_alone(self, stub: StubBw) -> None:
        env = make_env({"opnsense": {"api_key": KEY_URI}, "oci": {"x": PW_URI}})
        before = env.provider_settings
        out = with_resolved_provider_settings(env, "opnsense")
        assert out.provider_settings["opnsense"] == {"api_key": KEY_VALUE}
        assert out.provider_settings["oci"] == {"x": PW_URI}
        assert env.provider_settings is before
        assert env.provider_settings["opnsense"] == {"api_key": KEY_URI}

    def test_environment_data(self, stub: StubBw) -> None:
        env = make_env({"proxmox": {"api_token": PW_URI}})
        data = resolved_environment_data(env, "proxmox")
        assert data["provider_settings"]["proxmox"]["api_token"] == FIXTURE_VALUE
        assert env.provider_settings["proxmox"]["api_token"] == PW_URI


class TestOfflineProblems:
    def test_reports_paths_without_values(self, stub: StubBw) -> None:
        env = make_env(
            {
                "tailscale": {
                    "a": "secret://env_secrets/db/nope",
                    "b": "secret://file/x",
                    "c": "secret://bitwarden",
                    "d": {"e": ["secret://bitwarden/NoField"]},
                    "ok": PW_URI,
                }
            }
        )
        problems = provider_settings_secret_problems(env, "tailscale")
        joined = "\n".join(problems)
        assert len(problems) == 4
        assert "provider_settings.tailscale.a:" in joined
        assert "provider_settings.tailscale.b:" in joined
        assert "provider_settings.tailscale.c:" in joined
        assert "provider_settings.tailscale.d.e[0]:" in joined
        assert stub.calls() == []

    def test_presence_can_be_skipped(self) -> None:
        env = make_env({"tailscale": {"a": "secret://env_secrets/db/nope"}})
        assert provider_settings_secret_problems(env, "tailscale", check_presence=False) == []

    def test_report_helper(self) -> None:
        env = make_env({"tailscale": {"a": "secret://file/x"}})
        report = ValidationReport()
        report_settings_secret_problems(env, "tailscale", report)
        assert [r.check_name for r in report.results] == ["tailscale_settings_secrets"]
        assert report.has_errors()


class TestResolvedEnvOrReport:
    def test_failure_reported_once_without_value(self) -> None:
        env = make_env({"oci": {"k": "secret://env_secrets/db/missing"}})
        report = ValidationReport()
        assert resolved_env_or_report(env, "oci", report) is None
        assert len(report.results) == 1
        result = report.results[0]
        assert result.check_name == "oci_settings_secrets"
        assert "secret://env_secrets/db/missing" in result.message
        assert "from-sops" not in result.message

    def test_success_returns_resolved_copy(self, stub: StubBw) -> None:
        env = make_env({"oci": {"k": PW_URI}})
        resolved = resolved_env_or_report(env, "oci", ValidationReport())
        assert resolved is not None
        assert resolved.provider_settings["oci"]["k"] == FIXTURE_VALUE


class _Harness(TerraformGeneratorMixin):
    name = "test"

    def __init__(self, env: EnvironmentConfig) -> None:
        self.config_dir = Path("/nonexistent")
        self.terraform_dir = Path("/nonexistent/terraform")
        self._env = env

    def _load_environment_config(self) -> EnvironmentConfig | None:
        return self._env

    def _write_terraform_file(self, filename: str, content: str) -> None:  # pragma: no cover
        raise AssertionError


class TestBuildTerraformEnvVars:
    def test_resolves_bitwarden_by_default(self, stub: StubBw) -> None:
        env = make_env({"test": {"token": PW_URI, "plain": "p"}})
        out = _Harness(env).build_terraform_env_vars("test", {"token": "t", "plain": "p"})
        assert out == {"TF_VAR_t": FIXTURE_VALUE, "TF_VAR_p": "p"}

    def test_unmapped_uri_starts_no_bw(self, stub: StubBw) -> None:
        env = make_env({"test": {"token": PW_URI, "other": PW_URI}})
        _Harness(env).build_terraform_env_vars("test", {"plain": "p"})
        assert stub.calls() == []

    def test_no_secret_in_debug_logs(self, stub: StubBw, caplog: pytest.LogCaptureFixture) -> None:
        env = make_env({"test": {"token": PW_URI}})
        with caplog.at_level(logging.DEBUG):
            _Harness(env).build_terraform_env_vars("test", {"token": "t"})
        assert FIXTURE_VALUE not in caplog.text


def _opnsense_env(settings: dict[str, Any]) -> EnvironmentConfig:
    return make_env({"opnsense": settings})


class TestOpnsenseClient:
    def _build(self, env: EnvironmentConfig, provider: str = "opnsense") -> MagicMock:
        from infrafoundry.providers.opnsense.services.base import BaseService

        with (
            patch("infrafoundry.core.config.ConfigManager") as manager,
            patch("infrafoundry.providers.opnsense.services.base.OPNsenseClient") as client,
        ):
            manager.return_value.load_environment.return_value = env
            BaseService.client_from_environment("test", provider, Path("."))
        return client

    def test_flat_settings_resolved(self, stub: StubBw, caplog: pytest.LogCaptureFixture) -> None:
        env = _opnsense_env(
            {
                "api_url": "https://fw-a.example.com",
                "api_key": KEY_URI,
                "api_secret": PW_URI,
            }
        )
        with caplog.at_level(logging.DEBUG):
            client = self._build(env)
        kwargs = client.call_args.kwargs
        assert kwargs["api_key"] == KEY_VALUE
        assert kwargs["api_secret"] == FIXTURE_VALUE
        assert re.search(r"\bfw-a\.example\.com\b", kwargs["base_url"])
        assert FIXTURE_VALUE not in caplog.text

    def test_per_firewall_settings_resolved(self, stub: StubBw) -> None:
        env = _opnsense_env(
            {
                "firewalls": {
                    "fw-b": {
                        "api_url": "https://fw-b.example.com",
                        "api_key": KEY_URI,
                        "api_secret": PW_URI,
                    }
                }
            }
        )
        client = self._build(env, "opnsense@fw-b")
        assert client.call_args.kwargs["api_secret"] == FIXTURE_VALUE

    def test_repeated_client_builds_fetch_item_once(self, stub: StubBw) -> None:
        env = _opnsense_env(
            {"api_url": "https://fw-a.example.com", "api_key": KEY_URI, "api_secret": PW_URI}
        )
        for _ in range(5):
            kwargs = self._build(env).call_args.kwargs
            assert kwargs["api_key"] == KEY_VALUE
            assert kwargs["api_secret"] == FIXTURE_VALUE
        argvs = [c["argv"] for c in stub.calls()]
        assert sum(1 for a in argvs if a[:2] == ["list", "items"]) == 1
        assert sum(1 for a in argvs if a[0] == "sync") == 1


class TestOpnsenseValidatorHooks:
    def _provider(self, tmp_path: Path) -> Any:
        from infrafoundry.providers.opnsense import OPNsenseProvider

        return OPNsenseProvider(tmp_path, tmp_path)

    def test_connectivity_sees_resolved_creds(self, stub: StubBw, tmp_path: Path) -> None:
        env = _opnsense_env({"api_key": KEY_URI})
        with patch("infrafoundry.providers.opnsense.OPNsenseValidator") as validator:
            self._provider(tmp_path).validate_connectivity(env, ValidationReport())
        seen = validator.call_args.args[0]
        assert seen.provider_settings["opnsense"]["api_key"] == KEY_VALUE
        assert env.provider_settings["opnsense"]["api_key"] == KEY_URI

    def test_offline_makes_no_bw_call(self, stub: StubBw, tmp_path: Path) -> None:
        env = _opnsense_env({"api_key": KEY_URI})
        with patch("infrafoundry.providers.opnsense.OPNsenseValidator") as validator:
            self._provider(tmp_path).validate_offline([], [], env, ValidationReport())
        assert validator.call_args.args[0] is env
        assert stub.calls() == []

    def test_unresolvable_uri_is_reported(self, tmp_path: Path) -> None:
        env = _opnsense_env({"api_key": "secret://env_secrets/db/missing"})
        report = ValidationReport()
        with patch("infrafoundry.providers.opnsense.OPNsenseValidator") as validator:
            self._provider(tmp_path).validate_connectivity(env, report)
        validator.assert_not_called()
        assert [r.check_name for r in report.results] == ["opnsense_settings_secrets"]
        assert "from-sops" not in report.results[0].message


class TestOtherProviders:
    def test_proxmox_connectivity_resolved(self, stub: StubBw, tmp_path: Path) -> None:
        from infrafoundry.providers.proxmox import ProxmoxProvider

        env = make_env({"proxmox": {"api_token": PW_URI}})
        with patch("infrafoundry.providers.proxmox.ProxmoxValidator") as validator:
            ProxmoxProvider(tmp_path, tmp_path).validate_connectivity(env, ValidationReport())
        assert validator.call_args.args[0].provider_settings["proxmox"]["api_token"] == (
            FIXTURE_VALUE
        )

    def test_aws_terraform_env_vars_resolved(self, stub: StubBw, tmp_path: Path) -> None:
        from infrafoundry.providers.aws import AWSProvider

        env = make_env({"aws": {"region": "eu-west-1", "profile": PW_URI}})
        provider = AWSProvider(tmp_path, tmp_path)
        with patch.object(provider, "_load_environment_config", return_value=env):
            out = provider.get_terraform_env_vars()
        assert out["TF_VAR_aws_profile"] == FIXTURE_VALUE
        assert out["TF_VAR_aws_region"] == "eu-west-1"

    @pytest.mark.parametrize(
        ("module", "command", "target"),
        [
            ("export", "export_proxmox", "ProxmoxConfigExporter"),
            ("dump", "dump", "ProxmoxStateDumper"),
        ],
    )
    def test_proxmox_cli_hands_resolved_settings(
        self, stub: StubBw, tmp_path: Path, module: str, command: str, target: str
    ) -> None:
        import importlib

        from click.testing import CliRunner

        mod = importlib.import_module(f"infrafoundry.providers.proxmox.cli.{module}")
        config_manager = MagicMock()
        config_manager.load_environment.return_value = make_env(
            {"proxmox": {"api_url": "https://pve.example.com:8006", "api_token_secret": PW_URI}}
        )
        with (
            patch.object(mod, "ConfigManager", return_value=config_manager),
            patch.object(mod, target) as consumer,
        ):
            CliRunner().invoke(
                getattr(mod, command),
                ["--env", "test", "--output", str(tmp_path / "out")],
                obj={"config_dir": tmp_path},
            )
        handed = consumer.call_args.args[0]
        assert handed["provider_settings"]["proxmox"]["api_token_secret"] == FIXTURE_VALUE

    def test_proxmox_sdn_dry_run_client_resolved(self, stub: StubBw, tmp_path: Path) -> None:
        from infrafoundry.providers.proxmox import ProxmoxProvider

        env = make_env({"proxmox": {"api_token": PW_URI}})
        provider = ProxmoxProvider(tmp_path, tmp_path)
        with (
            patch.object(provider, "_load_environment_config", return_value=env),
            patch("infrafoundry.providers.proxmox.api_client.ProxmoxClient") as client,
        ):
            provider._sdn_dry_run_client()
        assert client.from_provider_settings.call_args.args[0]["api_token"] == FIXTURE_VALUE

    def test_oci_connectivity_resolved_offline_raw(self, stub: StubBw, tmp_path: Path) -> None:
        from infrafoundry.providers.oci import OCIProvider

        env = make_env({"oci": {"tenancy_ocid": PW_URI}})
        provider = OCIProvider(tmp_path, tmp_path)
        with patch("infrafoundry.providers.oci.OCIValidator") as validator:
            provider.validate_connectivity(env, ValidationReport())
            assert validator.call_args.args[0].provider_settings["oci"]["tenancy_ocid"] == (
                FIXTURE_VALUE
            )
            validator.reset_mock()
            stub_calls = len(stub.calls())
            provider.validate_offline([], [], env, ValidationReport())
        assert validator.call_args.args[0] is env
        assert len(stub.calls()) == stub_calls

    def test_kubernetes_connectivity_resolved(self, stub: StubBw, tmp_path: Path) -> None:
        from infrafoundry.providers.kubernetes import KubernetesProvider

        env = make_env({"kubernetes": {"kubeconfig_path": PW_URI}})
        provider = KubernetesProvider(tmp_path, tmp_path)
        with patch("infrafoundry.providers.kubernetes.KubernetesValidator") as validator:
            provider.validate_connectivity(env, ValidationReport())
        seen = validator.call_args.args[0]
        assert seen.provider_settings["kubernetes"]["kubeconfig_path"] == FIXTURE_VALUE

    def test_tailscale_validator_offline(self, stub: StubBw) -> None:
        from infrafoundry.providers.tailscale.validator import TailscaleValidator

        bad = make_env({"tailscale": {"api_key": "secret://file/x"}})
        report = ValidationReport()
        TailscaleValidator(bad, report).validate_connectivity()
        assert any(r.check_name == "tailscale_settings_secrets" for r in report.results)
        good = make_env({"tailscale": {"api_key": PW_URI}})
        report = ValidationReport()
        TailscaleValidator(good, report).validate_connectivity()
        assert not report.has_errors()
        assert stub.calls() == []

    def test_mikrotik_and_openwrt_settings_use_accessor(self, stub: StubBw) -> None:
        for name in ("mikrotik", "openwrt"):
            module = __import__(
                f"infrafoundry.providers.{name}.settings", fromlist=["resolved_provider_settings"]
            )
            assert module.resolved_provider_settings is resolved_provider_settings


class TestEsxi:
    def _provider(self, tmp_path: Path, env: EnvironmentConfig) -> Any:
        from infrafoundry.providers.esxi import EsxiProvider

        provider = EsxiProvider(tmp_path, tmp_path)
        provider._load_environment_config = lambda: env  # type: ignore[method-assign]
        return provider

    def test_uri_host_fields_become_env_vars_not_tfvars(self, stub: StubBw, tmp_path: Path) -> None:
        env = make_env(
            {
                "esxi": {
                    "hosts": {
                        "esx-a": {"hostname": PW_URI, "username": "root"},
                        "esx-b": {"hostname": "esx-b.example.com", "username": KEY_URI},
                    }
                }
            }
        )
        provider = self._provider(tmp_path, env)
        assert provider.get_terraform_env_vars() == {
            "TF_VAR_esxi_hostname_esx_a": FIXTURE_VALUE,
            "TF_VAR_esxi_username_esx_b": KEY_VALUE,
        }
        provider.terraform_dir = tmp_path
        provider._generate_multi_host_tfvars(
            [{"name": "esx-a", "alias": "esx_a"}, {"name": "esx-b", "alias": "esx_b"}]
        )
        tfvars = (tmp_path / "terraform.tfvars").read_text()
        assert FIXTURE_VALUE not in tfvars
        assert "secret://" not in tfvars
        assert "esxi_username_esx_a" in tfvars
        assert "esxi_hostname_esx_b" in tfvars

    def test_plaintext_hosts_emit_nothing(self, tmp_path: Path) -> None:
        env = make_env({"esxi": {"hosts": {"esx-a": {"hostname": "esx-a.example.com"}}}})
        assert self._provider(tmp_path, env).get_terraform_env_vars() == {}

    def test_connectivity_resolved(self, stub: StubBw, tmp_path: Path) -> None:
        env = make_env({"esxi": {"hosts": {"esx-a": {"hostname": PW_URI}}}})
        with patch("infrafoundry.providers.esxi.EsxiValidator") as validator:
            self._provider(tmp_path, env).validate_connectivity(env, ValidationReport())
        seen = validator.call_args.args[0]
        assert seen.provider_settings["esxi"]["hosts"]["esx-a"]["hostname"] == FIXTURE_VALUE


MISSING_URI = "secret://env_secrets/db/missing"


def _firewalls_env(fw_a: dict[str, Any], fw_b: dict[str, Any], **shared: Any) -> EnvironmentConfig:
    return make_env(
        {"opnsense": {"primary": "fw-a", "firewalls": {"fw-a": fw_a, "fw-b": fw_b}, **shared}}
    )


class TestOpnsenseInstanceScoping:
    """Only the addressed instance and the shared keys resolve (#1596)."""

    def test_sibling_failure_does_not_raise(self, stub: StubBw) -> None:
        env = _firewalls_env({"api_key": MISSING_URI}, {"api_key": KEY_URI})
        resolved = resolved_provider_settings(env, "opnsense@fw-b")
        assert resolved is not None
        assert resolved["firewalls"]["fw-b"]["api_key"] == KEY_VALUE
        assert resolved["firewalls"]["fw-a"]["api_key"] == MISSING_URI

    def test_plain_id_resolves_only_the_primary(self, stub: StubBw) -> None:
        env = _firewalls_env({"api_key": PW_URI}, {"api_key": KEY_URI})
        resolved = resolved_provider_settings(env, "opnsense")
        assert resolved is not None
        assert resolved["firewalls"]["fw-a"]["api_key"] == FIXTURE_VALUE
        assert resolved["firewalls"]["fw-b"]["api_key"] == KEY_URI

    def test_shared_key_failure_raises_for_every_instance(self) -> None:
        env = _firewalls_env({"api_key": "a"}, {"api_key": "b"}, api_secret=MISSING_URI)
        for provider in ("opnsense", "opnsense@fw-a", "opnsense@fw-b"):
            with pytest.raises(SecretResolutionError):
                resolved_provider_settings(env, provider)

    def test_undeclared_instance_resolves_shared_keys_only(self, stub: StubBw) -> None:
        env = _firewalls_env({"api_key": MISSING_URI}, {"api_key": MISSING_URI}, api_secret=PW_URI)
        resolved = resolved_provider_settings(env, "opnsense@fw-z")
        assert resolved is not None
        assert resolved["api_secret"] == FIXTURE_VALUE
        assert resolved["firewalls"]["fw-a"]["api_key"] == MISSING_URI

    def test_kubernetes_clusters_are_scoped(self, stub: StubBw) -> None:
        env = make_env(
            {
                "kubernetes": {
                    "primary": "c-a",
                    "clusters": {
                        "c-a": {"kubeconfig_path": MISSING_URI},
                        "c-b": {"kubeconfig_path": PW_URI},
                    },
                }
            }
        )
        resolved = resolved_provider_settings(env, "kubernetes@c-b")
        assert resolved is not None
        assert resolved["clusters"]["c-b"]["kubeconfig_path"] == FIXTURE_VALUE
        assert resolved["clusters"]["c-a"]["kubeconfig_path"] == MISSING_URI

    def test_original_untouched_and_siblings_are_copies(self, stub: StubBw) -> None:
        env = _firewalls_env({"api_key": MISSING_URI}, {"api_key": KEY_URI})
        resolved = resolved_provider_settings(env, "opnsense@fw-b")
        assert resolved is not None
        assert env.provider_settings["opnsense"]["firewalls"]["fw-b"]["api_key"] == KEY_URI
        assert (
            resolved["firewalls"]["fw-a"]
            is not env.provider_settings["opnsense"]["firewalls"]["fw-a"]
        )
        assert list(resolved["firewalls"]) == ["fw-a", "fw-b"]


class TestLabelAndDeduplicate:
    def test_same_report_twice_adds_one_result(self) -> None:
        env = _firewalls_env({"api_key": MISSING_URI}, {"api_key": "b"})
        report = ValidationReport()
        assert resolved_env_or_report(env, "opnsense", report) is None
        assert resolved_env_or_report(env, "opnsense", report) is None
        assert len(report.results) == 1

    def test_separate_reports_each_get_one(self) -> None:
        env = _firewalls_env({"api_key": MISSING_URI}, {"api_key": "b"})
        reports = [ValidationReport(), ValidationReport()]
        for report in reports:
            assert resolved_env_or_report(env, "opnsense", report) is None
        assert [len(r.results) for r in reports] == [1, 1]

    def test_message_is_labelled_and_names_only_its_own_uri(self) -> None:
        other = "secret://env_secrets/db/other-missing"
        env = _firewalls_env({"api_key": other}, {"api_key": MISSING_URI})
        report = ValidationReport()
        assert resolved_env_or_report(env, "opnsense@fw-b", report) is None
        message = report.results[0].message
        assert message.startswith("[fw-b] provider_settings.opnsense:")
        assert MISSING_URI in message
        assert other not in message
        assert "from-sops" not in message

    def test_flat_message_has_no_label(self) -> None:
        env = _opnsense_env({"api_key": MISSING_URI})
        report = ValidationReport()
        resolved_env_or_report(env, "opnsense", report)
        assert report.results[0].message.startswith("provider_settings.opnsense:")


class TestDuplicateHooks:
    def test_opnsense_sibling_failure_does_not_block_connectivity(
        self, stub: StubBw, tmp_path: Path
    ) -> None:
        from infrafoundry.providers.opnsense import OPNsenseProvider

        env = _firewalls_env({"api_key": MISSING_URI}, {"api_key": KEY_URI})
        report = ValidationReport()
        provider = OPNsenseProvider(tmp_path, tmp_path)
        provider.name = "opnsense@fw-b"
        with patch("infrafoundry.providers.opnsense.OPNsenseValidator") as validator:
            provider.validate_connectivity(env, report)
        validator.assert_called_once()
        assert [r.check_name for r in report.results] == []

    def test_opnsense_two_hooks_one_labelled_error(self, tmp_path: Path) -> None:
        from infrafoundry.providers.opnsense import OPNsenseProvider

        env = _firewalls_env({"api_key": MISSING_URI}, {"api_key": "b"})
        report = ValidationReport()
        provider = OPNsenseProvider(tmp_path, tmp_path)
        with patch("infrafoundry.providers.opnsense.OPNsenseValidator") as validator:
            provider.validate_connectivity(env, report)
            provider.validate_references([], env, report)
        validator.assert_not_called()
        errors = [r for r in report.results if r.check_name == "opnsense_settings_secrets"]
        assert len(errors) == 1
        assert errors[0].message.startswith("[fw-a] ")

    @pytest.mark.parametrize(
        ("module", "cls", "validator", "base", "settings"),
        [
            (
                "proxmox",
                "ProxmoxProvider",
                "ProxmoxValidator",
                "proxmox",
                {"api_token": MISSING_URI},
            ),
            ("oci", "OCIProvider", "OCIValidator", "oci", {"tenancy_ocid": MISSING_URI}),
            (
                "kubernetes",
                "KubernetesProvider",
                "KubernetesValidator",
                "kubernetes",
                {"kubeconfig_path": MISSING_URI},
            ),
        ],
    )
    def test_three_hooks_one_error(
        self,
        tmp_path: Path,
        module: str,
        cls: str,
        validator: str,
        base: str,
        settings: dict[str, Any],
    ) -> None:
        import importlib

        mod = importlib.import_module(f"infrafoundry.providers.{module}")
        provider = getattr(mod, cls)(tmp_path, tmp_path)
        env = make_env({base: settings})
        report = ValidationReport()
        with patch(f"infrafoundry.providers.{module}.{validator}"):
            provider.validate_connectivity(env, report)
            provider.validate_references([], env, report)
            provider.validate_references_in_context([], [], env, report)
        errors = [r for r in report.results if r.check_name == f"{base}_settings_secrets"]
        assert len(errors) == 1
