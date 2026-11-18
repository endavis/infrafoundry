"""Unit tests for ``HasyncValidator`` and ``HasyncLiveValidator`` (#1389)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validator import OPNsenseValidator
from infrafoundry.providers.opnsense.validators import HasyncLiveValidator, HasyncValidator
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext
from tests.helpers.env import make_env_config

FAKE = "FAKE-SYNC-PASSWORD-0001"


def _res(**config: Any) -> ResourceConfig:
    return ResourceConfig(
        name="hasync.settings", type="hasync.settings", provider="opnsense", config=config
    )


def _offline(**config: Any) -> ValidationReport:
    report = ValidationReport()
    HasyncValidator(report).validate(
        OPNsenseValidationContext(
            resources=[_res(**config)], interface_assignment_names={"sync_lan"}
        )
    )
    return report


def _live(
    interfaces: set[str], items: set[str], names: set[str] | None = None, **config: Any
) -> ValidationReport:
    report = ValidationReport()
    HasyncLiveValidator(report).validate(
        OPNsenseValidationContext(
            resources=[_res(**config)],
            interface_assignment_names=names or set(),
            existing_hasync_interfaces=interfaces,
            existing_hasync_sync_items=items,
        )
    )
    return report


def _levels(report: ValidationReport, level: ValidationLevel) -> list[str]:
    return [r.message for r in report.results if r.level == level]


def test_valid_config_has_no_errors() -> None:
    report = _offline(
        disable_preempt=False,
        pfsync_peer_ip="192.0.2.2",
        synchronize_to_ip="2001:db8::2",
        pfsync_version=1400,
        sync_items=["aliases", "rules"],
        username="fw-test-sync",
        password="secret://env_secrets/opnsense/hasync/password",
    )
    assert _levels(report, ValidationLevel.ERROR) == []
    assert _levels(report, ValidationLevel.WARNING) == []


def test_empty_ip_strings_accepted() -> None:
    report = _offline(pfsync_peer_ip="", synchronize_to_ip="", pfsync_interface="")
    assert _levels(report, ValidationLevel.ERROR) == []


def test_unknown_key_and_bad_bool() -> None:
    assert _levels(_offline(bogus=1), ValidationLevel.ERROR)
    assert _levels(_offline(verify_peer="yes"), ValidationLevel.ERROR)
    assert _levels(_offline(username=5), ValidationLevel.ERROR)


def test_bad_ips() -> None:
    assert _levels(_offline(pfsync_peer_ip="not-an-ip"), ValidationLevel.ERROR)
    assert _levels(_offline(pfsync_peer_ip="2001:db8::2"), ValidationLevel.ERROR)
    assert _levels(_offline(synchronize_to_ip="nope"), ValidationLevel.ERROR)


def test_version_enum() -> None:
    assert _levels(_offline(pfsync_version="1301"), ValidationLevel.ERROR) == []
    assert _levels(_offline(pfsync_version=1301), ValidationLevel.ERROR) == []
    assert _levels(_offline(pfsync_version="9"), ValidationLevel.ERROR)
    assert _levels(_offline(pfsync_version=True), ValidationLevel.ERROR)


def test_sync_items_shape() -> None:
    assert _levels(_offline(sync_items="rules"), ValidationLevel.ERROR)
    assert _levels(_offline(sync_items=["rules", "rules"]), ValidationLevel.ERROR)
    assert _levels(_offline(sync_items=["", "x"]), ValidationLevel.ERROR)
    assert _levels(_offline(sync_items=[]), ValidationLevel.ERROR) == []


def test_plaintext_password_warns_without_value() -> None:
    report = _offline(password=FAKE)
    assert len(_levels(report, ValidationLevel.WARNING)) == 1
    assert FAKE not in " ".join(r.message for r in report.results)
    assert _levels(report, ValidationLevel.ERROR) == []


def test_bad_password_and_update_flag() -> None:
    assert _levels(_offline(password=""), ValidationLevel.ERROR)
    assert _levels(_offline(password=5), ValidationLevel.ERROR)
    assert _levels(_offline(update_password=True), ValidationLevel.ERROR)
    assert _levels(_offline(update_password="x", password="secret://a/b"), ValidationLevel.ERROR)


def test_managed_assignment_is_info() -> None:
    report = _offline(pfsync_interface="sync_lan")
    assert len(_levels(report, ValidationLevel.INFO)) == 1


def test_live_interface_checks() -> None:
    assert _levels(_live({"lan"}, set(), pfsync_interface="lan"), ValidationLevel.ERROR) == []
    assert _levels(_live({"lan"}, set(), pfsync_interface="opt99"), ValidationLevel.ERROR)
    assert (
        _levels(
            _live({"lan"}, set(), names={"opt99"}, pfsync_interface="opt99"),
            ValidationLevel.ERROR,
        )
        == []
    )
    assert _levels(_live({"lan"}, set(), pfsync_interface=""), ValidationLevel.ERROR) == []


def test_live_sync_items_checks() -> None:
    errors = _levels(_live(set(), {"rules"}, sync_items=["rules", "bogus"]), ValidationLevel.ERROR)
    assert len(errors) == 1
    assert "bogus" in errors[0]


def test_empty_live_sets_give_no_error() -> None:
    report = _live(set(), set(), pfsync_interface="opt99", sync_items=["bogus"])
    assert _levels(report, ValidationLevel.ERROR) == []


def _validator() -> OPNsenseValidator:
    return OPNsenseValidator(make_env_config(), ValidationReport())


def test_validate_offline_runs_hasync_validator() -> None:
    validator = _validator()
    validator.validate_offline([_res(bogus=1)])
    assert any(
        r.level == ValidationLevel.ERROR and "unknown key" in r.message
        for r in validator.report.results
    )


def test_fetch_hasync_options() -> None:
    validator = _validator()
    payload = {
        "hasync": {
            "pfsyncinterface": {"": {"selected": 1}, "lan": {"selected": 0}},
            "syncitems": {"rules": {"selected": 0}},
        }
    }
    with patch.object(validator.api_validator, "fetch_json", return_value=payload) as fetch:
        assert validator._get_existing_hasync_options("https://fw.example.com", "k", "s") == (
            {"lan"},
            {"rules"},
        )
    assert fetch.call_args.kwargs["url"].endswith("/api/core/hasync/get")
    with patch.object(validator.api_validator, "fetch_json", return_value=None):
        assert validator._get_existing_hasync_options("https://fw.example.com", "k", "s") == (
            set(),
            set(),
        )


def test_references_fetch_only_when_hasync_present() -> None:
    validator = _validator()
    creds = {"api_url": "https://fw.example.com", "api_key": "k", "api_secret": "s"}
    with (
        patch.object(validator.api_validator, "get_credentials", return_value=creds),
        patch.object(validator, "_get_existing_aliases", return_value={}),
        patch.object(validator, "_get_existing_interfaces", return_value={}),
        patch.object(validator, "_get_existing_gateways", return_value=set()),
        patch.object(validator, "_get_existing_unbound_host_overrides", return_value=set()),
        patch.object(
            validator,
            "_get_existing_hasync_options",
            return_value=({"lan"}, {"rules"}),
        ) as fetch,
    ):
        validator.validate_references([])
        fetch.assert_not_called()
        validator.validate_references([_res(pfsync_interface="opt99", sync_items=["bogus"])])
        fetch.assert_called_once()
    errors = [r.message for r in validator.report.results if r.level == ValidationLevel.ERROR]
    assert any("opt99" in m for m in errors)
    assert any("bogus" in m for m in errors)


def test_reset_alone_is_valid() -> None:
    report = _offline(reset=True)
    assert _levels(report, ValidationLevel.ERROR) == []
    assert _levels(report, ValidationLevel.WARNING) == []


def test_reset_false_is_valid_and_validates_other_keys() -> None:
    assert _levels(_offline(reset=False, username="u"), ValidationLevel.ERROR) == []
    errors = _levels(_offline(reset=False, pfsync_version="9"), ValidationLevel.ERROR)
    assert any("pfsync_version" in m for m in errors)


def test_reset_with_other_keys_is_error_naming_keys_only() -> None:
    report = _offline(reset=True, password=FAKE, update_password=True)
    errors = _levels(report, ValidationLevel.ERROR)
    assert any("password" in m and "update_password" in m for m in errors)
    assert all(FAKE not in m for m in errors)


def test_reset_non_bool_is_error() -> None:
    errors = _levels(_offline(reset="yes"), ValidationLevel.ERROR)
    assert any("reset must be a boolean" in m for m in errors)
