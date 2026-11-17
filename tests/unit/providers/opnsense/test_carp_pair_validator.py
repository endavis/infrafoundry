"""CARP pair check across two firewalls (#1450)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validator import OPNsenseValidator
from infrafoundry.providers.opnsense.validators.carp_pair_validator import CarpPairValidator
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext
from tests.helpers.env import make_env_config


def _status(*rows: tuple[str, str, str]) -> dict[str, Any]:
    return {
        "rows": [
            {"interface": "lan", "vhid": vhid, "subnet": subnet, "status": state}
            for vhid, subnet, state in rows
        ],
        "carp": {"demotion": "0", "allow": "1", "maintenancemode": False},
    }


def _run(mine: dict[str, Any] | None, theirs: dict[str, Any] | None) -> ValidationReport:
    report = ValidationReport()
    CarpPairValidator(report).validate(
        OPNsenseValidationContext(
            resources=[],
            live_carp_status=mine,
            peer_carp_status=theirs,
            node_label="fw-a",
            peer_label="fw-b",
        )
    )
    return report


def _by_name(report: ValidationReport) -> dict[str, Any]:
    return {r.check_name: r for r in report.results}


def test_master_with_backup_peer_passes() -> None:
    report = _run(_status(("1", "192.0.2.1", "MASTER")), _status(("1", "192.0.2.1", "BACKUP")))
    results = _by_name(report)
    assert results["opnsense_carp_pair_1"].passed
    assert results["opnsense_carp_pair"].message == (
        "CARP pair fw-a/fw-b: fw-a 1 MASTER, 0 BACKUP; fw-b 0 MASTER, 1 BACKUP"
    )
    assert not report.has_errors()


def test_vip_missing_on_backup_is_an_error() -> None:
    report = _run(_status(("1", "192.0.2.1", "MASTER")), _status(("2", "192.0.2.9", "BACKUP")))
    result = _by_name(report)["opnsense_carp_pair_1"]
    assert not result.passed and result.level is ValidationLevel.ERROR
    assert "missing on fw-b" in result.message


def test_master_on_both_nodes_is_an_error() -> None:
    report = _run(_status(("1", "192.0.2.1", "MASTER")), _status(("1", "192.0.2.1", "MASTER")))
    result = _by_name(report)["opnsense_carp_pair_1"]
    assert result.level is ValidationLevel.ERROR
    assert "split" in result.message


@pytest.mark.parametrize(
    ("mine", "theirs"), [("BACKUP", "MASTER"), ("MASTER", "INIT"), ("INIT", "BACKUP")]
)
def test_any_other_state_pair_is_an_error(mine: str, theirs: str) -> None:
    report = _run(_status(("1", "192.0.2.1", mine)), _status(("1", "192.0.2.1", theirs)))
    assert _by_name(report)["opnsense_carp_pair_1"].level is ValidationLevel.ERROR


def test_vips_are_matched_on_vhid_and_subnet() -> None:
    report = _run(
        _status(("1", "192.0.2.1", "MASTER"), ("2", "198.51.100.1", "MASTER")),
        _status(("2", "198.51.100.1", "BACKUP"), ("1", "192.0.2.1", "BACKUP")),
    )
    assert not report.has_errors()


def test_no_pair_adds_nothing() -> None:
    assert _run(_status(("1", "192.0.2.1", "MASTER")), None).results == []
    assert _run(None, _status(("1", "192.0.2.1", "BACKUP"))).results == []
    assert _run({"rows": []}, _status(("1", "192.0.2.1", "BACKUP"))).results == []


# ---------------------------------------------------------------------------
# Wiring in OPNsenseValidator.validate_ha_health
# ---------------------------------------------------------------------------

_V = "infrafoundry.providers.opnsense.validator"


def _env(**primary_extra: Any) -> Any:
    return make_env_config(
        provider_settings={
            "opnsense": {
                "primary": "fw-a",
                "firewalls": {
                    "fw-a": {
                        "api_url": "https://fw-a.example.com",
                        "api_key": "ka",
                        "api_secret": "sa",
                        "ha_backup": "fw-b",
                        **primary_extra,
                    },
                    "fw-b": {
                        "api_url": "https://fw-b.example.com",
                        "api_key": "kb",
                        "api_secret": "sb",
                    },
                },
            }
        }
    )


def _client(vips: dict[str, Any] | Exception, sync_target: str = "") -> MagicMock:
    def reply(method: str, path: str, *a: Any, **k: Any) -> Any:
        if path == "diagnostics/interface/getVipStatus":
            if isinstance(vips, Exception):
                raise vips
            return vips
        if path == "core/hasync/get":
            return {"hasync": {"synchronizetoip": sync_target}}
        return {"response": False}

    client = MagicMock()
    client.request.side_effect = reply
    return client


def _validate(
    env: Any, primary: MagicMock, backup: MagicMock
) -> tuple[ValidationReport, list[str]]:
    clients = {"https://fw-a.example.com": primary, "https://fw-b.example.com": backup}
    built: list[str] = []

    def factory(**kwargs: Any) -> MagicMock:
        built.append(kwargs["base_url"])
        return clients[kwargs["base_url"]]

    report = ValidationReport()
    with patch(f"{_V}.OPNsenseClient", side_effect=factory):
        OPNsenseValidator(env, report, provider_name="opnsense").validate_ha_health()
    return report, built


def test_pair_check_reads_the_backup_through_its_own_client() -> None:
    primary = _client(_status(("1", "192.0.2.1", "MASTER")), sync_target="192.0.2.2")
    backup = _client(_status(("1", "192.0.2.1", "BACKUP")))
    report, built = _validate(_env(), primary, backup)
    assert built == ["https://fw-a.example.com", "https://fw-b.example.com"]
    results = _by_name(report)
    assert results["opnsense_carp_pair_1"].passed
    assert not report.has_errors()


def test_pair_check_flags_a_split() -> None:
    primary = _client(_status(("1", "192.0.2.1", "MASTER")), sync_target="192.0.2.2")
    backup = _client(_status(("1", "192.0.2.1", "MASTER")))
    report, _ = _validate(_env(), primary, backup)
    assert _by_name(report)["opnsense_carp_pair_1"].level is ValidationLevel.ERROR


def test_unreadable_backup_is_a_warning() -> None:
    primary = _client(_status(("1", "192.0.2.1", "MASTER")), sync_target="192.0.2.2")
    backup = _client(APIError("boom", response="", provider="opnsense"))
    report, _ = _validate(_env(), primary, backup)
    result = _by_name(report)["opnsense_carp_pair_read"]
    assert result.level is ValidationLevel.WARNING
    assert "fw-b" in result.message
    assert not report.has_errors()


def test_no_ha_backup_means_no_second_client() -> None:
    env = make_env_config(
        provider_settings={
            "opnsense": {
                "primary": "fw-a",
                "firewalls": {
                    "fw-a": {
                        "api_url": "https://fw-a.example.com",
                        "api_key": "k",
                        "api_secret": "s",
                    },
                    "fw-b": {
                        "api_url": "https://fw-b.example.com",
                        "api_key": "k",
                        "api_secret": "s",
                    },
                },
            }
        }
    )
    primary = _client(_status(("1", "192.0.2.1", "MASTER")), sync_target="192.0.2.2")
    _, built = _validate(env, primary, MagicMock())
    assert built == ["https://fw-a.example.com"]
