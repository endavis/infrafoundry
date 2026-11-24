"""Several OpenWrt devices per environment: settings, provider, validator, labels (#1656)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from infrafoundry.core.runners.openwrt_ansible_runner import OpenWrtAnsibleRunner
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.openwrt import OpenWrtProvider
from infrafoundry.providers.openwrt.devices import (
    device_label,
    device_settings,
    validate_devices_settings,
)
from infrafoundry.providers.openwrt.settings import (
    OpenWrtSettingsError,
    load_settings,
    settings_from_mapping,
)
from infrafoundry.providers.openwrt.validator import UCODE_OK, OpenWrtValidator

from .conftest import lan, make_env, printer
from .test_validator import UBUS_LISTING

GATEWAY = "192.0.2.2"
OFFICE = "198.51.100.2"
DEVICES: dict[str, Any] = {
    "ssh_user": "admin-example",
    "ssh_port": 2200,
    "primary": "gateway",
    "devices": {
        "gateway": {"address": GATEWAY},
        "office": {"address": OFFICE, "ssh_port": 2222},
    },
}


def _write_env(tmp_path: Path, openwrt: dict[str, Any]) -> None:
    env = tmp_path / "dev"
    env.mkdir(exist_ok=True)
    settings = {"name": "dev", "providers": ["openwrt"], "provider_settings": {"openwrt": openwrt}}
    (env / "settings.yaml").write_text(yaml.safe_dump(settings))


# ----- settings -----


def test_flat_settings_are_returned_unchanged() -> None:
    flat = {"address": GATEWAY}
    assert device_settings(flat, "openwrt") is flat


def test_shared_defaults_merge_and_the_entry_wins() -> None:
    merged = device_settings(DEVICES, "openwrt@office")
    assert merged == {"ssh_user": "admin-example", "ssh_port": 2222, "address": OFFICE}


def test_map_and_primary_keys_are_dropped() -> None:
    merged = device_settings(DEVICES, "openwrt") or {}
    assert "devices" not in merged and "primary" not in merged
    assert merged["address"] == GATEWAY and merged["ssh_port"] == 2200


def test_load_settings_resolves_each_device(tmp_path: Path) -> None:
    _write_env(tmp_path, DEVICES)
    assert load_settings(tmp_path, "dev").address == GATEWAY
    office = load_settings(tmp_path, "dev", "openwrt@office")
    assert (office.address, office.ssh_port, office.ssh_user) == (OFFICE, 2222, "admin-example")


def test_secret_resolution_is_scoped_to_the_device(tmp_path: Path) -> None:
    openwrt = {
        "primary": "gateway",
        "devices": {
            "gateway": {"address": GATEWAY},
            "office": {"address": "secret://missing/does-not-exist"},
        },
    }
    _write_env(tmp_path, openwrt)
    assert load_settings(tmp_path, "dev").address == GATEWAY


def test_load_settings_for_an_undeclared_device_raises(tmp_path: Path) -> None:
    _write_env(tmp_path, DEVICES)
    with pytest.raises(OpenWrtSettingsError, match="'lab' is not declared"):
        load_settings(tmp_path, "dev", "openwrt@lab")


@pytest.mark.parametrize(
    ("openwrt", "message"),
    [
        ({"address": GATEWAY, "devices": {"a": {"address": OFFICE}}}, "cannot combine"),
        (
            {"devices": {"a": {"address": GATEWAY}, "b": {"address": OFFICE}}},
            "'primary' is required",
        ),
        ({"primary": "z", "devices": {"a": {"address": GATEWAY}}}, "not declared under devices"),
        ({"devices": {"Office_1": {"address": GATEWAY}}}, "invalid"),
        ({"devices": {}}, "non-empty mapping"),
    ],
)
def test_shape_errors(openwrt: dict[str, Any], message: str, tmp_path: Path) -> None:
    assert any(message in e for e in validate_devices_settings(openwrt))
    _write_env(tmp_path, openwrt)
    with pytest.raises(OpenWrtSettingsError, match=message):
        load_settings(tmp_path, "dev")


def test_a_device_error_names_the_device_key() -> None:
    with pytest.raises(OpenWrtSettingsError, match=r"openwrt\.devices\.office\.ssh_port"):
        settings_from_mapping(
            {"address": OFFICE, "ssh_port": 70000}, "provider_settings.openwrt.devices.office"
        )


def test_device_label() -> None:
    assert device_label(DEVICES, "openwrt@office") == "office"
    assert device_label(DEVICES, "openwrt") == "gateway"
    assert device_label({"address": GATEWAY}, "openwrt") is None


# ----- provider -----


def test_spawn_instance_names_and_directories(tmp_path: Path) -> None:
    base = OpenWrtProvider(tmp_path, tmp_path / "generated")
    base.set_environment("dev")
    office = base.spawn_instance("office")
    assert office.name == "openwrt@office"
    assert office.ansible_dir.name == "openwrt@office"
    assert base.ansible_dir.name == "openwrt"


def test_render_run_writes_each_devices_inventory_and_host_key_alias(tmp_path: Path) -> None:
    _write_env(tmp_path, DEVICES)
    base = OpenWrtProvider(tmp_path, tmp_path / "generated")
    base.set_environment("dev")
    office = base.spawn_instance("office")
    base.render_run("dev", [lan()])
    office.render_run("dev", [printer()])
    primary_inv = yaml.safe_load((base.ansible_dir / "inventory.yml").read_text())
    office_inv = yaml.safe_load((office.ansible_dir / "inventory.yml").read_text())
    primary_host = primary_inv["all"]["hosts"]["openwrt"]
    office_host = office_inv["all"]["hosts"]["openwrt"]
    assert primary_host["ansible_host"] == GATEWAY
    assert office_host["ansible_host"] == OFFICE
    assert office_host["ansible_port"] == 2222
    assert office_host["ansible_ssh_common_args"] == f"-o HostKeyAlias={OFFICE}"


def test_label_is_cached_per_environment(tmp_path: Path) -> None:
    _write_env(tmp_path, DEVICES)
    office = OpenWrtProvider(tmp_path, tmp_path / "generated").spawn_instance("office")
    assert office.device_label("dev") == "office"
    assert office.device_label("missing") is None


# ----- validator and doctor labels -----


def _validator(
    report: ValidationReport, name: str, settings: dict[str, Any], fail: str | None = None
) -> OpenWrtValidator:
    def run(argv: list[str]) -> Any:
        if fail is not None and fail in argv:
            return subprocess.CompletedProcess(argv, 255, "", "refused")
        return subprocess.CompletedProcess(argv, 0, UBUS_LISTING + UCODE_OK + "\n", "")

    return OpenWrtValidator(
        make_env(settings),
        report,
        Path("."),
        run=run,
        which=lambda _n: "/usr/bin/ansible-playbook",
        collections_lookup=lambda: {"community.openwrt": "1.11.0"},
        provider_name=name,
    )


def test_primary_reports_shape_errors_once() -> None:
    bad = {"devices": {"a": {"address": GATEWAY}, "b": {"address": OFFICE}}}
    primary, other = ValidationReport(), ValidationReport()
    _validator(primary, "openwrt", bad).validate_offline([])
    _validator(other, "openwrt@b", bad).validate_offline([])
    assert [r.check_name for r in primary.results if not r.passed] == ["openwrt_devices_settings"]
    assert not [r for r in other.results if not r.passed]


def test_undeclared_device_is_reported_offline() -> None:
    report = ValidationReport()
    _validator(report, "openwrt@lab", DEVICES).validate_offline([lan()])
    failed = {r.check_name: r.message for r in report.results if not r.passed}
    assert "not declared" in failed["openwrt_settings"]


def test_a_device_out_of_range_port_names_the_device() -> None:
    settings = {"devices": {"office": {"address": OFFICE, "ssh_port": 70000}}}
    report = ValidationReport()
    _validator(report, "openwrt", settings).validate_offline([lan()])
    failed = [r.message for r in report.results if not r.passed]
    assert any("openwrt.devices.office.ssh_port" in m for m in failed)


def test_doctor_labels_each_device_and_isolates_failures(tmp_path: Path) -> None:
    _write_env(tmp_path, DEVICES)
    env = make_env(DEVICES)
    env.name = "dev"
    report = ValidationReport()
    base = OpenWrtProvider(tmp_path, tmp_path / "generated")
    office = base.spawn_instance("office")
    # the real probe is replaced per device through the validator's runner
    from unittest.mock import patch

    def run(argv: list[str]) -> Any:
        if OFFICE in argv:
            return subprocess.CompletedProcess(argv, 255, "", "refused")
        return subprocess.CompletedProcess(argv, 0, UBUS_LISTING + UCODE_OK + "\n", "")

    with (
        patch("infrafoundry.providers.openwrt.validator._run", run),
        patch("infrafoundry.providers.openwrt.validator.shutil.which", return_value="/bin/x"),
        patch(
            "infrafoundry.providers.openwrt.validator.installed_collections",
            return_value={"community.openwrt": "1.11.0"},
        ),
    ):
        base.validate_connectivity(env, report)
        office.validate_connectivity(env, report)
    connectivity = {r.message: r.passed for r in report.results if "ssh" in r.message}
    assert any(m.startswith("[gateway] ") and ok for m, ok in connectivity.items())
    assert any(m.startswith("[office] ") and not ok for m, ok in connectivity.items())


def test_flat_config_has_no_prefix(tmp_path: Path) -> None:
    env = make_env({"address": GATEWAY})
    report = ValidationReport()
    OpenWrtProvider(tmp_path, tmp_path / "generated").validate_offline([lan()], [], env, report)
    assert all(not r.message.startswith("[") for r in report.results)


# ----- runner -----


def test_runner_loads_only_the_instances_resources(tmp_path: Path) -> None:
    from unittest.mock import patch

    from infrafoundry.core.provider import ResourceConfig

    office = OpenWrtProvider(tmp_path, tmp_path).spawn_instance("office")
    mine = ResourceConfig(name="a", type="dhcp.host", provider="openwrt@office", config={})
    others = [
        ResourceConfig(name="a", type="dhcp.host", provider="openwrt", config={}),
        ResourceConfig(name="b", type="vm", provider="proxmox", config={}),
    ]
    with patch("infrafoundry.core.config.ConfigManager") as manager:
        manager.return_value.load_environment.return_value = object()
        manager.return_value.get_all_resources_all_providers.return_value = [mine, *others]
        assert OpenWrtAnsibleRunner._load_resources(office, "dev") == [mine]


def test_runner_supports_device_instances_only_for_openwrt(tmp_path: Path) -> None:
    office = OpenWrtProvider(tmp_path, tmp_path).spawn_instance("office")
    assert OpenWrtAnsibleRunner._supports(office)
    assert not OpenWrtAnsibleRunner._supports(type("P", (), {"name": "opnsense"})())


def test_runner_label(tmp_path: Path) -> None:
    _write_env(tmp_path, DEVICES)
    office = OpenWrtProvider(tmp_path, tmp_path / "generated").spawn_instance("office")
    office.set_environment("dev")
    assert OpenWrtAnsibleRunner._label(office) == "openwrt_ansible\\[office]"
    other = tmp_path / "other"
    other.mkdir()
    _write_env(other, {"address": GATEWAY})
    plain = OpenWrtProvider(other, other / "generated")
    plain.set_environment("dev")
    assert OpenWrtAnsibleRunner._label(plain) == "openwrt_ansible"
