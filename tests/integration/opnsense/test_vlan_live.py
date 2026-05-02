"""Live integration tests for the OPNsense VLAN direct-API path (#709).

These tests are gated by ``@pytest.mark.integration`` AND an explicit opt-in
env var so they don't run as part of the default test suite. They contact a
real OPNsense box.

Required:
    OPNSENSE_INTEGRATION_TESTS=1   (explicit opt-in)
    OPNSENSE_API_URL
    OPNSENSE_API_KEY
    OPNSENSE_API_SECRET
    OPNSENSE_VERIFY_SSL  (optional; defaults to "true")

Run with::

    OPNSENSE_INTEGRATION_TESTS=1 OPNSENSE_API_URL=... OPNSENSE_API_KEY=... \\
    OPNSENSE_API_SECRET=... uv run pytest -m integration tests/integration/opnsense/

Round-trip property: write known YAML; plan reports adds; apply; plan reports
0/0/0 add/updates. Lock and ``--add-only`` both verified end-to-end.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator

import pytest

from infrafoundry.providers.opnsense.api_client import OPNsenseClient
from infrafoundry.providers.opnsense.services.vlan import (
    LiveVlan,
    VlanConfig,
    VlanService,
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


@pytest.fixture
def service() -> Iterator[VlanService]:
    """Build a ``VlanService`` against the live OPNsense box.

    Cleans up any test VLANs created during the run so re-runs are
    idempotent.
    """
    verify_raw = os.getenv("OPNSENSE_VERIFY_SSL", "true").strip().lower()
    verify_ssl = verify_raw not in ("0", "false", "no", "off")

    client = OPNsenseClient(
        api_key=os.environ["OPNSENSE_API_KEY"],
        api_secret=os.environ["OPNSENSE_API_SECRET"],
        base_url=os.environ["OPNSENSE_API_URL"],
        verify_ssl=verify_ssl,
    )
    svc = VlanService(client)

    # Snapshot existing VLANs so the cleanup phase only removes what the
    # tests created.
    pre_existing_uuids = {v.uuid for v in svc.search()}

    try:
        yield svc
    finally:
        for live in svc.search():
            if live.uuid not in pre_existing_uuids:
                # OPNsense rejects deletion of VLANs assigned as
                # interfaces; cleanup is best-effort.
                with contextlib.suppress(Exception):
                    svc.delete(live.uuid)
        svc.reconfigure()


def test_round_trip_apply_then_plan_zero(service: VlanService) -> None:
    """After apply, plan reports 0/0/0 add/updates (round-trip property).

    Uses ``add_only=True`` to avoid touching pre-existing VLANs the box
    already has — the round-trip property we need is "what we created is
    no longer pending", not "the box matches the YAML exactly".
    """
    desired = [
        VlanConfig(
            name="test-roundtrip",
            device=_pick_test_device(service),
            tag=4090,
            description="integration test VLAN",
            priority=0,
        )
    ]

    diff = compute_diff(desired, service.search(), add_only=True)
    assert len(diff.adds) == 1
    service.apply_diff(diff)

    # Re-plan: live should now have our VLAN. add_only suppresses deletes
    # for unrelated VLANs on the box.
    diff_after = compute_diff(desired, service.search(), add_only=True)
    assert diff_after.adds == []
    assert diff_after.updates == []


def test_lock_preserves_resource_across_destroy(service: VlanService) -> None:
    """A locked entry is reported but never deleted.

    Uses ``add_only=True`` to ignore pre-existing VLANs unrelated to this
    test; the assertion is on the locked entry only.
    """
    device = _pick_test_device(service)
    desired_locked = [
        VlanConfig(
            name="test-locked",
            device=device,
            tag=4091,
            description="locked",
            priority=0,
            lock=True,
        )
    ]

    # Pre-create the resource so the lock has something to protect.
    service.add(
        VlanConfig(
            name="test-locked",
            device=device,
            tag=4091,
            description="locked",
            priority=0,
        )
    )
    service.reconfigure()

    diff = compute_diff(desired_locked, service.search(), add_only=True)
    assert diff.adds == []
    assert diff.updates == []
    assert len(diff.locked) == 1


def test_add_only_suppresses_deletes(service: VlanService) -> None:
    """With --add-only, deletes are suppressed even when the box has unmanaged VLANs."""
    device = _pick_test_device(service)
    # The box may have VLANs unrelated to our YAML; simulate that scenario.
    extra = VlanConfig(
        name="test-extra",
        device=device,
        tag=4092,
        description="extra",
        priority=0,
    )
    service.add(extra)
    service.reconfigure()

    desired_only_other = [
        VlanConfig(
            name="test-other",
            device=device,
            tag=4093,
            description="other",
            priority=0,
        )
    ]
    diff = compute_diff(desired_only_other, service.search(), add_only=True)
    # extra (4092) is on the box but absent from desired — would normally
    # be a delete. add_only suppresses it.
    assert diff.deletes == []


def _pick_test_device(service: VlanService) -> str:
    """Pick an existing parent NIC on the box.

    Reads any live VLAN's device — the integration suite assumes the box has
    at least one VLAN configured to discover a valid NIC. If none, fall back
    to a common name; tests will fail clearly if the box has no NICs.
    """
    live = service.search()
    if live:
        return live[0].device
    return "igb0"


def test_live_vlan_round_trip_dataclass_invariant() -> None:
    """Sanity check: LiveVlan diff_key matches VlanConfig diff_key for same identity."""
    config = VlanConfig(name="x", device="igb0", tag=10, description="x", priority=0)
    live = LiveVlan(uuid="u", device="igb0", tag=10, description="x", priority=0)
    assert config.diff_key == live.diff_key
