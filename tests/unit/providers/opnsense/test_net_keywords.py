"""Unit tests for the shared rule network-keyword helper (#1598)."""

from __future__ import annotations

from typing import Any

from infrafoundry.providers.opnsense.validators._net_keywords import (
    STATIC_NET_KEYWORDS,
    accepted_net_keywords,
    interface_net_keywords,
)
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext


def test_empty_context_gives_static_set() -> None:
    assert accepted_net_keywords(OPNsenseValidationContext()) == STATIC_NET_KEYWORDS


def test_managed_assignment_adds_network_and_address_forms() -> None:
    ctx = OPNsenseValidationContext(interface_assignment_names={"opt1"})
    keywords = accepted_net_keywords(ctx)
    assert {"opt1", "opt1ip"} <= keywords
    assert keywords >= STATIC_NET_KEYWORDS


def test_live_rows_use_identifier_not_device() -> None:
    row = {"identifier": "opt3", "device": "em2"}
    ctx = OPNsenseValidationContext(existing_interfaces={"opt3": row, "em2": row})
    keywords = accepted_net_keywords(ctx)
    assert {"opt3", "opt3ip"} <= keywords
    assert keywords.isdisjoint({"em2", "em2ip"})


def test_malformed_live_rows_add_nothing() -> None:
    rows: dict[str, Any] = {
        "a": {"device": "em0"},
        "b": {"identifier": 5},
        "c": "not-a-dict",
        "d": {"identifier": ""},
    }
    ctx = OPNsenseValidationContext(existing_interfaces=rows)
    assert accepted_net_keywords(ctx) == STATIC_NET_KEYWORDS


def test_live_option_keys_are_included() -> None:
    ctx = OPNsenseValidationContext(existing_net_keywords={"lo0"})
    assert "lo0" in accepted_net_keywords(ctx)


def test_unknown_interface_is_absent() -> None:
    ctx = OPNsenseValidationContext(
        interface_assignment_names={"opt1"}, existing_net_keywords={"lo0"}
    )
    keywords = accepted_net_keywords(ctx)
    assert "opt99" not in keywords
    assert "opt99ip" not in keywords


def test_interface_net_keywords_skips_empty_ids() -> None:
    assert interface_net_keywords(["", "opt2"]) == {"opt2", "opt2ip"}
