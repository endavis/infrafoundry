"""Unit tests for ``HasyncSettingsService`` (#1389)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.hasync_settings import (
    PASSWORD_PLACEHOLDER,
    REDACTED,
    HasyncSettingsService,
    live_options,
    password_unreadable,
    redacted,
    wants_password_update,
)

FAKE = "FAKE-SYNC-PASSWORD-0001"
OTHER = "FAKE-SYNC-PASSWORD-0002"


def _live(password: str = "", **over: Any) -> dict[str, Any]:
    live: dict[str, Any] = {
        "disablepreempt": "0",
        "disconnectppps": "0",
        "pfsyncinterface": {"": {"selected": 1}, "lan": {"selected": 0}, "wan": {"selected": 0}},
        "pfsyncpeerip": "",
        "pfsyncversion": {"1301": {"selected": 0}, "1400": {"selected": 1}},
        "pfsyncdefer": "0",
        "synchronizetoip": "",
        "verifypeer": "0",
        "username": "",
        "password": password,
        "syncitems": {"aliases": {"selected": 0}, "rules": {"selected": 0}},
    }
    live.update(over)
    return live


def _resource(**config: Any) -> ResourceConfig:
    return ResourceConfig(
        name="hasync.settings", type="hasync.settings", provider="opnsense", config=config
    )


def _service(response: Any = None) -> HasyncSettingsService:
    client = MagicMock()
    client.request.return_value = response
    return HasyncSettingsService(client)


def test_build_desired_converts_types() -> None:
    desired = _service().build_desired(
        _resource(
            disable_preempt=True,
            pfsync_version=1400,
            sync_items=["rules", "aliases", "rules"],
            pfsync_peer_ip="192.0.2.2",
            update_password=True,
            password=FAKE,
        )
    )
    assert desired == {
        "disable_preempt": "1",
        "pfsync_version": "1400",
        "sync_items": "aliases,rules",
        "pfsync_peer_ip": "192.0.2.2",
        "password": FAKE,
    }
    assert _service().build_desired(_resource(pfsync_version="1301")) == {"pfsync_version": "1301"}
    assert wants_password_update(_resource(update_password=True))
    assert not wants_password_update(_resource())


@pytest.mark.parametrize(
    "config",
    [
        {"bogus": 1},
        {"disable_preempt": "yes"},
        {"pfsync_version": 9},
        {"pfsync_version": True},
        {"sync_items": "rules"},
        {"sync_items": ["", "x"]},
        {"username": 5},
        {"update_password": "yes"},
        {"password": ""},
        {"password": 7},
    ],
)
def test_build_desired_rejects_bad_values_without_showing_them(config: dict[str, Any]) -> None:
    with pytest.raises(InvalidConfigurationError) as exc:
        _service().build_desired(_resource(**config))
    assert "FAKE" not in str(exc.value)


def test_password_value_not_in_error() -> None:
    with pytest.raises(InvalidConfigurationError) as exc:
        _service().build_desired(_resource(password=FAKE, pfsync_version=9))
    assert FAKE not in str(exc.value)


def test_live_hasync_missing_envelope_names_keys_only() -> None:
    with pytest.raises(APIError) as exc:
        _service().live_hasync({"other": FAKE})
    assert FAKE not in str(exc.value)
    assert FAKE not in str(getattr(exc.value, "response", ""))
    assert _service().live_hasync({"hasync": {"a": 1}}) == {"a": 1}
    with pytest.raises(APIError):
        _service().live_hasync("nope")


def test_live_options() -> None:
    live = _live()
    assert live_options(live, "pfsyncinterface") == {"lan", "wan"}
    assert live_options(live, "pfsyncpassword") == set()
    assert live_options({"x": "str"}, "x") == set()


def test_changed_fields_equal_and_differing() -> None:
    svc = _service()
    live = _live(
        pfsyncpeerip="192.0.2.2",
        syncitems={"aliases": {"selected": 1}, "rules": {"selected": 1}},
    )
    desired = {
        "pfsync_peer_ip": "192.0.2.2",
        "sync_items": "aliases,rules",
        "pfsync_version": "1400",
        "disable_preempt": "0",
        "pfsync_interface": "",
    }
    assert svc.changed_fields(live, desired, False) == []
    assert svc.changed_fields(live, {**desired, "verify_peer": "1"}, False) == ["verify_peer"]
    assert svc.changed_fields(live, {"sync_items": "rules"}, False) == ["sync_items"]


def test_changed_fields_sync_items_reorder_is_not_drift() -> None:
    live = _live(syncitems={"rules": {"selected": 1}, "aliases": {"selected": 1}})
    assert _service().changed_fields(live, {"sync_items": "aliases,rules"}, False) == []


def test_password_changed_fields() -> None:
    svc = _service()
    assert svc.changed_fields(_live(FAKE), {"password": FAKE}, False) == []
    assert svc.changed_fields(_live(OTHER), {"password": FAKE}, False) == ["password"]
    assert svc.changed_fields(_live(""), {"password": FAKE}, False) == []
    assert svc.changed_fields(_live("********"), {"password": FAKE}, False) == []
    assert svc.changed_fields(_live(""), {"password": FAKE}, True) == ["password"]
    assert password_unreadable(_live(""))
    assert password_unreadable(_live("***"))
    assert not password_unreadable(_live(FAKE))


def test_changed_fields_never_carry_values() -> None:
    changed = _service().changed_fields(_live(OTHER), {"password": FAKE}, False)
    assert FAKE not in repr(changed)


def test_should_send_password() -> None:
    svc = _service()
    assert svc.should_send_password({"password": FAKE}, [], True)
    assert svc.should_send_password({"password": FAKE, "username": "u"}, ["username"], False)
    assert not svc.should_send_password({"password": FAKE}, [], False)
    assert not svc.should_send_password({"username": "u"}, ["username"], True)


def test_build_set_payload_never_echoes_live_password() -> None:
    svc = _service()
    live = _live(OTHER)
    body = svc.build_set_payload(live, {"username": "fw-test-sync"}, False)["hasync"]
    assert "password" not in body
    assert OTHER not in repr(body)
    assert body["username"] == "fw-test-sync"
    assert body["pfsyncinterface"] == ""
    assert body["pfsyncversion"] == "1400"
    body = svc.build_set_payload(live, {"password": FAKE}, True)["hasync"]
    assert body["password"] == FAKE
    assert OTHER not in repr(body)


def test_unknown_references() -> None:
    svc = _service()
    live = _live()
    assert svc.unknown_references(live, {"pfsync_interface": "lan", "sync_items": "rules"}) == []
    msgs = svc.unknown_references(live, {"pfsync_interface": "opt99", "sync_items": "bogus"})
    assert len(msgs) == 2
    assert "opt99" in msgs[0]
    assert "bogus" in msgs[1]
    # an empty live option map skips the check
    assert svc.unknown_references({}, {"pfsync_interface": "opt99", "sync_items": "x"}) == []


def test_write_calls_raise_on_failed() -> None:
    svc = _service({"result": "failed", "validations": {"hasync.x": "bad"}})
    with pytest.raises(APIError):
        svc.set_settings({"hasync": {}})
    with pytest.raises(APIError):
        svc.reconfigure()
    assert _service({"status": "ok"}).reconfigure() == {"status": "ok"}
    with pytest.raises(APIError):
        _service({"status": "failed"}).reconfigure()
    ok = _service({"result": "saved"})
    ok.set_settings({"hasync": {"a": "1"}})
    args = ok.client.request.call_args  # type: ignore[attr-defined]
    assert args.args[0] == "POST"
    assert args.args[1] == "core/hasync/set"
    assert args.kwargs["data"] == {"hasync": {"a": "1"}}


def test_get_settings_uses_get_endpoint() -> None:
    svc = _service({"hasync": {}})
    svc.get_settings()
    assert svc.client.request.call_args.args[:2] == ("GET", "core/hasync/get")  # type: ignore[attr-defined]


def test_redacted_swaps_password_only() -> None:
    out = redacted({"password": FAKE, "username": "u"})
    assert out == {"password": REDACTED, "username": "u"}
    assert FAKE not in repr(out)


def test_export_to_yaml_placeholder_and_no_password_text() -> None:
    live = _live(
        FAKE,
        pfsyncpeerip="192.0.2.2",
        disablepreempt="1",
        syncitems={"rules": {"selected": 1}, "aliases": {"selected": 1}},
    )
    text = _service({"hasync": live}).export_to_yaml()
    assert FAKE not in text
    leaf = yaml.safe_load(text)["opnsense"]["hasync"]["settings"]
    assert leaf["password"] == PASSWORD_PLACEHOLDER
    assert leaf["disable_preempt"] is True
    assert leaf["sync_items"] == ["aliases", "rules"]
    assert leaf["pfsync_version"] == "1400"
    assert "update_password" not in leaf


def test_export_without_password_has_no_placeholder() -> None:
    text = _service({"hasync": _live("")}).export_to_yaml()
    leaf = yaml.safe_load(text)["opnsense"]["hasync"]["settings"]
    assert "password" not in leaf
    assert leaf["pfsync_interface"] == ""


def test_reset_builds_fixed_map_and_copies_constant() -> None:
    from infrafoundry.providers.opnsense.services.hasync_settings import RESET_DESIRED

    desired = _service().build_desired(_resource(reset=True))
    assert desired == RESET_DESIRED
    assert desired is not RESET_DESIRED
    assert desired["pfsync_version"] == "1400"
    assert "disable_preempt" not in desired
    assert not wants_password_update(_resource(reset=True))


@pytest.mark.parametrize("other", ["password", "update_password", "username", "pfsync_defer"])
def test_reset_with_other_key_rejected_naming_keys_only(other: str) -> None:
    value: Any = True if other in {"update_password", "pfsync_defer"} else FAKE
    with pytest.raises(InvalidConfigurationError) as exc:
        _service().build_desired(_resource(reset=True, **{other: value}))
    assert other in str(exc.value)
    assert FAKE not in str(exc.value)


@pytest.mark.parametrize("value", ["yes", 1, None])
def test_reset_non_bool_rejected(value: Any) -> None:
    with pytest.raises(InvalidConfigurationError, match="reset must be a boolean"):
        _service().build_desired(_resource(reset=value))


def test_reset_false_is_absent() -> None:
    assert _service().build_desired(_resource(reset=False, username="u")) == {"username": "u"}
    assert _service().build_desired(_resource(reset=False)) == {}


def test_reset_changed_fields_password_rules() -> None:
    service = _service()
    desired = service.build_desired(_resource(reset=True))
    assert service.changed_fields(_live(""), desired, False) == []
    assert service.changed_fields(_live(FAKE), desired, False) == ["password"]
    assert service.changed_fields(_live("***"), desired, False) == ["password"]
    assert service.changed_fields(_live("", username="u"), desired, False) == ["username"]


def test_reset_payload_writes_empty_password_and_keeps_booleans() -> None:
    service = _service()
    desired = service.build_desired(_resource(reset=True))
    live = _live(FAKE, disablepreempt="1", username="u")
    changed = service.changed_fields(live, desired, False)
    assert service.should_send_password(desired, changed, False)
    body = service.build_set_payload(live, desired, True)["hasync"]
    assert body["password"] == ""
    assert body["username"] == ""
    assert body["disablepreempt"] == "1"
    assert FAKE not in repr(body)
