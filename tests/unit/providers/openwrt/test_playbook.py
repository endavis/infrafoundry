"""Tests for the generated OpenWrt playbook."""

from typing import Any

import yaml

from infrafoundry.providers.openwrt.components.playbook import (
    ROLLBACK_MARKER,
    absent_task,
    build_playbook,
    commit_tail,
    dump_playbook,
    lease_guard_tasks,
    preflight_tasks,
    rescue_tasks,
    staging_task,
    task_name,
)
from infrafoundry.providers.openwrt.schema import Desired, desired_from_resources
from infrafoundry.providers.openwrt.settings import OpenWrtSettings

from .conftest import SETTINGS, lan, printer, res, web

UCI = "community.openwrt.uci"

HELPER = "/tmp/infrafoundry-handover-{{ infrafoundry_session | default('none') }}.uc"


def _item(resource: Any) -> Desired:
    return desired_from_resources([resource])[0]


def _absent(resource: Any) -> Desired:
    item = _item(resource)
    return Desired(item.spec, item.name, item.key, {}, absent=True)


def _block(items: list[Desired], settings: OpenWrtSettings = SETTINGS) -> dict[str, Any]:
    block: dict[str, Any] = build_playbook(settings, items)[0]["tasks"][-1]
    return block


def test_interface_task_is_a_named_section_without_replace_or_autocommit() -> None:
    task = staging_task(_item(lan()))
    assert task == {
        "name": "infrafoundry|network.interface|lan",
        UCI: {
            "command": "section",
            "config": "network",
            "type": "interface",
            "value": {"ipaddr": "192.0.2.1", "netmask": "255.255.255.0"},
            "replace": False,
            "name": "lan",
        },
        "tags": ["lan"],
    }
    assert "autocommit" not in task[UCI]


def test_pool_is_found_by_interface() -> None:
    task = staging_task(_item(res("dhcp.pool", "lan", start=100, limit=150, leasetime="12h")))
    assert task[UCI]["find"] == {"interface": "lan"}
    assert task[UCI]["type"] == "dhcp"
    assert task[UCI]["value"] == {
        "interface": "lan",
        "start": "100",
        "limit": "150",
        "leasetime": "12h",
    }
    assert "name" not in task[UCI]


def test_lease_is_matched_by_mac_and_never_named() -> None:
    task = staging_task(_item(printer()))
    args = task[UCI]
    assert args["find"] == {"mac": "02:00:00:00:00:0a"}
    assert "name" not in args
    assert (args["config"], args["type"], args["replace"]) == ("dhcp", "host", False)
    assert task["name"] == "infrafoundry|dhcp.host|printer"
    assert task["tags"] == ["printer"]


def test_redirect_is_matched_by_its_name_option_not_a_section_name() -> None:
    task = staging_task(_item(web()))
    assert task[UCI]["find"] == {"name": "web"}
    assert "name" not in task[UCI]
    assert task[UCI]["value"]["src"] == "wan"


def test_absent_tasks_delete_by_the_same_match() -> None:
    task = absent_task(_absent(printer()))
    assert task["name"] == "infrafoundry|absent|dhcp.host|printer"
    assert task[UCI] == {
        "command": "absent",
        "config": "dhcp",
        "type": "host",
        "find": {"mac": "02:00:00:00:00:0a"},
    }
    assert task_name(_absent(web())) == "infrafoundry|absent|firewall.redirect|web"


def test_lease_guards_cover_duplicates_and_other_case_forms() -> None:
    guards = lease_guard_tasks(_item(printer()), 3)
    finds = [g[UCI]["find"]["mac"] for g in guards if UCI in g]
    assert finds == ["02:00:00:00:00:0a", "02:00:00:00:00:0A"]
    fails = [g for g in guards if "ansible.builtin.fail" in g]
    assert "length > 1" in fails[0]["when"]
    assert "length > 0" in fails[1]["when"]
    assert all(g["tags"] == ["printer"] for g in guards)


def test_lease_guard_skips_case_variants_for_caseless_macs() -> None:
    guards = lease_guard_tasks(_item(printer(mac="02:00:00:00:00:01")), 0)
    assert [g[UCI]["find"]["mac"] for g in guards if UCI in g] == ["02:00:00:00:00:01"]


def test_guards_run_only_for_leases() -> None:
    names = [t["name"] for t in _block([_item(lan()), _item(web())])["block"]]
    assert not any("|guard|" in n for n in names)
    names = [t["name"] for t in _block([_item(printer())])["block"]]
    assert any("|guard|printer|duplicate" in n for n in names)


def test_preflight_is_tagged_always_and_fails_on_pending_changes() -> None:
    tasks = preflight_tasks()
    assert all(t["tags"] == ["always"] for t in tasks)
    assert [t[UCI]["config"] for t in tasks if UCI in t] == ["network", "dhcp", "firewall"]
    fail = tasks[-1]
    assert "ansible.builtin.fail" in fail
    assert all(f"infrafoundry_pending_{c}" in fail["when"] for c in ("network", "dhcp", "firewall"))


def _tail() -> dict[str, Any]:
    tasks = commit_tail(SETTINGS)
    return next(t for t in tasks if t["name"].endswith("|commit|tail"))


def test_commit_tail_runs_only_outside_check_mode_and_when_staged() -> None:
    tail = _tail()
    assert tail["tags"] == ["always"]
    assert "not ansible_check_mode" in tail["when"]
    assert "infrafoundry_staged" in tail["when"]
    for task in commit_tail(SETTINGS)[:2]:
        assert task["when"] == "not ansible_check_mode"
        assert task["tags"] == ["always"]


def test_commit_tail_follows_the_measured_ubus_sequence() -> None:
    steps = [t["name"].split("|")[-1] for t in _tail()["block"]]
    assert steps == [
        "create-session",
        "remember-session",
        "grant-session",
        "copy-helper",
        "replay-staged",
        "apply-with-rollback",
        "record-apply",
        "apply-failed",
        "use-new-address",
        "reset-connection",
        "wait-for-device",
        "confirm",
        "destroy-session",
    ]


def _by_step(step: str) -> dict[str, Any]:
    return next(t for t in _tail()["block"] if t["name"].endswith(f"|{step}"))


def test_session_is_created_with_a_timeout_beyond_the_rollback_and_validated() -> None:
    task = _by_step("create-session")
    command = task["ansible.builtin.raw"]
    assert command.startswith("ubus call session create '{\"timeout\":390}'")
    assert "jsonfilter -e @.ubus_rpc_session" in command
    assert "[0-9a-f]{32}" in task["failed_when"]


def test_session_is_granted_the_uci_scope() -> None:
    command = _by_step("grant-session")["ansible.builtin.raw"]
    assert command.startswith("ubus call session grant '")
    assert '"scope":"uci"' in command
    assert '"objects":[["*","read"],["*","write"]]' in command
    assert '"ubus_rpc_session":"{{ infrafoundry_session }}"' in command


def test_helper_is_copied_then_replayed_into_the_session_then_removed() -> None:
    copy = next(t for t in _tail()["block"] if t["name"].endswith("|copy-helper"))
    args = copy["community.openwrt.copy"]
    assert args["dest"] == HELPER
    assert args["mode"] == "0600"
    assert "ubus_rpc_session" in args["content"]
    assert args["content"].startswith("{% raw %}")
    command = _by_step("replay-staged")["ansible.builtin.raw"]
    # The helper is removed in the same step, before the apply can cut the link.
    assert command == (
        f"ucode {HELPER} {{{{ infrafoundry_session }}}} network,dhcp,firewall; "
        f"rc=$?; rm -f {HELPER}; exit $rc"
    )
    always = _tail()["always"]
    assert always[0]["ansible.builtin.raw"] == f"rm -f {HELPER}"


def test_no_task_touches_the_rpcd_save_dir() -> None:
    text = dump_playbook(build_playbook(SETTINGS, [_item(lan())]))
    assert "/var/run/rpcd" not in text
    assert "cp /tmp/.uci" not in text


def test_apply_uses_rollback_with_the_configured_timeout_and_session() -> None:
    settings = OpenWrtSettings(address="192.0.2.2", rollback_timeout=45)
    task = next(
        t for t in commit_tail(settings)[2]["block"] if t["name"].endswith("apply-with-rollback")
    )
    command = task["ansible.builtin.raw"]
    assert command.startswith("ubus call uci apply '")
    assert '"rollback":true' in command
    assert '"timeout":45' in command
    assert '"ubus_rpc_session":"{{ infrafoundry_session }}"' in command
    assert task["ignore_unreachable"] is True


def test_apply_is_recorded_only_when_it_ran() -> None:
    record = _by_step("record-apply")["ansible.builtin.set_fact"]["infrafoundry_applied"]
    assert "unreachable" in record
    assert "rc | default(1)) == 0" in record
    assert _by_step("apply-failed")["when"] == "not (infrafoundry_applied | bool)"


def test_wait_timeout_is_the_rollback_timeout_minus_fifteen() -> None:
    wait = _by_step("wait-for-device")["community.openwrt.wait_for_connection"]
    assert wait["timeout"] == 75
    settings = OpenWrtSettings(address="192.0.2.2", rollback_timeout=30)
    tail = commit_tail(settings)[2]["block"]
    waiting = next(t for t in tail if t["name"].endswith("wait-for-device"))
    assert waiting["community.openwrt.wait_for_connection"]["timeout"] == 15


def test_reconnect_resets_the_connection_before_waiting_and_confirms_last() -> None:
    names = [t["name"].split("|")[-1] for t in _tail()["block"]]
    assert names.index("use-new-address") < names.index("reset-connection")
    assert names.index("reset-connection") < names.index("wait-for-device")
    assert names.index("wait-for-device") < names.index("confirm")
    assert names.index("confirm") < names.index("destroy-session")
    assert _by_step("reset-connection")["ansible.builtin.meta"] == "reset_connection"
    assert _by_step("use-new-address")["when"] == "infrafoundry_reconnect_host is defined"
    assert _by_step("confirm")["ansible.builtin.raw"].startswith("ubus call uci confirm '")


def test_rescue_reverts_only_when_apply_was_not_reached() -> None:
    revert, session_revert, destroy, cleanup, pending, failed = rescue_tasks(SETTINGS)
    assert session_revert["ansible.builtin.raw"].startswith("ubus call uci revert '")
    assert '"config":"{{ item }}"' in session_revert["ansible.builtin.raw"]
    assert session_revert["loop"] == ["network", "dhcp", "firewall"]
    assert "not (infrafoundry_applied" in session_revert["when"]
    assert "infrafoundry_session is defined" in session_revert["when"]
    assert cleanup["ansible.builtin.raw"] == f"rm -f {HELPER}"
    assert revert[UCI] == {"command": "revert", "config": "{{ item }}"}
    assert revert["loop"] == ["network", "dhcp", "firewall"]
    assert "not (infrafoundry_applied" in revert["when"]
    assert destroy["ansible.builtin.raw"].startswith("ubus call session destroy '")
    assert "infrafoundry_session is defined" in destroy["when"]
    assert "not (infrafoundry_applied" in destroy["when"]
    assert ROLLBACK_MARKER in pending["ansible.builtin.fail"]["msg"]
    assert "90 s" in pending["ansible.builtin.fail"]["msg"]
    assert pending["when"] == "(infrafoundry_applied | default(false) | bool)"
    assert failed["when"] == "not (infrafoundry_applied | default(false) | bool)"


def test_play_orders_types_and_puts_deletes_last() -> None:
    items = [_item(web()), _absent(printer()), _item(lan()), _item(res("dhcp.pool", "lan"))]
    names = [t["name"] for t in _block(items)["block"] if "|commit|" not in t["name"]]
    assert names == [
        "infrafoundry|network.interface|lan",
        "infrafoundry|dhcp.pool|lan",
        "infrafoundry|firewall.redirect|web",
        "infrafoundry|absent|dhcp.host|printer",
    ]


def test_play_structure_and_yaml_round_trip() -> None:
    play = build_playbook(SETTINGS, [_item(lan()), _item(printer())])
    assert play[0]["hosts"] == "all"
    assert play[0]["gather_facts"] is False
    assert play[0]["tasks"][-1]["rescue"]
    text = dump_playbook(play)
    assert yaml.safe_load(text) == play
    assert "autocommit" not in text


def test_user_values_cannot_break_the_yaml() -> None:
    nasty = printer(hostname='x: [y] # \'"quoted" & more')
    play = build_playbook(SETTINGS, [_item(nasty)])
    assert yaml.safe_load(dump_playbook(play)) == play
    stage = next(t for t in play[0]["tasks"][-1]["block"] if t["name"].endswith("|printer"))
    assert stage[UCI]["value"]["name"] == 'x: [y] # \'"quoted" & more'
