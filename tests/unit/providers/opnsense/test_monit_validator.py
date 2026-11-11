"""Unit tests for ``MonitValidator`` (#791)."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators import MonitValidator, build_xref_index
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext
from tests.helpers.opnsense_monit import res, single, stock_resources

URI = "secret://env_secrets/opnsense/monit/settings/password"
LITERAL = "literal-value-not-real"


def _run(resources: list[ResourceConfig]) -> ValidationReport:
    report = ValidationReport()
    MonitValidator(report).validate(
        OPNsenseValidationContext(resources=resources, index=build_xref_index(resources))
    )
    return report


def _level(report: ValidationReport, level: ValidationLevel) -> list[Any]:
    return [c for c in report.results if not c.passed and c.level == level]


def _errors(report: ValidationReport) -> list[Any]:
    return _level(report, ValidationLevel.ERROR)


def _warnings(report: ValidationReport) -> list[Any]:
    return _level(report, ValidationLevel.WARNING)


def _names(checks: list[Any]) -> list[str]:
    return [c.check_name for c in checks]


def _svc(name: str = "svc", **c: Any) -> ResourceConfig:
    c.setdefault("type", "system")
    return res("monit.services", name, **c)


def _test(name: str = "tst", **c: Any) -> ResourceConfig:
    c.setdefault("condition", "failed ping")
    return res("monit.tests", name, **c)


def _alert(name: str = "alr", **c: Any) -> ResourceConfig:
    c.setdefault("recipient", "ops@example.com")
    return res("monit.alerts", name, **c)


def test_stock_equivalent_set_is_clean() -> None:
    report = _run(stock_resources())
    assert not _errors(report) and not _warnings(report)


def test_no_monit_resources_is_a_noop() -> None:
    assert not _run([res("firewall.aliases", "a")]).results


# -- settings ------------------------------------------------------------------------


def test_settings_unknown_key_and_type_errors() -> None:
    report = _run([single("monit.settings", bogus=1, interval="x", ssl_version="tls9")])
    names = _names(_errors(report))
    assert "monit_settings_unknown_key_bogus" in names
    assert "monit_settings_interval" in names and "monit_settings_ssl_version" in names


def test_literal_secret_warns_but_uri_and_empty_do_not() -> None:
    report = _run([single("monit.settings", password=LITERAL, httpd_password=URI, mmonit_url="")])
    assert _names(_warnings(report)) == ["monit_settings_password_literal_secret"]
    assert LITERAL not in " ".join(c.message for c in report.results)
    assert not _errors(report)


# -- list rows -----------------------------------------------------------------------


def test_unknown_key_is_an_error() -> None:
    assert "monit_test_tst_unknown_key_bogus" in _names(_errors(_run([_test(bogus=1)])))


def test_handle_must_not_contain_a_dot() -> None:
    assert "monit_test_a.b_handle" in _names(_errors(_run([_test("a.b")])))


def test_duplicate_identities_are_errors() -> None:
    report = _run([_test("a", test_name="Same"), _test("b", test_name="Same")])
    assert "monit_tests_unique_identity" in _names(_errors(report))
    report = _run([_test("a"), _test("b", test_name="a")])  # handle fallback collides
    assert "monit_tests_unique_identity" in _names(_errors(report))
    report = _run([_alert("a"), _alert("b")])
    assert "monit_alerts_unique_identity" in _names(_errors(report))


def test_alert_needs_recipient_and_valid_events() -> None:
    report = _run([res("monit.alerts", "a")])
    assert "monit_alert_a_recipient_required" in _names(_errors(report))
    report = _run([_alert(events=["bogus"])])
    assert "monit_alert_alr_events" in _names(_errors(report))
    assert not _errors(_run([_alert(events=["link", "pid"])]))
    assert not _errors(_run([_alert(events=[])]))


def test_test_needs_condition_and_valid_enums() -> None:
    report = _run([res("monit.tests", "t")])
    assert "monit_test_t_condition_required" in _names(_errors(report))
    assert "monit_test_tst_type" in _names(_errors(_run([_test(type="Permission")])))
    assert not _errors(_run([_test(type="Permisssion")]))
    assert "monit_test_tst_action" in _names(_errors(_run([_test(action="reboot")])))


def test_exec_action_without_path_is_a_warning() -> None:
    assert _names(_warnings(_run([_test(action="exec")]))) == ["monit_test_tst_exec_path"]
    assert not _warnings(_run([_test(action="exec", path="/opt/example/run.sh")]))


@pytest.mark.parametrize("kind", ["filesystem", "custom", "file", "fifo", "directory"])
def test_path_is_required_for_path_types(kind: str) -> None:
    assert "monit_service_svc_path_required" in _names(_errors(_run([_svc(type=kind)])))
    assert not _errors(_run([_svc(type=kind, path="/x")]))


@pytest.mark.parametrize(
    ("config", "check"),
    [
        ({"type": "process"}, "monit_service_svc_process_target"),
        ({"type": "host"}, "monit_service_svc_host_address"),
        ({"type": "network"}, "monit_service_svc_network_target"),
    ],
)
def test_unprobed_service_rules_are_warnings_not_errors(config: dict[str, Any], check: str) -> None:
    report = _run([_svc(**config)])
    assert _names(_warnings(report)) == [check] and not _errors(report)


def test_unprobed_rules_are_satisfied() -> None:
    for config in (
        {"type": "process", "pidfile": "/var/run/x.pid"},
        {"type": "process", "match": "x"},
        {"type": "host", "address": "192.0.2.1"},
        {"type": "network", "interface": "lan"},
        {"type": "network", "address": "192.0.2.1"},
    ):
        assert not _warnings(_run([_svc(**config)]))


def test_service_enum_and_int_errors() -> None:
    names = _names(_errors(_run([_svc(type="nope", timeout="x")])))
    assert "monit_service_svc_type" in names and "monit_service_svc_timeout" in names


# -- references ----------------------------------------------------------------------


def test_references_resolve_in_all_three_forms() -> None:
    tests = [_test("a"), _test("b"), _test("c")]
    svc = _svc(tests=["a", "tests.b", "monit.tests.c"], depends=["base", "services.base"])
    assert not _errors(_run([*tests, svc, _svc("base")]))


def test_unknown_or_wrong_type_references_are_errors() -> None:
    report = _run([_test("a"), _svc(tests=["ghost", "services.a"], depends=["tests.a", "a"])])
    names = _names(_errors(report))
    assert names.count("monit_service_svc_tests_ref") == 2
    assert names.count("monit_service_svc_depends_ref") == 2


def test_depends_self_and_cycle_are_errors() -> None:
    report = _run([_svc("a", depends=["a"])])
    assert "monit_service_a_depends_self" in _names(_errors(report))
    report = _run([_svc("a", depends=["b"]), _svc("b", depends=["c"]), _svc("c", depends=["a"])])
    names = _names(_errors(report))
    assert names == ["monit_service_a_depends_cycle"]
    assert "a -> b -> c -> a" in _errors(report)[0].message
    assert not _errors(_run([_svc("a", depends=["b"]), _svc("b")]))


def test_messages_never_carry_values() -> None:
    report = _run([_svc(timeout=LITERAL, description=1)])
    assert LITERAL not in " ".join(c.message for c in report.results)
