"""Selecting the openwrt device a resource belongs to, and normalizing it (#1656)."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
import yaml

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig

TWO_DEVICES: dict[str, object] = {
    "name": "dev",
    "providers": ["openwrt"],
    "provider_settings": {
        "openwrt": {
            "primary": "gateway",
            "devices": {
                "gateway": {"address": "192.0.2.2"},
                "office": {"address": "198.51.100.2"},
            },
        }
    },
}
FLAT: dict[str, object] = {
    "name": "dev",
    "providers": ["openwrt"],
    "provider_settings": {"openwrt": {"address": "192.0.2.2"}},
}
ITEM = (
    "{{name: {n}, type: dhcp.host, provider: openwrt{extra}, config: {{mac: '02:00:00:00:00:01'}}}}"
)


def _env(tmp_path: Path, settings: dict[str, object] | None = None) -> Path:
    env = tmp_path / "dev"
    (env / "resources").mkdir(parents=True)
    (env / "settings.yaml").write_text(yaml.safe_dump(settings or TWO_DEVICES))
    return env


def _item(name: str, extra: str = "") -> str:
    return ITEM.format(n=name, extra=extra)


def _load(tmp_path: Path) -> list[ResourceConfig]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return ConfigManager(tmp_path).get_all_resources_all_providers("dev")


def _by_name(resources: list[ResourceConfig]) -> dict[str, str]:
    return {r.name: r.provider for r in resources}


def test_entry_device_stamps_the_instance(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "resources" / "r.yaml").write_text(
        "resources:\n"
        f"  - {_item('one', ', device: office')}\n"
        f"  - {_item('two', ', device: gateway')}\n"
        f"  - {_item('three')}\n"
    )
    providers = _by_name(_load(tmp_path))
    assert providers == {"one": "openwrt@office", "two": "openwrt", "three": "openwrt"}


def test_file_level_device_stamps_only_openwrt_entries(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "resources" / "r.yaml").write_text(
        "device: office\n"
        "resources:\n"
        f"  - {_item('one')}\n"
        "  - {name: vm1, type: vm, provider: proxmox, config: {}}\n"
        f"  - {_item('two', ', device: gateway')}\n"
    )
    providers = _by_name(_load(tmp_path))
    assert providers == {"one": "openwrt@office", "vm1": "proxmox", "two": "openwrt"}


def test_manifest_device_stamps_the_packages_openwrt_resources(tmp_path: Path) -> None:
    env = _env(tmp_path)
    pkg = env / "openwrt" / "site"
    pkg.mkdir(parents=True)
    (pkg / "infrafoundry.yml").write_text(
        "name: site\nprovider: openwrt\ndevice: office\nresources:\n"
        "  - a.yaml\n  - b.yaml\n  - c.yaml\n"
    )
    (pkg / "a.yaml").write_text(f"resources:\n  - {_item('manifest-level')}\n")
    (pkg / "b.yaml").write_text(f"device: gateway\nresources:\n  - {_item('file-level')}\n")
    (pkg / "c.yaml").write_text(
        f"device: gateway\nresources:\n  - {_item('entry-level', ', device: office')}\n"
    )
    providers = _by_name(_load(tmp_path))
    assert providers["manifest-level"] == "openwrt@office"
    assert providers["file-level"] == "openwrt"
    assert providers["entry-level"] == "openwrt@office"


def test_tailscale_device_field_without_config_key_still_loads(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "resources" / "r.yaml").write_text(
        "resources:\n"
        "  - {name: routes, type: device_subnet_routes, provider: tailscale,"
        " device: {hostname: fw-test}, routes: [192.0.2.0/24]}\n"
    )
    resources = _load(tmp_path)
    assert [r.provider for r in resources] == ["tailscale"]


def test_resource_targeting_an_undeclared_device_raises(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "resources" / "r.yaml").write_text(f"resources:\n  - {_item('one', ', device: lab')}\n")
    with pytest.raises(
        InvalidConfigurationError, match=r"not declared under provider_settings\.openwrt\.devices"
    ):
        _load(tmp_path)


def test_invalid_device_name_raises(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "resources" / "r.yaml").write_text(
        f"resources:\n  - {_item('one', ', device: Office_1')}\n"
    )
    with pytest.raises(InvalidConfigurationError, match="invalid device name"):
        _load(tmp_path)


def test_flat_and_primary_device_share_the_same_provider_id(tmp_path: Path) -> None:
    env = _env(tmp_path, FLAT)
    (env / "resources" / "r.yaml").write_text(f"resources:\n  - {_item('one')}\n")
    flat = _by_name(_load(tmp_path))
    (env / "settings.yaml").write_text(yaml.safe_dump(TWO_DEVICES))
    (env / "resources" / "r.yaml").write_text(
        f"resources:\n  - {_item('one', ', device: gateway')}\n"
    )
    assert _by_name(_load(tmp_path)) == flat == {"one": "openwrt"}


def test_same_name_on_two_devices_does_not_collide(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "resources" / "r.yaml").write_text(
        f"resources:\n  - {_item('lan')}\n  - {_item('lan', ', device: office')}\n"
    )
    assert sorted(r.provider for r in _load(tmp_path)) == ["openwrt", "openwrt@office"]
