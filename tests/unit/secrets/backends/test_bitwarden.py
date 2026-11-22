"""Tests for the bitwarden secret backend, against a stub ``bw`` on PATH."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from infrafoundry.secrets.backends import bitwarden
from infrafoundry.secrets.backends.bitwarden import (
    BitwardenSecretBackend,
    close_bitwarden_sessions,
    register,
)
from infrafoundry.secrets.protocol import SecretBackendError, SecretNotFoundError
from infrafoundry.secrets.resolver import SecretResolutionError, SecretResolver
from tests.unit.secrets.bw_stub import (
    CLIENT_ID,
    CLIENT_SECRET,
    COL_ID,
    FIXTURE_VALUE,
    ITEM_ID,
    MASTER,
    ORG_ID,
    SERVER,
    StubBw,
    install_stub,
)


@pytest.fixture(autouse=True)
def _close_sessions() -> Iterator[None]:
    close_bitwarden_sessions()
    yield
    close_bitwarden_sessions()


@pytest.fixture
def stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StubBw:
    return install_stub(tmp_path, monkeypatch)


def make(**overrides: Any) -> BitwardenSecretBackend:
    config: dict[str, Any] = {"server": SERVER}
    config.update(overrides)
    return BitwardenSecretBackend(config)


def test_login_unlock_order_and_isolation(stub: StubBw, monkeypatch: pytest.MonkeyPatch) -> None:
    before = dict(os.environ)
    assert make().get_secret("Router Admin/password") == FIXTURE_VALUE
    calls = stub.calls()
    subs = [c["argv"][0] for c in calls]
    assert subs[:5] == ["config", "status", "login", "unlock", "sync"]
    assert calls[0]["argv"] == ["config", "server", SERVER, "--nointeraction"]
    assert calls[2]["argv"] == ["login", "--apikey", "--nointeraction"]
    assert calls[3]["argv"] == [
        "unlock",
        "--passwordenv",
        "BW_PASSWORD",
        "--raw",
        "--nointeraction",
    ]
    assert all(c["argv"][-1] == "--nointeraction" for c in calls)

    dirs = {c["appdir"] for c in calls}
    assert len(dirs) == 1
    (appdir,) = dirs
    assert appdir != os.environ["BITWARDENCLI_APPDATA_DIR"]
    assert {c["appdir_mode"] for c in calls} == {"0o700"}

    for call in calls:
        env = call["env"]
        sub = call["argv"][0]
        assert env["BW_SESSION"] != "inherited-session"
        assert (env["BW_CLIENTID"], env["BW_CLIENTSECRET"]) == (
            (CLIENT_ID, CLIENT_SECRET) if sub == "login" else (None, None)
        )
        assert env["BW_PASSWORD"] == (MASTER if sub == "unlock" else None)
        assert env["BW_SERVER"] is None
        if sub in ("config", "status", "login", "unlock"):
            assert env["BW_SESSION"] is None
        else:
            assert env["BW_SESSION"] == "session-key-abc"
    assert dict(os.environ) == before


def test_credentials_never_in_argv(stub: StubBw) -> None:
    make().get_secret("Router Admin/password")
    for call in stub.calls():
        joined = " ".join(call["argv"])
        for secret in (CLIENT_ID, CLIENT_SECRET, MASTER, "session-key-abc"):
            assert secret not in joined


def test_unlock_uses_passwordenv_and_takes_session_key(stub: StubBw) -> None:
    make().get_secret("Router Admin/username")
    unlock = next(c for c in stub.calls() if c["argv"][0] == "unlock")
    assert unlock["env"]["BW_PASSWORD"] == MASTER
    after = [c for c in stub.calls() if c["argv"][0] == "list"]
    assert after[0]["env"]["BW_SESSION"] == "session-key-abc"


def test_server_mismatch_raises(stub: StubBw) -> None:
    # The stub reports the URL it was configured with; make config silently not stick.
    bw = stub.log.parent / "bin" / "bw"
    text = bw.read_text(encoding="utf-8").replace(
        'state["server"] = argv[2]; save()', 'state["server"] = "https://other.example.net"; save()'
    )
    bw.write_text(text, encoding="utf-8")
    with pytest.raises(SecretBackendError, match="server URL"):
        make().get_secret("Router Admin/password")
    assert not Path(stub.calls()[0]["appdir"]).exists()


def test_http_server_rejected_by_backend() -> None:
    with pytest.raises(SecretBackendError, match="https"):
        BitwardenSecretBackend({"server": "http://vault.example.com"})


def test_second_backend_reuses_session(stub: StubBw) -> None:
    make().get_secret("Router Admin/password")
    count = len(stub.calls())
    make().get_secret("Router Admin/username")
    new = stub.calls()[count:]
    assert not {"login", "unlock", "config", "sync"} & {c["argv"][0] for c in new}


def test_close_sessions_locks_logs_out_and_removes_dir(stub: StubBw) -> None:
    make().get_secret("Router Admin/password")
    appdir = Path(stub.calls()[0]["appdir"])
    assert appdir.is_dir()
    close_bitwarden_sessions()
    assert stub.subcommands()[-2:] == ["lock", "logout"]
    assert not appdir.exists()


def test_atexit_registered_once(stub: StubBw, monkeypatch: pytest.MonkeyPatch) -> None:
    registered: list[object] = []
    monkeypatch.setattr(bitwarden, "_ATEXIT_REGISTERED", False)
    monkeypatch.setattr(bitwarden.atexit, "register", lambda fn: registered.append(fn))
    make().get_secret("Router Admin/password")
    make(collection=COL_ID).get_secret("Router Admin/password")
    assert registered == [close_bitwarden_sessions]


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("username", "admin"),
        ("password", FIXTURE_VALUE),
        ("notes", "note text"),
        ("uri", "https://first.example.com"),
        ("totp", "123456"),
        ("api_key", "fixture-api-456"),
    ],
)
def test_field_kinds(stub: StubBw, field: str, expected: str) -> None:
    assert make().get_secret(f"Router Admin/{field}") == expected


def test_totp_uses_get_totp_by_id(stub: StubBw) -> None:
    make().get_secret("Router Admin/totp")
    totp = next(c for c in stub.calls() if c["argv"][:2] == ["get", "totp"])
    assert totp["argv"][2] == ITEM_ID


def test_builtin_name_wins_over_custom_field(stub: StubBw) -> None:
    assert make().get_secret("Router Admin/password") == FIXTURE_VALUE


def test_lookup_by_id_uses_get_item(stub: StubBw) -> None:
    assert make().get_secret(f"{ITEM_ID}/password") == FIXTURE_VALUE
    assert any(c["argv"][:3] == ["get", "item", ITEM_ID] for c in stub.calls())
    assert not any(c["argv"][:2] == ["list", "items"] for c in stub.calls())


def test_lookup_by_name_is_exact(stub: StubBw) -> None:
    # --search "Router Admin" also returns "Router Admin Backup"; only the exact one counts.
    assert make().get_secret("Router Admin/username") == "admin"
    assert make().get_secret("Router Admin Backup/username") == "backup"
    with pytest.raises(SecretNotFoundError):
        make().get_secret("Router/username")


def test_item_name_may_contain_slash(stub: StubBw) -> None:
    assert make().get_secret("team/shared/db/password") == "slashed"


def test_scope_flags_and_name_resolution_once(stub: StubBw) -> None:
    backend = make(organization="Example Org", collection="Automation")
    assert backend.get_secret("Router Admin/password") == FIXTURE_VALUE
    backend.get_secret("Router Admin/username")
    lists = [c["argv"] for c in stub.calls() if c["argv"][0] == "list"]
    assert sum(1 for a in lists if a[1] == "organizations") == 1
    assert sum(1 for a in lists if a[1] == "collections") == 1
    items = [a for a in lists if a[1] == "items"]
    assert items
    for argv in items:
        assert argv[argv.index("--organizationid") + 1] == ORG_ID
        assert argv[argv.index("--collectionid") + 1] == COL_ID


def test_collection_scope_filters_name_lookup(stub: StubBw) -> None:
    """Two same-named items in sibling collections: the collection scope picks one.

    bw ignores ``--collectionid`` next to ``--organizationid`` (the stub does too), so the
    backend has to apply the collection filter itself.
    """
    other_col = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    fx = json.loads(stub.fixture.read_text(encoding="utf-8"))
    fx["collections"].append({"id": other_col, "name": "Other"})
    for item_id, col, pw in (
        ("88888888-8888-4888-8888-888888888888", COL_ID, "in-automation"),
        ("99999999-9999-4999-8999-999999999999", other_col, "in-other"),
    ):
        fx["items"].append(
            {
                "id": item_id,
                "name": "Shared Name",
                "organizationId": ORG_ID,
                "collectionIds": [col],
                "login": {"password": pw},
            }
        )
    stub.fixture.write_text(json.dumps(fx), encoding="utf-8")

    scoped = make(organization="Example Org", collection="Other")
    assert scoped.get_secret("Shared Name/password") == "in-other"
    assert "Router Admin" not in scoped.list_secrets()
    assert make(organization="Example Org", collection="Automation").get_secret(
        "Shared Name/password"
    ) == ("in-automation")
    with pytest.raises(SecretBackendError, match="2 items"):
        make(organization="Example Org").get_secret("Shared Name/password")


def test_scope_uuid_passed_without_lookup(stub: StubBw) -> None:
    make(organization=ORG_ID, collection=COL_ID).get_secret("Router Admin/password")
    assert not any(c["argv"][1:2] in (["organizations"], ["collections"]) for c in stub.calls())


def test_item_by_id_outside_scope_not_found(stub: StubBw) -> None:
    elsewhere = "66666666-6666-4666-8666-666666666666"
    with pytest.raises(SecretNotFoundError):
        make(organization=ORG_ID).get_secret(f"{elsewhere}/password")


def test_unknown_scope_name_raises(stub: StubBw) -> None:
    with pytest.raises(SecretBackendError, match="organization"):
        make(organization="No Such Org").get_secret("Router Admin/password")


def test_missing_item_not_found(stub: StubBw) -> None:
    with pytest.raises(SecretNotFoundError):
        make().get_secret("Nope/password")
    with pytest.raises(SecretNotFoundError):
        make().get_secret("99999999-9999-4999-8999-999999999999/password")


def test_ambiguous_name_names_the_count(stub: StubBw) -> None:
    with pytest.raises(SecretBackendError, match="2 items"):
        make().get_secret("Twin/password")


def test_missing_and_duplicate_fields_and_empty_value(stub: StubBw) -> None:
    with pytest.raises(SecretNotFoundError, match="no field"):
        make().get_secret("Router Admin/nothing")
    with pytest.raises(SecretBackendError, match="2 custom fields"):
        make().get_secret("Router Admin/dup")
    with pytest.raises(SecretNotFoundError):
        make().get_secret("Empty/password")
    with pytest.raises(SecretNotFoundError):
        make().get_secret("Elsewhere/uri")


def test_key_without_field_rejected(stub: StubBw) -> None:
    with pytest.raises(SecretBackendError, match="<item>/<field>"):
        make().get_secret("Router Admin")


def test_list_secrets_returns_names_only(stub: StubBw) -> None:
    names = make(organization=ORG_ID).list_secrets()
    assert "Router Admin" in names
    assert "Elsewhere" not in names
    assert FIXTURE_VALUE not in " ".join(names)
    assert make().list_secrets("Router") == ["Router Admin", "Router Admin Backup"]


def test_health_check(stub: StubBw, monkeypatch: pytest.MonkeyPatch) -> None:
    assert make().health_check() is True
    close_bitwarden_sessions()
    monkeypatch.setenv("PATH", str(stub.log.parent))
    assert make().health_check() is False


def test_missing_bw_binary(stub: StubBw, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    with pytest.raises(SecretBackendError, match="not found on PATH"):
        make().get_secret("Router Admin/password")
    resolver = SecretResolver()
    resolver.configure_backend("bitwarden", {"server": SERVER})
    with pytest.raises(SecretResolutionError, match="not found on PATH"):
        resolver.resolve("secret://bitwarden/Router Admin/password")


@pytest.mark.parametrize(
    ("failing", "key"),
    [
        ("login", "Router Admin/password"),
        ("unlock", "Router Admin/password"),
        ("config", "Router Admin/password"),
        ("list", "Router Admin/password"),
        ("get", f"{ITEM_ID}/password"),
    ],
)
def test_failures_never_leak_credentials_or_values(
    stub: StubBw,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failing: str,
    key: str,
) -> None:
    monkeypatch.setenv("STUB_BW_FAIL", failing)
    caplog.set_level(logging.DEBUG)
    resolver = SecretResolver()
    resolver.configure_backend("bitwarden", {"server": SERVER})
    with pytest.raises(SecretResolutionError) as exc:
        resolver.resolve(f"secret://bitwarden/{key}")
    blob = str(exc.value) + str(exc.value.__cause__) + caplog.text
    for secret in (CLIENT_ID, CLIENT_SECRET, MASTER, "leaked-item-value", "FetchError"):
        assert secret not in blob
    assert f"bw {failing} failed" in str(exc.value)


def test_bw_failure_message_names_only_the_subcommand(
    stub: StubBw, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STUB_BW_FAIL", "get")
    with pytest.raises(SecretBackendError) as exc:
        make().get_secret(f"{ITEM_ID}/password")
    assert str(exc.value) == "bw get failed (exit 1)"


def test_unlock_failure_message_has_no_password(
    stub: StubBw, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STUB_BW_FAIL", "unlock")
    with pytest.raises(SecretBackendError) as exc:
        make().get_secret("Router Admin/password")
    assert MASTER not in str(exc.value)
    assert not Path(stub.calls()[0]["appdir"]).exists()


# -- per-session item cache (#1606) ---------------------------------------------------------


def _argv_count(stub: StubBw, prefix: list[str]) -> int:
    return sum(1 for c in stub.calls() if c["argv"][: len(prefix)] == prefix)


def test_repeated_lookup_runs_list_items_once(stub: StubBw) -> None:
    for _ in range(3):
        assert make().get_secret("Router Admin/password") == FIXTURE_VALUE
    assert make().get_secret("Router Admin/api_key") == "fixture-api-456"
    assert make().get_secret("Router Admin/username") == "admin"
    assert _argv_count(stub, ["list", "items"]) == 1


def test_distinct_items_each_fetched_once(stub: StubBw) -> None:
    for _ in range(2):
        assert make().get_secret("Router Admin/username") == "admin"
        assert make().get_secret("Router Admin Backup/username") == "backup"
        assert make().get_secret("team/shared/db/password") == "slashed"
    assert _argv_count(stub, ["list", "items"]) == 3


def test_uuid_lookup_cached(stub: StubBw) -> None:
    for _ in range(2):
        assert make().get_secret(f"{ITEM_ID}/password") == FIXTURE_VALUE
    assert _argv_count(stub, ["get", "item"]) == 1


def test_not_found_name_is_cached(stub: StubBw) -> None:
    messages = []
    for _ in range(2):
        with pytest.raises(SecretNotFoundError) as exc:
            make().get_secret("Nope/password")
        messages.append(str(exc.value))
    assert messages[0] == messages[1]
    assert _argv_count(stub, ["list", "items"]) == 1


def test_not_found_uuid_and_out_of_scope_cached(stub: StubBw) -> None:
    missing = "99999999-9999-4999-8999-999999999999"
    for _ in range(2):
        with pytest.raises(SecretNotFoundError):
            make().get_secret(f"{missing}/password")
    assert _argv_count(stub, ["get", "item"]) == 1
    close_bitwarden_sessions()
    stub.log.write_text("", encoding="utf-8")
    elsewhere = "66666666-6666-4666-8666-666666666666"
    for _ in range(2):
        with pytest.raises(SecretNotFoundError, match="not found in scope"):
            make(organization=ORG_ID).get_secret(f"{elsewhere}/password")
    assert _argv_count(stub, ["get", "item"]) == 1


def test_transient_failure_not_cached(stub: StubBw, monkeypatch: pytest.MonkeyPatch) -> None:
    assert make().get_secret("Router Admin/username") == "admin"
    monkeypatch.setenv("STUB_BW_FAIL", "list")
    with pytest.raises(SecretBackendError):
        make().get_secret("Router Admin Backup/username")
    monkeypatch.delenv("STUB_BW_FAIL")
    assert make().get_secret("Router Admin Backup/username") == "backup"
    assert _argv_count(stub, ["list", "items"]) == 3


def test_ambiguous_not_cached(stub: StubBw) -> None:
    for _ in range(2):
        with pytest.raises(SecretBackendError, match="2 items"):
            make().get_secret("Twin/password")
    assert _argv_count(stub, ["list", "items"]) == 2


def test_totp_fetched_each_time_item_once(stub: StubBw) -> None:
    make().get_secret("Router Admin/totp")
    make().get_secret("Router Admin/totp")
    assert _argv_count(stub, ["get", "totp"]) == 2
    assert _argv_count(stub, ["list", "items"]) <= 1


def test_close_sessions_clears_cache(stub: StubBw) -> None:
    make().get_secret("Router Admin/password")
    close_bitwarden_sessions()
    make().get_secret("Router Admin/password")
    assert _argv_count(stub, ["list", "items"]) == 2


def test_teardown_clears_item_cache(stub: StubBw) -> None:
    make().get_secret("Router Admin/password")
    (session,) = bitwarden._SESSIONS.values()
    assert session.item_cache
    session.teardown()
    assert session.item_cache == {}


def test_cache_does_not_leak_across_scopes(stub: StubBw) -> None:
    other_col = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    fx = json.loads(stub.fixture.read_text(encoding="utf-8"))
    fx["collections"].append({"id": other_col, "name": "Other"})
    for item_id, col, pw in (
        ("88888888-8888-4888-8888-888888888888", COL_ID, "in-automation"),
        ("99999999-9999-4999-8999-999999999999", other_col, "in-other"),
    ):
        fx["items"].append(
            {
                "id": item_id,
                "name": "Shared Name",
                "organizationId": ORG_ID,
                "collectionIds": [col],
                "login": {"password": pw},
            }
        )
    stub.fixture.write_text(json.dumps(fx), encoding="utf-8")
    other = make(organization="Example Org", collection="Other")
    assert other.get_secret("Shared Name/password") == "in-other"
    automation = make(organization="Example Org", collection="Automation")
    assert automation.get_secret("Shared Name/password") == "in-automation"
    assert _argv_count(stub, ["list", "items"]) == 2


def test_concurrent_lookups_fetch_once(stub: StubBw) -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: make().get_secret("Router Admin/password"), range(8)))
    assert results == [FIXTURE_VALUE] * 8
    assert _argv_count(stub, ["list", "items"]) == 1


def test_cached_values_not_logged(stub: StubBw, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    for _ in range(3):
        make().get_secret("Router Admin/password")
        make().get_secret("Router Admin/api_key")
    assert FIXTURE_VALUE not in caplog.text
    assert "fixture-api-456" not in caplog.text


class TestCredentialUris:
    def test_env_defaults(self, stub: StubBw) -> None:
        make().get_secret("Router Admin/password")
        login = next(c for c in stub.calls() if c["argv"][0] == "login")
        assert login["env"]["BW_CLIENTID"] == CLIENT_ID

    def test_env_secrets_uris(self, stub: StubBw, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in ("BW_CLIENTID", "BW_CLIENTSECRET", "BW_PASSWORD"):
            monkeypatch.delenv(name)
        backend = make(
            client_id="secret://env_secrets/bw/id",
            client_secret="secret://env_secrets/bw/secret",
            master_password="secret://env_secrets/bw/master",
            env_secrets={"bw": {"id": "from-sops-id", "secret": "from-sops-sec", "master": "m"}},
        )
        backend.get_secret("Router Admin/password")
        login = next(c for c in stub.calls() if c["argv"][0] == "login")
        assert login["env"]["BW_CLIENTID"] == "from-sops-id"
        assert login["env"]["BW_CLIENTSECRET"] == "from-sops-sec"

    def test_vault_credential_rejected(self, stub: StubBw) -> None:
        with pytest.raises(SecretBackendError, match="env or env_secrets"):
            make(master_password="secret://bitwarden/other/password")

    def test_non_uri_credential_rejected(self, stub: StubBw) -> None:
        with pytest.raises(SecretBackendError, match="secret:// URI"):
            make(client_id="plain-text")

    def test_missing_credential_names_no_value(
        self, stub: StubBw, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BW_PASSWORD")
        with pytest.raises(SecretBackendError) as exc:
            make()
        assert "master_password" in str(exc.value)
        assert MASTER not in str(exc.value)
        assert stub.calls() == []


def test_register_metadata() -> None:
    meta = register()
    assert meta.name == "bitwarden"
    assert meta.read_only is True


def test_resolver_finds_plugin_through_entry_point(stub: StubBw) -> None:
    resolver = SecretResolver()
    resolver.configure_backend("bitwarden", {"server": SERVER})
    assert resolver.resolve("secret://bitwarden/Router Admin/password") == FIXTURE_VALUE
    resolver.close()
    # Closing the resolver does not log out: the session lives for the process.
    assert "logout" not in stub.subcommands()


# -- persisted device identity (#1604) -------------------------------------------------------

_APP_ID_KEY = "global_applicationId_appId"
_STORED_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


def _app_ids(stub: StubBw, sub: str = "login") -> list[str]:
    return [c["app_id"] for c in stub.calls() if c["argv"][0] == sub]


def _state_home() -> Path:
    return Path(os.environ["INFRAFOUNDRY_STATE_HOME"])


def _default_file(server: str = SERVER) -> Path:
    return Path(bitwarden._default_device_id_file(server))


def _fresh_dir(tmp_path: Path, content: Any = None) -> Path:
    app_dir = tmp_path / "appdir"
    app_dir.mkdir(exist_ok=True)
    if content is not None:
        (app_dir / "data.json").write_text(
            content if isinstance(content, str) else json.dumps(content), encoding="utf-8"
        )
    return app_dir


def test_two_sessions_present_same_app_id(stub: StubBw) -> None:
    make().get_secret("Router Admin/password")
    close_bitwarden_sessions()
    first_mtime = _default_file().stat().st_mtime_ns
    make().get_secret("Router Admin/password")
    ids = _app_ids(stub)
    assert len(ids) == 2
    assert ids[0] == ids[1]
    assert _default_file().read_text(encoding="utf-8").strip() == ids[0]
    assert _default_file().stat().st_mtime_ns == first_mtime


def test_first_run_creates_private_file_holding_bw_id(stub: StubBw) -> None:
    make().get_secret("Router Admin/password")
    path = _default_file()
    assert path.read_text(encoding="utf-8").strip() == _app_ids(stub)[0]
    assert (path.stat().st_mode & 0o777) == 0o600
    assert (path.parent.stat().st_mode & 0o777) == 0o700
    assert (path.parent.parent.stat().st_mode & 0o777) == 0o700
    assert path.is_relative_to(_state_home())


def test_existing_valid_file_seeds_data_json_before_login(stub: StubBw) -> None:
    path = _default_file()
    path.parent.mkdir(parents=True, mode=0o700)
    path.write_text(_STORED_ID + "\n", encoding="utf-8")
    path.chmod(0o600)
    make().get_secret("Router Admin/password")
    assert _app_ids(stub, "config")[0] != _STORED_ID  # bw generated its own before seeding
    assert _app_ids(stub) == [_STORED_ID]
    assert path.read_text(encoding="utf-8").strip() == _STORED_ID


def test_non_uuid_stored_id_is_ignored(stub: StubBw) -> None:
    path = _default_file()
    path.parent.mkdir(parents=True, mode=0o700)
    path.write_text("not-a-uuid\n", encoding="utf-8")
    path.chmod(0o600)
    assert make().get_secret("Router Admin/password") == FIXTURE_VALUE
    assert _app_ids(stub)[0] != "not-a-uuid"
    assert path.read_text(encoding="utf-8") == "not-a-uuid\n"


@pytest.mark.parametrize(
    "content", [None, "not json", "[1, 2]", {"other": "x"}, {_APP_ID_KEY: "nope"}, {_APP_ID_KEY: 3}]
)
def test_bad_data_json_falls_back(tmp_path: Path, content: Any) -> None:
    app_dir = _fresh_dir(tmp_path, content)
    target = tmp_path / "ids" / "app-id"
    bitwarden._seed_app_id(str(app_dir), str(target), SERVER)
    assert not target.exists()
    if content is not None:
        assert (app_dir / "data.json").read_text(encoding="utf-8") == (
            content if isinstance(content, str) else json.dumps(content)
        )


def test_different_servers_get_different_files(stub: StubBw) -> None:
    make().get_secret("Router Admin/password")
    close_bitwarden_sessions()
    make(server="https://other.example.net").get_secret("Router Admin/password")
    a, b = _default_file(SERVER), _default_file("https://other.example.net")
    assert a != b
    assert a.read_text(encoding="utf-8") != b.read_text(encoding="utf-8")


def test_device_id_file_setting_overrides_path(stub: StubBw, tmp_path: Path) -> None:
    target = tmp_path / "custom" / "device"
    make(device_id_file=str(target)).get_secret("Router Admin/password")
    assert target.read_text(encoding="utf-8").strip() == _app_ids(stub)[0]
    assert not _default_file().exists()


def test_relative_device_id_file_rejected() -> None:
    with pytest.raises(SecretBackendError, match="absolute"):
        BitwardenSecretBackend({"server": SERVER, "device_id_file": "rel/path"})


def test_tilde_device_id_file_expands(stub: StubBw, monkeypatch: pytest.MonkeyPatch) -> None:
    home = Path(os.environ["INFRAFOUNDRY_STATE_HOME"]) / "fakehome"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    make(device_id_file="~/dev-id").get_secret("Router Admin/password")
    assert (home / "dev-id").is_file()


def test_tempdir_removed_and_lock_logout_still_run(stub: StubBw) -> None:
    make().get_secret("Router Admin/password")
    appdir = Path(stub.calls()[0]["appdir"])
    close_bitwarden_sessions()
    assert stub.subcommands()[-2:] == ["lock", "logout"]
    assert not appdir.exists()
    assert _default_file().is_file()


def test_no_debug_log_contains_app_id(
    stub: StubBw, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    caplog.set_level(logging.DEBUG)
    make().get_secret("Router Admin/password")
    close_bitwarden_sessions()
    make().get_secret("Router Admin/password")
    bad = tmp_path / "bad"
    bad.write_text(_STORED_ID, encoding="utf-8")
    bad.chmod(0o666)
    bitwarden._seed_app_id(str(_fresh_dir(tmp_path, {_APP_ID_KEY: _STORED_ID})), str(bad), SERVER)
    for app_id in (*_app_ids(stub), _STORED_ID):
        assert app_id not in caplog.text


def test_race_stored_id_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    generated = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    app_dir = _fresh_dir(tmp_path, {_APP_ID_KEY: generated})
    target = tmp_path / "ids" / "app-id"
    real_read = bitwarden._read_stored_app_id
    calls = {"n": 0}

    def racing_read(path: Path) -> tuple[str, str | None]:
        calls["n"] += 1
        result = real_read(path)
        if calls["n"] == 1:  # another process creates the file after our "missing" check
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_STORED_ID + "\n", encoding="utf-8")
            path.chmod(0o600)
        return result

    monkeypatch.setattr(bitwarden, "_read_stored_app_id", racing_read)
    bitwarden._seed_app_id(str(app_dir), str(target), SERVER)
    assert json.loads((app_dir / "data.json").read_text(encoding="utf-8"))[_APP_ID_KEY] == (
        _STORED_ID
    )
    assert target.read_text(encoding="utf-8").strip() == _STORED_ID


@pytest.mark.parametrize("mode", [0o620, 0o602, 0o666])
def test_writable_app_id_file_ignored(tmp_path: Path, mode: int) -> None:
    app_dir = _fresh_dir(tmp_path, {_APP_ID_KEY: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"})
    target = tmp_path / "app-id"
    target.write_text(_STORED_ID, encoding="utf-8")
    target.chmod(mode)
    bitwarden._seed_app_id(str(app_dir), str(target), SERVER)
    data = json.loads((app_dir / "data.json").read_text(encoding="utf-8"))
    assert data[_APP_ID_KEY] == "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"


def test_symlinked_app_id_file_ignored(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.write_text(_STORED_ID, encoding="utf-8")
    real.chmod(0o600)
    link = tmp_path / "app-id"
    link.symlink_to(real)
    app_dir = _fresh_dir(tmp_path, {_APP_ID_KEY: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"})
    bitwarden._seed_app_id(str(app_dir), str(link), SERVER)
    data = json.loads((app_dir / "data.json").read_text(encoding="utf-8"))
    assert data[_APP_ID_KEY] == "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"


@pytest.mark.skipif(os.getuid() == 0, reason="root ignores directory permissions")
def test_unwritable_app_id_dir_falls_back(stub: StubBw, tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        backend = make(device_id_file=str(locked / "sub" / "app-id"))
        assert backend.get_secret("Router Admin/password") == FIXTURE_VALUE
    finally:
        locked.chmod(0o700)
    assert not (locked / "sub").exists()


def test_seeded_data_json_stays_private(tmp_path: Path) -> None:
    app_dir = _fresh_dir(tmp_path, {_APP_ID_KEY: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", "k": 1})
    target = tmp_path / "app-id"
    target.write_text(_STORED_ID, encoding="utf-8")
    target.chmod(0o600)
    bitwarden._seed_app_id(str(app_dir), str(target), SERVER)
    data_path = app_dir / "data.json"
    assert json.loads(data_path.read_text(encoding="utf-8")) == {_APP_ID_KEY: _STORED_ID, "k": 1}
    assert (data_path.stat().st_mode & 0o777) == 0o600
    assert [p.name for p in app_dir.iterdir()] == ["data.json"]
