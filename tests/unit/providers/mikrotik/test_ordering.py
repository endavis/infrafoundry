"""Table-driven tests for MikroTik phase ordering and the lock-out refusals."""

import ipaddress
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.mikrotik.components.diff import TypeDiff, compute_type_diff
from infrafoundry.providers.mikrotik.components.ordering import (
    Step,
    check_management_path,
    check_service_changes,
    end_state,
    live_management_path,
    order_changes,
)
from infrafoundry.providers.mikrotik.schema import (
    DEPENDENCY_ORDER,
    SPECS,
    desired_from_resources,
)

from .conftest import MGMT_IP, FakeRouterOS, bootstrap_https, resource, with_https_services

MGMT = ipaddress.ip_address(MGMT_IP)


def _live(fake: FakeRouterOS) -> dict[str, list[dict[str, str]]]:
    return {t: fake.tables.get(spec.path, []) for t, spec in SPECS.items()}


def _diffs(
    fake: FakeRouterOS,
    resources: list[ResourceConfig],
    managed: dict[str, set[Any]] | None = None,
) -> dict[str, TypeDiff]:
    diffs: dict[str, TypeDiff] = {}
    for type_name in DEPENDENCY_ORDER:
        spec = SPECS[type_name]
        desired = desired_from_resources([r for r in resources if r.type == type_name])
        keys = (managed or {}).get(type_name)
        if not desired and keys is None:
            continue
        diffs[type_name] = compute_type_diff(
            spec, desired, fake.tables.get(spec.path, []), add_only=False, managed_keys=keys
        )
    return diffs


def _steps(
    fake: FakeRouterOS, resources: list[ResourceConfig], managed: dict[str, set[Any]] | None = None
) -> list[Step]:
    diffs = _diffs(fake, resources, managed)
    live = _live(fake)
    return order_changes(diffs, live, live_management_path(live, MGMT))


def _refusals(fake: FakeRouterOS, resources: list[ResourceConfig]) -> list[str]:
    diffs = _diffs(fake, resources)
    return check_management_path(end_state(diffs, _live(fake)), MGMT).refusals


def _phases(steps: list[Step]) -> str:
    return "".join(s.phase for s in steps)


def test_new_filtering_bridge_enables_filtering_after_everything_else(
    factory: FakeRouterOS,
) -> None:
    resources = [
        resource("interface.bridge", "br2", **{"vlan-filtering": True}),
        resource("interface.bridge.vlan", "v10", bridge="br2", **{"vlan-ids": 10}),
        resource("interface.bridge.port", "p", interface="ether6", bridge="br2", pvid=10),
    ]

    steps = _steps(factory, resources)

    assert _phases(steps) == "BBBC"
    assert [s.type_name for s in steps[:3]] == [
        "interface.bridge",
        "interface.bridge.vlan",
        "interface.bridge.port",
    ]
    assert steps[0].body["vlan-filtering"] == "no"
    assert steps[3].body == {"vlan-filtering": "yes"}


def test_member_removal_splits_union_then_exact(wan_edge: FakeRouterOS) -> None:
    res = resource(
        "interface.bridge.vlan",
        "v10",
        bridge="bridge",
        **{"vlan-ids": 10, "tagged": ["bridge", "ether3"]},
    )

    steps = _steps(wan_edge, [res])

    assert [(s.phase, s.body) for s in steps] == [
        ("B", {"tagged": "bridge,ether3,ether4"}),
        ("D", {"tagged": "bridge,ether3"}),
    ]


def test_pure_member_removal_is_only_exact(wan_edge: FakeRouterOS) -> None:
    res = resource(
        "interface.bridge.vlan", "v10", bridge="bridge", **{"vlan-ids": 10, "tagged": ["bridge"]}
    )
    assert _phases(_steps(wan_edge, [res])) == "D"


def test_pure_member_addition_is_only_widening(wan_edge: FakeRouterOS) -> None:
    res = resource(
        "interface.bridge.vlan",
        "v10",
        bridge="bridge",
        **{"vlan-ids": 10, "tagged": ["bridge", "ether4", "ether3"]},
    )
    assert _phases(_steps(wan_edge, [res])) == "B"


def test_pvid_on_filtering_bridge_lands_in_narrowing(wan_edge: FakeRouterOS) -> None:
    res = resource("interface.bridge.port", "p", interface="ether2", bridge="bridge", pvid=11)
    assert _phases(_steps(wan_edge, [res])) == "D"


def test_pvid_on_non_filtering_bridge_lands_in_creation_phase(factory: FakeRouterOS) -> None:
    res = resource("interface.bridge.port", "p", interface="ether2", bridge="bridge", pvid=11)
    assert _phases(_steps(factory, [res])) == "B"


def test_pvid_moves_to_creation_phase_when_filtering_goes_off(wan_edge: FakeRouterOS) -> None:
    resources = [
        resource("interface.bridge", "bridge", **{"vlan-filtering": False}),
        resource("interface.bridge.port", "p", interface="ether2", bridge="bridge", pvid=11),
    ]
    assert _phases(_steps(wan_edge, resources)) == "AB"


def test_disabling_filtering_runs_first(wan_edge: FakeRouterOS) -> None:
    resources = [
        resource("interface.bridge", "bridge", **{"vlan-filtering": False}, comment="x"),
        resource("interface.vlan", "vlan99", interface="bridge", **{"vlan-id": 99}, mtu=1400),
    ]
    steps = _steps(wan_edge, resources)
    assert steps[0].phase == "A" and steps[0].body == {"vlan-filtering": "no"}
    assert _phases(steps) == "ADD"


def test_enabling_filtering_on_existing_bridge_runs_after_creates(factory: FakeRouterOS) -> None:
    resources = [
        resource("interface.bridge", "bridge", **{"vlan-filtering": True}),
        resource("interface.bridge.vlan", "v10", bridge="bridge", **{"vlan-ids": 10}),
    ]
    assert _phases(_steps(factory, resources)) == "BC"


def test_deletes_run_in_reverse_dependency_order(wan_edge: FakeRouterOS) -> None:
    managed: dict[str, set[Any]] = {
        t: set(_keys(wan_edge, t)) for t in DEPENDENCY_ORDER if t != "ip.service"
    }
    steps = _steps(wan_edge, [], managed)
    types = [s.type_name for s in steps]
    assert set(_phases(steps)) == {"E"}
    assert types.index("ip.address") < types.index("interface.vlan")
    assert types.index("interface.vlan") < types.index("interface.bridge")
    assert types.index("interface.bridge.port") < types.index("interface.bridge")
    assert types[-1] == "interface.bridge"


def _keys(fake: FakeRouterOS, type_name: str) -> set[Any]:
    from infrafoundry.providers.mikrotik.schema import key_of

    spec = SPECS[type_name]
    return {k for r in fake.tables[spec.path] if (k := key_of(spec, r)) is not None}


def test_moving_management_to_a_new_address_deletes_the_old_one_last(
    wan_edge: FakeRouterOS,
) -> None:
    new = resource("ip.address", "mgmt", address="192.0.2.2/25", interface="ether5")
    managed: dict[str, set[Any]] = {"ip.address": {("192.0.2.2/24",)}}

    steps = _steps(wan_edge, [new], managed)

    assert [(s.phase, s.kind, s.key) for s in steps] == [
        ("B", "create", ("192.0.2.2/25",)),
        ("E", "delete", ("192.0.2.2/24",)),
    ]
    assert steps[1].management is True
    assert _refusals(wan_edge, [new]) == []


def test_management_changes_sort_last_within_a_phase(wan_edge: FakeRouterOS) -> None:
    wan_edge.tables["interface/vlan"].append(
        {".id": "*8", "name": "vlan50", "interface": "bridge", "vlan-id": "50", "disabled": "false"}
    )
    resources = [
        resource("interface.vlan", "vlan99", interface="bridge", **{"vlan-id": 99}, mtu=1400),
        resource("interface.vlan", "vlan50", interface="bridge", **{"vlan-id": 50}, mtu=1400),
    ]

    steps = _steps(wan_edge, resources)

    assert [(s.key, s.management) for s in steps] == [(("vlan50",), False), (("vlan99",), True)]


# --- lock-out refusals ---------------------------------------------------------


def test_refuses_when_no_address_holds_the_management_address(wan_edge: FakeRouterOS) -> None:
    res = resource("ip.address", "other", address="198.51.100.2/24", interface="vlan99")
    diffs = _diffs(wan_edge, [res], {"ip.address": {("192.0.2.2/24",)}})
    refusals = check_management_path(end_state(diffs, _live(wan_edge)), MGMT).refusals
    assert refusals and "no address" in refusals[0]


def test_refuses_management_vlan_without_bridge_tagged(wan_edge: FakeRouterOS) -> None:
    res = resource(
        "interface.bridge.vlan", "v99", bridge="bridge", **{"vlan-ids": 99, "tagged": ["ether4"]}
    )
    assert "tagged" in "\n".join(_refusals(wan_edge, [res]))


def test_refuses_management_vlan_without_member_port(wan_edge: FakeRouterOS) -> None:
    res = resource(
        "interface.bridge.vlan",
        "v99",
        bridge="bridge",
        **{"vlan-ids": 99, "tagged": ["bridge"], "untagged": []},
    )
    port = resource("interface.bridge.port", "p1", interface="ether1", bridge="bridge", pvid=5)
    assert "member port" in "\n".join(_refusals(wan_edge, [res, port]))


def test_pvid_makes_a_port_a_member(wan_edge: FakeRouterOS) -> None:
    res = resource(
        "interface.bridge.vlan",
        "v99",
        bridge="bridge",
        **{"vlan-ids": 99, "tagged": ["bridge"], "untagged": []},
    )
    assert _refusals(wan_edge, [res]) == []


def test_refuses_management_interface_that_is_a_bridge_slave(wan_edge: FakeRouterOS) -> None:
    res = resource("interface.bridge.port", "p", interface="vlan99", bridge="bridge")
    assert "bridge port" in "\n".join(_refusals(wan_edge, [res]))


def test_refuses_bridge_management_without_port_on_bridge_pvid(factory: FakeRouterOS) -> None:
    factory.tables["ip/address"][0]["address"] = "192.0.2.2/24"
    resources = [
        resource("interface.bridge", "bridge", **{"vlan-filtering": True}),
        *[
            resource(
                "interface.bridge.port", f"p{i}", interface=f"ether{i}", bridge="bridge", pvid=10
            )
            for i in range(1, 6)
        ],
    ]
    assert "pvid" in "\n".join(_refusals(factory, resources))
    resources[1:] = []
    assert _refusals(factory, resources) == []


def _dhcp_edge(wan_edge: FakeRouterOS) -> FakeRouterOS:
    """The edge switch with the management address leased to vlan99 through DHCP."""
    wan_edge.tables["ip/address"] = [
        {
            ".id": "*30",
            "address": "192.0.2.2/24",
            "interface": "vlan99",
            "disabled": "false",
            "dynamic": "true",
        }
    ]
    wan_edge.tables["ip/dhcp-client"] = [
        {".id": "*50", "interface": "vlan99", "disabled": "false", "dynamic": "false"}
    ]
    return wan_edge


def test_dhcp_held_address_with_intact_path_is_allowed(wan_edge: FakeRouterOS) -> None:
    fake = _dhcp_edge(wan_edge)
    res = resource("interface.bridge.port", "p2", interface="ether2", bridge="bridge", pvid=12)
    assert _refusals(fake, [res]) == []


def test_dhcp_held_address_refuses_bridge_dropped_from_vlan_tagged(
    wan_edge: FakeRouterOS,
) -> None:
    fake = _dhcp_edge(wan_edge)
    res = resource(
        "interface.bridge.vlan", "v99", bridge="bridge", **{"vlan-ids": 99, "tagged": ["ether4"]}
    )
    assert "tagged" in "\n".join(_refusals(fake, [res]))


def test_dhcp_held_address_refuses_vlan_without_member_port(wan_edge: FakeRouterOS) -> None:
    fake = _dhcp_edge(wan_edge)
    res = resource(
        "interface.bridge.vlan",
        "v99",
        bridge="bridge",
        **{"vlan-ids": 99, "tagged": ["bridge"], "untagged": []},
    )
    port = resource("interface.bridge.port", "p1", interface="ether1", bridge="bridge", pvid=5)
    assert "member port" in "\n".join(_refusals(fake, [res, port]))


def test_dhcp_held_address_refuses_bridge_slave(wan_edge: FakeRouterOS) -> None:
    fake = _dhcp_edge(wan_edge)
    res = resource("interface.bridge.port", "p", interface="vlan99", bridge="bridge")
    assert "bridge port" in "\n".join(_refusals(fake, [res]))


def test_dhcp_client_disabled_is_refused(wan_edge: FakeRouterOS) -> None:
    fake = _dhcp_edge(wan_edge)
    res = resource("ip.dhcp-client", "mgmt", interface="vlan99", disabled=True)
    assert "dhcp-client" in "\n".join(_refusals(fake, [res]))


def test_dhcp_client_removed_is_refused(wan_edge: FakeRouterOS) -> None:
    fake = _dhcp_edge(wan_edge)
    diffs = _diffs(fake, [], {"ip.dhcp-client": {("vlan99",)}})
    refusals = check_management_path(end_state(diffs, _live(fake)), MGMT).refusals
    assert "dhcp-client" in "\n".join(refusals)


def test_disabling_the_http_service_is_refused(wan_edge: FakeRouterOS) -> None:
    diffs = _diffs(wan_edge, [resource("ip.service", "www", disabled=False)])
    assert check_service_changes(diffs["ip.service"], "http", 80).refusals == []
    diffs = _diffs(wan_edge, [resource("ip.service", "www-ssl", disabled=True)])
    assert check_service_changes(diffs["ip.service"], "https", 443).refusals
    assert check_service_changes(diffs["ip.service"], "http", 80).refusals == []


def test_http_service_disable_refused() -> None:
    fake = FakeRouterOS(
        {"ip/service": [{".id": "*1", "name": "www", "port": "80", "disabled": "false"}]}
    )
    diffs = _diffs(fake, [resource("ip.service", "www", disabled=True)])
    assert check_service_changes(diffs["ip.service"], "http", 80).refusals


def test_service_port_mismatch_refused(wan_edge: FakeRouterOS) -> None:
    diffs = _diffs(wan_edge, [resource("ip.service", "www-ssl", port=8443)])
    assert "port" in check_service_changes(diffs["ip.service"], "https", 443).refusals[0]


def test_service_address_change_only_warns(wan_edge: FakeRouterOS) -> None:
    diffs = _diffs(wan_edge, [resource("ip.service", "www-ssl", address="192.0.2.0/24")])
    check = check_service_changes(diffs["ip.service"], "https", 443)
    assert check.refusals == [] and check.warnings


def test_other_services_may_change_freely(wan_edge: FakeRouterOS) -> None:
    diffs = _diffs(wan_edge, [resource("ip.service", "www", disabled=False)])
    check = check_service_changes(diffs["ip.service"], "https", 443)
    assert check.refusals == []


def test_certificate_create_is_followed_by_its_sign_before_services(
    factory: FakeRouterOS,
) -> None:
    steps = _steps(with_https_services(factory), bootstrap_https())
    assert [(s.phase, s.kind, s.type_name) for s in steps] == [
        ("B", "create", "certificate"),
        ("B", "sign", "certificate"),
        ("F", "update", "ip.service"),
        ("F", "update", "ip.service"),
    ]
    assert steps[0].key == steps[1].key


def test_sign_only_change_is_one_b_step(factory: FakeRouterOS) -> None:
    factory.tables["certificate"] = [{".id": "*9", "name": "c1", "common-name": "x"}]
    steps = _steps(factory, [resource("certificate", "c1", **{"common-name": "x"})])
    assert [(s.phase, s.kind, s.live_id) for s in steps] == [("B", "sign", "*9")]


def test_certificate_precedes_services_in_dependency_order() -> None:
    assert DEPENDENCY_ORDER.index("certificate") < DEPENDENCY_ORDER.index("ip.service")
