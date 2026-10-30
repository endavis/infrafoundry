"""Cluster broadcast domain MTU in the ontap-cluster blueprint (#1206).

The simulator leaves the ``Cluster`` broadcast domain at MTU 9000, which drops
cluster packets on a network below that. The blueprint sets it from the
``cluster_mtu`` input (default 1500) before any data configuration.

File-based and offline: no Ansible runtime, no ONTAP simulator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jinja2.nativetypes import NativeEnvironment

BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprints" / "ontap-cluster"
ROLE_DIR = BLUEPRINT_DIR / "roles" / "ontap-post-cluster"
MODULE = "netapp.ontap.na_ontap_broadcast_domain"


def _tasks() -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = yaml.safe_load((ROLE_DIR / "tasks" / "main.yml").read_text())
    return tasks


def _mtu_task() -> dict[str, Any]:
    return next(t for t in _tasks() if MODULE in t)


def _mtu_expression() -> str:
    plays: list[dict[str, Any]] = yaml.safe_load(
        (BLUEPRINT_DIR / "ontap-lab-cluster-setup.yml").read_text()
    )
    play = next(p for p in plays if p["name"] == "Configure ONTAP cluster (aggregates, SVMs, LIFs)")
    role = next(r for r in play["roles"] if r["role"] == "ontap-post-cluster")
    return str(role["vars"]["ontap_cluster_mtu"])


def _render(env_vars: dict[str, str]) -> Any:
    def lookup(plugin: str, name: str) -> str:
        assert plugin == "env"
        return env_vars.get(name, "")

    env = NativeEnvironment()
    env.globals["lookup"] = lookup
    return env.from_string(_mtu_expression()).render()


def test_input_defaults_to_1500() -> None:
    blueprint = yaml.safe_load((BLUEPRINT_DIR / "blueprint.yaml").read_text())
    inputs = {i["name"]: i for i in blueprint["inputs"]}

    assert inputs["cluster_mtu"]["default"] == 1500
    assert inputs["cluster_mtu"]["description"]


def test_playbook_maps_input_into_post_cluster_play() -> None:
    assert "INFRAFOUNDRY_VAR_cluster_mtu" in _mtu_expression()
    assert _render({"INFRAFOUNDRY_VAR_cluster_mtu": "9000"}) == 9000


def test_playbook_falls_back_to_1500_when_unset() -> None:
    assert _render({}) == 1500


def test_role_default_is_1500() -> None:
    defaults = yaml.safe_load((ROLE_DIR / "defaults" / "main.yml").read_text())

    assert defaults["ontap_cluster_mtu"] == 1500


def test_task_targets_cluster_broadcast_domain() -> None:
    module = _mtu_task()[MODULE]

    assert module["state"] == "present"
    assert module["name"] == "Cluster"
    assert module["ipspace"] == "Cluster"
    assert "ontap_cluster_mtu" in str(module["mtu"])
    assert "ports" not in module


def test_task_runs_before_aggregate_creation() -> None:
    names = [str(t.get("name")) for t in _tasks()]
    mtu_name = str(_mtu_task()["name"])

    assert names.index(mtu_name) < names.index("Create data aggregates")
