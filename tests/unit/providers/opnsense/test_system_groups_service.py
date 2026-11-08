"""Tests for the system-groups service (#805)."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.system_groups import (
    GroupConfig,
    GroupService,
    compute_diff,
    group_configs_from_resources,
    row_to_live_group,
)
from tests.helpers.opnsense_auth import FakeClient, group_row


def _cfg(name: str, **config: Any) -> GroupConfig:
    res = ResourceConfig(name=name, type="system.groups", provider="opnsense", config=config)
    return group_configs_from_resources([res])[0]


def _live(name: str, gid: str, member: str = "", **extra: str) -> Any:
    return row_to_live_group(group_row(name, gid, member, **extra))


class TestParse:
    def test_payload_without_refs_has_no_member(self) -> None:
        cfg = _cfg("admins", gid=1999, description="d")
        assert cfg.to_payload(["5"]) == {
            "group": {"name": "admins", "description": "d", "gid": "1999"}
        }

    def test_payload_with_refs_sorted_numeric(self) -> None:
        cfg = _cfg("admins", member_refs=["a", "b"])
        assert cfg.to_payload(["10", "2"])["group"]["member"] == "2,10"

    def test_bad_input(self) -> None:
        with pytest.raises(ValueError, match="member_refs"):
            _cfg("g", member_refs="a")
        with pytest.raises(ValueError, match="unknown keys"):
            _cfg("g", member="1")


class TestDiff:
    def test_member_set_compared_unordered(self) -> None:
        want = _cfg("admins", member_refs=["a", "b"])
        have = _live("admins", "1999", "3,2")
        assert compute_diff([want], {"admins": ("2", "3")}, [have]).is_empty

    def test_member_change_updates(self) -> None:
        want = _cfg("admins", member_refs=["a"])
        diff = compute_diff([want], {"admins": ("2",)}, [_live("admins", "1999", "2,3")])
        assert len(diff.updates) == 1

    def test_no_refs_ignores_live_members(self) -> None:
        assert compute_diff([_cfg("admins")], {}, [_live("admins", "1999", "2,3")]).is_empty

    def test_pending_member_forces_update(self) -> None:
        want = _cfg("admins", member_refs=["a"])
        diff = compute_diff([want], {"admins": ()}, [_live("admins", "1")], pending={"admins"})
        assert len(diff.updates) == 1

    def test_add_delete_and_managed_keys(self) -> None:
        live = [_live("x", "1"), _live("y", "2")]
        diff = compute_diff([_cfg("n")], {}, live, managed_keys={"x"})
        assert [g.name for g in diff.adds] == ["n"]
        assert [g.name for g in diff.deletes] == ["x"]
        assert [g.name for g in diff.unmanaged] == ["y"]

    def test_add_only_and_lock(self) -> None:
        assert compute_diff([], {}, [_live("x", "1")], add_only=True).deletes == []
        diff = compute_diff([_cfg("x", description="q", lock=True)], {}, [_live("x", "1")])
        assert diff.is_empty and len(diff.locked) == 1


class TestService:
    def test_apply_diff_endpoints_and_member_payload(self) -> None:
        client = FakeClient()
        svc = GroupService(client)  # type: ignore[arg-type]
        diff = compute_diff(
            [_cfg("new", member_refs=["a"]), _cfg("old", member_refs=["a"])],
            {"new": ("5",), "old": ("5",)},
            [row_to_live_group(group_row("old", "9", "1")), row_to_live_group(group_row("z", "8"))],
        )
        assert svc.apply_diff(diff) == {"created": 1, "updated": 1, "deleted": 1}
        writes = client.writes()
        assert [(m, e) for m, e, _ in writes] == [
            ("POST", "auth/group/add"),
            ("POST", "auth/group/set/gu-old"),
            ("POST", "auth/group/del/gu-z"),
        ]
        assert writes[0][2] == {"group": {"name": "new", "member": "5"}}

    def test_search_users_uses_user_endpoint(self) -> None:
        client = FakeClient(users=[{"uuid": "u", "name": "a", "uid": "5"}])
        users = GroupService(client).search_users()  # type: ignore[arg-type]
        assert users[0].uid == "5"
        assert client.calls[0][:2] == ("GET", "auth/user/search")
