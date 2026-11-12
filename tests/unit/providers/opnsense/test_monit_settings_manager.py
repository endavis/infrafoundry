"""Unit tests for ``MonitSettingsManager`` (#791)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.providers.opnsense.components.monit_settings import MonitSettingsManager
from infrafoundry.providers.opnsense.services.monit_settings import REDACTED, MonitSettingsService
from tests.helpers.opnsense_monit import SECRET, FakeMonitBox, single

SECRETS_CM = "infrafoundry.providers.opnsense.components._secrets.ConfigManager"
URI = "secret://env_secrets/opnsense/monit/settings/httpd_password"


def _cm() -> MagicMock:
    env = MagicMock()
    env.secrets = {"opnsense": {"monit": {"settings": {"httpd_password": SECRET}}}}
    cls = MagicMock()
    cls.return_value.load_environment.return_value = env
    return cls


@pytest.fixture
def box() -> FakeMonitBox:
    return FakeMonitBox()


@pytest.fixture
def manager(box: FakeMonitBox, tmp_path: Path) -> Iterator[MonitSettingsManager]:
    client = MagicMock()
    client.request.side_effect = box.request
    with (
        patch.object(
            MonitSettingsService, "from_environment", return_value=MonitSettingsService(client)
        ),
        patch(SECRETS_CM, _cm()),
    ):
        yield MonitSettingsManager(tmp_path)


def test_class_attributes() -> None:
    assert MonitSettingsManager.FINALIZATION_HOOK == "monit_reconfigure"


def test_in_sync_box_plans_empty_and_writes_nothing(
    manager: MonitSettingsManager, box: FakeMonitBox
) -> None:
    resources = [single("monit.settings", enabled=False, interval=120, mailserver=["127.0.0.1"])]
    assert manager.plan("env", resources).is_empty
    result = manager.apply("env", resources)
    assert result["resource_outcomes"] == [] and result["resources_updated"] == 0
    assert not box.writes()


def test_drift_gives_one_update_one_set_call_and_no_reconfigure(
    manager: MonitSettingsManager, box: FakeMonitBox
) -> None:
    resources = [single("monit.settings", enabled=True)]
    diff = manager.plan("env", resources)
    assert len(diff.updates) == 1 and diff.updates[0] == {"enabled": "1"}
    result = manager.apply("env", resources)
    assert result["resources_updated"] == 1
    assert [o.action for o in result["resource_outcomes"]] == ["update"]
    assert box.paths() == ["monit/settings/set"]
    assert box.general["enabled"] == "1"
    assert manager.plan("env", resources).is_empty


def test_plan_map_is_redacted_and_secret_resolved_before_compare(
    manager: MonitSettingsManager, box: FakeMonitBox
) -> None:
    resources = [single("monit.settings", httpd_password=URI)]
    diff = manager.plan("env", resources)
    assert diff.updates == [{"httpd_password": REDACTED}]
    manager.apply("env", resources)
    assert box.general["httpdPassword"] == SECRET
    assert manager.plan("env", resources).is_empty


def test_empty_secret_is_allowed_and_matches_an_empty_box(
    manager: MonitSettingsManager, box: FakeMonitBox
) -> None:
    assert manager.plan("env", [single("monit.settings", httpd_password="")]).is_empty


def test_apply_never_echoes_an_undeclared_live_secret(
    manager: MonitSettingsManager, box: FakeMonitBox
) -> None:
    box.general["password"] = "masked-live-sentinel"  # fake fixture value
    manager.apply("env", [single("monit.settings", enabled=True)])
    _, _, body = box.writes()[0]
    assert "password" not in body["monit"]["general"]
    assert box.general["password"] == "masked-live-sentinel"  # untouched on the box


def test_logs_carry_field_names_only(
    manager: MonitSettingsManager, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        manager.apply("env", [single("monit.settings", httpd_password=URI)])
    assert "httpd_password" in caplog.text and SECRET not in caplog.text


def test_add_only_has_no_effect(manager: MonitSettingsManager) -> None:
    resources = [single("monit.settings", enabled=True)]
    assert len(manager.plan("env", resources, add_only=True).updates) == 1
    assert manager.apply("env", resources, add_only=True)["resources_updated"] == 1


def test_destroy_is_a_noop(manager: MonitSettingsManager, box: FakeMonitBox) -> None:
    result = manager.destroy("env", [single("monit.settings", enabled=True)])
    assert result["resources_destroyed"] == 0
    assert not box.calls


def test_more_than_one_resource_raises(manager: MonitSettingsManager) -> None:
    with pytest.raises(InvalidConfigurationError, match="exactly one"):
        manager.plan("env", [single("monit.settings"), single("monit.settings")])


def test_missing_envelope_raises_before_any_write(
    manager: MonitSettingsManager, box: FakeMonitBox
) -> None:
    with (
        patch.object(box, "_render", return_value={"monit": {"alert": {}}}),
        pytest.raises(APIError, match="no general object"),
    ):
        manager.apply("env", [single("monit.settings", enabled=True)])
    assert not box.writes()


def test_resource_ids_and_migrate(manager: MonitSettingsManager) -> None:
    resource = single("monit.settings")
    assert manager.get_resource_ids("env", [resource]) == {"monit.settings": "global"}
    out = manager.migrate("env")
    assert "settings:" in out and "enabled: false" in out
