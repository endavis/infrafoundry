"""QnapConfigManager with port resources: plan, apply, read-back, destroy and scope."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.providers.qnap import QnapProvider
from infrafoundry.providers.qnap.components.diff import QnapPlanError
from infrafoundry.providers.qnap.components.manager import QnapConfigManager

from .config_fake import FakeQnapConfig
from .conftest import lag, manager_for, port, vlan

pytestmark = pytest.mark.unit


def _mgr(
    fake: FakeQnapConfig, mp: pytest.MonkeyPatch, tmp_path: Path, **s: Any
) -> QnapConfigManager:
    return manager_for(fake, mp, tmp_path, **s)


def _paths(fake: FakeQnapConfig) -> list[str]:
    return [p for m, p, _ in fake.calls if m == "GET"]


# -- plan


def test_alias_change_plans_one_phase_h_step_and_applies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    mgr = _mgr(fake, monkeypatch, tmp_path)
    plan = mgr.plan("test", [port(port=5, alias="renamed-5")])
    assert not plan.refusals and [s.phase for s in plan.steps] == ["H"]
    assert "phase H (update port settings): 1 step(s)" in plan.summary_lines()
    assert "port 5: set alias" in plan.summary_lines()
    result = mgr.apply("test", plan)
    assert result.success, result.error
    [body] = fake.port_writes()
    live = {**fake.port_rows[5], "Alias": "spare-5"}  # read back below has the new alias
    expected = {**live, "Alias": "renamed-5", "Speed": "autoNegMode", "AutoMode": True}
    assert body == [{"idx": "5", "data": expected}]
    assert fake.timeouts == [("portlist", 60)]
    assert [o.address for o in result.outcomes] == ["qnap_port.p5"]
    assert result.counts == {"create": 0, "update": 1, "delete": 0}
    again = mgr.plan("test", [port(port=5, alias="renamed-5")])
    assert not again.has_changes


def test_converged_ports_read_ports_once_and_write_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    fake.port_rows[5]["Alias"] = "spare-5"
    plan = _mgr(fake, monkeypatch, tmp_path).plan("test", [port(port=5, alias="spare-5")])
    assert not plan.has_changes and not plan.steps
    assert _paths(fake).count("ports") == 1 and "ip/ipv4/interface" not in _paths(fake)


def test_plan_with_changes_reads_ports_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    _mgr(fake, monkeypatch, tmp_path).plan("test", [port(port=5, alias="x")])
    assert _paths(fake).count("ports") == 1


def test_speed_auto_reads_back_clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeQnapConfig()
    fake.port_rows[5].update(AutoMode=False, Speed="tenGB")
    mgr = _mgr(fake, monkeypatch, tmp_path, protected_ports=(1,))
    result = mgr.apply("test", mgr.plan("test", [port(port=5, speed="auto")]))
    assert result.success, result.error
    assert fake.port_rows[5]["AutoMode"] is True


def test_ignored_write_fails_the_apply_and_names_the_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    fake.ignore_writes.add(("PUT", "portlist"))
    mgr = _mgr(fake, monkeypatch, tmp_path)
    result = mgr.apply("test", mgr.plan("test", [port("uplink-5", port=5, alias="x")]))
    assert not result.success and result.error is not None
    assert "port 'uplink-5'" in result.error


def test_port_only_plan_with_no_management_vlan_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig(mgmt_key="not-a-vlan")
    plan = _mgr(fake, monkeypatch, tmp_path, management_vlan=None).plan(
        "test", [port(port=5, alias="x")]
    )
    assert any("cannot determine the management VLAN" in r for r in plan.refusals)


def test_watched_port_shutdown_is_refused_and_overridable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()  # VLAN 1 holds every port, so every port is watched
    plan = _mgr(fake, monkeypatch, tmp_path).plan("test", [port(port=5, shutdown=True)])
    assert any("shuts down port 5" in r for r in plan.refusals)
    mgr = _mgr(fake, monkeypatch, tmp_path, allow_lockout_risk=True)
    plan = mgr.plan("test", [port(port=5, shutdown=True)])
    assert not plan.refusals and any("lock-out risk allowed" in w for w in plan.warnings)


def test_protected_ports_narrow_the_watched_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    mgr = _mgr(fake, monkeypatch, tmp_path, protected_ports=(1,))
    assert not mgr.plan("test", [port(port=5, shutdown=True)]).refusals
    assert mgr.plan("test", [port(port=1, shutdown=True)]).refusals


def test_lag_in_protected_ports_watches_its_members(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    fake.add_lag(1, [5, 6])
    mgr = _mgr(fake, monkeypatch, tmp_path, protected_ports=("lag1",))
    assert mgr.plan("test", [port(port=5, speed="10G")]).refusals
    assert not mgr.plan("test", [port(port=2, speed="10G")]).refusals


def test_mtu_is_refused_then_warns_that_it_is_switch_wide(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    fake.mtu_switch_wide = True
    resources = [port(port=5, mtu=9000)]
    plan = _mgr(fake, monkeypatch, tmp_path).plan("test", resources)
    assert any("switch-wide" in r for r in plan.refusals)
    mgr = _mgr(fake, monkeypatch, tmp_path, allow_lockout_risk=True)
    result = mgr.apply("test", mgr.plan("test", resources))
    assert result.success, result.error
    assert [s.phase for s in result.completed] == ["I"]
    assert any("MTU is switch-wide" in w and "1" in w for w in result.warnings)


def test_per_port_mtu_gives_no_spread_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    mgr = _mgr(fake, monkeypatch, tmp_path, allow_lockout_risk=True)
    result = mgr.apply("test", mgr.plan("test", [port(port=5, mtu=9000)]))
    assert result.success, result.error
    assert not any("switch-wide" in w and "undeclared" in w for w in result.warnings)


def test_fec_rule_blocks_the_plan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeQnapConfig()
    for p in (1, 2):
        fake.port_rows[p]["FEC"] = "auto"
    with pytest.raises(QnapPlanError, match="at least two"):
        _mgr(fake, monkeypatch, tmp_path, allow_lockout_risk=True).plan(
            "test", [port(port=1, fec="none")]
        )


def test_port_steps_follow_vlan_and_lag_steps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    plan = _mgr(fake, monkeypatch, tmp_path).plan(
        "test",
        [
            port(port=5, alias="x"),
            vlan(id=30, tagged=[1]),
            lag("up", group=1, mode="lacp", members=[6, 7]),
        ],
    )
    assert [s.phase for s in plan.steps] == ["A", "C", "H"]


def test_vlan_member_beyond_the_physical_count_is_rejected_with_lag_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: LAG rows in ``GET ports`` made port 9 look physical."""
    fake = FakeQnapConfig(ports=8, start_index=12)
    fake.add_lag(1, [5, 6])
    with pytest.raises(QnapPlanError, match="port 9 does not exist"):
        _mgr(fake, monkeypatch, tmp_path).plan("test", [vlan(id=30, tagged=[9])])


# -- scope


def test_targets_filter_ports_and_an_unmatched_target_makes_no_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    resources = [port("a", port=5, alias="x"), port("b", port=6, alias="y")]
    plan = _mgr(fake, monkeypatch, tmp_path).plan("test", resources, target_resources=["a"])
    assert [c.key for c in plan.diffs["port"].changes] == [(5,)]
    other = FakeQnapConfig()
    _mgr(other, monkeypatch, tmp_path).plan("test", resources, target_resources=["zzz"])
    assert other.calls == []


def test_managed_port_rows_alone_make_no_device_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    plan = _mgr(fake, monkeypatch, tmp_path).plan(
        "test", [], managed_resources={"port": [port("old", port=5, alias="x")]}
    )
    assert not plan.has_changes and fake.calls == []


def test_a_port_row_that_leaves_the_yaml_is_released_never_deleted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    mgr = _mgr(fake, monkeypatch, tmp_path)
    old = port("old", port=5, alias="x")
    plan = mgr.plan("test", [vlan(id=30, tagged=[1])], managed_resources={"port": [old]})
    result = mgr.apply("test", plan)
    assert result.success, result.error
    assert result.released == [{"resource_type": "port", "name": "old"}]
    assert fake.port_writes() == []


# -- destroy and ids


def test_destroy_never_writes_portlist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeQnapConfig()
    result = _mgr(fake, monkeypatch, tmp_path).destroy(
        "test", [port(port=5, alias="x"), vlan(id=10, tagged=[1, 2])]
    )
    assert result.success, result.error
    assert fake.port_writes() == [] and 10 not in fake.vlans
    assert fake.port_rows[5]["Alias"] == "spare-5"


def test_destroy_with_only_ports_makes_no_device_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    _mgr(fake, monkeypatch, tmp_path).destroy("test", [port(port=5, alias="x")])
    assert fake.calls == []


def test_resource_ids_include_existing_ports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    ids = _mgr(fake, monkeypatch, tmp_path).resource_ids(
        "test", [port("p5", port=5, alias="x"), port("gone", port=40, alias="y")]
    )
    assert ids == {"p5": "5"}


# -- provider


def test_provider_registers_port_and_deletes_only_vlan_and_lacp(tmp_path: Path) -> None:
    provider = QnapProvider(tmp_path, tmp_path / "generated")
    assert "port" in provider.get_resource_types()
    assert provider.get_terraform_resource_types()["port"] == ["qnap_port"]
    assert provider.get_dependencies()["port"] == ["vlan", "lacp.group"]
    assert provider.deletable_types() == {"vlan", "lacp.group"}
