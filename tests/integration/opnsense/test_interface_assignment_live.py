"""Live integration tests for the OPNsense interface-assignment direct-API path (#720).

These tests are gated by ``@pytest.mark.integration`` AND an explicit
opt-in env var so they don't run as part of the default test suite.
They contact a real OPNsense box.

Required env vars::

    OPNSENSE_INTEGRATION_TESTS=1   (explicit opt-in)
    OPNSENSE_API_URL
    OPNSENSE_API_KEY
    OPNSENSE_API_SECRET
    OPNSENSE_VERIFY_SSL  (optional; defaults to "true")

For the write-path tests an SSH credential is also required so the
installer can verify (and if needed deploy) the PHP controller::

    OPNSENSE_SSH_HOST       (or derived from OPNSENSE_API_URL)
    OPNSENSE_SSH_KEY        (path to private key; optional if ssh-agent
                             provides the identity)

Run with::

    OPNSENSE_INTEGRATION_TESTS=1 OPNSENSE_API_URL=... OPNSENSE_API_KEY=... \\
    OPNSENSE_API_SECRET=... uv run pytest -m integration tests/integration/opnsense/

Coverage:
    - ``service.list()`` against the live box returns at least one
      assignment with a non-empty identifier.
    - ``service.export_to_yaml()`` produces a parseable resource
      document.
    - ``installer.verify_installed_checksum()`` returns sensible
      values for an opted-in box (skipped automatically when SSH
      credentials are absent).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from infrafoundry.providers.opnsense.api_client import OPNsenseClient
from infrafoundry.providers.opnsense.extensions.interface_assignments import installer
from infrafoundry.providers.opnsense.services.interface_assignment import (
    InterfaceAssignmentService,
)

REQUIRED_VARS = ("OPNSENSE_API_URL", "OPNSENSE_API_KEY", "OPNSENSE_API_SECRET")


def _opted_in() -> bool:
    return bool(os.getenv("OPNSENSE_INTEGRATION_TESTS")) and all(
        os.getenv(v) for v in REQUIRED_VARS
    )


def _ssh_opted_in() -> bool:
    """Installer-level checks need either SSH_HOST or API_URL plus opt-in."""
    return _opted_in() and bool(os.getenv("OPNSENSE_SSH_HOST") or os.getenv("OPNSENSE_API_URL"))


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
    """``list()`` against the live box returns at least one assignment.

    Every functioning OPNsense box has at least a LAN interface; if
    this returns zero rows the parser is broken or the box is
    misconfigured. Each row must carry a non-empty ``identifier``
    (the service skips unassigned NICs) and a ``device`` string.
    """
    assignments = service.list()
    assert len(assignments) >= 1
    for entry in assignments:
        assert entry.identifier  # non-empty per service contract
        assert isinstance(entry.device, str)
        assert isinstance(entry.ipv4, dict)
        assert isinstance(entry.ipv6, dict)


def test_export_to_yaml_round_trip_parses(service: InterfaceAssignmentService) -> None:
    """``export_to_yaml()`` produces a parseable resource-centric document."""
    import yaml

    rendered = service.export_to_yaml()
    parsed = yaml.safe_load(rendered)
    assert "resources" in parsed
    for entry in parsed["resources"]:
        assert entry["provider"] == "opnsense"
        assert entry["type"] == "interface_assignments"
        assert "device" in entry["config"]


@pytest.mark.skipif(
    not _ssh_opted_in(),
    reason=(
        "installer checksum probe requires OPNSENSE_SSH_HOST or OPNSENSE_API_URL "
        "to derive an SSH target."
    ),
)
def test_installer_checksum_probe() -> None:
    """``verify_installed_checksum`` returns sensible values for the live box.

    This does NOT install — it only probes. Returns ``(False, None,
    local_sum)`` when the controller hasn't been installed yet; that
    is the operator's signal to run a write-path test which will
    invoke ``installer.ensure_installed()`` automatically.
    """
    target = installer.load_ssh_target()
    matches, remote_sum, local_sum = installer.verify_installed_checksum(target)
    # Local sum is always computable from the bundled PHP file.
    assert isinstance(local_sum, str) and len(local_sum) == 64
    # Remote sum is either None (not installed) or the hex digest.
    if remote_sum is not None:
        assert isinstance(remote_sum, str) and len(remote_sum) == 64
        assert matches == (remote_sum == local_sum)
