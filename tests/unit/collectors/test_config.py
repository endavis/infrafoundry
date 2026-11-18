"""Tests for collector configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from infrafoundry.collectors.base import CollectorConfigError
from infrafoundry.collectors.config import load_collection, resolve_device
from infrafoundry.core.config.models import CollectorsConfig, EnvironmentConfig

from .conftest import FakeConfigManager, make_env

DEV = {"name": "ont-isp", "type": "huawei-ont-web", "address": "http://192.0.2.1",
       "username": "admin", "password": "secret://env_secrets/ont/password"}  # fmt: skip


def _cm(tmp_path: Path, env: EnvironmentConfig) -> FakeConfigManager:
    (tmp_path / "envs").mkdir(exist_ok=True)
    return FakeConfigManager(tmp_path / "envs", env)


def test_section_parses() -> None:
    env = EnvironmentConfig.model_validate({"name": "t", "collectors": {"devices": [DEV]}})
    assert env.collectors and env.collectors.devices[0].timeout == 30


def test_duplicate_names_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        CollectorsConfig(devices=[DEV, DEV])  # type: ignore[list-item]


@pytest.mark.parametrize("name", ["../x", "Upper"])
def test_bad_name_rejected(name: str) -> None:
    with pytest.raises(ValidationError):
        CollectorsConfig(devices=[{**DEV, "name": name}])  # type: ignore[list-item]


def test_defaults_and_selection(tmp_path: Path) -> None:
    other = {**DEV, "name": "switch-core"}
    c = load_collection(_cm(tmp_path, make_env([DEV, other])), "test", ("switch-core",))
    assert c.output_dir == (tmp_path / "device-configs" / "test").resolve()
    assert [d.name for d in c.devices] == ["switch-core"]


def test_unknown_type(tmp_path: Path) -> None:
    with pytest.raises(CollectorConfigError, match="unknown collector type"):
        load_collection(_cm(tmp_path, make_env([{**DEV, "type": "nope"}])), "test")


def test_unknown_device(tmp_path: Path) -> None:
    with pytest.raises(CollectorConfigError, match="ghost"):
        load_collection(_cm(tmp_path, make_env([DEV])), "test", ("ghost",))


def test_missing_section(tmp_path: Path) -> None:
    with pytest.raises(CollectorConfigError, match="No collectors"):
        load_collection(_cm(tmp_path, EnvironmentConfig(name="test")), "test")


@pytest.mark.parametrize("out", ["../outside", "envs/test/x", "envs", "/etc"])
def test_bad_output_dir(tmp_path: Path, out: str) -> None:
    with pytest.raises(CollectorConfigError):
        load_collection(_cm(tmp_path, make_env([DEV], output_dir=out)), "test")


def test_secret_resolves(tmp_path: Path) -> None:
    env = make_env([DEV], secrets={"ont": {"password": "CANARY-LOGIN-0001"}})
    d = resolve_device(env, env.collectors.devices[0])
    assert d.password == "CANARY-LOGIN-0001"


def test_unresolvable_ref_no_value_leak(tmp_path: Path) -> None:
    env = make_env([DEV], secrets={"ont": {"other": "CANARY-LOGIN-0001"}})
    with pytest.raises(CollectorConfigError) as info:
        resolve_device(env, env.collectors.devices[0])
    assert "CANARY" not in str(info.value)


def test_required_fields(tmp_path: Path) -> None:
    env = make_env([{**DEV, "password": None}])
    with pytest.raises(CollectorConfigError, match="password"):
        resolve_device(env, env.collectors.devices[0])
    env = make_env([{"name": "travel-router", "type": "openwrt-ssh", "address": "192.0.2.5"}])
    with pytest.raises(CollectorConfigError, match="username"):
        resolve_device(env, env.collectors.devices[0])
    env = make_env([{**DEV, "address": "ftp://x", "password": "p"}])
    with pytest.raises(CollectorConfigError, match="http"):
        resolve_device(env, env.collectors.devices[0])
