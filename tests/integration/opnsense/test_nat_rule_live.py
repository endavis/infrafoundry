"""Live integration tests for the OPNsense NAT-rule direct-API path (#713).

These tests are gated by ``@pytest.mark.integration`` AND an explicit opt-in
env var so they don't run as part of the default test suite. They contact a
real OPNsense box.

Required:
    OPNSENSE_INTEGRATION_TESTS=1   (explicit opt-in)
    OPNSENSE_API_URL
    OPNSENSE_API_KEY
    OPNSENSE_API_SECRET
    OPNSENSE_VERIFY_SSL  (optional; defaults to "true")
    OPNSENSE_NAT_TEST_INTERFACE  (optional; defaults to "wan")

Run with::

    OPNSENSE_INTEGRATION_TESTS=1 OPNSENSE_API_URL=... OPNSENSE_API_KEY=... \\
    OPNSENSE_API_SECRET=... uv run pytest -m integration \\
    tests/integration/opnsense/test_nat_rule_live.py

The tests exercise the round-trip property for each kind plus the lock,
add-only, and per-kind isolation invariants. All test rules are tagged
``[infrafoundry:test-...]`` and cleaned up in the fixture teardown.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator

import pytest

from infrafoundry.providers.opnsense.api_client import OPNsenseClient
from infrafoundry.providers.opnsense.services.nat_rule import (
    NATRuleConfig,
    NATRuleService,
    compute_diff,
)

REQUIRED_VARS = ("OPNSENSE_API_URL", "OPNSENSE_API_KEY", "OPNSENSE_API_SECRET")


def _opted_in() -> bool:
    return bool(os.getenv("OPNSENSE_INTEGRATION_TESTS")) and all(
        os.getenv(v) for v in REQUIRED_VARS
    )


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _opted_in(),
        reason=(
            "OPNsense live integration tests require OPNSENSE_INTEGRATION_TESTS=1 "
            "plus OPNSENSE_API_URL/KEY/SECRET — they hit a real box."
        ),
    ),
]


def _test_interface() -> str:
    return os.getenv("OPNSENSE_NAT_TEST_INTERFACE", "wan")


@pytest.fixture
def service() -> Iterator[NATRuleService]:
    """Build a ``NATRuleService`` against the live OPNsense box.

    Cleans up any test NAT rules created during the run so re-runs are
    idempotent. Identifies test rules by the InfraFoundry identity
    suffix tag and the ``test-`` name convention.
    """
    verify_raw = os.getenv("OPNSENSE_VERIFY_SSL", "true").strip().lower()
    verify_ssl = verify_raw not in ("0", "false", "no", "off")

    client = OPNsenseClient(
        api_key=os.environ["OPNSENSE_API_KEY"],
        api_secret=os.environ["OPNSENSE_API_SECRET"],
        base_url=os.environ["OPNSENSE_API_URL"],
        verify_ssl=verify_ssl,
    )
    svc = NATRuleService(client)

    # Snapshot existing managed UUIDs so cleanup only touches our rules.
    pre_existing = {(r.kind, r.uuid) for r in svc.search_all() if r.managed_name}

    try:
        yield svc
    finally:
        for live in svc.search_all():
            if (
                live.managed_name
                and live.managed_name.startswith("test-")
                and (live.kind, live.uuid) not in pre_existing
            ):
                with contextlib.suppress(Exception):
                    svc.delete(live.uuid, live.kind)
        # Apply changes for both kinds; suppress errors if no changes.
        for kind in ("outbound", "one_to_one"):
            with contextlib.suppress(Exception):
                svc.apply_changes(kind)  # type: ignore[arg-type]


def test_outbound_round_trip_apply_then_plan_zero(service: NATRuleService) -> None:
    """After apply, plan reports 0/0/0 add/updates for an outbound rule."""
    desired = [
        NATRuleConfig(
            name="test-outbound-roundtrip",
            kind="outbound",
            interface=_test_interface(),
            target="wanip",
            description="integration test outbound",
            sequence=999,
        )
    ]

    diff = compute_diff(desired, service.search_all(), add_only=True)
    assert len(diff.adds) == 1
    service.apply_diff(diff)

    diff_after = compute_diff(desired, service.search_all(), add_only=True)
    assert diff_after.adds == []
    assert diff_after.updates == []


def test_one_to_one_round_trip_apply_then_plan_zero(service: NATRuleService) -> None:
    """After apply, plan reports 0/0/0 add/updates for a 1:1 rule."""
    desired = [
        NATRuleConfig(
            name="test-1to1-roundtrip",
            kind="one_to_one",
            interface=_test_interface(),
            external="198.51.100.99",
            source_net="10.99.99.99",
            description="integration test 1:1",
            sequence=999,
        )
    ]

    diff = compute_diff(desired, service.search_all(), add_only=True)
    assert len(diff.adds) == 1
    service.apply_diff(diff)

    diff_after = compute_diff(desired, service.search_all(), add_only=True)
    assert diff_after.adds == []
    assert diff_after.updates == []


def test_lock_preserves_resource(service: NATRuleService) -> None:
    """A locked entry is reported but never updated/deleted."""
    # Pre-create the rule so the lock has something to protect.
    rule = NATRuleConfig(
        name="test-locked",
        kind="outbound",
        interface=_test_interface(),
        target="wanip",
        description="locked",
        sequence=998,
    )
    service.add(rule)
    service.apply_changes("outbound")

    desired_locked = [
        NATRuleConfig(
            name="test-locked",
            kind="outbound",
            interface=_test_interface(),
            target="wanip",
            description="DIFFERENT description",  # would normally cause update
            sequence=998,
            lock=True,
        )
    ]
    diff = compute_diff(desired_locked, service.search_all(), add_only=True)
    assert diff.adds == []
    assert diff.updates == []
    assert len(diff.locked) == 1


def test_add_only_suppresses_deletes(service: NATRuleService) -> None:
    """With add-only, deletes are suppressed even when managed rules
    aren't in YAML."""
    extra = NATRuleConfig(
        name="test-extra",
        kind="outbound",
        interface=_test_interface(),
        target="wanip",
        description="extra",
        sequence=997,
    )
    service.add(extra)
    service.apply_changes("outbound")

    # YAML mentions only a *different* test rule.
    desired = [
        NATRuleConfig(
            name="test-other",
            kind="outbound",
            interface=_test_interface(),
            target="wanip",
            description="other",
            sequence=996,
        )
    ]
    diff = compute_diff(desired, service.search_all(), add_only=True)
    # extra (sequence 997) is on the box but not in desired — would be
    # a delete normally; add_only suppresses it.
    assert diff.deletes == []


def test_per_kind_isolation_same_name(service: NATRuleService) -> None:
    """An outbound test rule and a 1:1 test rule with the same name co-exist."""
    iface = _test_interface()
    out = NATRuleConfig(
        name="test-shared",
        kind="outbound",
        interface=iface,
        target="wanip",
        description="outbound shared",
        sequence=995,
    )
    oto = NATRuleConfig(
        name="test-shared",
        kind="one_to_one",
        interface=iface,
        external="198.51.100.88",
        source_net="10.88.88.88",
        description="1:1 shared",
        sequence=995,
    )
    service.add(out)
    service.add(oto)
    service.apply_changes("outbound")
    service.apply_changes("one_to_one")

    # Both rules should be present and matched independently in a diff.
    diff = compute_diff([out, oto], service.search_all(), add_only=True)
    assert diff.adds == []
    assert diff.updates == []
