"""Tests for offline provider validation on ``infra plan`` and ``infra apply`` (#1433)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.events import EventType
from infrafoundry.core.exceptions import ConfigValidationError, ProviderFilterError
from infrafoundry.core.orchestrator_workflows import (
    PlanOrchestrator,
    ProviderResourceBatch,
    ValidationOrchestrator,
)
from infrafoundry.core.protocols import ValidatesOffline
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.state import DeploymentStatus
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.aws import AWSProvider
from infrafoundry.providers.esxi import EsxiProvider
from infrafoundry.providers.host import HostProvider
from infrafoundry.providers.host.validator import HostValidator
from infrafoundry.providers.kubernetes import KubernetesProvider
from infrafoundry.providers.kubernetes.validators import KubeconfigValidator
from infrafoundry.providers.oci import OCIProvider
from infrafoundry.providers.oci.validator import OCIValidator
from infrafoundry.providers.opnsense import OPNsenseProvider
from infrafoundry.providers.opnsense.validator import OPNsenseValidator
from infrafoundry.providers.proxmox import ProxmoxProvider
from infrafoundry.providers.proxmox.validator import ProxmoxValidator
from infrafoundry.providers.tailscale import TailscaleProvider


def _res(name: str, provider: str = "proxmox", type_: str = "vm", **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, provider=provider, type=type_, config=config)


class _OfflineProvider:
    """Provider double with a real ``validate_offline`` (mocks fail ``isinstance``)."""

    def __init__(self, level: ValidationLevel | None, message: str = "bad") -> None:
        self.level = level
        self.message = message
        self.crash: Exception | None = None
        self.validate_offline = MagicMock(side_effect=self._validate)
        self.ensure_directories = MagicMock()
        self.set_environment = MagicMock()

    def _validate(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        if self.crash is not None:
            raise self.crash
        if self.level is not None:
            report.add_check("offline_check", False, self.message, self.level)


def _offline_provider(level: ValidationLevel | None, message: str = "bad") -> _OfflineProvider:
    return _OfflineProvider(level, message)


class _Harness:
    """A ``PlanOrchestrator`` wired to doubles, with the real offline validation pass."""

    def __init__(
        self,
        providers: dict[str, Any],
        resources: dict[str, list[ResourceConfig]],
        wire_validation: bool = True,
    ) -> None:
        self.output = io.StringIO()
        self.console = Console(file=self.output, width=200)
        self.state = MagicMock()
        self.state.create_deployment.return_value = 7
        self.state.get_managed_resources.return_value = []
        self.events = MagicMock()
        registry = MagicMock()
        registry.list_runners.return_value = []
        self.batches_calls = 0
        self.resources = resources
        self.providers = providers

        def iter_batches(
            by_provider: dict[str, list[ResourceConfig]],
            filt: list[str] | None,
            reverse: bool,
            env_name: str | None,
        ) -> list[ProviderResourceBatch]:
            self.batches_calls += 1
            out = []
            for name, res in by_provider.items():
                chosen = [r for r in res if not filt or r.name in filt]
                out.append(ProviderResourceBatch(name, chosen, len(res)))
            return out

        def load(env: str) -> Any:
            return [r for rs in resources.values() for r in rs], dict(resources)

        validation = ValidationOrchestrator(
            config_manager=MagicMock(),
            console=self.console,
            get_providers=lambda: providers,
            load_resources=load,
            iter_provider_batches=iter_batches,
        )
        self.orchestrator = PlanOrchestrator(
            self.console,
            self.state,
            self.events,
            registry,
            get_providers=lambda: providers,
            load_resources=load,
            iter_provider_batches=iter_batches,
            validate_resources=MagicMock(),
            has_policies=lambda: False,
            check_policies=MagicMock(),
            secret_manager_factory=MagicMock(),
            get_current_user=lambda: "tester",
            fail_on_missing_secrets=False,
            get_runner_priorities=lambda _: {},
            load_environment=lambda name: EnvironmentConfig(name=name),
            validate_offline=validation.validate_offline if wire_validation else None,
        )

    def plan(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("dry_run", False)
        return self.orchestrator.plan(
            env_name="dev",
            resource_filter=kwargs.pop("resource_filter", None),
            enforce_policies=False,
            **kwargs,
        )

    @property
    def text(self) -> str:
        return self.output.getvalue()


def test_warning_is_printed_and_plan_continues() -> None:
    provider = _offline_provider(ValidationLevel.WARNING, "heads up")
    h = _Harness({"proxmox": provider}, {"proxmox": [_res("vm1")]})

    result = h.plan()

    assert "heads up" in h.text
    assert "Config validation: proxmox" in h.text
    assert "proxmox" in result
    h.state.get_managed_resources.assert_called()


def test_error_raises_and_stops_before_any_state_write() -> None:
    provider = _offline_provider(ValidationLevel.ERROR, "broken reference")
    h = _Harness({"proxmox": provider}, {"proxmox": [_res("vm1")]})

    with pytest.raises(ConfigValidationError):
        h.plan()

    assert "broken reference" in h.text
    assert "Configuration validation failed: 1 errors" in h.text
    assert "Traceback" not in h.text
    h.state.get_managed_resources.assert_not_called()
    h.state.update_deployment_status.assert_called_with(
        7, DeploymentStatus.FAILED, "Configuration validation failed with 1 errors"
    )
    emitted = [c.args[0] for c in h.events.emit_event.call_args_list]
    assert EventType.PLAN_FAILED in emitted
    assert EventType.AFTER_PLAN not in emitted
    provider.ensure_directories.assert_not_called()


def test_error_in_second_provider_stops_before_first_provider_work() -> None:
    first = _offline_provider(None)
    second = _offline_provider(ValidationLevel.ERROR)
    h = _Harness(
        {"proxmox": first, "oci": second},
        {"proxmox": [_res("vm1")], "oci": [_res("i1", "oci", "instance")]},
    )

    with pytest.raises(ConfigValidationError):
        h.plan()

    h.state.get_managed_resources.assert_not_called()


def test_dry_run_still_validates() -> None:
    h = _Harness({"proxmox": _offline_provider(ValidationLevel.ERROR)}, {"proxmox": [_res("vm1")]})

    with pytest.raises(ConfigValidationError):
        h.plan(dry_run=True)


def test_validator_crash_becomes_warning_and_plan_continues() -> None:
    provider = _offline_provider(None)
    provider.crash = RuntimeError("boom")
    h = _Harness({"proxmox": provider}, {"proxmox": [_res("vm1")]})

    result = h.plan()

    assert "Offline validation of proxmox crashed: RuntimeError: boom" in h.text
    assert "proxmox" in result


def test_provider_without_validate_offline_is_skipped() -> None:
    provider = MagicMock(spec=ProviderBase)
    assert not isinstance(provider, ValidatesOffline)
    h = _Harness({"proxmox": provider}, {"proxmox": [_res("vm1")]})

    h.plan(dry_run=True)

    assert "Config validation" not in h.text


def test_resource_filter_validates_filtered_and_resolves_against_all() -> None:
    provider = _offline_provider(None)
    vm1, vm2 = _res("vm1"), _res("vm2")
    h = _Harness({"proxmox": provider}, {"proxmox": [vm1, vm2]})

    h.plan(resource_filter=["vm1"], dry_run=True)

    args = provider.validate_offline.call_args.args
    assert args[0] == [vm1]
    assert args[1] == [vm1, vm2]
    assert h.batches_calls == 1


def test_provider_filter_validates_only_selected_providers() -> None:
    selected = _offline_provider(None)
    other = _offline_provider(ValidationLevel.ERROR)
    h = _Harness(
        {"proxmox": selected, "oci": other},
        {"proxmox": [_res("vm1")], "oci": [_res("i1", "oci", "instance")]},
    )

    h.plan(provider_filter=["proxmox"], dry_run=True)

    selected.validate_offline.assert_called_once()
    other.validate_offline.assert_not_called()


def test_unknown_provider_filter_still_raises_provider_filter_error() -> None:
    h = _Harness({"proxmox": _offline_provider(None)}, {"proxmox": [_res("vm1")]})

    with pytest.raises(ProviderFilterError):
        h.plan(provider_filter=["nope"])


def test_old_construction_without_validate_offline_keeps_behaviour() -> None:
    provider = _offline_provider(ValidationLevel.ERROR)
    h = _Harness({"proxmox": provider}, {"proxmox": [_res("vm1")]}, wire_validation=False)

    h.plan(dry_run=True)

    provider.validate_offline.assert_not_called()


def test_clean_provider_prints_nothing() -> None:
    h = _Harness({"proxmox": _offline_provider(None)}, {"proxmox": [_res("vm1")]})

    h.plan(dry_run=True)

    assert "Config validation" not in h.text


# --- providers ---------------------------------------------------------------


@pytest.mark.parametrize(
    "provider_cls",
    [
        OPNsenseProvider,
        ProxmoxProvider,
        OCIProvider,
        HostProvider,
        AWSProvider,
        EsxiProvider,
        TailscaleProvider,
        KubernetesProvider,
    ],
)
def test_provider_implements_validates_offline(provider_cls: Any, tmp_path: Path) -> None:
    assert isinstance(provider_cls(tmp_path, tmp_path), ValidatesOffline)


def _subnet_with_conflict() -> ResourceConfig:
    return _res(
        "lan",
        "opnsense",
        "kea.dhcp4.subnets",
        subnet="192.0.2.0/24",
        auto_collect=True,
        routers=["192.0.2.1"],
    )


def test_opnsense_offline_gives_autocollect_warning_without_credentials_or_network() -> None:
    report = ValidationReport()
    validator = OPNsenseValidator(EnvironmentConfig(name="t"), report)
    validator.api_validator.get_credentials = MagicMock()  # type: ignore[method-assign]
    validator.api_validator.fetch_json = MagicMock()  # type: ignore[method-assign]

    validator.validate_offline([_subnet_with_conflict()])

    warnings = [r for r in report.results if r.level == ValidationLevel.WARNING and not r.passed]
    assert len(warnings) == 1
    assert "routers" in warnings[0].message
    validator.api_validator.get_credentials.assert_not_called()
    validator.api_validator.fetch_json.assert_not_called()


def test_opnsense_offline_skips_live_validators() -> None:
    validator = OPNsenseValidator(EnvironmentConfig(name="t"), ValidationReport())
    live = [
        "firewall_rule_validator",
        "vlan_validator",
        "interface_assignment_validator",
        "nat_rule_validator",
        "gateway_validator",
        "static_route_validator",
        "virtual_ip_validator",
        "unbound_host_alias_validator",
        "hostdiscovery_validator",
        "radvd_validator",
    ]
    for name in live:
        setattr(validator, name, MagicMock())

    validator.validate_offline([_subnet_with_conflict()])

    for name in live:
        getattr(validator, name).validate.assert_not_called()


def test_opnsense_provider_offline_does_not_check_endpoint_support(tmp_path: Path) -> None:
    provider = OPNsenseProvider(tmp_path, tmp_path)
    with patch.object(OPNsenseValidator, "validate_endpoint_support") as endpoint:
        provider.validate_offline(
            [_subnet_with_conflict()],
            [_subnet_with_conflict()],
            EnvironmentConfig(name="t"),
            ValidationReport(),
        )
    endpoint.assert_not_called()


def test_opnsense_references_still_run_live_validators() -> None:
    validator = OPNsenseValidator(EnvironmentConfig(name="t"), ValidationReport())
    validator.api_validator.get_credentials = MagicMock(  # type: ignore[method-assign]
        return_value={
            "api_url": "https://opnsense.example.com",
            "api_key": "key",
            "api_secret": "secret",
        }
    )
    validator.api_validator.fetch_json = MagicMock(return_value=None)  # type: ignore[method-assign]
    validator.vlan_validator = MagicMock()
    validator.kea_ha_validator = MagicMock()

    validator.validate_references([_subnet_with_conflict()])

    validator.vlan_validator.validate.assert_called_once()
    validator.kea_ha_validator.validate.assert_called_once()


def test_host_offline_never_probes_but_references_do() -> None:
    probe = MagicMock(return_value=0)
    resource = _res("vps-01", "host", "host", address="vps-01.example.com")

    HostValidator(
        EnvironmentConfig(name="t"), ValidationReport(), ssh_probe=probe
    ).validate_offline([resource])
    probe.assert_not_called()

    HostValidator(
        EnvironmentConfig(name="t"), ValidationReport(), ssh_probe=probe
    ).validate_references([resource])
    probe.assert_called_once()


def test_proxmox_offline_builds_no_client_and_flags_bad_secret_reference() -> None:
    report = ValidationReport()
    env = EnvironmentConfig(name="t", secrets={"other": {"x": "y"}})
    vm = _res("vm1", "proxmox", "vm", terraform_secrets=["nope.missing"])
    with patch(
        "infrafoundry.providers.proxmox.validator.ProxmoxClient.from_provider_settings"
    ) as client:
        ProxmoxValidator(env, report).validate_offline([vm])
    client.assert_not_called()
    assert any(
        "nope.missing" in r.message and r.level == ValidationLevel.ERROR
        for r in report.results
        if not r.passed
    )


def test_oci_offline_builds_no_client_and_flags_bad_secret_reference() -> None:
    report = ValidationReport()
    env = EnvironmentConfig(name="t", secrets={"other": {"x": "y"}})
    instance = _res("i1", "oci", "instance", terraform_secrets=["nope.missing"])
    with patch.object(OCIValidator, "_create_client") as create:
        OCIValidator(env, report).validate_offline([instance])
    create.assert_not_called()
    assert any("nope.missing" in r.message for r in report.results if not r.passed)


def test_kubernetes_plan_pass_errors_on_missing_configmap_without_touching_cluster(
    tmp_path: Path,
) -> None:
    provider = KubernetesProvider(tmp_path, tmp_path)
    deployment = _res("web", "kubernetes", "deployments", env_from=[{"configmap": "missing"}])
    h = _Harness({"kubernetes": provider}, {"kubernetes": [deployment]})

    with (
        patch.object(KubeconfigValidator, "validate") as probe,
        pytest.raises(ConfigValidationError),
    ):
        h.plan()

    probe.assert_not_called()
    assert "missing" in h.text
