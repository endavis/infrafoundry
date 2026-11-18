"""Tests for the collection runner."""

from __future__ import annotations

from pathlib import Path

from infrafoundry.collectors.base import Artifact, CollectorError
from infrafoundry.collectors.runner import collect_environment
from infrafoundry.core.config.models import CollectorDeviceConfig

from .conftest import FakeConfigManager, ReversibleFakeEncryptor, make_env


class _Ok:
    def __init__(self, device: CollectorDeviceConfig) -> None:
        self.device = device

    def collect(self) -> list[Artifact]:
        return [Artifact("a.txt", b"x"), Artifact("s.conf", b"CANARY", secret_bearing=True)]


class _Bad(_Ok):
    def collect(self) -> list[Artifact]:
        raise CollectorError("down")


def _cm(tmp_path: Path) -> FakeConfigManager:
    (tmp_path / "envs").mkdir(exist_ok=True)
    devs = [
        {"name": "ont-isp", "type": "bad", "address": "192.0.2.1", "username": "u"},
        {"name": "switch-core", "type": "ok", "address": "192.0.2.2", "username": "u"},
    ]
    return FakeConfigManager(tmp_path / "envs", make_env(devs))


def test_failure_isolated(tmp_path: Path, encryptor: ReversibleFakeEncryptor) -> None:
    built: list[str] = []

    def ok(d: CollectorDeviceConfig) -> _Ok:
        built.append(d.name)
        return _Ok(d)

    report = collect_environment(
        _cm(tmp_path),
        "test",
        registry={"bad": _Bad, "ok": ok},
        encryptor=encryptor,
    )
    assert [r.name for r in report.failed] == ["ont-isp"]
    assert len(report.changed) == 2
    assert (tmp_path / "device-configs/test/switch-core/a.txt").exists()


def test_device_filter_limits_construction(
    tmp_path: Path, encryptor: ReversibleFakeEncryptor
) -> None:
    built: list[str] = []

    def ok(d: CollectorDeviceConfig) -> _Ok:
        built.append(d.name)
        return _Ok(d)

    report = collect_environment(
        _cm(tmp_path),
        "test",
        ("switch-core",),
        registry={"bad": _Bad, "ok": ok},
        encryptor=encryptor,
    )
    assert built == ["switch-core"] and not report.failed
    again = collect_environment(
        _cm(tmp_path),
        "test",
        ("switch-core",),
        registry={"bad": _Bad, "ok": ok},
        encryptor=encryptor,
    )
    assert again.changed == []
