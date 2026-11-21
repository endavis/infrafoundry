"""Tests for the shared strict SSH host-key options and failure hint (#1588)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from infrafoundry.core.ssh_host_keys import known_hosts_for
from infrafoundry.core.ssh_options import (
    STRICT_HOST_KEY_ARGS,
    STRICT_HOST_KEY_OPTS,
    host_key_hint,
)

_SRC = Path(__file__).resolve().parents[3] / "src" / "infrafoundry"
_FORBIDDEN = (
    "StrictHostKeyChecking=no",
    "UserKnownHostsFile=/dev/null",
    "host_key_checking = False",
)


def test_option_forms_agree() -> None:
    assert STRICT_HOST_KEY_OPTS == "-o StrictHostKeyChecking=yes"
    assert " ".join(STRICT_HOST_KEY_ARGS) == STRICT_HOST_KEY_OPTS


class TestHostKeyHint:
    def test_unknown_key(self) -> None:
        output = (
            "No ED25519 host key is known for 192.0.2.10 and you have requested strict "
            "checking.\nHost key verification failed.\n"
        )

        hint = host_key_hint(output)

        assert hint is not None
        assert "192.0.2.10" in hint
        assert "ssh-keyscan -t ed25519 192.0.2.10" in hint
        assert "ssh-keygen -R" not in hint

    def test_changed_key_mentions_removal(self) -> None:
        output = (
            "@@@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED! @@@\n"
            "Host key for fw-test.example.com has changed and you have requested strict "
            "checking.\nHost key verification failed.\n"
        )

        hint = host_key_hint(output)

        assert hint is not None
        # A word-bounded regex, not `in`: CodeQL reads a hostname substring check
        # as URL sanitization; this only checks the hint names the host.
        assert re.search(r"\bfw-test\.example\.com\b", hint)
        assert re.search(r"ssh-keygen -R fw-test\.example\.com\b", hint)
        assert "ssh-keyscan" in hint

    def test_bare_failure_uses_the_host_fallback(self) -> None:
        hint = host_key_hint("Host key verification failed.", "jump.example.com")

        assert hint is not None
        assert re.search(r"\bjump\.example\.com\b", hint)

    def test_bare_failure_without_host(self) -> None:
        hint = host_key_hint("Host key verification failed.")

        assert hint is not None
        assert "the host" in hint

    @pytest.mark.parametrize("output", ["Permission denied (publickey).", ""])
    def test_other_errors_give_none(self, output: str) -> None:
        assert host_key_hint(output, "h") is None


class TestKnownHostsFor:
    def test_exact_name(self) -> None:
        assert known_hosts_for("vm1 ssh-ed25519 AAAA", "vm1") == ("vm1 ssh-ed25519 AAAA",)

    def test_name_and_address(self) -> None:
        value = "vm1,192.0.2.5 ssh-ed25519 AAAA;vm2 ssh-ed25519 BBBB"

        assert known_hosts_for(value, "vm1") == ("vm1,192.0.2.5 ssh-ed25519 AAAA",)

    def test_no_match(self) -> None:
        assert known_hosts_for("vm10 ssh-ed25519 AAAA", "vm1") == ()

    def test_empty(self) -> None:
        assert known_hosts_for("", "vm1") == ()


def test_no_source_disables_host_key_checking() -> None:
    offenders = [
        f"{path.relative_to(_SRC)}: {text}"
        for path in _SRC.rglob("*")
        if path.is_file() and path.suffix in {".py", ".j2", ".sh", ".cfg"}
        for text in _FORBIDDEN
        if text in path.read_text(encoding="utf-8", errors="ignore")
    ]

    assert offenders == []
