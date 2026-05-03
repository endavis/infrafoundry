"""Live integration tests for the OPNsense gateway direct-API path (#721).

These tests are gated by ``@pytest.mark.integration`` AND an explicit opt-in
env var so they don't run as part of the default test suite. They contact a
real OPNsense box.

Required:
    OPNSENSE_INTEGRATION_TESTS=1   (explicit opt-in)
    OPNSENSE_API_URL
    OPNSENSE_API_KEY
    OPNSENSE_API_SECRET
    OPNSENSE_VERIFY_SSL  (optional; defaults to "true")
    OPNSENSE_GATEWAY_TEST_INTERFACE  (optional; defaults to "wan")

Run with::

    OPNSENSE_INTEGRATION_TESTS=1 OPNSENSE_API_URL=... OPNSENSE_API_KEY=... \\
    OPNSENSE_API_SECRET=... uv run pytest -m integration \\
    tests/integration/opnsense/test_gateway_live.py

The tests exercise the round-trip property plus the lock and add-only
invariants. All test gateways are named ``infrafoundry-test-*`` and cleaned
up in the fixture teardown — re-runs are idempotent.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator

import pytest

from infrafoundry.providers.opnsense.api_client import OPNsenseClient
from infrafoundry.providers.opnsense.services.gateway import (
    GatewayConfig,
    GatewayService,
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
    return os.getenv("OPNSENSE_GATEWAY_TEST_INTERFACE", "wan")


@pytest.fixture
def service() -> Iterator[GatewayService]:
    """Build a ``GatewayService`` against the live OPNsense box.

    Cleans up any test gateways created during the run so re-runs are
    idempotent. Identifies test gateways by the ``infrafoundry-test-`` name
    convention; pre-existing managed gateways are snapshotted and never
    touched.
    """
    verify_raw = os.getenv("OPNSENSE_VERIFY_SSL", "true").strip().lower()
    verify_ssl = verify_raw not in ("0", "false", "no", "off")

    client = OPNsenseClient(
        api_key=os.environ["OPNSENSE_API_KEY"],
        api_secret=os.environ["OPNSENSE_API_SECRET"],
        base_url=os.environ["OPNSENSE_API_URL"],
        verify_ssl=verify_ssl,
    )
    svc = GatewayService(client)

    # Snapshot existing managed UUIDs so cleanup only touches test gateways.
    pre_existing = {g.uuid for g in svc.search() if g.is_managed}

    try:
        yield svc
    finally:
        for live in svc.search():
            if (
                live.is_managed
                and live.name.startswith("infrafoundry-test-")
                and live.uuid not in pre_existing
            ):
                with contextlib.suppress(Exception):
                    svc.delete(live.uuid)
        with contextlib.suppress(Exception):
            svc.reconfigure()


def test_round_trip_apply_then_plan_zero(service: GatewayService) -> None:
    """After apply, plan reports 0 add/update for the same desired state."""
    desired = [
        GatewayConfig(
            name="infrafoundry-test-roundtrip",
            interface=_test_interface(),
            protocol="inet",
            gateway="192.0.2.250",
            description="integration test gateway",
            priority=200,
        )
    ]

    diff = compute_diff(desired, service.search(), add_only=True)
    assert len(diff.adds) == 1
    service.apply_diff(diff)

    diff_after = compute_diff(desired, service.search(), add_only=True)
    assert diff_after.adds == []
    assert diff_after.updates == []


def test_update_weight(service: GatewayService) -> None:
    """Updating ``weight`` triggers a single update on the second apply."""
    initial = GatewayConfig(
        name="infrafoundry-test-weight",
        interface=_test_interface(),
        protocol="inet",
        gateway="192.0.2.251",
        description="weight test",
        weight=1,
    )
    service.add(initial)
    service.reconfigure()

    desired = [
        GatewayConfig(
            name="infrafoundry-test-weight",
            interface=_test_interface(),
            protocol="inet",
            gateway="192.0.2.251",
            description="weight test",
            weight=5,  # changed
        )
    ]
    diff = compute_diff(desired, service.search(), add_only=True)
    assert len(diff.updates) == 1


def test_lock_preserves_resource(service: GatewayService) -> None:
    """A locked entry is reported but never updated/deleted."""
    rule = GatewayConfig(
        name="infrafoundry-test-locked",
        interface=_test_interface(),
        protocol="inet",
        gateway="192.0.2.252",
        description="locked",
    )
    service.add(rule)
    service.reconfigure()

    desired_locked = [
        GatewayConfig(
            name="infrafoundry-test-locked",
            interface=_test_interface(),
            protocol="inet",
            gateway="192.0.2.252",
            description="DIFFERENT description",  # would normally cause update
            lock=True,
        )
    ]
    diff = compute_diff(desired_locked, service.search(), add_only=True)
    assert diff.adds == []
    assert diff.updates == []
    assert len(diff.locked) == 1


def test_add_only_suppresses_deletes(service: GatewayService) -> None:
    """With add-only, deletes are suppressed even when managed gateways
    aren't in YAML."""
    extra = GatewayConfig(
        name="infrafoundry-test-extra",
        interface=_test_interface(),
        protocol="inet",
        gateway="192.0.2.253",
        description="extra",
    )
    service.add(extra)
    service.reconfigure()

    # YAML mentions only a *different* test gateway.
    desired = [
        GatewayConfig(
            name="infrafoundry-test-other",
            interface=_test_interface(),
            protocol="inet",
            gateway="192.0.2.254",
            description="other",
        )
    ]
    diff = compute_diff(desired, service.search(), add_only=True)
    # extra is on the box but not in desired — would be a delete normally;
    # add_only suppresses it.
    assert diff.deletes == []


def test_dynamic_gateways_excluded_from_diff(service: GatewayService) -> None:
    """Live dynamic gateways (e.g., WAN_DHCP) must not show up as deletes."""
    desired: list[GatewayConfig] = []
    diff = compute_diff(desired, service.search())
    # If any dynamic gateways exist on the box, they would erroneously
    # appear as deletes if the diff engine didn't filter them.
    for live in diff.deletes:
        assert live.is_managed, f"dynamic gateway {live.name!r} leaked into diff.deletes"
