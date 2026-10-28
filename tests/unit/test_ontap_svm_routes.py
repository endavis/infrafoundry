"""SVM routes in the ontap-cluster blueprint (#1160).

The data SVM needs a default route when its DNS server or clients are off the
data LIF subnet. The route is created after the data LIFs (it needs a LIF on
the gateway's subnet) and before DNS (ONTAP checks the DNS server is reachable).
Without ``data_gateway`` the playbook adds no route, so existing packages are
unchanged.

File-based and offline: no Ansible runtime, no ONTAP simulator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from jinja2.nativetypes import NativeEnvironment

BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprints" / "ontap-cluster"
ROLE_DIR = BLUEPRINT_DIR / "roles" / "ontap-post-cluster"


def _main_task_names() -> list[str]:
    tasks: list[dict[str, Any]] = yaml.safe_load((ROLE_DIR / "tasks" / "main.yml").read_text())
    return [str(t.get("name")) for t in tasks]


def _route_task() -> dict[str, Any]:
    tasks: list[dict[str, Any]] = yaml.safe_load((ROLE_DIR / "tasks" / "main.yml").read_text())
    return next(t for t in tasks if t.get("name") == "Create SVM routes")


def _svm_routes_expression() -> str:
    plays: list[dict[str, Any]] = yaml.safe_load(
        (BLUEPRINT_DIR / "ontap-lab-cluster-setup.yml").read_text()
    )
    play = next(p for p in plays if p["name"] == "Configure ONTAP cluster (aggregates, SVMs, LIFs)")
    role = next(r for r in play["roles"] if r["role"] == "ontap-post-cluster")
    return str(role["vars"]["ontap_svm_routes"])


def _render(expression: str, env_vars: dict[str, str]) -> Any:
    def lookup(plugin: str, name: str) -> str:
        assert plugin == "env"
        return env_vars.get(name, "")

    env = NativeEnvironment()
    env.globals["lookup"] = lookup
    return env.from_string(expression).render()


def test_route_task_runs_after_data_lifs_and_before_dns() -> None:
    names = _main_task_names()

    assert (
        names.index("Create data LIFs")
        < names.index("Create SVM routes")
        < names.index("Configure DNS for SVMs")
    )


def test_route_task_creates_each_listed_route() -> None:
    task = _route_task()
    module = task["netapp.ontap.na_ontap_net_routes"]

    assert task["loop"] == "{{ ontap_svm_routes }}"
    assert module["state"] == "present"
    assert module["vserver"] == "{{ item.vserver }}"
    assert module["destination"] == "{{ item.destination }}"
    assert module["gateway"] == "{{ item.gateway }}"
    assert "ignore_errors" not in task


def test_role_default_adds_no_routes() -> None:
    defaults = yaml.safe_load((ROLE_DIR / "defaults" / "main.yml").read_text())

    assert defaults["ontap_svm_routes"] == []


@pytest.mark.parametrize("gateway", ["", None])
def test_playbook_adds_no_route_without_data_gateway(gateway: str | None) -> None:
    env_vars = {"INFRAFOUNDRY_VAR_svm_name": "svm_data"}
    if gateway is not None:
        env_vars["INFRAFOUNDRY_VAR_data_gateway"] = gateway

    assert _render(_svm_routes_expression(), env_vars) == []


def test_playbook_adds_a_default_route_via_data_gateway() -> None:
    routes = _render(
        _svm_routes_expression(),
        {
            "INFRAFOUNDRY_VAR_svm_name": "svm_data",
            "INFRAFOUNDRY_VAR_data_gateway": "192.168.99.1",
        },
    )

    assert routes == [
        {"vserver": "svm_data", "destination": "0.0.0.0/0", "gateway": "192.168.99.1"}
    ]


def test_blueprint_declares_data_gateway_with_an_empty_default() -> None:
    blueprint = yaml.safe_load((BLUEPRINT_DIR / "blueprint.yaml").read_text())
    data_gateway = next(i for i in blueprint["inputs"] if i["name"] == "data_gateway")

    assert data_gateway["default"] == ""
