"""Tests for the artifact store."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrafoundry.collectors.base import Artifact, CollectorError
from infrafoundry.collectors.store import ArtifactStore

from .conftest import ReversibleFakeEncryptor

SECRET = Artifact("config.xml", b"<?xml?>CANARY-PSK-0001", secret_bearing=True)
PLAIN = Artifact("ip-route.txt", b"default via 198.51.100.1\n")


def test_first_then_identical_run(tmp_path: Path, encryptor: ReversibleFakeEncryptor) -> None:
    store = ArtifactStore(tmp_path, encryptor)
    first = store.store("ont-isp", [SECRET, PLAIN])
    assert {c.status for c in first} == {"new"}
    files = sorted((tmp_path / "ont-isp").iterdir())
    before = {f: (f.read_bytes(), f.stat().st_mtime_ns) for f in files}
    second = store.store("ont-isp", [SECRET, PLAIN])
    assert {c.status for c in second} == {"unchanged"}
    assert before == {f: (f.read_bytes(), f.stat().st_mtime_ns) for f in files}
    assert sorted((tmp_path / "ont-isp").iterdir()) == files  # no .tmp leftovers


def test_changed_only_that_file(tmp_path: Path, encryptor: ReversibleFakeEncryptor) -> None:
    store = ArtifactStore(tmp_path, encryptor)
    store.store("ont-isp", [SECRET, PLAIN])
    new = Artifact("config.xml", b"other CANARY", secret_bearing=True)
    changes = {c.path.name: c.status for c in store.store("ont-isp", [new, PLAIN])}
    assert changes == {"config.xml.sops.json": "changed", "ip-route.txt": "unchanged"}


def test_plaintext_only_in_removed_tempdir(
    tmp_path: Path, encryptor: ReversibleFakeEncryptor
) -> None:
    ArtifactStore(tmp_path, encryptor).store("ont-isp", [SECRET])
    assert encryptor.plaintext_paths and not encryptor.plaintext_paths[0].parent.exists()
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert b"CANARY" not in f.read_bytes() or f.read_bytes().startswith(b"{")
            assert b"CANARY-PSK" not in f.read_bytes()


def test_tempdir_removed_when_encrypt_raises(
    tmp_path: Path, encryptor: ReversibleFakeEncryptor
) -> None:
    encryptor.fail = True
    with pytest.raises(RuntimeError):
        ArtifactStore(tmp_path, encryptor).store("ont-isp", [SECRET])
    assert not list((tmp_path / "ont-isp").iterdir())


def test_previous_unreadable(tmp_path: Path, encryptor: ReversibleFakeEncryptor) -> None:
    (tmp_path / "ont-isp").mkdir()
    (tmp_path / "ont-isp" / "config.xml.sops.json").write_text("garbage")
    changes = ArtifactStore(tmp_path, encryptor).store("ont-isp", [SECRET])
    assert changes[0].status == "changed (previous unreadable)"


def test_plain_written_in_clear(tmp_path: Path, encryptor: ReversibleFakeEncryptor) -> None:
    ArtifactStore(tmp_path, encryptor).store("ont-isp", [PLAIN])
    assert (tmp_path / "ont-isp" / "ip-route.txt").read_bytes() == PLAIN.content


@pytest.mark.parametrize("name", ["../x", "Upper", "a/b"])
def test_bad_device_name(tmp_path: Path, encryptor: ReversibleFakeEncryptor, name: str) -> None:
    with pytest.raises(CollectorError):
        ArtifactStore(tmp_path, encryptor).store(name, [PLAIN])


def test_resalted_ont_export_is_unchanged_but_real_change_is_reported(
    tmp_path: Path, encryptor: ReversibleFakeEncryptor
) -> None:
    from infrafoundry.collectors.huawei_ont_web import mask_salted_values

    def ont(psk: bytes, ssid: bytes) -> Artifact:
        body = b'<?xml?><WLAN SSID="' + ssid + b'" PreSharedKey="' + psk + b'"/>'
        return Artifact("config.xml", body, secret_bearing=True, compare_key=mask_salted_values)

    store = ArtifactStore(tmp_path, encryptor)
    store.store("ont-isp", [ont(b"$2SALT-A-CANARY$", b"lab")])
    final = tmp_path / "ont-isp" / "config.xml.sops.json"
    before = final.read_bytes()
    # Same device, new salt: no change reported, file not rewritten.
    [same] = store.store("ont-isp", [ont(b"$2SALT-B-CANARY$", b"lab")])
    assert same.status == "unchanged"
    assert final.read_bytes() == before
    # A change outside the salted values is still reported.
    [changed] = store.store("ont-isp", [ont(b"$2SALT-C-CANARY$", b"guest")])
    assert changed.status == "changed"
