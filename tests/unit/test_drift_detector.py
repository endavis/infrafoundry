"""Unit tests for DriftDetector."""

from types import SimpleNamespace
from typing import Any, ClassVar, cast
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.base_manager import BaseManager
from infrafoundry.core.drift_detector import DriftDetector
from infrafoundry.core.events import EventManager, EventType
from infrafoundry.core.runners.terraform_runner import TerraformRunner


@pytest.fixture
def mock_config_manager() -> MagicMock:
    """Create a mock config manager."""
    return MagicMock()


@pytest.fixture
def mock_runner_registry() -> MagicMock:
    """Create a mock runner registry."""
    return MagicMock()


@pytest.fixture
def mock_event_manager() -> MagicMock:
    """Create a mock event manager."""
    return MagicMock(spec=EventManager)


@pytest.fixture
def mock_providers() -> dict[str, Any]:
    """Create a mock providers dict."""
    return {}


@pytest.fixture
def drift_detector(
    mock_config_manager: MagicMock,
    mock_runner_registry: MagicMock,
    mock_event_manager: MagicMock,
    mock_providers: dict[str, Any],
) -> DriftDetector:
    """Create a DriftDetector instance for testing."""
    return DriftDetector(
        config_manager=mock_config_manager,
        runner_registry=mock_runner_registry,
        event_manager=mock_event_manager,
        providers=mock_providers,
    )


@pytest.mark.unit
class TestDriftDetector:
    """Tests for DriftDetector."""

    def test_inherits_from_base_manager(self, drift_detector: DriftDetector) -> None:
        """Test that DriftDetector inherits from BaseManager."""
        assert isinstance(drift_detector, BaseManager)
        # Should have BaseManager methods
        assert hasattr(drift_detector, "_log_info")
        assert hasattr(drift_detector, "_log_warning")
        assert hasattr(drift_detector, "_log_error")
        assert hasattr(drift_detector, "_log_debug")
        assert hasattr(drift_detector, "cleanup")

    def test_cleanup_method(self, drift_detector: DriftDetector) -> None:
        """Test that cleanup method works."""
        # cleanup() should not raise any exceptions
        drift_detector.cleanup()

    def test_context_manager(
        self,
        mock_config_manager: MagicMock,
        mock_runner_registry: MagicMock,
        mock_event_manager: MagicMock,
        mock_providers: dict[str, Any],
    ) -> None:
        """Test that DriftDetector can be used as context manager."""
        with DriftDetector(
            config_manager=mock_config_manager,
            runner_registry=mock_runner_registry,
            event_manager=mock_event_manager,
            providers=mock_providers,
        ) as detector:
            assert isinstance(detector, DriftDetector)
        # Exiting context should call cleanup without error

    def test_init_stores_dependencies(
        self,
        mock_config_manager: MagicMock,
        mock_runner_registry: MagicMock,
        mock_event_manager: MagicMock,
        mock_providers: dict[str, Any],
    ) -> None:
        """Test that __init__ properly stores dependencies."""
        detector = DriftDetector(
            config_manager=mock_config_manager,
            runner_registry=mock_runner_registry,
            event_manager=mock_event_manager,
            providers=mock_providers,
        )

        assert detector.config_manager is mock_config_manager
        assert detector.runner_registry is mock_runner_registry
        assert detector.event_manager is mock_event_manager
        assert detector.providers is mock_providers

    def test_detect_emits_started_event(
        self,
        mock_config_manager: MagicMock,
        mock_runner_registry: MagicMock,
        mock_event_manager: MagicMock,
        mock_providers: dict[str, Any],
    ) -> None:
        """Test that detect emits DRIFT_CHECK_STARTED event."""
        # Set up mocks
        mock_runner = MagicMock()
        mock_runner_registry.create_runner.return_value = mock_runner
        mock_config_manager.get_all_resources_all_providers.return_value = []

        detector = DriftDetector(
            config_manager=mock_config_manager,
            runner_registry=mock_runner_registry,
            event_manager=mock_event_manager,
            providers=mock_providers,
        )

        detector.detect("test-env")

        # Verify DRIFT_CHECK_STARTED was emitted
        calls = mock_event_manager.emit_event.call_args_list
        assert len(calls) >= 1
        first_call = calls[0]
        assert first_call[0][1] == "test-env"  # environment name

    def test_detect_returns_empty_dict_when_no_providers(
        self,
        mock_config_manager: MagicMock,
        mock_runner_registry: MagicMock,
        mock_event_manager: MagicMock,
        mock_providers: dict[str, Any],
    ) -> None:
        """Test that detect returns empty dict when no providers have resources."""
        # Set up mocks
        mock_runner = MagicMock()
        mock_runner_registry.create_runner.return_value = mock_runner
        mock_config_manager.get_all_resources_all_providers.return_value = []

        detector = DriftDetector(
            config_manager=mock_config_manager,
            runner_registry=mock_runner_registry,
            event_manager=mock_event_manager,
            providers=mock_providers,
        )

        results = detector.detect("test-env")

        assert results == {}

    def test_detect_uses_configured_iac_tool(
        self,
        mock_config_manager: MagicMock,
        mock_runner_registry: MagicMock,
        mock_event_manager: MagicMock,
        mock_providers: dict[str, Any],
    ) -> None:
        """Test that detect resolves the IaC tool from environment config."""
        from infrafoundry.core.config.models import EnvironmentConfig, IaCTool

        # Configure environment with opentofu
        env_config = EnvironmentConfig(name="test-env", iac_tool=IaCTool.OPENTOFU)
        mock_config_manager.load_environment.return_value = env_config

        mock_runner = MagicMock()
        mock_runner_registry.create_runner.return_value = mock_runner
        mock_config_manager.get_all_resources_all_providers.return_value = []

        detector = DriftDetector(
            config_manager=mock_config_manager,
            runner_registry=mock_runner_registry,
            event_manager=mock_event_manager,
            providers=mock_providers,
        )

        detector.detect("test-env")

        # Should create runner with "opentofu", not "terraform"
        mock_runner_registry.create_runner.assert_called_once_with("opentofu")

    def test_detect_defaults_to_terraform_when_no_env_config(
        self,
        mock_runner_registry: MagicMock,
        mock_event_manager: MagicMock,
        mock_providers: dict[str, Any],
    ) -> None:
        """Test that detect falls back to terraform when env config is missing."""
        mock_config_manager = MagicMock()
        mock_config_manager.load_environment.side_effect = FileNotFoundError("no config")
        mock_config_manager.get_all_resources_all_providers.return_value = []

        mock_runner = MagicMock()
        mock_runner_registry.create_runner.return_value = mock_runner

        detector = DriftDetector(
            config_manager=mock_config_manager,
            runner_registry=mock_runner_registry,
            event_manager=mock_event_manager,
            providers=mock_providers,
        )

        detector.detect("test-env")

        # Should fall back to "terraform"
        mock_runner_registry.create_runner.assert_called_once_with("terraform")


@pytest.mark.unit
class TestDriftDetectorUnparsedPlan:
    """An unparsable plan is reported as unknown drift, not as no drift (#1077)."""

    def _detect(
        self, plan_output: str, mock_runner_registry: MagicMock, mock_event_manager: MagicMock
    ) -> tuple[dict[str, Any], list[str], list[str]]:
        """Run ``detect`` on one provider whose plan prints ``plan_output``.

        Returns:
            The results, the warning messages and the info messages logged
        """
        config_manager = MagicMock()
        config_manager.load_environment.side_effect = FileNotFoundError("no config")
        config_manager.get_all_resources_all_providers.return_value = [
            SimpleNamespace(provider="proxmox")
        ]
        runner = TerraformRunner()
        mock_runner_registry.create_runner.return_value = runner
        detector = DriftDetector(
            config_manager=config_manager,
            runner_registry=mock_runner_registry,
            event_manager=mock_event_manager,
            providers={"proxmox": MagicMock()},
        )

        with (
            patch.object(runner, "plan", return_value={"success": True, "output": plan_output}),
            patch.object(detector, "_log_warning") as warn,
            patch.object(detector, "_log_info") as info,
        ):
            results = detector.detect("dev")

        warnings = [c.args[0] for c in warn.call_args_list]
        infos = [c.args[0] for c in info.call_args_list]
        return results, warnings, infos

    def test_unparsable_plan_warns_instead_of_reporting_no_drift(
        self, mock_runner_registry: MagicMock, mock_event_manager: MagicMock
    ) -> None:
        results, warnings, infos = self._detect(
            "Error: provider crashed", mock_runner_registry, mock_event_manager
        )

        assert results["proxmox"]["parsed"] is False
        assert results["proxmox"]["has_changes"] is False
        assert warnings == ["Could not determine drift for proxmox: Unable to parse plan output"]
        assert "No drift detected for proxmox" not in infos
        emitted = [c.args[0] for c in mock_event_manager.emit_event.call_args_list]
        assert EventType.DRIFT_DETECTED not in emitted

    def test_no_changes_plan_reports_no_drift(
        self, mock_runner_registry: MagicMock, mock_event_manager: MagicMock
    ) -> None:
        results, warnings, infos = self._detect(
            "No changes. Your infrastructure matches the configuration.",
            mock_runner_registry,
            mock_event_manager,
        )

        assert "parsed" not in results["proxmox"]
        assert warnings == []
        assert "No drift detected for proxmox" in infos


class _StubTerraformRunner(TerraformRunner):
    """Terraform runner whose plan reports no drift and records its calls."""

    calls: ClassVar[list[str]] = []

    def plan(self, provider: Any, **kwargs: Any) -> Any:
        type(self).calls.append(provider.name)
        return {"success": True, "has_changes": False}

    def parse_plan_for_drift(self, plan_result: Any) -> Any:
        return {"has_changes": False, "summary": "none"}


def _direct_detector(provider: Any, name: str) -> tuple[DriftDetector, MagicMock]:
    from infrafoundry.core.runners import (
        MikroTikRestRunner,
        OPNsenseDirectRunner,
        RunnerRegistry,
    )

    registry = RunnerRegistry()
    registry.register(OPNsenseDirectRunner)
    registry.register(MikroTikRestRunner)
    registry.register(_StubTerraformRunner, "terraform")
    config_manager = MagicMock()
    config_manager.load_environment.side_effect = FileNotFoundError
    config_manager.get_all_resources_all_providers.return_value = [SimpleNamespace(provider=name)]
    events = MagicMock(spec=EventManager)
    _StubTerraformRunner.calls = []
    return DriftDetector(config_manager, registry, events, {name: provider}), events


@pytest.mark.unit
class TestDirectRunnerDrift:
    """A provider with a drift-detectable direct runner skips Terraform."""

    def _mikrotik(self, tmp_path: Any, changes: tuple[str, ...]) -> Any:
        from infrafoundry.core.runners.mikrotik_rest_runner import MikroTikRestRunner
        from infrafoundry.providers.mikrotik import MikroTikProvider
        from infrafoundry.providers.mikrotik.components.diff import Change, TypeDiff
        from infrafoundry.providers.mikrotik.components.manager import MikroTikPlan

        diff = TypeDiff("interface.bridge.port")
        diff.changes = [
            Change(k, "interface.bridge.port", ("ether2",), "p2", "*1", {}, {"pvid": 11}, ("pvid",))
            for k in changes
        ]
        provider = MikroTikProvider(tmp_path, tmp_path / "generated")
        patches = (
            patch.object(provider, "rest_plan", return_value=MikroTikPlan({diff.type_name: diff})),
            patch.object(MikroTikRestRunner, "_load_resources", return_value=[]),
        )
        mocks = [p.start() for p in patches]
        return provider, patches, mocks[0]

    def test_out_of_band_pvid_change_is_drift(self, tmp_path: Any) -> None:
        provider, patches, rest_plan = self._mikrotik(tmp_path, ("update",))
        detector, events = _direct_detector(provider, "mikrotik")
        try:
            results = detector.detect("lab")
        finally:
            for p in patches:
                p.stop()

        assert results["mikrotik"]["has_changes"] is True
        assert results["mikrotik"]["to_change"] == 1
        assert provider._current_environment == "lab"
        assert rest_plan.call_args.kwargs["add_only"] is True
        assert _StubTerraformRunner.calls == []
        emitted = [c.args[0] for c in events.emit_event.call_args_list]
        assert EventType.DRIFT_DETECTED in emitted

    def test_clean_device_reports_no_drift(self, tmp_path: Any) -> None:
        provider, patches, _ = self._mikrotik(tmp_path, ())
        detector, events = _direct_detector(provider, "mikrotik")
        try:
            results = detector.detect("lab")
        finally:
            for p in patches:
                p.stop()

        assert results["mikrotik"]["has_changes"] is False
        emitted = [c.args[0] for c in events.emit_event.call_args_list]
        assert EventType.DRIFT_DETECTED not in emitted

    def test_managed_rows_reach_plan(self, tmp_path: Any) -> None:
        """Drift plans with the env's managed rows, as ``infra plan`` does (#1495)."""
        provider, patches, rest_plan = self._mikrotik(tmp_path, ("update",))
        detector, _ = _direct_detector(provider, "mikrotik")
        row = SimpleNamespace(
            resource_type="interface.bridge.port",
            name="p2",
            config={"name": "p2", "type": "interface.bridge.port", "provider": "mikrotik"},
        )
        state_manager = MagicMock()
        state_manager.get_managed_resources.return_value = [row]
        detector.state_manager = state_manager
        try:
            detector.detect("lab")
        finally:
            for p in patches:
                p.stop()

        state_manager.get_managed_resources.assert_called_once_with("lab", "mikrotik")
        managed = rest_plan.call_args.kwargs["managed_resources"]
        assert [r.name for r in managed["interface.bridge.port"]] == ["p2"]

    def test_no_state_manager_passes_no_managed_set(self, tmp_path: Any) -> None:
        """Without a state manager the plan call is unchanged."""
        provider, patches, rest_plan = self._mikrotik(tmp_path, ("update",))
        detector, _ = _direct_detector(provider, "mikrotik")
        try:
            detector.detect("lab")
        finally:
            for p in patches:
                p.stop()

        assert not rest_plan.call_args.kwargs.get("managed_resources")

    def test_provider_without_direct_hook_uses_terraform(self) -> None:
        provider = SimpleNamespace(name="proxmox", set_environment=lambda env: None)
        detector, _ = _direct_detector(provider, "proxmox")

        detector.detect("lab")

        assert _StubTerraformRunner.calls == ["proxmox"]

    def test_opnsense_keeps_terraform_path(self) -> None:
        provider = SimpleNamespace(
            name="opnsense",
            generate_opnsense_direct=lambda r: None,
            set_environment=lambda env: None,
        )
        detector, _ = _direct_detector(provider, "opnsense")

        detector.detect("lab")

        assert _StubTerraformRunner.calls == ["opnsense"]


@pytest.mark.unit
class TestOntapDirectRunnerDrift:
    """The ONTAP provider is drift-detected add-only through its direct runner (ADR-0042)."""

    def _detector(self, tmp_path: Any, kinds: tuple[str, ...]) -> tuple[Any, Any, Any, Any]:
        from infrafoundry.core.runners import OntapRestRunner, RunnerRegistry
        from infrafoundry.providers.ontap import OntapProvider
        from infrafoundry.providers.ontap.components.interface import Change, InterfaceDiff
        from infrafoundry.providers.ontap.components.manager import OntapPlan

        plan = OntapPlan()
        plan.diff = InterfaceDiff(
            changes=[Change(k, ("svm1", "lif1"), "lif1", "u1", {}, {}, ("address",)) for k in kinds]
        )
        provider = OntapProvider(tmp_path, tmp_path / "generated")
        registry = RunnerRegistry()
        registry.register(OntapRestRunner)
        registry.register(_StubTerraformRunner, "terraform")
        config_manager = MagicMock()
        config_manager.load_environment.side_effect = FileNotFoundError
        config_manager.get_all_resources_all_providers.return_value = [
            SimpleNamespace(provider="ontap")
        ]
        events = MagicMock(spec=EventManager)
        _StubTerraformRunner.calls = []
        detector = DriftDetector(config_manager, registry, events, {"ontap": provider})
        return detector, events, provider, (plan, OntapRestRunner)

    def test_out_of_band_change_is_drift_and_terraform_is_skipped(self, tmp_path: Any) -> None:
        detector, events, provider, (plan, runner_cls) = self._detector(tmp_path, ("update",))
        with (
            patch.object(provider, "rest_plan", return_value=plan) as rest_plan,
            patch.object(runner_cls, "_load_resources", return_value=[]),
        ):
            results = detector.detect("lab")

        assert results["ontap"]["has_changes"] is True
        assert results["ontap"]["to_change"] == 1
        assert provider._current_environment == "lab"
        assert rest_plan.call_args.kwargs["add_only"] is True
        assert _StubTerraformRunner.calls == []
        emitted = [c.args[0] for c in events.emit_event.call_args_list]
        assert EventType.DRIFT_DETECTED in emitted

    def test_converged_cluster_reports_no_drift(self, tmp_path: Any) -> None:
        detector, events, provider, (plan, runner_cls) = self._detector(tmp_path, ())
        with (
            patch.object(provider, "rest_plan", return_value=plan),
            patch.object(runner_cls, "_load_resources", return_value=[]),
        ):
            results = detector.detect("lab")

        assert results["ontap"]["has_changes"] is False
        emitted = [c.args[0] for c in events.emit_event.call_args_list]
        assert EventType.DRIFT_DETECTED not in emitted


class _EnvProvider:
    """Provider stand-in that scopes ``terraform_dir`` like ``ProviderBase``."""

    def __init__(self, name: str, base: Any, generate: bool = True) -> None:
        self.name = name
        self.base = base
        self.generate = generate
        self.terraform_dir = base / "terraform" / name
        self.env_calls: list[str] = []

    def set_environment(self, env_name: str) -> None:
        self.env_calls.append(env_name)
        self.terraform_dir = self.base / env_name / "terraform" / self.name
        if self.generate:
            self.terraform_dir.mkdir(parents=True, exist_ok=True)


class _DirRecordingRunner(_StubTerraformRunner):
    """Terraform stub that records the directory each plan sees and can fail."""

    dirs: ClassVar[list[Any]] = []
    fail_for: ClassVar[set[str]] = set()

    def plan(self, provider: Any, **kwargs: Any) -> Any:
        type(self).dirs.append(provider.terraform_dir)
        if provider.name in type(self).fail_for:
            raise RuntimeError(f"plan blew up for {provider.name}")
        return super().plan(provider, **kwargs)


def _multi_detector(providers: dict[str, Any]) -> tuple[DriftDetector, MagicMock]:
    from infrafoundry.core.runners import RunnerRegistry

    registry = RunnerRegistry()
    registry.register(_DirRecordingRunner, "terraform")
    config_manager = MagicMock()
    config_manager.load_environment.side_effect = FileNotFoundError
    config_manager.get_all_resources_all_providers.return_value = [
        SimpleNamespace(provider=n) for n in providers
    ]
    events = MagicMock(spec=EventManager)
    _StubTerraformRunner.calls = []
    _DirRecordingRunner.dirs = []
    _DirRecordingRunner.fail_for = set()
    return DriftDetector(config_manager, registry, events, providers), events


@pytest.mark.unit
class TestDriftDetectorPerProvider:
    """The Terraform path scopes the provider to the env; a failure stays per provider (#1488)."""

    def test_set_environment_runs_before_plan(self, tmp_path: Any) -> None:
        provider = _EnvProvider("proxmox", tmp_path)
        detector, _ = _multi_detector({"proxmox": provider})

        results = detector.detect("lab")

        assert provider.env_calls == ["lab"]
        assert _DirRecordingRunner.dirs == [tmp_path / "lab" / "terraform" / "proxmox"]
        assert results["proxmox"]["has_changes"] is False

    def test_failing_provider_does_not_stop_later_providers(self, tmp_path: Any) -> None:
        bad = _EnvProvider("proxmox", tmp_path)
        good = _EnvProvider("other", tmp_path)
        detector, events = _multi_detector({"proxmox": bad, "other": good})
        _DirRecordingRunner.fail_for = {"proxmox"}

        results = detector.detect("lab")

        assert results["proxmox"]["has_changes"] is False
        assert results["proxmox"]["parsed"] is False
        assert "plan blew up for proxmox" in results["proxmox"]["summary"]
        assert "other" in results
        assert _StubTerraformRunner.calls == ["other"]
        emitted = [c.args[0] for c in events.emit_event.call_args_list]
        assert emitted[-1] == EventType.DRIFT_CHECK_COMPLETED

    def test_failure_then_direct_runner_provider_still_checked(self, tmp_path: Any) -> None:
        from infrafoundry.core.runners import MikroTikRestRunner, RunnerRegistry
        from infrafoundry.core.runners.mikrotik_rest_runner import MikroTikRestRunner as Rest
        from infrafoundry.providers.mikrotik import MikroTikProvider
        from infrafoundry.providers.mikrotik.components.diff import TypeDiff
        from infrafoundry.providers.mikrotik.components.manager import MikroTikPlan

        bad = _EnvProvider("proxmox", tmp_path)
        mikrotik = MikroTikProvider(tmp_path, tmp_path / "generated")
        registry = RunnerRegistry()
        registry.register(MikroTikRestRunner)
        registry.register(_DirRecordingRunner, "terraform")
        config_manager = MagicMock()
        config_manager.load_environment.side_effect = FileNotFoundError
        config_manager.get_all_resources_all_providers.return_value = [
            SimpleNamespace(provider="proxmox"),
            SimpleNamespace(provider="mikrotik"),
        ]
        detector = DriftDetector(
            config_manager,
            registry,
            MagicMock(spec=EventManager),
            cast(Any, {"proxmox": bad, "mikrotik": mikrotik}),
        )
        _DirRecordingRunner.fail_for = {"proxmox"}
        with (
            patch.object(mikrotik, "rest_plan", return_value=MikroTikPlan({"x": TypeDiff("x")})),
            patch.object(Rest, "_load_resources", return_value=[]),
        ):
            results = detector.detect("lab")

        assert results["proxmox"]["parsed"] is False
        assert results["mikrotik"]["has_changes"] is False
        assert "parsed" not in results["mikrotik"]


@pytest.mark.unit
class TestOpenWrtDrift:
    """The openwrt provider's Ansible runner is the direct drift runner."""

    @staticmethod
    def _detector(provider: Any) -> tuple[DriftDetector, MagicMock]:
        from infrafoundry.core.runners import OpenWrtAnsibleRunner, RunnerRegistry

        registry = RunnerRegistry()
        registry.register(OpenWrtAnsibleRunner)
        registry.register(_StubTerraformRunner, "terraform")
        config_manager = MagicMock()
        config_manager.load_environment.side_effect = FileNotFoundError
        config_manager.get_all_resources_all_providers.return_value = [
            SimpleNamespace(provider="openwrt")
        ]
        events = MagicMock(spec=EventManager)
        _StubTerraformRunner.calls = []
        return DriftDetector(config_manager, registry, events, {"openwrt": provider}), events

    @pytest.mark.parametrize(("changed", "expected"), [(True, 1), (False, 0)])
    def test_out_of_band_change_is_drift_and_terraform_is_skipped(
        self, tmp_path: Any, changed: bool, expected: int
    ) -> None:
        import json
        import subprocess

        from infrafoundry.core.runners.openwrt_ansible_runner import OpenWrtAnsibleRunner
        from infrafoundry.providers.openwrt import OpenWrtProvider
        from infrafoundry.providers.openwrt.settings import OpenWrtSettings

        resource = SimpleNamespace(
            name="printer",
            type="dhcp.host",
            provider="openwrt",
            config={"name": "printer", "mac": "02:00:00:00:00:0a", "ip": "192.0.2.50"},
        )
        output = json.dumps(
            {
                "plays": [
                    {
                        "tasks": [
                            {
                                "task": {"name": "infrafoundry|dhcp.host|printer"},
                                "hosts": {"openwrt": {"changed": changed, "diff": []}},
                            }
                        ]
                    }
                ]
            }
        )
        provider = OpenWrtProvider(tmp_path, tmp_path / "generated")
        detector, _events = self._detector(provider)
        completed = subprocess.CompletedProcess([], 0, output, "")
        with (
            patch.object(OpenWrtAnsibleRunner, "_load_resources", return_value=[resource]),
            patch(
                "infrafoundry.core.runners.openwrt_ansible_runner._run", return_value=completed
            ) as run,
            patch(
                "infrafoundry.providers.openwrt.load_settings",
                return_value=OpenWrtSettings(address="192.0.2.2"),
            ),
            patch(
                "infrafoundry.core.runners.openwrt_ansible_runner.shutil.which",
                return_value="/usr/bin/ansible-playbook",
            ),
        ):
            results = detector.detect("lab")

        assert results["openwrt"]["has_changes"] is bool(expected)
        assert results["openwrt"]["to_add"] == expected
        assert "--check" in run.call_args.args[0]
        assert _StubTerraformRunner.calls == []
