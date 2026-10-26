"""Disk handling in the ontap-post-cluster role (#1089).

Newly assigned disks can stay in container type "unknown" on the ONTAP
simulator, and ``na_ontap_command`` reports a rejected CLI command as
``changed`` with ``result_value`` 0. These tests pin how the role handles
both: every assignment is followed by the settle step, the root-aggregate
commands fail on a rejected command, and snapshot tuning only warns.

File-based and offline: no Ansible runtime, no ONTAP simulator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from jinja2 import Environment

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE_DIR = REPO_ROOT / "blueprints" / "ontap-cluster" / "roles" / "ontap-post-cluster"


def _tasks(name: str) -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = yaml.safe_load((ROLE_DIR / "tasks" / name).read_text())
    return loaded


def _by_name(tasks: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(task for task in tasks if task.get("name") == name)


MAIN = _tasks("main.yml")
SETTLE = _tasks("settle-disks.yml")


def test_no_task_ignores_errors() -> None:
    assert [t["name"] for t in MAIN if "ignore_errors" in t] == []


@pytest.mark.parametrize(
    ("name", "register"),
    [
        ("Add disks to root aggregates", "root_add_disks"),
        ("Expand root volume to use new aggregate space", "root_vol_size"),
    ],
)
def test_root_aggregate_commands_fail_on_a_rejected_command(name: str, register: str) -> None:
    task = _by_name(MAIN, name)

    assert task["netapp.ontap.na_ontap_command"]["return_dict"] is True
    assert task["register"] == register
    assert task["failed_when"] == f"{register}.msg.result_value | default(0) | int != 1"


@pytest.mark.parametrize(
    ("assign", "settle"),
    [
        (
            "Assign unowned disks for root aggregate expansion",
            "Wait for assigned disks to become spares",
        ),
        ("Assign all unowned disks", "Wait for disks to become spares before creating aggregates"),
    ],
)
def test_every_disk_assignment_is_followed_by_the_settle_step(assign: str, settle: str) -> None:
    names = [t.get("name") for t in MAIN]
    assign_task = MAIN[names.index(assign)]
    settle_task = MAIN[names.index(assign) + 1]

    assert settle_task["name"] == settle
    assert settle_task["ansible.builtin.include_tasks"] == "settle-disks.yml"
    assert settle_task["loop"] == "{{ ontap_discovered_nodes }}"
    assert settle_task["loop_control"] == {"loop_var": "ontap_settle_node"}
    assert settle_task["when"] == assign_task["when"]


def test_settle_step_comes_before_aggregate_creation() -> None:
    names = [t.get("name") for t in MAIN]

    assert names.index("Wait for disks to become spares before creating aggregates") < names.index(
        "Create data aggregates"
    )


def test_settle_waits_then_reassigns_only_stuck_disks() -> None:
    wait, reassign = SETTLE

    assert "container_type=unknown" in wait["ansible.builtin.uri"]["url"]
    assert "home_node.name={{ ontap_settle_node }}" in wait["ansible.builtin.uri"]["url"]
    assert wait["until"] == "ontap_unsettled.json.num_records == 0"
    # Running out of retries leads to the re-assignment, not a failure.
    assert wait["failed_when"] == "ontap_unsettled.json is not defined"
    assert reassign["when"] == "ontap_unsettled.json.num_records > 0"

    removeowner, assign, wait_again, check = reassign["block"]
    assert removeowner["netapp.ontap.na_ontap_command"]["command"] == (
        "storage disk removeowner -disk {{ item }} -force true"
    )
    assert assign["netapp.ontap.na_ontap_command"]["command"] == (
        "storage disk assign -disk {{ item }} -owner {{ ontap_settle_node }}"
    )
    assert wait_again["until"] == "ontap_still_unsettled.json.num_records == 0"
    assert check["ansible.builtin.assert"]["that"] == (
        "ontap_still_unsettled.json.num_records | default(1) == 0"
    )


def test_settle_commands_avoid_commas() -> None:
    """``na_ontap_command`` splits a ``command`` string on commas."""
    removeowner, assign, *_ = SETTLE[1]["block"]

    for task in (removeowner, assign):
        assert "," not in task["netapp.ontap.na_ontap_command"]["command"]


def test_settle_timing_has_defaults() -> None:
    defaults = yaml.safe_load((ROLE_DIR / "defaults" / "main.yml").read_text())

    assert defaults["ontap_disk_settle_retries"] == 12
    assert defaults["ontap_disk_settle_delay"] == 5


def test_snapshot_tuning_fails_only_on_a_module_error() -> None:
    task = _by_name(MAIN, "Tune root volume snapshots")

    assert task["netapp.ontap.na_ontap_command"]["return_dict"] is True
    # A missing netapp-lib makes msg a string, so result_value is undefined.
    assert task["failed_when"] == "ontap_snap_tuning.msg.result_value is not defined"


def test_snapshot_tuning_warns_only_about_rejected_commands() -> None:
    warn = _by_name(MAIN, "Warn about rejected snapshot tuning commands")
    results = [
        {"item": ["ontapcl-01", "snap autodelete vol0 on"], "msg": {"result_value": 1}},
        {"item": ["ontapcl-02", "snap sched vol0 0 0 0"], "msg": {"result_value": 0}},
    ]

    rendered = (
        Environment()
        .from_string(warn["loop"].replace("| list }}", "| map(attribute='item') | list }}"))
        .render(ontap_snap_tuning={"results": results})
    )

    assert rendered == "[['ontapcl-02', 'snap sched vol0 0 0 0']]"
