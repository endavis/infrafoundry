"""Live integration tests for the OPNsense interface-assignment direct-API path (#711).

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

Coverage: ``service.list()`` against the live box returns at least one
assignment with a non-empty ``identifier``. Writes are not exercised
because OPNsense `26.1.6_2` exposes no REST write endpoint for this
resource (#711 reduced scope).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from infrafoundry.providers.opnsense.api_client import OPNsenseClient
from infrafoundry.providers.opnsense.services.interface_assignment import (
    InterfaceAssignmentService,
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
def service() -> Iterator[InterfaceAssignmentService]:
    """Build an ``InterfaceAssignmentService`` against the live OPNsense box."""
    verify_raw = os.getenv("OPNSENSE_VERIFY_SSL", "true").strip().lower()
    verify_ssl = verify_raw not in ("0", "false", "no", "off")

    client = OPNsenseClient(
        api_key=os.environ["OPNSENSE_API_KEY"],
        api_secret=os.environ["OPNSENSE_API_SECRET"],
        base_url=os.environ["OPNSENSE_API_URL"],
        verify_ssl=verify_ssl,
    )
    yield InterfaceAssignmentService(client)


def test_list_returns_assignments(service: InterfaceAssignmentService) -> None:
    """`list()` against the live box returns at least one assignment.

    Every functioning OPNsense box has at least a LAN interface; if this
    returns zero rows the parser is broken or the box is misconfigured.
    Each row must carry a non-empty ``identifier`` (the service skips
    unassigned NICs) and a ``device`` string.
    """
    assignments = service.list()
    assert len(assignments) >= 1
    for entry in assignments:
        assert entry.identifier  # non-empty per service contract
        assert isinstance(entry.device, str)
        assert isinstance(entry.ipv4, dict)
        assert isinstance(entry.ipv6, dict)


def test_export_to_yaml_round_trip_parses(
    service: InterfaceAssignmentService,
) -> None:
    """`export_to_yaml()` produces a parseable resource-centric document."""
    import yaml

    rendered = service.export_to_yaml()
    parsed = yaml.safe_load(rendered)
    assert "resources" in parsed
    for entry in parsed["resources"]:
        assert entry["provider"] == "opnsense"
        assert entry["type"] == "interface_assignments"
        assert "device" in entry["config"]
