"""A ``glinet.firmware`` entry without ``config:`` validates clean (#1660).

The package loader hands an entry without ``config:`` to the provider with the whole entry
as its config, so the entry-level keys (``provider``, ``type``, ``device`` ...) must not read
as firmware fields.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.openwrt.glinet.firmware import FIRMWARE_TYPE, check_firmware_resources

pytestmark = pytest.mark.unit

SETTINGS: dict[str, object] = {
    "name": "dev",
    "providers": ["openwrt"],
    "provider_settings": {
        "openwrt": {
            "primary": "gateway",
            "devices": {"gateway": {"address": "192.0.2.2"}, "office": {"address": "192.0.2.3"}},
        }
    },
}

BARE = "name: fw\ntype: glinet.firmware\nprovider: openwrt\ndevice: office\n"
EMPTY_CONFIG = BARE + "config: {}\n"
BAD_BARE = BARE + "version: '1.0'\n"
BAD_CONFIG = BARE + "config:\n  version: '1.0'\n"


def _resources_yaml(body: str) -> str:
    lines = body.rstrip("\n").splitlines()
    return "resources:\n  - " + "\n    ".join(lines) + "\n"


def _package(tmp_path: Path, body: str) -> list[ResourceConfig]:
    envs = tmp_path / "envs"
    package = envs / "dev" / "openwrt" / "demo"
    package.mkdir(parents=True)
    (package / "infrafoundry.yml").write_text("name: demo\nresources:\n  - resources.yaml\n")
    (package / "resources.yaml").write_text(_resources_yaml(body))
    resources, _events, _variables = PackageLoader(envs).load_package(
        package, provider="openwrt", env_name="dev"
    )
    return resources


def _messages(resources: list[ResourceConfig]) -> str:
    return "\n".join(f.message for f in check_firmware_resources(resources))


@pytest.mark.parametrize("body", [BARE, EMPTY_CONFIG])
def test_package_entry_validates_clean(tmp_path: Path, body: str) -> None:
    resources = _package(tmp_path, body)
    assert [r.type for r in resources] == [FIRMWARE_TYPE]
    assert check_firmware_resources(resources) == []


@pytest.mark.parametrize("body", [BAD_BARE, BAD_CONFIG])
def test_package_entry_with_a_real_field_still_errors(tmp_path: Path, body: str) -> None:
    text = _messages(_package(tmp_path, body))
    assert "unknown field(s): version" in text
    assert "device" not in text.split("unknown field(s):")[1]


@pytest.mark.filterwarnings("ignore:Loose resources:DeprecationWarning")
@pytest.mark.parametrize(("body", "clean"), [(BARE, True), (BAD_CONFIG, False)])
def test_resource_centric_file_validates(tmp_path: Path, body: str, clean: bool) -> None:
    env = tmp_path / "dev"
    (env / "resources").mkdir(parents=True)
    (env / "settings.yaml").write_text(yaml.safe_dump(SETTINGS))
    (env / "resources" / "fw.yaml").write_text(_resources_yaml(body))
    resources = ConfigManager(tmp_path).get_all_resources_all_providers("dev")
    findings = check_firmware_resources([r for r in resources if r.type == FIRMWARE_TYPE])
    assert (findings == []) is clean
