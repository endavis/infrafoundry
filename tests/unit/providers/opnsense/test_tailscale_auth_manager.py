"""Unit tests for ``TailscaleAuthManager`` (#787).

Coverage:
    - plan emits an empty diff when live matches desired.
    - plan emits one update entry when a field changes.
    - apply skips set_authentication when the singleton is in sync.
    - apply calls set_authentication with the desired wire payload on drift.
    - pre_auth_key write-only behavior: live always returns empty so
      any YAML value triggers an update (intentional re-apply).
    - destroy is a no-op (returns ``resources_destroyed=0``).
    - get_resource_ids returns ``{"auth": "global"}``.
    - plan raises ``InvalidConfigurationError`` if not exactly one resource.
    - FINALIZATION_HOOK class variable is ``"tailscale_reconfigure"``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.tailscale_auth import TailscaleAuthManager

SERVICE_PATH = "infrafoundry.providers.opnsense.components.tailscale_auth.TailscaleService"


def _resource(
    *,
    login_server: str = "",
    pre_auth_key: str = "",
) -> ResourceConfig:
    return ResourceConfig(
        name="auth",
        type="tailscale.auth",
        provider="opnsense",
        config={
            "login_server": login_server,
            "pre_auth_key": pre_auth_key,
        },
    )


def _make_live_fields(
    *,
    login_server: str = "",
    pre_auth_key: str = "",
) -> dict[str, Any]:
    return {
        "login_server": login_server,
        "pre_auth_key": pre_auth_key,
    }


def _make_service_mock(*, live_fields: dict[str, Any] | None = None) -> MagicMock:
    service = MagicMock()
    fields = live_fields if live_fields is not None else _make_live_fields()
    service.get_authentication.return_value = {"authentication": {}}
    service.extract_auth_fields.return_value = fields
    service.build_desired_auth_fields.side_effect = lambda resource: {
        "login_server": str(resource.config.get("login_server", "") or "").strip(),
        "pre_auth_key": str(resource.config.get("pre_auth_key", "") or "").strip(),
    }
    service.build_auth_wire_payload.side_effect = lambda fields: {
        "authentication": {
            "loginServer": fields.get("login_server", ""),
            "preAuthKey": fields.get("pre_auth_key", ""),
        }
    }
    service.set_authentication.return_value = {"result": "saved"}
    return service


class TestFinalizationHook:
    def test_hook_declared(self) -> None:
        assert TailscaleAuthManager.FINALIZATION_HOOK == "tailscale_reconfigure"


class TestPlan:
    def test_plan_no_change(self, tmp_path: Path) -> None:
        manager = TailscaleAuthManager(tmp_path)
        live = _make_live_fields(login_server="", pre_auth_key="")
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource()])
        assert diff.is_empty
        assert diff.updates == []

    def test_plan_update_on_login_server_change(self, tmp_path: Path) -> None:
        manager = TailscaleAuthManager(tmp_path)
        live = _make_live_fields(login_server="")
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan(
                "test-env", [_resource(login_server="https://controlplane.tailscale.com")]
            )
        assert not diff.is_empty
        assert len(diff.updates) == 1

    def test_plan_update_on_pre_auth_key(self, tmp_path: Path) -> None:
        """pre_auth_key is write-only: live is always empty, YAML sets trigger update."""
        manager = TailscaleAuthManager(tmp_path)
        # Live API always returns empty string for pre_auth_key.
        live = _make_live_fields(login_server="", pre_auth_key="")
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource(pre_auth_key="tskey-auth-abc123")])
        assert not diff.is_empty
        assert len(diff.updates) == 1

    def test_plan_raises_on_multiple_resources(self, tmp_path: Path) -> None:
        manager = TailscaleAuthManager(tmp_path)
        with pytest.raises(InvalidConfigurationError):
            manager.plan("test-env", [_resource(), _resource()])

    def test_plan_raises_on_no_resources(self, tmp_path: Path) -> None:
        manager = TailscaleAuthManager(tmp_path)
        with pytest.raises(InvalidConfigurationError):
            manager.plan("test-env", [])


class TestApply:
    def test_apply_no_change_skips_set_authentication(self, tmp_path: Path) -> None:
        manager = TailscaleAuthManager(tmp_path)
        live = _make_live_fields()
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource()])
        service.set_authentication.assert_not_called()
        assert result["resources_updated"] == 0
        assert result["resource_outcomes"] == []

    def test_apply_drift_calls_set_authentication(self, tmp_path: Path) -> None:
        manager = TailscaleAuthManager(tmp_path)
        live = _make_live_fields(login_server="")
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply(
                "test-env",
                [_resource(login_server="https://controlplane.tailscale.com")],
            )
        service.set_authentication.assert_called_once()
        wire = service.set_authentication.call_args.args[0]
        assert wire["authentication"]["loginServer"] == "https://controlplane.tailscale.com"
        assert result["resources_updated"] == 1
        outcome = result["resource_outcomes"][0]
        assert outcome.action == "update"
        assert outcome.resource_name == "auth"

    def test_apply_does_not_call_apply_settings_patch(self, tmp_path: Path) -> None:
        """Auth apply must call set_authentication, not apply_settings_patch."""
        manager = TailscaleAuthManager(tmp_path)
        live = _make_live_fields(login_server="")
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            manager.apply(
                "test-env",
                [_resource(login_server="https://controlplane.tailscale.com")],
            )
        service.apply_settings_patch.assert_not_called()

    def test_apply_raises_on_multiple_resources(self, tmp_path: Path) -> None:
        manager = TailscaleAuthManager(tmp_path)
        with pytest.raises(InvalidConfigurationError):
            manager.apply("test-env", [_resource(), _resource()])


class TestDestroy:
    def test_destroy_noop(self, tmp_path: Path) -> None:
        manager = TailscaleAuthManager(tmp_path)
        result = manager.destroy("test-env", [_resource()])
        assert result["resources_destroyed"] == 0
        assert result["resource_outcomes"] == []


class TestGetResourceIds:
    def test_returns_global(self, tmp_path: Path) -> None:
        manager = TailscaleAuthManager(tmp_path)
        result = manager.get_resource_ids("test-env", [_resource()])
        assert result == {"auth": "global"}
