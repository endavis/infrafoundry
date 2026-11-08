"""Tests for the system-users service (#805)."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.system_users import (
    Diff,
    LiveUser,
    UserConfig,
    UserService,
    changed_fields,
    compute_diff,
    reject_hashed_passwords,
    row_to_live,
    user_configs_from_resources,
)
from tests.helpers.opnsense_auth import BCRYPT, PLAIN, FakeClient, user_row


def _res(name: str, /, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type="system.users", provider="opnsense", config=config)


def _cfg(name: str, **config: Any) -> UserConfig:
    return user_configs_from_resources([_res(name, **config)])[0]


def _live(name: str, uid: str, **raw: str) -> LiveUser:
    return row_to_live(user_row(name, uid, **raw))


class TestParse:
    def test_only_set_fields_and_serialization(self) -> None:
        cfg = _cfg("example-user", disabled=False, priv=["b", "a", "a"], description="x")
        assert cfg.to_payload() == {
            "user": {"name": "example-user", "descr": "x", "disabled": "0", "priv": "a,b"}
        }

    def test_description_maps_to_descr_and_descr_rejected(self) -> None:
        assert _cfg("u", description="x").fields == (("descr", "x"),)
        with pytest.raises(ValueError, match="unknown keys"):
            _cfg("u", descr="x")

    def test_uid_and_group_memberships_not_accepted(self) -> None:
        with pytest.raises(ValueError, match="unknown keys"):
            _cfg("u", uid=2000)
        with pytest.raises(ValueError, match="unknown keys"):
            _cfg("u", group_memberships="admins")

    def test_bad_scope_and_types(self) -> None:
        with pytest.raises(ValueError, match="scope"):
            _cfg("u", scope="other")
        with pytest.raises(ValueError, match="disabled"):
            _cfg("u", disabled="yes")
        with pytest.raises(ValueError, match="update_password"):
            _cfg("u", update_password="yes")

    def test_skips_other_types(self) -> None:
        other = ResourceConfig(name="x", type="firewall.aliases", provider="opnsense", config={})
        assert user_configs_from_resources([other]) == []

    def test_password_kept_out_of_fields_and_repr(self) -> None:
        cfg = _cfg("u", password=PLAIN)
        assert cfg.fields == ()
        assert PLAIN not in repr(cfg)

    def test_payload_password_only_when_asked(self) -> None:
        cfg = _cfg("u", password=PLAIN)
        assert cfg.to_payload() == {"user": {"name": "u"}}
        assert cfg.to_payload(include_password=True) == {"user": {"name": "u", "password": PLAIN}}

    def test_bcrypt_looking_password_rejected_never_echoes_value(self) -> None:
        reject_hashed_passwords([_cfg("u", password=PLAIN), _cfg("v")])
        with pytest.raises(ValueError) as exc:
            reject_hashed_passwords([_cfg("example-user", password=BCRYPT)])
        assert "example-user" in str(exc.value)
        assert BCRYPT not in str(exc.value)


class TestDiff:
    def test_no_change_ignoring_password_and_reordered_priv(self) -> None:
        want = _cfg("example-user", password=PLAIN, priv=["b", "a"], disabled=False)
        have = _live("example-user", "2000", password="", priv="a,b", disabled="0")
        assert compute_diff([want], [have]).is_empty

    def test_update_password_counts_as_change(self) -> None:
        have = _live("example-user", "2000", password="")
        diff = compute_diff([_cfg("example-user", password=PLAIN, update_password=True)], [have])
        assert len(diff.updates) == 1
        assert changed_fields(have, diff.updates[0][1]) == ["password"]

    def test_add(self) -> None:
        diff = compute_diff([_cfg("example-user")], [])
        assert [u.name for u in diff.adds] == ["example-user"]

    def test_update_on_keys(self) -> None:
        have = _live("example-user", "2000", authorizedkeys="k1")
        diff = compute_diff([_cfg("example-user", authorizedkeys="k2")], [have])
        assert len(diff.updates) == 1

    def test_sparse_keeps_unset_fields(self) -> None:
        have = _live("root", "0", descr="whatever", shell="/bin/sh")
        assert compute_diff([_cfg("root")], [have]).is_empty

    def test_delete_only_managed(self) -> None:
        live = [_live("a", "2001"), _live("b", "2002")]
        diff = compute_diff([], live, managed_keys={"a"})
        assert [u.name for u in diff.deletes] == ["a"]
        assert [u.name for u in diff.unmanaged] == ["b"]

    def test_add_only_suppresses_deletes(self) -> None:
        diff = compute_diff([], [_live("a", "2001")], add_only=True, managed_keys={"a"})
        assert diff.deletes == []

    def test_locked(self) -> None:
        diff = compute_diff([_cfg("a", description="x", lock=True)], [_live("a", "2001")])
        assert diff.is_empty and len(diff.locked) == 1

    @pytest.mark.parametrize("managed", [None, {"root"}])
    def test_uid_zero_never_deleted(self, managed: set[str] | None) -> None:
        diff = compute_diff([], [_live("root", "0"), _live("a", "2001")], managed_keys=managed)
        assert "root" not in [u.name for u in diff.deletes]

    def test_uid_zero_log_only_when_delete_would_be_planned(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        root = _live("root", "0")
        with caplog.at_level("WARNING"):
            compute_diff([_cfg("root")], [root])
            compute_diff([], [root], add_only=True)
            compute_diff([], [root], managed_keys={"other"})
        assert "uid 0" not in caplog.text
        with caplog.at_level("WARNING"):
            compute_diff([], [root], managed_keys={"root"})
        assert "uid 0" in caplog.text


class TestService:
    def test_apply_diff_uses_registry_endpoints(self) -> None:
        client = FakeClient()
        svc = UserService(client)  # type: ignore[arg-type]
        have = row_to_live(user_row("b", "2002", "u-b"))
        gone = row_to_live(user_row("c", "2003", "u-c"))
        diff = compute_diff(
            [_cfg("a"), _cfg("b", description="new")], [have, gone], managed_keys={"c"}
        )
        counts = svc.apply_diff(diff)
        assert counts == {"created": 1, "updated": 1, "deleted": 1}
        assert [(m, e) for m, e, _ in client.writes()] == [
            ("POST", "auth/user/add"),
            ("POST", "auth/user/set/u-b"),
            ("POST", "auth/user/del/u-c"),
        ]

    def test_add_sends_password_update_omits_it(self) -> None:
        client = FakeClient()
        svc = UserService(client)  # type: ignore[arg-type]
        want = _cfg("u", password=PLAIN, description="d")
        svc.add(want)
        svc.update("uu-u", want)
        assert client.writes()[0][2] == {"user": {"name": "u", "descr": "d", "password": PLAIN}}
        assert client.writes()[1][2] == {"user": {"name": "u", "descr": "d"}}

    def test_search_uses_get(self) -> None:
        client = FakeClient(users=[user_row("a", "5")])
        assert UserService(client).search()[0].uid == "5"  # type: ignore[arg-type]
        assert client.calls[0][:2] == ("GET", "auth/user/search")

    def test_failed_write_names_user_not_value(self) -> None:
        client = FakeClient()
        client.write_result = {"result": "failed", "validations": {"user.name": "bad"}}
        svc = UserService(client)  # type: ignore[arg-type]
        with pytest.raises(APIError) as exc:
            svc.add(_cfg("example-user", password=PLAIN))
        assert "example-user" in str(exc.value)
        assert PLAIN not in str(exc.value)

    def test_delete_and_apply_diff_refuse_uid_zero(self) -> None:
        client = FakeClient()
        svc = UserService(client)  # type: ignore[arg-type]
        root = row_to_live(user_row("root", "0", "u-root"))
        assert svc.delete(root) is None
        assert svc.apply_diff(Diff(deletes=[root]))["deleted"] == 0
        assert client.writes() == []
