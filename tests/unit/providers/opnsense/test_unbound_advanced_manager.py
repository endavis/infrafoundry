"""Unit tests for ``UnboundAdvancedManager`` (#1254)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.unbound_advanced import UnboundAdvancedManager
from infrafoundry.providers.opnsense.services.unbound_advanced import UnboundAdvancedService

SERVICE_PATH = "infrafoundry.providers.opnsense.components.unbound_advanced.UnboundAdvancedService"

LIVE = {
    "unbound": {
        "advanced": {
            "hideidentity": "0",
            "privatedomain": {"a.example": {"selected": 1}},
            "insecuredomain": {"": {"selected": 1}},
            "privateaddress": {"10.0.0.0/8": {"selected": 1}},
        }
    }
}


def _resource(config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(
        name="unbound.advanced", type="unbound.advanced", provider="opnsense", config=config
    )


def _service() -> UnboundAdvancedService:
    service = UnboundAdvancedService(MagicMock())
    client = MagicMock()
    client.request.return_value = LIVE
    service.client = client
    return service


def _run(method: str, tmp_path: Path, resources: list[ResourceConfig]) -> tuple[Any, MagicMock]:
    service = _service()
    set_mock = MagicMock(return_value={"result": "saved"})
    service.set_settings = set_mock  # type: ignore[method-assign]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        result = getattr(UnboundAdvancedManager(tmp_path), method)("env", resources)
    return result, set_mock


def test_plan_in_sync_is_empty(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, [_resource({"private_domains": ["a.example"]})])
    assert diff.is_empty
    assert diff.updates == []


def test_plan_drift_is_one_update_only(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, [_resource({"private_domains": ["b.example"]})])
    assert len(diff.updates) == 1
    assert not diff.adds
    assert not diff.deletes


def test_apply_on_drift_writes_once(tmp_path: Path) -> None:
    result, set_mock = _run("apply", tmp_path, [_resource({"insecure_domains": ["x.example"]})])
    set_mock.assert_called_once()
    payload = set_mock.call_args.args[0]
    flat = payload["unbound"]["advanced"]
    assert flat["insecuredomain"] == "x.example"
    assert flat["hideidentity"] == "0"
    assert flat["privatedomain"] == "a.example"
    assert result["resources_updated"] == 1
    assert [o.action for o in result["resource_outcomes"]] == ["update"]


def test_apply_in_sync_makes_no_write(tmp_path: Path) -> None:
    result, set_mock = _run("apply", tmp_path, [_resource({"private_domains": ["a.example"]})])
    set_mock.assert_not_called()
    assert result["resources_updated"] == 0
    assert result["resource_outcomes"] == []


def test_apply_never_reconfigures(tmp_path: Path) -> None:
    service = _service()
    reconfigure = MagicMock()
    service.reconfigure = reconfigure  # type: ignore[attr-defined]
    service.set_settings = MagicMock()  # type: ignore[method-assign]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        UnboundAdvancedManager(tmp_path).apply(
            "env", [_resource({"insecure_domains": ["x.example"]})]
        )
    reconfigure.assert_not_called()


def test_apply_logs_field_names_not_values(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    _run("apply", tmp_path, [_resource({"insecure_domains": ["secret-zone.example"]})])
    assert "insecure_domains" in caplog.text
    assert "secret-zone.example" not in caplog.text


def test_finalization_hook() -> None:
    assert UnboundAdvancedManager.FINALIZATION_HOOK == "unbound_reconfigure"


def test_destroy_is_a_noop(tmp_path: Path) -> None:
    with patch(SERVICE_PATH) as cls:
        result = UnboundAdvancedManager(tmp_path).destroy(
            "env", [_resource({"private_domains": ["a.example"]})]
        )
    cls.from_environment.assert_not_called()
    assert result["resources_destroyed"] == 0


def test_get_resource_ids(tmp_path: Path) -> None:
    ids = UnboundAdvancedManager(tmp_path).get_resource_ids("env", [_resource({})])
    assert ids == {"unbound.advanced": "global"}


def test_two_resources_rejected(tmp_path: Path) -> None:
    with pytest.raises(InvalidConfigurationError):
        _run("plan", tmp_path, [_resource({}), _resource({})])
