"""Provider instances sort right after their base provider (#1450)."""

from __future__ import annotations

from infrafoundry.core.execution_planner import ExecutionPlanner


def test_instances_follow_their_base_in_apply_order() -> None:
    planner = ExecutionPlanner()
    ordered = planner.sort_providers(["proxmox", "opnsense@fw-b", "opnsense", "opnsense@fw-a"])
    assert ordered == ["opnsense", "opnsense@fw-a", "opnsense@fw-b", "proxmox"]


def test_instances_run_before_the_base_on_destroy() -> None:
    planner = ExecutionPlanner()
    ordered = planner.sort_providers(
        ["proxmox", "opnsense@fw-b", "opnsense", "opnsense@fw-a"], reverse=True
    )
    assert ordered == ["proxmox", "opnsense@fw-b", "opnsense@fw-a", "opnsense"]


def test_instance_of_unlisted_provider_sorts_after_listed_ones() -> None:
    planner = ExecutionPlanner(provider_order=["opnsense"])
    assert planner.sort_providers(["other@x", "opnsense@fw-b", "opnsense"]) == [
        "opnsense",
        "opnsense@fw-b",
        "other@x",
    ]


def test_order_key_of_an_instance_is_its_base_position() -> None:
    planner = ExecutionPlanner()
    assert planner.get_provider_order_key("opnsense@fw-b") == planner.get_provider_order_key(
        "opnsense"
    )
