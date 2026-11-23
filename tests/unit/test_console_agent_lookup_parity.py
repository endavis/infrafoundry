"""Parity test for the duplicated ``agents_at_address`` helper (#1629).

Blueprints are self-contained, so console-connector and ontap-cluster each carry a copy.
Both copies must return the same result for the same Console listing.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

BLUEPRINTS = Path(__file__).resolve().parents[2] / "blueprints"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


CONNECTOR: Any = _load(
    "parity_console_connector_register",
    BLUEPRINTS / "console-connector" / "scripts" / "console-connector-register.py",
)
ONTAP: Any = _load(
    "parity_ontap_console_discover",
    BLUEPRINTS / "ontap-cluster" / "scripts" / "ontap-console-discover.py",
)


def _occm(agent_id: str, uri: str, status: str = "active") -> dict[str, Any]:
    return {"agent": {"agentId": agent_id}, "status": status, "primaryCallbackUri": uri}


CASES: list[tuple[Any, str, list[tuple[str, str]]]] = [
    (
        {"occms": [_occm("agent-a1clients", "https://192.0.2.1:443/occm")]},
        "192.0.2.1",
        [("agent-a1clients", "active")],
    ),
    (
        [{"occms": [_occm("agent-a1clients", "192.0.2.1")]}],
        "192.0.2.1",
        [("agent-a1clients", "active")],
    ),
    (
        [_occm("agent-a1clients", "http://192.0.2.1/x", "inactive")],
        "192.0.2.1",
        [("agent-a1clients", "inactive")],
    ),
    ({"occms": [_occm("agent-a1clients", "https://192.0.2.10")]}, "192.0.2.1", []),
    ({"occms": [_occm("", "https://192.0.2.1")]}, "192.0.2.1", []),
    ("junk", "192.0.2.1", []),
]


@pytest.mark.parametrize(("listing", "address", "expected"), CASES)
def test_both_copies_agree(listing: Any, address: str, expected: list[tuple[str, str]]) -> None:
    assert CONNECTOR.agents_at_address(listing, address) == expected
    assert ONTAP.agents_at_address(listing, address) == expected
