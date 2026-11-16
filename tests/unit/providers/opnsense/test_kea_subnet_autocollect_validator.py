"""Unit tests for ``KeaSubnetAutoCollectValidator`` (#1432)."""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators import KeaSubnetAutoCollectValidator
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext


def _run(*resources: ResourceConfig) -> ValidationReport:
    report = ValidationReport()
    KeaSubnetAutoCollectValidator(report).validate(
        OPNsenseValidationContext(resources=list(resources))
    )
    return report


def _warnings(*resources: ResourceConfig) -> list[Any]:
    return [r for r in _run(*resources).results if r.level == ValidationLevel.WARNING]


def _errors(*resources: ResourceConfig) -> list[Any]:
    return [r for r in _run(*resources).results if r.level == ValidationLevel.ERROR]


def _subnet(name: str = "lan", type_: str = "kea.dhcp4.subnets", **config: Any) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type=type_,
        provider="opnsense",
        config={"subnet": "192.0.2.0/24", **config},
    )


def test_single_conflict_warns() -> None:
    res = _subnet(auto_collect=True, dns_servers=["198.51.100.53"])
    warnings = _warnings(res)
    assert len(warnings) == 1
    assert "lan" in warnings[0].message
    assert "dns_servers" in warnings[0].message
    assert _errors(res) == []


def test_all_keys_named_in_order() -> None:
    res = _subnet(
        auto_collect=True,
        ntp_servers=["198.51.100.123"],
        dns_servers=["198.51.100.53"],
        routers=["192.0.2.1"],
    )
    warnings = _warnings(res)
    assert len(warnings) == 1
    assert "routers, dns_servers, ntp_servers" in warnings[0].message


def test_auto_collect_false_no_warning() -> None:
    assert _warnings(_subnet(auto_collect=False, dns_servers=["198.51.100.53"])) == []


def test_auto_collect_absent_no_warning() -> None:
    assert _warnings(_subnet(dns_servers=["198.51.100.53"], routers=["192.0.2.1"])) == []


def test_non_collected_options_no_warning() -> None:
    res = _subnet(auto_collect=True, domain_search=["example.com"], domain_name="example.com")
    assert _warnings(res) == []


def test_no_options_no_warning() -> None:
    assert _warnings(_subnet(auto_collect=True)) == []


def test_empty_list_no_warning() -> None:
    assert _warnings(_subnet(auto_collect=True, dns_servers=[])) == []


def test_non_bool_truthy_auto_collect_no_warning() -> None:
    assert _warnings(_subnet(auto_collect="yes", dns_servers=["198.51.100.53"])) == []


def test_dhcp6_subnet_ignored() -> None:
    res = _subnet(type_="kea.dhcp6.subnets", auto_collect=True, dns_servers=["198.51.100.53"])
    assert _warnings(res) == []


def test_two_subnets_two_warnings() -> None:
    a = _subnet("a", auto_collect=True, routers=["192.0.2.1"])
    b = _subnet("b", auto_collect=True, ntp_servers=["198.51.100.123"])
    warnings = _warnings(a, b)
    assert len(warnings) == 2
    assert len({w.check_name for w in warnings}) == 2
