"""A stub ``bw`` executable and fixtures shared by the bitwarden backend tests.

The stub is a Python script placed on ``PATH``. It logs each call (argv, the ``BW_*`` and
app-data variables it received, and the ``global_applicationId_appId`` read from ``data.json``) to
a JSONL file and keeps its own server/login state in the ``BITWARDENCLI_APPDATA_DIR`` it is
given, like the real ``bw``. Its behaviour is driven by variables that do not start with
``BW_`` (the backend strips those): ``STUB_BW_LOG``, ``STUB_BW_FIXTURE`` and ``STUB_BW_FAIL``.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

FIXTURE_VALUE = "fixture-value-123"  # test fixture, not a real credential
CLIENT_ID = "fixture-client-id"
CLIENT_SECRET = "fixture-client-secret"  # test fixture, not a real credential
MASTER = "fixture-master-pw"  # test fixture, not a real credential
SERVER = "https://vault.example.com"
ORG_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
COL_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
ITEM_ID = "11111111-1111-4111-8111-111111111111"
OTHER_ORG_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

STUB = """#!/usr/bin/env python3
import json, os, sys, uuid
argv = [a for a in sys.argv[1:] if a != "--nointeraction"]
appdir = os.environ.get("BITWARDENCLI_APPDATA_DIR")
env_keys = ("BW_CLIENTID", "BW_CLIENTSECRET", "BW_PASSWORD", "BW_SESSION", "BW_SERVER")
data_path = os.path.join(appdir, "data.json") if appdir else None
if data_path and not os.path.exists(data_path):
    # Like real bw: the first command creates data.json with a fresh random app id.
    with open(data_path, "w") as f:
        json.dump({"global_applicationId_appId": str(uuid.uuid4())}, f)
app_id = None
if data_path:
    try:
        app_id = json.load(open(data_path)).get("global_applicationId_appId")
    except (OSError, ValueError, AttributeError):
        app_id = None
rec = {
    "app_id": app_id,
    "argv": sys.argv[1:],
    "appdir": appdir,
    "appdir_mode": (
        oct(os.stat(appdir).st_mode & 0o777) if appdir and os.path.isdir(appdir) else None
    ),
    "env": {k: os.environ.get(k) for k in env_keys},
}
with open(os.environ["STUB_BW_LOG"], "a") as f:
    f.write(json.dumps(rec) + "\\n")
if os.environ.get("STUB_BW_FAIL") == argv[0]:
    fx = json.load(open(os.environ["STUB_BW_FIXTURE"]))
    sys.stderr.write("FetchError secrets: " + " ".join(
        str(os.environ.get(k)) for k in env_keys) + " " + fx["leak"] + "\\n")
    sys.exit(1)
state_path = os.path.join(appdir, "stub-state.json") if appdir else None
state = {"server": None, "status": "unauthenticated"}
if state_path and os.path.exists(state_path):
    state = json.load(open(state_path))
def save():
    json.dump(state, open(state_path, "w"))
fx = json.load(open(os.environ["STUB_BW_FIXTURE"]))
cmd = argv[0]
if cmd == "config":
    state["server"] = argv[2]; save(); print("Saved setting `config`.")
elif cmd == "status":
    print(json.dumps({"serverUrl": state["server"], "lastSync": None, "status": state["status"]}))
elif cmd == "login":
    if not os.environ.get("BW_CLIENTID") or not os.environ.get("BW_CLIENTSECRET"):
        sys.exit(1)
    state["status"] = "locked"; save(); print("You are logged in!")
elif cmd == "unlock":
    ok = argv == ["unlock", "--passwordenv", "BW_PASSWORD", "--raw"]
    if not ok or not os.environ.get("BW_PASSWORD"):
        sys.exit(1)
    state["status"] = "unlocked"; save(); print("session-key-abc")
elif cmd in ("lock", "logout"):
    state["status"] = "locked" if cmd == "lock" else "unauthenticated"; save()
elif os.environ.get("BW_SESSION") != "session-key-abc":
    sys.stderr.write("You are not logged in.\\n"); sys.exit(1)
elif cmd == "sync":
    print("Syncing complete.")
elif cmd == "list" and argv[1] == "organizations":
    print(json.dumps(fx["organizations"]))
elif cmd == "list" and argv[1] == "collections":
    print(json.dumps(fx["collections"]))
elif cmd == "list":
    def opt(name):
        return argv[argv.index(name) + 1] if name in argv else None
    items = fx["items"]
    if opt("--search"):
        items = [i for i in items if opt("--search").lower() in i["name"].lower()]
    # Like bw 2026.10.1: --collectionid is ignored when --organizationid is also given.
    if opt("--organizationid"):
        items = [i for i in items if i.get("organizationId") == opt("--organizationid")]
    elif opt("--collectionid"):
        items = [i for i in items if opt("--collectionid") in (i.get("collectionIds") or [])]
    print(json.dumps(items))
elif cmd == "get" and argv[1] == "item":
    found = [i for i in fx["items"] if i["id"] == argv[2]]
    if not found:
        sys.stderr.write("Not found.\\n"); sys.exit(1)
    print(json.dumps(found[0]))
elif cmd == "get" and argv[1] == "totp":
    print("123456")
else:
    sys.exit(2)
"""


def _items() -> list[dict[str, Any]]:
    return [
        {
            "id": ITEM_ID,
            "name": "Router Admin",
            "organizationId": ORG_ID,
            "collectionIds": [COL_ID],
            "notes": "note text",
            "login": {
                "username": "admin",
                "password": FIXTURE_VALUE,
                "uris": [
                    {"uri": "https://first.example.com"},
                    {"uri": "https://second.example.com"},
                ],
            },
            "fields": [
                {"name": "api_key", "value": "fixture-api-456", "type": 1},
                {"name": "password", "value": "custom-shadow", "type": 0},
                {"name": "dup", "value": "one", "type": 0},
                {"name": "dup", "value": "two", "type": 0},
            ],
        },
        {
            "id": "22222222-2222-4222-8222-222222222222",
            "name": "Router Admin Backup",
            "organizationId": ORG_ID,
            "collectionIds": [COL_ID],
            "login": {"username": "backup", "password": "fixture-backup-789"},
        },
        {
            "id": "33333333-3333-4333-8333-333333333333",
            "name": "Twin",
            "organizationId": ORG_ID,
            "collectionIds": [COL_ID],
            "login": {"password": "a"},
        },
        {
            "id": "44444444-4444-4444-8444-444444444444",
            "name": "Twin",
            "organizationId": ORG_ID,
            "collectionIds": [COL_ID],
            "login": {"password": "b"},
        },
        {
            "id": "55555555-5555-4555-8555-555555555555",
            "name": "Empty",
            "organizationId": ORG_ID,
            "collectionIds": [COL_ID],
            "login": {"username": "u", "password": None},
        },
        {
            "id": "66666666-6666-4666-8666-666666666666",
            "name": "Elsewhere",
            "organizationId": OTHER_ORG_ID,
            "collectionIds": [],
            "login": {"password": "outside"},
        },
        {
            "id": "77777777-7777-4777-8777-777777777777",
            "name": "team/shared/db",
            "organizationId": ORG_ID,
            "collectionIds": [COL_ID],
            "login": {"password": "slashed"},
        },
    ]


class StubBw:
    """Handle on the installed stub: its call log and fixture."""

    def __init__(self, log: Path, fixture: Path) -> None:
        self.log = log
        self.fixture = fixture

    def calls(self) -> list[dict[str, Any]]:
        """Return every logged call, in order."""
        if not self.log.exists():
            return []
        return [json.loads(ln) for ln in self.log.read_text(encoding="utf-8").splitlines()]

    def subcommands(self) -> list[str]:
        """Return the first argv word of every call."""
        return [c["argv"][0] for c in self.calls()]


def install_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StubBw:
    """Install the stub on ``PATH`` and set the bootstrap credentials in the environment."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    bw = bin_dir / "bw"
    bw.write_text(STUB, encoding="utf-8")
    bw.chmod(bw.stat().st_mode | stat.S_IEXEC)
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "items": _items(),
                "organizations": [{"id": ORG_ID, "name": "Example Org"}],
                "collections": [{"id": COL_ID, "name": "Automation"}],
                "leak": "leaked-item-value",
            }
        ),
        encoding="utf-8",
    )
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("STUB_BW_LOG", str(log))
    monkeypatch.setenv("STUB_BW_FIXTURE", str(fixture))
    monkeypatch.delenv("STUB_BW_FAIL", raising=False)
    monkeypatch.setenv("BW_CLIENTID", CLIENT_ID)
    monkeypatch.setenv("BW_CLIENTSECRET", CLIENT_SECRET)
    monkeypatch.setenv("BW_PASSWORD", MASTER)
    monkeypatch.setenv("BW_SESSION", "inherited-session")
    monkeypatch.setenv("BITWARDENCLI_APPDATA_DIR", str(tmp_path / "operator-bw"))
    return StubBw(log, fixture)
