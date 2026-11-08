"""Fake OPNsense client for the system users/groups tests (#805). Fake data only."""

from __future__ import annotations

from typing import Any

BCRYPT = "$2y$10$" + "a" * 53
PLAIN = "example-plaintext-pw"
PUBKEY = "ssh-ed25519 AAAAFAKE example-user@example.com"


class FakeClient:
    """Route ``auth/user`` and ``auth/group`` calls to in-memory rows and record writes."""

    def __init__(
        self, users: list[dict[str, Any]] | None = None, groups: list[dict[str, Any]] | None = None
    ) -> None:
        self.users = users or []
        self.groups = groups or []
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.write_result: dict[str, Any] = {"result": "saved"}

    def request(
        self, method: str, endpoint: str, data: dict[str, Any] | None = None, **_: Any
    ) -> dict[str, Any]:
        self.calls.append((method, endpoint, data))
        if endpoint == "auth/user/search":
            return {"rows": self.users, "rowCount": len(self.users)}
        if endpoint == "auth/group/search":
            return {"rows": self.groups, "rowCount": len(self.groups)}
        return self.write_result

    def writes(self) -> list[tuple[str, str, dict[str, Any] | None]]:
        return [c for c in self.calls if not c[1].endswith("/search")]


def user_row(name: str, uid: str, uuid: str | None = None, **extra: str) -> dict[str, Any]:
    return {"uuid": uuid or f"uu-{name}", "name": name, "uid": uid, **extra}


def group_row(name: str, gid: str, member: str = "", **extra: str) -> dict[str, Any]:
    return {"uuid": f"gu-{name}", "name": name, "gid": gid, "member": member, **extra}


def register_env_secrets_backend() -> None:
    """Register the env_secrets backend in the plugin registry (as the VIP manager tests do)."""
    import contextlib

    from infrafoundry.core.plugin_system import get_registry
    from infrafoundry.core.plugin_system.exceptions import PluginConflictError
    from infrafoundry.core.plugin_system.plugin_type import PluginMetadata
    from infrafoundry.secrets.backends.env_secrets import EnvSecretsBackend

    with contextlib.suppress(PluginConflictError):
        get_registry().register(
            PluginMetadata(
                name="env_secrets",
                version="1.0.0",
                plugin_type="secret_backend",
                description="Test",
                implementation=EnvSecretsBackend,
            )
        )
