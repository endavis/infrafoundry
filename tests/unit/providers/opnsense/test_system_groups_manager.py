"""Tests for ``GroupManager`` (#805)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from infrafoundry.core.exceptions import ReferenceValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.system_groups import GroupManager
from infrafoundry.providers.opnsense.services.system_groups import GroupService
from tests.helpers.opnsense_auth import FakeClient, group_row, user_row


def _grp(name: str, /, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type="system.groups", provider="opnsense", config=config)


def _usr(name: str, /, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type="system.users", provider="opnsense", config=config)


def _patch(client: FakeClient) -> Any:
    service = GroupService(client)  # type: ignore[arg-type]
    return patch.object(GroupService, "from_environment", return_value=service)


def test_class_vars() -> None:
    assert GroupManager.SIBLING_RESOURCE_TYPE == "system.users"
    assert GroupManager.DELETE_SCOPE == "managed_set"
    assert GroupManager.SPLIT_DELETE_PHASE is True


def test_plan_resolves_refs_to_live_uids(tmp_path: Path) -> None:
    client = FakeClient(
        users=[user_row("a", "2001"), user_row("b", "2002")],
        groups=[group_row("admins", "1999", "2001,2002")],
    )
    users = [_usr("a"), _usr("beta", name="b")]
    with _patch(client):
        diff = GroupManager(tmp_path).plan(
            "env",
            [_grp("admins", member_refs=["a", "system.users.beta"])],
            sibling_resources=users,
        )
    assert diff.is_empty


def test_plan_pending_user_without_uid_marks_update(tmp_path: Path) -> None:
    client = FakeClient(groups=[group_row("admins", "1999", "")])
    with _patch(client):
        diff = GroupManager(tmp_path).plan(
            "env", [_grp("admins", member_refs=["new"])], sibling_resources=[_usr("new")]
        )
    assert len(diff.updates) == 1


def test_unknown_ref_raises(tmp_path: Path) -> None:
    with _patch(FakeClient()), pytest.raises(ReferenceValidationError):
        GroupManager(tmp_path).plan(
            "env", [_grp("g", member_refs=["nobody"])], sibling_resources=[]
        )


def test_apply_writes_member_uids(tmp_path: Path) -> None:
    client = FakeClient(users=[user_row("a", "2001"), user_row("b", "2002")])
    with _patch(client):
        result = GroupManager(tmp_path).apply(
            "env",
            [_grp("admins", member_refs=["b", "a"])],
            sibling_resources=[_usr("a"), _usr("b")],
        )
    assert result["resources_created"] == 1
    assert client.writes()[0][2] == {"group": {"name": "admins", "member": "2001,2002"}}


def test_apply_raises_for_non_live_ref(tmp_path: Path) -> None:
    with _patch(FakeClient()), pytest.raises(ReferenceValidationError):
        GroupManager(tmp_path).apply(
            "env", [_grp("g", member_refs=["a"])], sibling_resources=[_usr("a")]
        )


def test_deletes_only_runs_only_deletes_and_skips_refs(tmp_path: Path) -> None:
    client = FakeClient(groups=[group_row("old", "1"), group_row("keep", "2")])
    with _patch(client):
        result = GroupManager(tmp_path).apply(
            "env",
            [_grp("keep", member_refs=["ghost"]), _grp("new")],
            deletes_only=True,
            managed_resources=[_grp("old"), _grp("keep")],
            sibling_resources=[],
        )
    assert result["resources_created"] == 0
    assert result["resources_deleted"] == 1
    assert [e for _, e, _ in client.writes()] == ["auth/group/del/gu-old"]


def test_destroy_and_ids(tmp_path: Path) -> None:
    client = FakeClient(groups=[group_row("a", "1"), group_row("b", "2")])
    with _patch(client):
        manager = GroupManager(tmp_path)
        result = manager.destroy("env", [_grp("a"), _grp("b", lock=True), _grp("zz")])
        ids = manager.get_resource_ids("env", [_grp("op", name="b"), _grp("zz")])
    assert result["resources_destroyed"] == 1
    assert result["locked_skipped"] == 1
    assert ids == {"op": "gu-b"}
