"""Unit tests for the shared Proxmox import_id check (#1613)."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.providers.proxmox.validators.import_id import import_id_problems


class TestValid:
    @pytest.mark.parametrize("value", ["pve-a/100", "node1/999999999", "n/100"])
    def test_format_only(self, value: str) -> None:
        assert import_id_problems(value, {}) == []

    def test_matches_config(self) -> None:
        assert import_id_problems("pve-a/100", {"vmid": 100, "target_node": "pve-a"}) == []

    def test_numeric_string_vmid(self) -> None:
        assert import_id_problems("pve-a/100", {"vmid": "100"}) == []

    def test_non_int_vmid_skips_cross_check(self) -> None:
        assert import_id_problems("pve-a/100", {"vmid": "auto"}) == []


class TestMalformed:
    @pytest.mark.parametrize(
        "value",
        [
            "100",
            "pve-a/",
            "/100",
            "pve-a/abc",
            "pve-a/100/x",
            "pve a/100",
            "-pve/100",
            'pve-a/"100',
            "",
        ],
    )
    def test_rejected(self, value: str) -> None:
        problems = import_id_problems(value, {})
        assert len(problems) == 1
        assert "<node>/<vmid>" in problems[0]


class TestRange:
    @pytest.mark.parametrize("value", ["pve-a/99", "pve-a/1000000000"])
    def test_out_of_range(self, value: str) -> None:
        problems = import_id_problems(value, {})
        assert len(problems) == 1
        assert "between" in problems[0]


class TestMismatch:
    @pytest.mark.parametrize(
        ("value", "config", "needle"),
        [
            ("pve-a/101", {"vmid": 100}, "vmid is 100"),
            ("pve-b/100", {"target_node": "pve-a"}, "target_node is 'pve-a'"),
        ],
    )
    def test_mismatch(self, value: str, config: dict[str, Any], needle: str) -> None:
        problems = import_id_problems(value, config)
        assert len(problems) == 1
        assert needle in problems[0]
