"""Provider, validator and device-shape behaviour for glinet.firmware (#1655)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.openwrt import OpenWrtProvider, register
from infrafoundry.providers.openwrt.glinet.firmware import (
    FIRMWARE_ADDRESS_PREFIX,
    FIRMWARE_TYPE,
    FirmwareStatus,
)
from infrafoundry.providers.openwrt.glinet.rpc import GlinetUnreachableError
from infrafoundry.providers.openwrt.glinet.settings import GlinetWebSettings
from infrafoundry.providers.openwrt.schema import SPECS
from infrafoundry.providers.openwrt.settings import OpenWrtSettings, OpenWrtSettingsError
from infrafoundry.providers.openwrt.validator import OpenWrtValidator, ssh_argv

from .conftest import lan, make_env, printer, res

pytestmark = pytest.mark.unit

SETTINGS = OpenWrtSettings(address="192.0.2.2", ssh_user="admin-example")
WEB = GlinetWebSettings(address="192.0.2.2", password="example-pw", fingerprint="ab" * 32)
PIN = "ab" * 32


def _provider(tmp_path: Path) -> OpenWrtProvider:
    provider = OpenWrtProvider(tmp_path, tmp_path / "generated")
    provider.set_environment("test")
    return provider


def _render(provider: OpenWrtProvider, *resources: object, **kwargs: object):  # type: ignore[no-untyped-def]
    with patch("infrafoundry.providers.openwrt.load_settings", return_value=SETTINGS):
        return provider.render_run("test", list(resources), **kwargs)  # type: ignore[arg-type]


# ----- provider -----


def test_types_dependencies_and_terraform_prefixes(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    assert FIRMWARE_TYPE in provider.get_resource_types()
    assert provider.get_dependencies()[FIRMWARE_TYPE] == []
    assert provider.get_terraform_resource_types()[FIRMWARE_TYPE] == [FIRMWARE_ADDRESS_PREFIX]
    assert provider.get_terraform_resource_types()["dhcp.host"] == ["openwrt_dhcp_host"]


def test_empty_result_for_a_firmware_only_run(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    for mode in ("apply", "destroy"):
        run = _render(provider, res(FIRMWARE_TYPE, "fw"), mode=mode)
        result = provider.empty_result(run)
        assert result is not None and result.success and not result.outcomes


def test_empty_result_is_none_when_there_is_work(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    assert provider.empty_result(_render(provider, lan(), res(FIRMWARE_TYPE, "fw"))) is None
    assert provider.empty_result(_render(provider, printer(), mode="destroy")) is None


def test_firmware_plan_lines_without_a_firmware_resource(tmp_path: Path) -> None:
    assert _provider(tmp_path).firmware_plan_lines("test", [lan()]) == []


def _lines(tmp_path: Path, status: FirmwareStatus | Exception) -> list[tuple[str, bool]]:
    side = {"side_effect": status} if isinstance(status, Exception) else {"return_value": status}
    with (
        patch("infrafoundry.providers.openwrt.load_web_settings", return_value=WEB),
        patch("infrafoundry.providers.openwrt.check_firmware", **side),
    ):
        return _provider(tmp_path).firmware_plan_lines("test", [res(FIRMWARE_TYPE, "fw")])


def test_plan_line_up_to_date(tmp_path: Path) -> None:
    assert _lines(tmp_path, FirmwareStatus("4.8.7", None, None)) == [
        ("glinet.firmware 'fw': up to date (4.8.7)", False)
    ]


def test_plan_line_offer(tmp_path: Path) -> None:
    [(line, warning)] = _lines(tmp_path, FirmwareStatus("4.8.7", None, "4.8.8"))
    assert not warning and "4.8.7 → 4.8.8 available" in line


@pytest.mark.parametrize("error", [GlinetUnreachableError("down"), OSError("io")])
def test_plan_line_failure_is_a_warning(tmp_path: Path, error: Exception) -> None:
    [(line, warning)] = _lines(tmp_path, error)
    assert warning and "firmware check failed" in line


def test_plan_line_settings_failure_is_a_warning(tmp_path: Path) -> None:
    with patch(
        "infrafoundry.providers.openwrt.load_web_settings",
        side_effect=OpenWrtSettingsError("web_password is required"),
    ):
        [(line, warning)] = _provider(tmp_path).firmware_plan_lines(
            "test", [res(FIRMWARE_TYPE, "fw")]
        )
    assert warning and "web_password" in line


def test_register_returns_metadata_with_cli_registration() -> None:
    meta = register()
    assert meta.name == "openwrt" and meta.provider_class is OpenWrtProvider
    assert meta.resource_types == [*SPECS, FIRMWARE_TYPE]
    assert callable(meta.cli_registration)


# ----- validator -----


def _validate(openwrt: dict[str, object], *resources: object) -> ValidationReport:
    report = ValidationReport()
    OpenWrtValidator(make_env(openwrt), report).validate_offline(list(resources))  # type: ignore[arg-type]
    return report


def _failed(report: ValidationReport) -> list[str]:
    return [r.message for r in report.results if not r.passed]


def test_firmware_schema_and_settings_findings() -> None:
    report = _validate({"address": "192.0.2.2"}, res(FIRMWARE_TYPE, "fw", version="x"))
    text = "\n".join(_failed(report))
    assert "unknown field(s): version" in text
    assert "web_password is required" in text
    assert "tls_fingerprint" in text and "verify_ssl" in text


def test_valid_firmware_settings_pass() -> None:
    report = _validate(
        {"address": "192.0.2.2", "web_password": "secret://env_secrets/x", "tls_fingerprint": PIN},
        res(FIRMWARE_TYPE, "fw"),
    )
    assert _failed(report) == []


def test_web_settings_are_not_required_without_a_firmware_resource() -> None:
    assert _failed(_validate({"address": "192.0.2.2"}, lan())) == []


def test_devices_findings_name_the_device() -> None:
    report = _validate(
        {
            "primary": "office",
            "devices": {"office": {"address": "192.0.2.2"}},
        },
        res(FIRMWARE_TYPE, "fw"),
    )
    assert any(
        "provider_settings.openwrt.devices.office.web_password" in m for m in _failed(report)
    )


def test_ssh_argv_host_key_alias() -> None:
    plain = ssh_argv(SETTINGS, "true")
    assert "StrictHostKeyChecking=yes" not in plain and not any("HostKeyAlias" in a for a in plain)
    pinned = ssh_argv(SETTINGS, "true", host_key_alias="192.0.2.2")
    assert "StrictHostKeyChecking=yes" in pinned and "HostKeyAlias=192.0.2.2" in pinned
    assert pinned[-3:] == ["--", "192.0.2.2", "true"]
