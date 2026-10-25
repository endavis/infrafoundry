"""Tests for ``tools/opnsense-parser.py``'s NAT outbound parsing (#1056).

``parse_nat_outbound`` was annotated as returning a list but returned a dict
with ``mode`` and ``rules``. It now always returns that dict, including when the
config has no NAT section, and its callers gate on ``.get("rules")``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

PARSER_PATH = Path(__file__).resolve().parents[2] / "tools" / "opnsense-parser.py"


def _load_parser() -> ModuleType:
    spec = importlib.util.spec_from_file_location("opnsense_parser", PARSER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["opnsense_parser"] = module
    spec.loader.exec_module(module)
    return module


def _parse(tmp_path: Path, body: str) -> dict[str, Any]:
    config = tmp_path / "config.xml"
    config.write_text(f"<opnsense>{body}</opnsense>", encoding="utf-8")
    parser = _load_parser().OPNsenseParser(config)
    result: dict[str, Any] = parser.parse_nat_outbound()
    return result


def test_no_nat_section_returns_empty_automatic(tmp_path: Path) -> None:
    assert _parse(tmp_path, "") == {"mode": "automatic", "rules": []}


def test_nat_without_outbound_returns_empty_automatic(tmp_path: Path) -> None:
    assert _parse(tmp_path, "<nat></nat>") == {"mode": "automatic", "rules": []}


def test_outbound_rules_are_parsed_with_mode(tmp_path: Path) -> None:
    body = (
        "<nat><outbound><mode>hybrid</mode>"
        "<rule><descr>lan out</descr><interface>wan</interface>"
        "<source><network>lan</network></source><destination><any>1</any></destination>"
        "</rule></outbound></nat>"
    )

    result = _parse(tmp_path, body)

    assert result["mode"] == "hybrid"
    assert result["rules"] == [
        {
            "description": "lan out",
            "interface": "wan",
            "protocol": "inet",
            "source_network": "lan",
            "destination": "any",
        }
    ]
