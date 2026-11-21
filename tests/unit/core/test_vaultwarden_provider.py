"""Tests for VaultwardenProvider keeping the master password off the bw command line."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from infrafoundry.core.exceptions import SecretError, SecretNotFoundError
from infrafoundry.core.secrets.providers.vaultwarden import VaultwardenProvider

FIXTURE_VALUE = "fixture-value-123"  # test fixture, not a real credential

STUB = """#!/usr/bin/env python3
import json, os, sys
log = os.environ["BW_STUB_LOG"]
with open(log, "a") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "env_set": "BW_PASSWORD" in os.environ}) + "\\n")
cmd = sys.argv[1]
if cmd == "status":
    print(json.dumps({"status": "locked"}))
elif cmd == "unlock":
    print("session-key-abc")
elif cmd == "get":
    sys.stderr.write("Not found.")
    sys.exit(1)
"""


@pytest.fixture
def stub_bw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put a stub bw on PATH that logs argv and env presence."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    bw = bin_dir / "bw"
    bw.write_text(STUB, encoding="utf-8")
    bw.chmod(bw.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("BW_STUB_LOG", str(log))
    monkeypatch.setenv("BW_PASSWORD", FIXTURE_VALUE)
    # Register BW_SESSION with monkeypatch so the provider's os.environ write is undone.
    monkeypatch.setenv("BW_SESSION", "placeholder")
    monkeypatch.delenv("BW_SESSION")
    monkeypatch.delenv("CI", raising=False)
    return log


def _calls(log: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_unlock_uses_passwordenv_and_takes_session_key(stub_bw: Path) -> None:
    provider = VaultwardenProvider()
    assert provider.session_key == "session-key-abc"

    calls = _calls(stub_bw)
    unlock = next(c for c in calls if c["argv"][0] == "unlock")  # type: ignore[index]
    assert unlock["argv"] == ["unlock", "--passwordenv", "BW_PASSWORD", "--raw", "--nointeraction"]
    assert unlock["env_set"] is True


def test_password_never_in_any_argv(stub_bw: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    VaultwardenProvider()
    for call in _calls(stub_bw):
        assert FIXTURE_VALUE not in " ".join(call["argv"])  # type: ignore[arg-type]


def test_not_found_error_has_no_args(stub_bw: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = VaultwardenProvider(session_key="preset")
    with pytest.raises(SecretNotFoundError) as exc:
        provider._run_bw(["get", "item", FIXTURE_VALUE])
    assert FIXTURE_VALUE not in str(exc.value)


def test_unlock_failure_message_has_no_password(
    stub_bw: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bw = stub_bw.parent / "bin" / "bw"
    bw.write_text("#!/bin/sh\necho boom >&2\nexit 1\n", encoding="utf-8")
    with pytest.raises(SecretError) as exc:
        VaultwardenProvider()
    assert FIXTURE_VALUE not in str(exc.value)
