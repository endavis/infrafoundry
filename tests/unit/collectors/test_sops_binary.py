"""Tests for the binary SOPS helpers."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from infrafoundry.core.config.sops import (
    SopsCreationRuleError,
    SopsError,
    decrypt_binary,
    encrypt_binary,
)


def _fake(
    returncode: int = 0, stdout: bytes = b"out", stderr: bytes = b""
) -> tuple[Callable[..., Any], list[tuple[list[str], dict[str, Any]]]]:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def run(argv: list[str], **kw: Any) -> SimpleNamespace:
        calls.append((argv, kw))
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    return run, calls


@patch("infrafoundry.core.config.sops.shutil.which", return_value="/usr/bin/sops")
def test_encrypt_argv(_w: object, tmp_path: Path) -> None:
    run, calls = _fake()
    out = encrypt_binary(tmp_path / "p", tmp_path / "final.sops.json", cwd=tmp_path, run=run)
    assert out == b"out"
    argv, kw = calls[0]
    assert argv == [
        "/usr/bin/sops", "encrypt", "--input-type", "binary", "--output-type", "json",
        "--filename-override", str(tmp_path / "final.sops.json"), str(tmp_path / "p"),
    ]  # fmt: skip
    assert kw["cwd"] == str(tmp_path)


@patch("infrafoundry.core.config.sops.shutil.which", return_value="/usr/bin/sops")
def test_decrypt_argv(_w: object, tmp_path: Path) -> None:
    run, calls = _fake()
    decrypt_binary(tmp_path / "f", cwd=tmp_path, run=run)
    assert calls[0][0] == [
        "/usr/bin/sops", "decrypt", "--input-type", "json", "--output-type", "binary",
        str(tmp_path / "f"),
    ]  # fmt: skip


@patch("infrafoundry.core.config.sops.shutil.which", return_value="/usr/bin/sops")
def test_no_creation_rule(_w: object, tmp_path: Path) -> None:
    run, _ = _fake(1, stderr=b"error: no matching creation rules found")
    with pytest.raises(SopsCreationRuleError, match=r"final\.sops\.json"):
        encrypt_binary(tmp_path / "p", tmp_path / "final.sops.json", cwd=tmp_path, run=run)


@patch("infrafoundry.core.config.sops.shutil.which", return_value="/usr/bin/sops")
def test_failure_has_no_stderr(_w: object, tmp_path: Path) -> None:
    run, _ = _fake(2, stderr=b"CANARY-LEAK")
    with pytest.raises(SopsError) as info:
        decrypt_binary(tmp_path / "f", cwd=tmp_path, run=run)
    assert "CANARY" not in str(info.value)


@patch("infrafoundry.core.config.sops.shutil.which", return_value=None)
def test_missing_binary(_w: object, tmp_path: Path) -> None:
    with pytest.raises(SopsError, match="not found"):
        decrypt_binary(tmp_path / "f", cwd=tmp_path)


@pytest.mark.skipif(
    not (shutil.which("sops") and shutil.which("age-keygen")), reason="sops/age not installed"
)
def test_real_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = tmp_path / "key.txt"
    gen = subprocess.run(["age-keygen", "-o", str(key)], capture_output=True, text=True)
    pub = (gen.stderr + gen.stdout).split("Public key:")[1].split()[0]
    (tmp_path / ".sops.yaml").write_text(
        f"creation_rules:\n  - path_regex: .*\\.sops\\.json$\n    age: {pub}\n"
    )
    monkeypatch.setenv("SOPS_AGE_KEY_FILE", str(key))
    plain = tmp_path / "plain.bin"
    plain.write_bytes(b"CANARY-SECRET\n")
    final = tmp_path / "x.sops.json"
    final.write_bytes(encrypt_binary(plain, final, cwd=tmp_path))
    assert b"CANARY" not in final.read_bytes()
    assert decrypt_binary(final, cwd=tmp_path) == b"CANARY-SECRET\n"
