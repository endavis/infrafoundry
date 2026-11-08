"""Tests for ``UserManager`` (#805)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.system_users import UserManager
from infrafoundry.providers.opnsense.services.system_users import UserService
from infrafoundry.secrets.resolver import SecretResolutionError
from tests.helpers.opnsense_auth import (
    BCRYPT,
    PLAIN,
    FakeClient,
    register_env_secrets_backend,
    user_row,
)

SECRETS_CM = "infrafoundry.providers.opnsense.components._secrets.ConfigManager"


def _res(name: str, /, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type="system.users", provider="opnsense", config=config)


def _cm(secrets: dict[str, Any] | None) -> MagicMock:
    env = MagicMock()
    env.secrets = secrets
    cls = MagicMock()
    cls.return_value.load_environment.return_value = env
    return cls


def _run(client: FakeClient, secrets: dict[str, Any] | None = None) -> Any:
    register_env_secrets_backend()
    service = UserService(client)  # type: ignore[arg-type]
    return (
        patch.object(UserService, "from_environment", return_value=service),
        patch(SECRETS_CM, _cm(secrets)),
    )


def test_class_vars() -> None:
    assert UserManager.DELETE_SCOPE == "managed_set"
    assert not getattr(UserManager, "SPLIT_DELETE_PHASE", False)


def test_apply_resolves_secret_and_writes_plaintext(tmp_path: Path) -> None:
    client = FakeClient()
    p1, p2 = _run(client, {"users": {"example-user": {"password": PLAIN}}})
    with p1, p2:
        result = UserManager(tmp_path).apply(
            "env",
            [_res("example-user", password="secret://env_secrets/users/example-user/password")],
        )
    assert result["resources_created"] == 1
    assert client.writes()[0][2] == {"user": {"name": "example-user", "password": PLAIN}}
    assert result["resource_outcomes"][0].address == "opnsense_system_user.example-user"


def test_missing_secret_raises(tmp_path: Path) -> None:
    p1, p2 = _run(FakeClient(), {})
    with p1, p2, pytest.raises(SecretResolutionError):
        UserManager(tmp_path).plan(
            "env", [_res("u", password="secret://env_secrets/users/u/password")]
        )


def test_bcrypt_looking_password_rejected_without_value(tmp_path: Path) -> None:
    p1, p2 = _run(FakeClient(), {"pw": BCRYPT})
    with p1, p2, pytest.raises(ValueError) as exc:
        UserManager(tmp_path).plan("env", [_res("u", password="secret://env_secrets/pw")])
    assert BCRYPT not in str(exc.value)
    assert "'u'" in str(exc.value)
    assert "plaintext" in str(exc.value)


def test_plan_idempotent_with_empty_live_password(tmp_path: Path) -> None:
    client = FakeClient(users=[user_row("u", "2000", password="", descr="d")])
    p1, p2 = _run(client, {"pw": PLAIN})
    with p1, p2:
        diff = UserManager(tmp_path).plan(
            "env", [_res("u", password="secret://env_secrets/pw", description="d")]
        )
    assert diff.is_empty


def test_apply_update_omits_password_unless_update_password(tmp_path: Path) -> None:
    client = FakeClient(users=[user_row("u", "2000", password="", descr="old")])
    p1, p2 = _run(client, {"pw": PLAIN})
    with p1, p2:
        UserManager(tmp_path).apply(
            "env", [_res("u", password="secret://env_secrets/pw", description="new")]
        )
    assert client.writes()[0][2] == {"user": {"name": "u", "descr": "new"}}


def test_apply_update_password_sends_password(tmp_path: Path) -> None:
    client = FakeClient(users=[user_row("u", "2000", password="")])
    p1, p2 = _run(client, {"pw": PLAIN})
    with p1, p2:
        result = UserManager(tmp_path).apply(
            "env", [_res("u", password="secret://env_secrets/pw", update_password=True)]
        )
    assert result["resources_updated"] == 1
    assert client.writes()[0][2] == {"user": {"name": "u", "password": PLAIN}}


def test_apply_never_deletes_uid_zero(tmp_path: Path) -> None:
    client = FakeClient(users=[user_row("root", "0"), user_row("old", "2001")])
    p1, p2 = _run(client)
    with p1, p2:
        result = UserManager(tmp_path).apply("env", [], managed_resources=[_res("root")])
    assert result["resources_deleted"] == 0
    assert client.writes() == []


def test_unparsable_managed_row_is_unresolved(tmp_path: Path) -> None:
    client = FakeClient()
    p1, p2 = _run(client)
    with p1, p2:
        result = UserManager(tmp_path).apply(
            "env", [], managed_resources=[_res("bad", scope="nonsense")]
        )
    assert result["unresolved_managed"] == ["bad"]


def test_destroy_skips_root_and_locked(tmp_path: Path) -> None:
    client = FakeClient(users=[user_row("root", "0"), user_row("a", "2001"), user_row("b", "2002")])
    p1, p2 = _run(client)
    with p1, p2:
        result = UserManager(tmp_path).destroy(
            "env", [_res("root"), _res("a"), _res("b", lock=True), _res("gone")]
        )
    assert result["resources_destroyed"] == 1
    assert result["protected_skipped"] == 1
    assert result["locked_skipped"] == 1
    assert [e for _, e, _ in client.writes()] == ["auth/user/del/uu-a"]


def test_get_resource_ids(tmp_path: Path) -> None:
    client = FakeClient(users=[user_row("a", "2001", "uuid-a")])
    p1, p2 = _run(client)
    with p1, p2:
        ids = UserManager(tmp_path).get_resource_ids(
            "env", [_res("op-name", name="a"), _res("missing")]
        )
    assert ids == {"op-name": "uuid-a"}
