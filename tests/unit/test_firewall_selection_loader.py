"""Selecting the firewall a resource belongs to, and normalizing it (#1450)."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
import yaml

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import DuplicateResourceNameError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig

TWO_FIREWALLS = {
    "name": "dev",
    "providers": ["opnsense"],
    "provider_settings": {
        "opnsense": {
            "primary": "fw-a",
            "firewalls": {
                "fw-a": {"api_url": "https://fw-a.example.com", "api_key": "k", "api_secret": "s"},
                "fw-b": {"api_url": "https://fw-b.example.com", "api_key": "k", "api_secret": "s"},
            },
        }
    },
}


def _env(tmp_path: Path, settings: dict[str, object] | None = None) -> Path:
    env = tmp_path / "dev"
    (env / "opnsense").mkdir(parents=True)
    (env / "settings.yaml").write_text(yaml.safe_dump(settings or TWO_FIREWALLS))
    return env


def _load(tmp_path: Path) -> list[ResourceConfig]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return ConfigManager(tmp_path).get_all_resources_all_providers("dev")


def _by_key(resources: list[ResourceConfig]) -> dict[tuple[str, str], str]:
    return {(r.name, r.type): r.provider for r in resources}


def test_file_level_firewall_stamps_every_entry(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "opnsense" / "aliases.yaml").write_text(
        "firewall: fw-b\n"
        "opnsense:\n"
        "  firewall:\n"
        "    aliases:\n"
        "      - {name: one, config: {type: host}}\n"
        "      - {name: two, config: {type: host}}\n"
    )
    assert {r.provider for r in _load(tmp_path)} == {"opnsense@fw-b"}


def test_entry_firewall_overrides_the_file_default(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "opnsense" / "aliases.yaml").write_text(
        "firewall: fw-b\n"
        "opnsense:\n"
        "  firewall:\n"
        "    aliases:\n"
        "      - {name: one, firewall: fw-a, config: {type: host}}\n"
        "      - {name: two, config: {type: host}}\n"
    )
    providers = _by_key(_load(tmp_path))
    assert providers[("one", "firewall.aliases")] == "opnsense"  # primary, normalized
    assert providers[("two", "firewall.aliases")] == "opnsense@fw-b"


def test_unselected_resources_stay_on_the_primary(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "opnsense" / "aliases.yaml").write_text(
        "opnsense:\n  firewall:\n    aliases:\n      - {name: one, config: {type: host}}\n"
    )
    assert {r.provider for r in _load(tmp_path)} == {"opnsense"}


def test_same_name_on_both_firewalls_is_allowed(tmp_path: Path) -> None:
    env = _env(tmp_path)
    for fw in ("fw-a", "fw-b"):
        (env / "opnsense" / f"vlans-{fw}.yaml").write_text(
            f"firewall: {fw}\n"
            "opnsense:\n  interfaces:\n    vlans:\n"
            "      - {name: lan, config: {device: igb0, tag: 10}}\n"
        )
    assert sorted(r.provider for r in _load(tmp_path)) == ["opnsense", "opnsense@fw-b"]


def test_same_name_twice_on_one_firewall_is_a_duplicate(tmp_path: Path) -> None:
    env = _env(tmp_path)
    for index in (1, 2):
        (env / "opnsense" / f"vlans-{index}.yaml").write_text(
            "firewall: fw-b\n"
            "opnsense:\n  interfaces:\n    vlans:\n"
            "      - {name: lan, config: {device: igb0, tag: 10}}\n"
        )
    with pytest.raises(DuplicateResourceNameError, match="opnsense@fw-b:lan"):
        _load(tmp_path)


def test_singletons_in_two_files_load_per_firewall(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "opnsense" / "ha-a.yaml").write_text(
        "opnsense:\n  hasync:\n    settings: {synchronize_to_ip: 192.0.2.2}\n"
    )
    (env / "opnsense" / "ha-b.yaml").write_text(
        "firewall: fw-b\nopnsense:\n  hasync:\n    settings: {synchronize_to_ip: 192.0.2.1}\n"
    )
    resources = {r.provider: r for r in _load(tmp_path)}
    assert resources["opnsense"].config["synchronize_to_ip"] == "192.0.2.2"
    assert resources["opnsense@fw-b"].config["synchronize_to_ip"] == "192.0.2.1"


def test_package_manifest_firewall_applies_when_nothing_is_more_specific(tmp_path: Path) -> None:
    env = _env(tmp_path)
    pkg = env / "opnsense" / "backup-node"
    pkg.mkdir()
    (pkg / "infrafoundry.yml").write_text(
        "name: backup-node\nprovider: opnsense\nfirewall: fw-b\n"
        "resources:\n  - a.yaml\n  - b.yaml\n"
    )
    (pkg / "a.yaml").write_text(
        "opnsense:\n  firewall:\n    aliases:\n      - {name: one, config: {type: host}}\n"
    )
    (pkg / "b.yaml").write_text(
        "firewall: fw-a\n"
        "opnsense:\n  firewall:\n    aliases:\n      - {name: two, config: {type: host}}\n"
    )
    providers = _by_key(_load(tmp_path))
    assert providers[("one", "firewall.aliases")] == "opnsense@fw-b"
    assert providers[("two", "firewall.aliases")] == "opnsense"  # file-level fw-a is the primary


def test_resource_centric_item_firewall(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "resources").mkdir()
    (env / "resources" / "r.yaml").write_text(
        "resources:\n"
        "  - {name: one, type: alias, provider: opnsense, firewall: fw-b, config: {type: host}}\n"
        "  - {name: two, type: alias, provider: opnsense, config: {type: host}}\n"
    )
    providers = _by_key(_load(tmp_path))
    assert providers[("one", "alias")] == "opnsense@fw-b"
    assert providers[("two", "alias")] == "opnsense"


def test_other_extra_top_level_keys_still_raise(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "opnsense" / "aliases.yaml").write_text(
        "other: 1\nopnsense:\n  firewall:\n    aliases:\n      - {name: one}\n"
    )
    with pytest.raises(InvalidConfigurationError, match="cannot mix nested"):
        _load(tmp_path)


def test_undeclared_firewall_raises(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "opnsense" / "aliases.yaml").write_text(
        "firewall: fw-z\nopnsense:\n  firewall:\n    aliases:\n      - {name: one}\n"
    )
    with pytest.raises(InvalidConfigurationError, match="not declared"):
        _load(tmp_path)


def test_invalid_firewall_name_raises(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "opnsense" / "aliases.yaml").write_text(
        "firewall: FW_B\nopnsense:\n  firewall:\n    aliases:\n      - {name: one}\n"
    )
    with pytest.raises(InvalidConfigurationError, match="invalid firewall name"):
        _load(tmp_path)


def test_firewall_on_a_non_opnsense_resource_raises(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "resources").mkdir()
    (env / "resources" / "r.yaml").write_text(
        "resources:\n  - {name: vm1, type: vm, provider: proxmox, firewall: fw-b, config: {}}\n"
    )
    with pytest.raises(InvalidConfigurationError, match="only supported for provider"):
        _load(tmp_path)


def test_legacy_environment_never_reads_settings_for_normalization(tmp_path: Path) -> None:
    env = tmp_path / "dev"
    (env / "opnsense").mkdir(parents=True)  # no settings.yaml at all
    (env / "opnsense" / "aliases.yaml").write_text(
        "opnsense:\n  firewall:\n    aliases:\n      - {name: one, config: {type: host}}\n"
    )
    assert {r.provider for r in _load(tmp_path)} == {"opnsense"}
