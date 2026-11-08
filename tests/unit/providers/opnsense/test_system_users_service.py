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
    check_password_hashes,
    compute_diff,
    row_to_live,
    user_configs_from_resources,
)
from tests.helpers.opnsense_auth import BCRYPT, FakeClient, user_row


def _res(name: str, /, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type="system.users", provider="opnsense", config=config)


def _cfg(name: str, **config: Any) -> UserConfig:
    return user_configs_from_resources([_res(name, **config)])[0]


def _live(name: str, uid: str, **raw: str) -> LiveUser:
    return row_to_live(user_row(name, uid, **raw))


class TestParse:
    def test_only_set_fields_and_serialization(self) -> None:
        cfg = _cfg("example-user", uid=2000, disabled=False, priv=["b", "a", "a"], descr="x")
        assert cfg.to_payload() == {
            "user": {
                "name": "example-user",
                "descr": "x",
                "disabled": "0",
                "priv": "a,b",
                "uid": "2000",
            }
        }

    def test_group_memberships_not_accepted(self) -> None:
        with pytest.raises(ValueError, match="unknown keys"):
            _cfg("u", group_memberships="admins")

    def test_bad_scope_and_types(self) -> None:
        with pytest.raises(ValueError, match="scope"):
            _cfg("u", scope="other")
        with pytest.raises(ValueError, match="disabled"):
            _cfg("u", disabled="yes")
        with pytest.raises(ValueError, match="uid"):
            _cfg("u", uid=-1)

    def test_skips_other_types(self) -> None:
        other = ResourceConfig(name="x", type="firewall.aliases", provider="opnsense", config={})
        assert user_configs_from_resources([other]) == []

    def test_password_hash_check_never_echoes_value(self) -> None:
        check_password_hashes([_cfg("u", password=BCRYPT)])
        with pytest.raises(ValueError) as exc:
            check_password_hashes([_cfg("example-user", password="plain-text-pw")])
        assert "example-user" in str(exc.value)
        assert "plain-text-pw" not in str(exc.value)


class TestDiff:
    def test_no_change_including_hash_and_reordered_priv(self) -> None:
        want = _cfg("example-user", password=BCRYPT, priv=["b", "a"], disabled=False)
        have = _live("example-user", "2000", password=BCRYPT, priv="a,b", disabled="0")
        assert compute_diff([want], [have]).is_empty

    def test_add(self) -> None:
        diff = compute_diff([_cfg("example-user")], [])
        assert [u.name for u in diff.adds] == ["example-user"]

    def test_update_on_password_and_keys(self) -> None:
        have = _live("example-user", "2000", password="$2y$10$" + "b" * 53, authorizedkeys="k1")
        diff = compute_diff([_cfg("example-user", password=BCRYPT, authorizedkeys="k2")], [have])
        assert len(diff.updates) == 1

    def test_sparse_keeps_unset_fields(self) -> None:
        have = _live("root", "0", descr="whatever", shell="/bin/sh")
        assert compute_diff([_cfg("root", uid=0)], [have]).is_empty

    def test_delete_only_managed(self) -> None:
        live = [_live("a", "2001"), _live("b", "2002")]
        diff = compute_diff([], live, managed_keys={"a"})
        assert [u.name for u in diff.deletes] == ["a"]
        assert [u.name for u in diff.unmanaged] == ["b"]

    def test_add_only_suppresses_deletes(self) -> None:
        diff = compute_diff([], [_live("a", "2001")], add_only=True, managed_keys={"a"})
        assert diff.deletes == []

    def test_locked(self) -> None:
        diff = compute_diff([_cfg("a", descr="x", lock=True)], [_live("a", "2001")])
        assert diff.is_empty and len(diff.locked) == 1

    @pytest.mark.parametrize("managed", [None, {"root"}])
    def test_uid_zero_never_deleted(self, managed: set[str] | None) -> None:
        diff = compute_diff([], [_live("root", "0"), _live("a", "2001")], managed_keys=managed)
        assert "root" not in [u.name for u in diff.deletes]


class TestService:
    def test_apply_diff_uses_registry_endpoints(self) -> None:
        client = FakeClient()
        svc = UserService(client)  # type: ignore[arg-type]
        have = row_to_live(user_row("b", "2002", "u-b"))
        gone = row_to_live(user_row("c", "2003", "u-c"))
        diff = compute_diff([_cfg("a"), _cfg("b", descr="new")], [have, gone], managed_keys={"c"})
        counts = svc.apply_diff(diff)
        assert counts == {"created": 1, "updated": 1, "deleted": 1}
        assert [(m, e) for m, e, _ in client.writes()] == [
            ("POST", "auth/user/add"),
            ("POST", "auth/user/set/u-b"),
            ("POST", "auth/user/del/u-c"),
        ]

    def test_search_uses_get(self) -> None:
        client = FakeClient(users=[user_row("a", "5")])
        assert UserService(client).search()[0].uid == "5"  # type: ignore[arg-type]
        assert client.calls[0][:2] == ("GET", "auth/user/search")

    def test_failed_write_names_user_not_value(self) -> None:
        client = FakeClient()
        client.write_result = {"result": "failed", "validations": {"user.name": "bad"}}
        svc = UserService(client)  # type: ignore[arg-type]
        with pytest.raises(APIError) as exc:
            svc.add(_cfg("example-user", password=BCRYPT))
        assert "example-user" in str(exc.value)
        assert BCRYPT not in str(exc.value)

    def test_delete_and_apply_diff_refuse_uid_zero(self) -> None:
        client = FakeClient()
        svc = UserService(client)  # type: ignore[arg-type]
        root = row_to_live(user_row("root", "0", "u-root"))
        assert svc.delete(root) is None
        assert svc.apply_diff(Diff(deletes=[root]))["deleted"] == 0
        assert client.writes() == []
