"""Unit tests for the monit settings service (#791)."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.providers.opnsense.services import monit_settings as svc
from tests.helpers.opnsense_monit import SECRET, FakeMonitBox, single

T = "monit.settings"


def _service(box: FakeMonitBox) -> svc.MonitSettingsService:
    client = MagicMock()
    client.request.side_effect = box.request
    return svc.MonitSettingsService(client)


def _desired(service: svc.MonitSettingsService, **config: Any) -> dict[str, str]:
    return service.build_desired(single(T, **config))


def test_field_mapping_to_wire_names_and_envelope() -> None:
    service = _service(FakeMonitBox())
    desired = _desired(
        service,
        start_delay=60,
        ssl_version="tlsv12",
        ssl_verify=False,
        eventqueue_path="/var/q",
        eventqueue_slots=100,
        httpd_enabled=True,
        httpd_username="mon",
        httpd_port=2813,
        mmonit_timeout=7,
        mmonit_register_credentials=False,
    )
    assert service.build_set_payload({}, desired) == {
        "monit": {
            "general": {
                "startdelay": "60",
                "sslversion": "tlsv12",
                "sslverify": "0",
                "eventqueuePath": "/var/q",
                "eventqueueSlots": "100",
                "httpdEnabled": "1",
                "httpdUsername": "mon",
                "httpdPort": "2813",
                "mmonitTimeout": "7",
                "mmonitRegisterCredentials": "0",
            }
        }
    }


def test_unknown_key_raises() -> None:
    service = _service(FakeMonitBox())
    with pytest.raises(InvalidConfigurationError, match="unknown key"):
        _desired(service, bogus=1)


@pytest.mark.parametrize(
    ("config", "needle"),
    [
        ({"enabled": "yes-sentinel"}, "boolean"),
        ({"interval": "x-sentinel"}, "integer"),
        ({"interval": 0}, "range"),
        ({"port": 70000}, "1-65535"),
        ({"httpd_port": 0}, "1-65535"),
        ({"ssl_version": "tls9-sentinel"}, "one of"),
        ({"mailserver": "host-sentinel"}, "list of non-empty strings"),
        ({"httpd_allow": [1]}, "list of non-empty strings"),
    ],
)
def test_type_errors_never_carry_the_value(config: dict[str, Any], needle: str) -> None:
    with pytest.raises(InvalidConfigurationError, match=needle) as exc:
        _desired(_service(FakeMonitBox()), **config)
    assert "sentinel" not in str(exc.value)


def test_lists_compare_as_sets_and_flatten_option_dicts() -> None:
    box = FakeMonitBox()
    box.general["mailserver"] = "b.example.com,a.example.com"
    box.general["httpdAllow"] = "192.0.2.1"
    service = _service(box)
    general = service.live_general(service.get_model())
    desired = _desired(
        service,
        mailserver=["a.example.com", "b.example.com"],
        httpd_allow=["192.0.2.1"],
        ssl_version="auto",
    )
    live = service.extract_live(general, desired)
    assert live["ssl_version"] == "auto" and live["httpd_allow"] == "192.0.2.1"
    assert service.drift(live, desired) == []
    changed = _desired(service, mailserver=["a.example.com"])
    assert service.drift(service.extract_live(general, changed), changed) == ["mailserver"]


def test_drift_returns_field_names_only() -> None:
    box = FakeMonitBox()
    service = _service(box)
    general = service.live_general(service.get_model())
    desired = _desired(service, enabled=True, interval=120, password=SECRET)
    changed = service.drift(service.extract_live(general, desired), desired)
    assert changed == ["enabled", "password"]
    assert SECRET not in str(changed)


def test_only_declared_secrets_are_written_and_undeclared_live_ones_never_echoed() -> None:
    box = FakeMonitBox()
    box.general["password"] = "live-pw-sentinel"  # nosec B105
    box.general["httpdPassword"] = "live-httpd-sentinel"  # nosec B105
    box.general["mmonitUrl"] = "https://u:live-url-sentinel@mmonit.example.com"
    service = _service(box)
    general = service.live_general(service.get_model())
    payload = service.build_set_payload(general, _desired(service, enabled=True))
    body = payload["monit"]["general"]
    for wire in ("password", "httpdPassword", "mmonitUrl"):
        assert wire not in body
    assert body["enabled"] == "1" and body["interval"] == "120"
    declared = service.build_set_payload(general, _desired(service, password=SECRET))
    assert declared["monit"]["general"]["password"] == SECRET
    assert "httpdPassword" not in declared["monit"]["general"]


def test_set_settings_writes_the_envelope_to_the_box() -> None:
    box = FakeMonitBox()
    service = _service(box)
    general = service.live_general(service.get_model())
    service.set_settings(service.build_set_payload(general, _desired(service, enabled=True)))
    assert box.general["enabled"] == "1"
    assert box.paths() == ["monit/settings/set"]


def test_redacted_replaces_all_three_secrets() -> None:
    desired = {"enabled": "1", "password": "a", "httpd_password": "b", "mmonit_url": "c"}
    shown = svc.redacted(desired)
    assert shown == {
        "enabled": "1",
        "password": "[REDACTED]",
        "httpd_password": "[REDACTED]",
        "mmonit_url": "[REDACTED]",
    }
    assert desired["password"] == "a"


def test_missing_envelope_or_field_raises_apierror_with_key_names_only() -> None:
    client = MagicMock()
    client.request.return_value = {"nope": 1}
    with pytest.raises(APIError, match="no monit object"):
        svc.MonitSettingsService(client).get_model()
    service = svc.MonitSettingsService(MagicMock())
    with pytest.raises(APIError, match="no general object"):
        service.live_general({"alert": {}})
    with pytest.raises(APIError, match="no 'startdelay' field"):
        service.extract_live({"enabled": "0"}, ["start_delay"])


def test_reconfigure_posts_and_raises_on_failure() -> None:
    box = FakeMonitBox()
    _service(box).reconfigure()
    assert box.paths() == ["monit/service/reconfigure"]
    client = MagicMock()
    client.request.return_value = {"result": "failed", "validations": {"x": "y"}}
    with pytest.raises(APIError, match="reconfigure monit"):
        svc.MonitSettingsService(client).reconfigure()


def test_export_emits_placeholders_never_secret_values(caplog: pytest.LogCaptureFixture) -> None:
    box = FakeMonitBox()
    box.general.update(
        {
            "password": SECRET,
            "httpdPassword": "",
            "mmonitUrl": f"https://u:{SECRET}@mmonit.example.com",
            "mailserver": "mail.example.com",
            "eventqueueSlots": "",
            "mmonitTimeout": "soon",
        }
    )
    with caplog.at_level(logging.DEBUG):
        out = _service(box).export_to_yaml()
    assert SECRET not in out and SECRET not in caplog.text
    config = yaml.safe_load(out)["opnsense"]["monit"]["settings"]
    assert config["password"] == "secret://env_secrets/opnsense/monit/settings/password"
    assert config["mmonit_url"] == "secret://env_secrets/opnsense/monit/settings/mmonit_url"
    assert config["httpd_password"] == ""
    assert config["mailserver"] == ["mail.example.com"]
    assert config["enabled"] is False and config["interval"] == 120
    assert config["ssl_version"] == "auto" and config["ssl_verify"] is True
    assert "eventqueue_slots" not in config and "mmonit_timeout" not in config
    assert config["httpd_allow"] == []


def test_errors_and_logs_carry_no_secret(caplog: pytest.LogCaptureFixture) -> None:
    service = _service(FakeMonitBox())
    with caplog.at_level(logging.DEBUG), pytest.raises(InvalidConfigurationError) as exc:
        _desired(service, password=SECRET, port="x")
    assert SECRET not in str(exc.value) and SECRET not in caplog.text
