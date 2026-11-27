"""Atomic writes into encrypted ``secrets.yaml`` files."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from infrafoundry.core.certs.models import CertificateStoreError
from infrafoundry.core.certs.store import SecretsWriter, temp_path

from .fakes import FakeRun, FakeSopsRun, have_tool

pytestmark = pytest.mark.unit

SENTINEL = "-----BEGIN " + "PRIVATE KEY-----\nSENTINEL-NOT-A-REAL-KEY\n"


def test_the_value_goes_to_sops_on_stdin_and_the_copy_replaces_the_file(tmp_path: Path) -> None:
    path = tmp_path / "secrets.yaml"
    path.write_text("{}")
    run = FakeSopsRun()
    SecretsWriter(run).write_value(
        path, ("variables", "acme_certificates", "proxy-cert"), {"key_pem": SENTINEL}
    )
    argv, kwargs = run.calls[0]
    assert argv[:3] == ["sops", "set", "--value-stdin"]
    assert argv[3] == str(temp_path(path))
    assert argv[4] == '["variables"]["acme_certificates"]["proxy-cert"]'
    assert "SENTINEL" not in " ".join(argv)
    assert json.loads(kwargs["input"]) == {"key_pem": SENTINEL}
    assert json.loads(path.read_text())["variables"]["acme_certificates"]["proxy-cert"] == {
        "key_pem": SENTINEL
    }
    assert not temp_path(path).exists()


def test_a_failed_write_leaves_the_original_untouched_and_removes_the_copy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "secrets.yaml"
    path.write_text("original")
    run = FakeRun(returncode=1, stderr="sops: could not encrypt\n")
    with pytest.raises(CertificateStoreError, match=r"exit 1\): sops: could not encrypt"):
        SecretsWriter(run).write_value(path, ("a", "b"), {"v": SENTINEL})
    assert path.read_text() == "original"
    assert list(tmp_path.iterdir()) == [path]


def test_errors_never_carry_the_value(tmp_path: Path) -> None:
    path = tmp_path / "secrets.yaml"
    path.write_text("x")
    run = FakeRun(returncode=1, stderr="failed\n")
    with pytest.raises(CertificateStoreError) as caught:
        SecretsWriter(run).write_value(path, ("a",), {"v": SENTINEL})
    assert "SENTINEL" not in str(caught.value)
    run.raises = subprocess.TimeoutExpired("sops", 60)
    with pytest.raises(CertificateStoreError, match="timed out") as timed:
        SecretsWriter(run).write_value(path, ("a",), {"v": SENTINEL})
    assert "SENTINEL" not in str(timed.value)


@pytest.mark.parametrize("keys", [(), ("a b",), ('a"]["b',), ("a/b",)])
def test_keys_must_be_plain_identifiers(tmp_path: Path, keys: tuple[str, ...]) -> None:
    path = tmp_path / "secrets.yaml"
    path.write_text("x")
    run = FakeRun()
    with pytest.raises(CertificateStoreError):
        SecretsWriter(run).write_value(path, keys, {})
    assert run.calls == []


def test_a_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(CertificateStoreError, match="does not exist"):
        SecretsWriter(FakeRun()).write_value(tmp_path / "nope.yaml", ("a",), {})


def test_ensure_file_passes_the_initial_content_and_wraps_errors(tmp_path: Path) -> None:
    path = tmp_path / "env" / "secrets.yaml"
    run = FakeRun(stdout="encrypted: true\n")
    SecretsWriter(run).ensure_file(path, tmp_path, "acme: {}\n")
    assert run.calls[0][1]["input"] == "acme: {}\n"
    assert path.read_text() == "encrypted: true\n"
    failing = FakeRun(returncode=1, stderr="no creation rule\n")
    with pytest.raises(CertificateStoreError, match="no creation rule"):
        SecretsWriter(failing).ensure_file(tmp_path / "other.yaml", tmp_path, "acme: {}\n")


@pytest.mark.skipif(
    not (have_tool("sops") and have_tool("age-keygen")), reason="sops and age are not installed"
)
def test_with_real_sops_the_file_stays_encrypted_and_round_trips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key_file = tmp_path / "age.key"
    generated = subprocess.run(
        ["age-keygen", "-o", str(key_file)], capture_output=True, text=True, check=True
    )
    recipient = next(
        line.split()[-1]
        for line in (generated.stderr + generated.stdout).splitlines()
        if line.startswith("Public key:")
    )
    (tmp_path / ".sops.yaml").write_text(
        yaml.safe_dump({"creation_rules": [{"path_regex": ".*", "age": recipient}]})
    )
    monkeypatch.setenv("SOPS_AGE_KEY_FILE", str(key_file))
    path = tmp_path / "pkg" / "secrets.yaml"
    writer = SecretsWriter()
    writer.ensure_file(path, tmp_path, "variables: {}\n")
    writer.write_value(
        path, ("variables", "acme_certificates", "proxy-cert"), {"key_pem": SENTINEL}
    )

    on_disk = path.read_text()
    assert "SENTINEL" not in on_disk
    assert "ENC[AES256_GCM" in on_disk
    assert not temp_path(path).exists()
    plain = subprocess.run(
        ["sops", "--decrypt", str(path)], capture_output=True, text=True, check=True
    ).stdout
    stored = yaml.safe_load(plain)["variables"]["acme_certificates"]["proxy-cert"]
    assert stored == {"key_pem": SENTINEL}
