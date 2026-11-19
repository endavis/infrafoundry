"""Tests for the OpenWrt validator."""

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.openwrt.settings import (
    OpenWrtSettings,
    OpenWrtSettingsError,
    settings_from_mapping,
)
from infrafoundry.providers.openwrt.validator import (
    PROBE_COMMAND,
    UCODE_OK,
    OpenWrtValidator,
    ssh_argv,
)

from .conftest import SETTINGS, lan, make_env, web

UBUS_LISTING = (
    "'uci' @1a2b3c4d\n"
    '\t"apply":{"rollback":"Boolean","timeout":"Integer"}\n'
    '\t"confirm":{}\n'
    '\t"rollback":{}\n'
)


def _completed(stdout: str = "", returncode: int = 0, stderr: str = "") -> Any:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def _validator(
    report: ValidationReport,
    *,
    run: Any = None,
    which: Any = lambda _name: "/usr/bin/ansible-playbook",
    collections: Any = lambda: {"community.openwrt": "1.11.0"},
    settings: dict[str, Any] | None = None,
) -> OpenWrtValidator:
    return OpenWrtValidator(
        make_env({"address": "192.0.2.2"} if settings is None else settings),
        report,
        Path("."),
        run=run or (lambda argv: _completed(UBUS_LISTING + UCODE_OK + "\n")),
        which=which,
        collections_lookup=collections,
    )


def _failed(report: ValidationReport) -> dict[str, str]:
    return {r.check_name: r.message for r in report.results if not r.passed}


def _connectivity(validator: OpenWrtValidator) -> None:
    with patch("infrafoundry.providers.openwrt.validator.load_settings", return_value=SETTINGS):
        validator.validate_connectivity()


def test_ssh_argv_keeps_host_key_checking_and_puts_the_address_after_the_separator() -> None:
    settings = OpenWrtSettings(
        address="192.0.2.2", ssh_user="admin-example", ssh_port=2222, ssh_private_key_file="/k"
    )
    argv = ssh_argv(settings, "uptime")
    assert argv[:4] == ["ssh", "-o", "BatchMode=yes", "-o"]
    assert "StrictHostKeyChecking=no" not in argv
    assert argv[-3:] == ["--", "192.0.2.2", "uptime"]
    assert argv[argv.index("-p") + 1] == "2222"
    assert argv[argv.index("-i") + 1] == "/k"
    assert argv[argv.index("-l") + 1] == "admin-example"


def test_offline_reports_schema_findings_with_the_resource_name() -> None:
    report = ValidationReport()
    _validator(report).validate_offline([lan(bogus=1)])
    assert "openwrt_schema_lan" in _failed(report)


def test_offline_reports_missing_settings() -> None:
    report = ValidationReport()
    _validator(report, settings={}).validate_offline([lan()])
    assert "openwrt_settings" in _failed(report)


def test_offline_uses_the_ssh_port_for_the_redirect_check() -> None:
    report = ValidationReport()
    _validator(report, settings={"address": "192.0.2.2", "ssh_port": 2222}).validate_offline(
        [web(src_dport=2222)]
    )
    assert "SSH port 2222" in _failed(report)["openwrt_schema_web"]


def test_references_run_the_offline_checks() -> None:
    report = ValidationReport()
    _validator(report).validate_references([lan(bogus=1)])
    assert "openwrt_schema_lan" in _failed(report)


def test_a_healthy_device_passes_every_connectivity_check() -> None:
    report = ValidationReport()
    _connectivity(_validator(report))
    assert _failed(report) == {}
    assert {r.check_name for r in report.results} == {
        "openwrt_collection",
        "openwrt_connectivity",
        "openwrt_ubus_rollback",
        "openwrt_ucode",
    }


def test_the_probe_is_read_only() -> None:
    seen: list[list[str]] = []

    def run(argv: list[str]) -> Any:
        seen.append(argv)
        return _completed(UBUS_LISTING + UCODE_OK)

    _connectivity(_validator(ValidationReport(), run=run))
    assert seen[0][-1] == PROBE_COMMAND
    assert "uci set" not in PROBE_COMMAND and "apply" not in PROBE_COMMAND.split(";")[0]


def test_a_listing_without_apply_rollback_is_an_error() -> None:
    report = ValidationReport()
    _connectivity(
        _validator(report, run=lambda argv: _completed("'uci'\n\t\"get\":{}\n" + UCODE_OK))
    )
    assert "openwrt_ubus_rollback" in _failed(report)


def test_a_missing_ucode_is_an_error() -> None:
    report = ValidationReport()
    _connectivity(_validator(report, run=lambda argv: _completed(UBUS_LISTING)))
    assert "openwrt_ucode" in _failed(report)


def test_a_missing_collection_is_an_error() -> None:
    report = ValidationReport()
    _connectivity(_validator(report, collections=lambda: {}))
    assert "run foundry deps sync" in _failed(report)["openwrt_collection"]


def test_an_old_collection_is_an_error() -> None:
    report = ValidationReport()
    _connectivity(_validator(report, collections=lambda: {"community.openwrt": "1.10.0"}))
    assert "openwrt_collection" in _failed(report)


def test_a_missing_binary_is_an_error() -> None:
    report = ValidationReport()
    _connectivity(_validator(report, which=lambda _name: None))
    assert "openwrt_ansible" in _failed(report)


def test_ssh_failure_is_reported_without_raising() -> None:
    report = ValidationReport()
    _connectivity(_validator(report, run=lambda argv: _completed(returncode=255, stderr="refused")))
    assert "refused" in _failed(report)["openwrt_connectivity"]


def test_ssh_not_installed_is_reported() -> None:
    def run(argv: list[str]) -> Any:
        raise FileNotFoundError("ssh")

    report = ValidationReport()
    _connectivity(_validator(report, run=run))
    assert "openwrt_connectivity" in _failed(report)


def test_missing_settings_fail_connectivity_cleanly() -> None:
    report = ValidationReport()
    validator = OpenWrtValidator(
        make_env(None),
        report,
        Path("."),
        which=lambda _n: "/x",
        collections_lookup=lambda: {"community.openwrt": "1.11.0"},
    )
    with patch(
        "infrafoundry.providers.openwrt.validator.load_settings",
        side_effect=OpenWrtSettingsError("provider_settings.openwrt is missing: address"),
    ):
        validator.validate_connectivity()
    assert "address" in _failed(report)["openwrt_connectivity"]


def test_no_config_dir_fails_connectivity_cleanly() -> None:
    report = ValidationReport()
    OpenWrtValidator(
        make_env({"address": "192.0.2.2"}),
        report,
        None,
        which=lambda _n: "/x",
        collections_lookup=lambda: {"community.openwrt": "1.11.0"},
    ).validate_connectivity()
    assert "no config directory" in _failed(report)["openwrt_connectivity"]


def test_settings_from_mapping_round_trips_for_the_validator() -> None:
    assert settings_from_mapping({"address": "192.0.2.2"}).address == "192.0.2.2"
