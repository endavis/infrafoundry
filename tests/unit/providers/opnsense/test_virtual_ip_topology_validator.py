"""Unit tests for ``VirtualIPTopologyValidator`` (#1391).

Coverage:
    - VHID reuse across interfaces (WARNING), same-interface reuse allowed.
    - CARP address outside the interface's static network (ERROR), inside passes.
    - Skips: non-static, missing assignment, no index, link-local, family mismatch.
    - ipalias network allowance, dotted interface refs, malformed VIPs.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators._xref import build_xref_index
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext
from infrafoundry.providers.opnsense.validators.virtual_ip_topology_validator import (
    VirtualIPTopologyValidator,
)


def _vip(name: str, mode: str, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {"mode": mode, "interface": "lan", "network": "24"}
    config.update(overrides)
    return ResourceConfig(
        name=name, type="interfaces.virtual_ips", provider="opnsense", config=config
    )


def _carp(name: str, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {"address": "192.0.2.10", "vhid": 1, "password": "x"}
    config.update(overrides)
    return _vip(name, "carp", **config)


def _ipalias(name: str, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {"address": "198.51.100.2"}
    config.update(overrides)
    return _vip(name, "ipalias", **config)


def _assignment(
    name: str, ipv4: dict[str, Any] | None = None, ipv6: dict[str, Any] | None = None
) -> ResourceConfig:
    config: dict[str, Any] = {"device": "vtnet1"}
    if ipv4 is not None:
        config["ipv4"] = ipv4
    if ipv6 is not None:
        config["ipv6"] = ipv6
    return ResourceConfig(
        name=name, type="interfaces.assignments", provider="opnsense", config=config
    )


_LAN = _assignment("lan", ipv4={"type": "static", "address": "192.0.2.1", "subnet": 24})


def _run(
    vips: list[ResourceConfig],
    others: list[ResourceConfig] | None = None,
    *,
    with_index: bool = True,
) -> ValidationReport:
    report = ValidationReport()
    index = build_xref_index([*vips, *(others or [])]) if with_index else None
    context = OPNsenseValidationContext(
        resources=[], existing_interfaces={}, virtual_ips=vips, index=index
    )
    VirtualIPTopologyValidator(report).validate(context)
    return report


def _failures(report: ValidationReport, level: ValidationLevel) -> list[Any]:
    return [r for r in report.results if not r.passed and r.level == level]


class TestVhidReuse:
    def test_reuse_across_interfaces_warns_naming_both(self) -> None:
        report = _run([_carp("a", vhid=5), _carp("b", vhid=5, interface="opt1")])
        warnings = _failures(report, ValidationLevel.WARNING)
        assert len(warnings) == 1
        assert warnings[0].check_name == "virtual_ip_vhid_5_reused"
        assert "'a' on 'lan'" in warnings[0].message
        assert "'b' on 'opt1'" in warnings[0].message

    def test_string_and_int_vhid_match(self) -> None:
        report = _run([_carp("a", vhid="5"), _carp("b", vhid=5, interface="opt1")])
        assert len(_failures(report, ValidationLevel.WARNING)) == 1

    def test_same_interface_not_warned(self) -> None:
        report = _run(
            [_carp("a", vhid=5), _carp("b", vhid=5, address="192.0.2.11"), _carp("c", vhid=5)]
        )
        assert _failures(report, ValidationLevel.WARNING) == []

    def test_three_vips_two_interfaces_single_warning(self) -> None:
        report = _run(
            [
                _carp("a", vhid=7),
                _carp("b", vhid=7, address="192.0.2.11"),
                _carp("c", vhid=7, interface="opt1"),
            ]
        )
        warnings = _failures(report, ValidationLevel.WARNING)
        assert len(warnings) == 1
        for name in ("'a'", "'b'", "'c'"):
            assert name in warnings[0].message

    def test_invalid_vhid_and_non_carp_ignored(self) -> None:
        report = _run(
            [
                _carp("a", vhid="x"),
                _carp("b", vhid=0, interface="opt1"),
                _carp("c", vhid=300, interface="opt2"),
                _carp("d", vhid=None, interface="opt3"),
                _carp("e", vhid=True, interface="opt4"),
                _ipalias("f", vhid=1, interface="opt5"),
                _ipalias("g", vhid=1, interface="opt6"),
            ]
        )
        assert report.results == []


class TestSubnetMembership:
    def test_outside_subnet_errors(self) -> None:
        report = _run([_carp("a", address="198.51.100.5")], [_LAN])
        errors = _failures(report, ValidationLevel.ERROR)
        assert len(errors) == 1
        assert errors[0].check_name == "virtual_ip_a_subnet"
        for text in ("'a'", "198.51.100.5", "'lan'", "192.0.2.0/24"):
            assert text in errors[0].message

    def test_inside_subnet_passes(self) -> None:
        report = _run([_carp("a")], [_LAN])
        assert _failures(report, ValidationLevel.ERROR) == []
        assert [r.passed for r in report.results] == [True]
        assert report.results[0].level == ValidationLevel.INFO

    def test_ipv6_inside_and_outside(self) -> None:
        lan6 = _assignment("lan", ipv6={"type": "static", "address": "2001:db8:1::1", "subnet": 64})
        ok = _run([_carp("a", address="2001:db8:1::10", network="64")], [lan6])
        bad = _run([_carp("a", address="2001:db8:2::10", network="64")], [lan6])
        assert _failures(ok, ValidationLevel.ERROR) == []
        assert len(_failures(bad, ValidationLevel.ERROR)) == 1

    def test_link_local_skipped(self) -> None:
        lan6 = _assignment("lan", ipv6={"type": "static", "address": "2001:db8:1::1", "subnet": 64})
        assert _run([_carp("a", address="fe80::1", network="64")], [lan6]).results == []

    def test_unknown_interface_address_skipped(self) -> None:
        dhcp = _assignment("lan", ipv4={"type": "dhcp"})
        none = _assignment("lan", ipv4={"type": "none"})
        track = _assignment("lan", ipv6={"type": "track-interface"})
        v6 = _carp("a", address="2001:db8:1::10", network="64")
        far = _carp("a", address="198.51.100.5")
        assert _run([far], [dhcp]).results == []
        assert _run([far], [none]).results == []
        assert _run([v6], [track]).results == []
        assert _run([far]).results == []  # no assignment (live-only interface)
        assert _run([far], [_LAN], with_index=False).results == []

    def test_family_mismatch_skipped(self) -> None:
        v6 = _carp("a", address="2001:db8:1::10", network="64")
        assert _run([v6], [_LAN]).results == []

    def test_dotted_interface_resolves(self) -> None:
        report = _run(
            [_carp("a", address="198.51.100.5", interface="interfaces.assignments.lan")], [_LAN]
        )
        assert len(_failures(report, ValidationLevel.ERROR)) == 1

    def test_ipalias_network_allows(self) -> None:
        report = _run(
            [_carp("a", address="198.51.100.5"), _ipalias("alias", address="198.51.100.2")],
            [_LAN],
        )
        assert _failures(report, ValidationLevel.ERROR) == []

    def test_ipalias_on_other_interface_does_not_allow(self) -> None:
        report = _run(
            [
                _carp("a", address="198.51.100.5"),
                _ipalias("alias", address="198.51.100.2", interface="opt1"),
            ],
            [_LAN],
        )
        assert len(_failures(report, ValidationLevel.ERROR)) == 1

    def test_ipalias_and_proxyarp_not_checked(self) -> None:
        report = _run(
            [
                _ipalias("a", address="198.51.100.5"),
                _vip("p", "proxyarp", address="198.51.100.6", network="32"),
            ],
            [_LAN],
        )
        assert report.results == []

    def test_malformed_vips_do_not_raise(self) -> None:
        report = _run(
            [
                _carp("a", address="not-an-ip"),
                _carp("b", address=None),
                _carp("c", interface=None),
                _carp("d", interface=""),
            ],
            [_LAN],
        )
        assert report.results == []

    def test_malformed_assignment_skipped(self) -> None:
        bad = _assignment("lan", ipv4={"type": "static", "address": "bogus", "subnet": 24})
        nosub = _assignment("lan", ipv4={"type": "static", "address": "192.0.2.1"})
        far = _carp("a", address="198.51.100.5")
        assert _run([far], [bad]).results == []
        assert _run([far], [nosub]).results == []


def test_empty_virtual_ips_gives_no_checks() -> None:
    assert _run([], [_LAN]).results == []
