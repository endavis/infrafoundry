"""Gist-based REST spike for OPNsense interface_assignments — informs ADR-0014.

Drives a forked + extended copy of `szymczag`'s ``AssignSettingsController.php``
(the gist at ``df152a82e86aff67b984ed3786b027ba``) installed on the OPNsense
box. The community-reported ``sessionClose()`` patch is applied locally; the
fork additionally adds ``setItemAction``, ``getItemAction``, ``searchItemAction``,
IPv6 support across add/set, and explicit-name on add. See
``AssignSettingsController.php`` for the PHP source.

This is a sibling to ``tools/spikes/vlan_direct_api.py`` — same Python shape,
different OPNsense surface. Server-side validation (controller-side) is a
deliberate departure from #714's SSH+PHP-edit path: bad inputs get rejected
loudly with an ``errorMessage`` field instead of producing silent-bad XML.

Subcommands:

    inspect          Detect controller install state, OPNsense version, baseline.
    list             Dump current interface assignments via interfacesInfo.
    plan <yaml>      Diff YAML vs live state.
    apply <yaml>     Execute changes via REST (requires --confirm).
    install          Idempotent install of the PHP controller (delegates to install.py).
    verify-install   Check controller-on-box checksum matches local file.

Environment variables:

    REST (always required):
        OPNSENSE_API_URL
        OPNSENSE_API_KEY
        OPNSENSE_API_SECRET
        OPNSENSE_VERIFY_SSL    (optional; defaults to "true")

    SSH (only required for ``install`` / ``verify-install`` / ``inspect`` checksum probe):
        OPNSENSE_SSH_HOST
        OPNSENSE_SSH_USER      (defaults to "root")
        OPNSENSE_SSH_PORT      (defaults to "22")
        OPNSENSE_SSH_KEY       (path to SSH private key)
        OPNSENSE_INSTALL_PATH  (optional override)

Usage::

    SPIKE=tools/spikes/interface_assignment_gist_rest/interface_assignment_gist_rest.py
    python $SPIKE inspect
    python $SPIKE list
    python $SPIKE plan ./example-interface-assignments.yaml
    python $SPIKE apply ./example-interface-assignments.yaml --confirm
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from opnsense_openapi import OPNsenseClient

# Support both invocation modes: as a module (``python -m tools.spikes...``)
# and as a script (``python tools/spikes/.../interface_assignment_gist_rest.py``).
# The latter doesn't have ``tools.spikes...`` on sys.path, so fall back to a
# direct path-based import of the sibling install module.
try:
    from tools.spikes.interface_assignment_gist_rest import install as installer
except ImportError:  # pragma: no cover — exercised only when run as a script.
    import importlib.util as _importlib_util

    _install_path = Path(__file__).resolve().parent / "install.py"
    _spec = _importlib_util.spec_from_file_location("install", _install_path)
    if _spec is None or _spec.loader is None:
        raise
    installer = _importlib_util.module_from_spec(_spec)
    # Register in sys.modules BEFORE exec — dataclass() reads the module's
    # __dict__ via sys.modules.get(__module__), so the module must be there.
    sys.modules["install"] = installer
    _spec.loader.exec_module(installer)

# ---------------------------------------------------------------------------
# Constants — controller endpoint coordinates
# ---------------------------------------------------------------------------

# The OPNsense MVC URL routing converts ``AssignSettingsController`` to
# ``assign_settings`` (snake_case). This is the same heterogeneity the VLAN
# spike documented; the live path has the underscore.
ASSIGN_MODULE = "interfaces"
ASSIGN_CONTROLLER = "assign_settings"

# OPNsense's interfacesInfo endpoint — the read-only baseline used for ``list``
# and as the source-of-truth for diffing during ``plan``/``apply``. The
# controller's own ``searchItem`` is also available post-install but we keep
# ``interfacesInfo`` as the default since it's part of OPNsense's stock API
# (no controller dependency needed for read-only views).
INTERFACES_INFO_MODULE = "interfaces"
INTERFACES_INFO_CONTROLLER = "overview"
INTERFACES_INFO_COMMAND = "interfacesInfo"

# Backup endpoints used for pre-apply snapshot capture + auto-rollback.
BACKUP_MODULE = "core"
BACKUP_CONTROLLER = "backup"
BACKUP_LIST_COMMAND = "backups"
BACKUP_REVERT_COMMAND = "revertBackup"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Credentials:
    """Resolved OPNsense REST credentials sourced from env."""

    api_url: str
    api_key: str
    api_secret: str
    verify_ssl: bool


@dataclass(frozen=True)
class InterfaceAssignmentConfig:
    """Desired-state interface-assignment config loaded from YAML.

    Mirrors ``src/infrafoundry/providers/opnsense/services/interface_assignment.py``'s
    ``InterfaceAssignmentConfig`` but with extra fields the spike's controller
    accepts (``ipv4Type``/``ipv6Type``/``spoofMac``/...). Diff key is the
    logical interface name (``identifier``); that's what makes an assignment
    unique on a box.

    The ``lock`` meta-property declares "observed but untouchable" — the
    spike treats the matching live record as untouchable and never adds,
    updates, or deletes it. Locks travel with specific resources in YAML.
    """

    name: str
    device: str
    description: str
    enabled: bool = True
    lock: bool = False
    spoof_mac: str | None = None
    # IPv4 fields
    ipv4_type: str = "none"  # static | dhcp | none
    ipv4_address: str | None = None
    ipv4_subnet: int | None = None
    # IPv6 fields
    ipv6_type: str = "none"  # static | dhcp | track-interface | none
    ipv6_address: str | None = None
    ipv6_subnet: int | None = None
    ipv6_track: str | None = None

    @property
    def diff_key(self) -> str:
        """Identity on the box: the logical interface name (e.g. 'opt3')."""
        return self.name

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the dict shape the controller expects.

        The controller accepts ``{"assign": {<fields>}}``. ``name`` is forwarded
        only when set (the controller falls back to auto-numbering otherwise).
        """
        assign: dict[str, Any] = {
            "device": self.device,
            "description": self.description,
            "enable": self.enabled,
            "name": self.name,
            "ipv4Type": self.ipv4_type,
            "ipv6Type": self.ipv6_type,
        }
        if self.spoof_mac:
            assign["spoofMac"] = self.spoof_mac
        if self.ipv4_type == "static":
            assign["ipv4Address"] = self.ipv4_address
            assign["ipv4Subnet"] = self.ipv4_subnet
        if self.ipv6_type == "static":
            assign["ipv6Address"] = self.ipv6_address
            assign["ipv6Subnet"] = self.ipv6_subnet
        if self.ipv6_type == "track-interface":
            assign["ipv6Track"] = self.ipv6_track
        return {"assign": assign}


@dataclass(frozen=True)
class LiveInterfaceAssignment:
    """A live interface assignment as returned by interfacesInfo.

    Mirrors the production ``LiveInterfaceAssignment`` shape but redeclared
    locally so the spike is self-contained (per the established
    ``vlan_direct_api`` / ``LiveVlan`` pattern).
    """

    identifier: str
    device: str
    description: str
    is_physical: bool
    ipv4: dict[str, Any]
    ipv6: dict[str, Any]
    macaddr: str
    mtu: int

    @property
    def diff_key(self) -> str:
        """Identity on the box: the logical interface name."""
        return self.identifier


@dataclass
class Diff:
    """Result of comparing desired YAML state to live state."""

    adds: list[InterfaceAssignmentConfig] = field(default_factory=list)
    updates: list[tuple[LiveInterfaceAssignment, InterfaceAssignmentConfig]] = field(
        default_factory=list
    )
    deletes: list[LiveInterfaceAssignment] = field(default_factory=list)
    locked: list[tuple[InterfaceAssignmentConfig, LiveInterfaceAssignment | None]] = field(
        default_factory=list
    )

    @property
    def is_empty(self) -> bool:
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Environment / configuration loading
# ---------------------------------------------------------------------------


def load_env_credentials(env: dict[str, str] | None = None) -> Credentials:
    """Read OPNsense REST credentials from env vars.

    Args:
        env: Mapping to read from. Defaults to ``os.environ``. Injectable for tests.

    Returns:
        A populated ``Credentials``.

    Raises:
        RuntimeError: If any of ``OPNSENSE_API_URL``/``_API_KEY``/``_API_SECRET``
            is missing or empty.
    """
    source: dict[str, str] = dict(os.environ if env is None else env)
    required: tuple[str, ...] = (
        "OPNSENSE_API_URL",
        "OPNSENSE_API_KEY",
        "OPNSENSE_API_SECRET",
    )
    missing: list[str] = [key for key in required if not source.get(key)]
    if missing:
        raise RuntimeError(
            "Missing required OPNsense environment variable(s): "
            f"{', '.join(missing)}. Source them from the secrets repo before "
            "running this spike — see tools/spikes/README.md."
        )

    verify_raw: str = source.get("OPNSENSE_VERIFY_SSL", "true").strip().lower()
    verify_ssl: bool = verify_raw not in ("0", "false", "no", "off")

    return Credentials(
        api_url=source["OPNSENSE_API_URL"],
        api_key=source["OPNSENSE_API_KEY"],
        api_secret=source["OPNSENSE_API_SECRET"],
        verify_ssl=verify_ssl,
    )


def load_assignments_from_yaml(path: Path) -> list[InterfaceAssignmentConfig]:
    """Parse a YAML file of interface_assignment resource definitions.

    Expects the InfraFoundry resource shape::

        - provider: opnsense
          type: interface_assignments
          name: opt3
          config:
            device: igc0
            description: spike-test
            enabled: true
            ipv4:
              type: static
              address: 10.20.30.1
              subnet: 24
            ipv6:
              type: track-interface
              track: wan

    Args:
        path: YAML file path.

    Returns:
        Validated list of ``InterfaceAssignmentConfig`` instances.

    Raises:
        ValueError: On malformed YAML or invalid per-field values.
    """
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, list):
        raise ValueError(
            f"Expected top-level list of resources in {path}, got {type(raw).__name__}"
        )

    configs: list[InterfaceAssignmentConfig] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"Resource at index {index} is not a mapping")
        if entry.get("type") != "interface_assignments":
            # Allow non-matching resources to coexist; they're ignored here.
            continue

        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"Resource at index {index} missing string 'name'")

        config = entry.get("config")
        if not isinstance(config, dict):
            raise ValueError(f"interface_assignment '{name}' missing or invalid 'config' mapping")

        device = config.get("device")
        if not isinstance(device, str) or not device:
            raise ValueError(f"interface_assignment '{name}' missing string 'device'")

        description = config.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"interface_assignment '{name}' description must be a string")

        enabled_raw = config.get("enabled", True)
        if not isinstance(enabled_raw, bool):
            raise ValueError(f"interface_assignment '{name}' enabled must be a boolean")

        # ``lock`` is a top-level meta-property, not nested under ``config``.
        lock_raw = entry.get("lock", False)
        if not isinstance(lock_raw, bool):
            raise ValueError(f"interface_assignment '{name}' lock must be a boolean")

        spoof_mac_raw = config.get("spoof_mac")
        if spoof_mac_raw is not None and not isinstance(spoof_mac_raw, str):
            raise ValueError(f"interface_assignment '{name}' spoof_mac must be a string")

        ipv4_type, ipv4_address, ipv4_subnet = _parse_ipv4_block(config.get("ipv4", {}), name)
        ipv6_type, ipv6_address, ipv6_subnet, ipv6_track = _parse_ipv6_block(
            config.get("ipv6", {}), name
        )

        configs.append(
            InterfaceAssignmentConfig(
                name=name,
                device=device,
                description=description,
                enabled=enabled_raw,
                lock=lock_raw,
                spoof_mac=spoof_mac_raw,
                ipv4_type=ipv4_type,
                ipv4_address=ipv4_address,
                ipv4_subnet=ipv4_subnet,
                ipv6_type=ipv6_type,
                ipv6_address=ipv6_address,
                ipv6_subnet=ipv6_subnet,
                ipv6_track=ipv6_track,
            )
        )

    return configs


def _parse_ipv4_block(block: Any, name: str) -> tuple[str, str | None, int | None]:
    """Parse the ``ipv4`` sub-block of an interface_assignments config.

    Returns ``(type, address, subnet)``. Defaults to ``("none", None, None)``.
    """
    if not isinstance(block, dict):
        raise ValueError(f"interface_assignment '{name}' ipv4 must be a mapping")
    if not block:
        return ("none", None, None)

    ipv4_type = block.get("type", "none")
    if ipv4_type not in ("static", "dhcp", "none"):
        raise ValueError(
            f"interface_assignment '{name}' ipv4.type must be one of: static, dhcp, none"
        )

    address = block.get("address")
    subnet = block.get("subnet")

    if ipv4_type == "static":
        if not isinstance(address, str) or not address:
            raise ValueError(
                f"interface_assignment '{name}' ipv4.address required when type is 'static'"
            )
        if subnet is None:
            raise ValueError(
                f"interface_assignment '{name}' ipv4.subnet required when type is 'static'"
            )
        try:
            subnet_int = int(subnet)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"interface_assignment '{name}' ipv4.subnet must be an integer 1-32"
            ) from exc
        if not 1 <= subnet_int <= 32:
            raise ValueError(
                f"interface_assignment '{name}' ipv4.subnet {subnet_int} out of range 1-32"
            )
        return ("static", address, subnet_int)

    # dhcp / none — extra fields not allowed.
    if address or subnet is not None:
        raise ValueError(
            f"interface_assignment '{name}' ipv4.address/subnet only valid when type is 'static'"
        )
    return (ipv4_type, None, None)


def _parse_ipv6_block(block: Any, name: str) -> tuple[str, str | None, int | None, str | None]:
    """Parse the ``ipv6`` sub-block of an interface_assignments config.

    Returns ``(type, address, subnet, track)``. Defaults to ``("none", None, None, None)``.
    """
    if not isinstance(block, dict):
        raise ValueError(f"interface_assignment '{name}' ipv6 must be a mapping")
    if not block:
        return ("none", None, None, None)

    ipv6_type = block.get("type", "none")
    if ipv6_type not in ("static", "dhcp", "track-interface", "none"):
        raise ValueError(
            f"interface_assignment '{name}' ipv6.type must be one of: "
            "static, dhcp, track-interface, none"
        )

    address = block.get("address")
    subnet = block.get("subnet")
    track = block.get("track")

    if ipv6_type == "static":
        if not isinstance(address, str) or not address:
            raise ValueError(
                f"interface_assignment '{name}' ipv6.address required when type is 'static'"
            )
        if subnet is None:
            raise ValueError(
                f"interface_assignment '{name}' ipv6.subnet required when type is 'static'"
            )
        try:
            subnet_int = int(subnet)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"interface_assignment '{name}' ipv6.subnet must be an integer 1-128"
            ) from exc
        if not 1 <= subnet_int <= 128:
            raise ValueError(
                f"interface_assignment '{name}' ipv6.subnet {subnet_int} out of range 1-128"
            )
        return ("static", address, subnet_int, None)

    if ipv6_type == "track-interface":
        if not isinstance(track, str) or not track:
            raise ValueError(
                f"interface_assignment '{name}' ipv6.track required when type is 'track-interface'"
            )
        return ("track-interface", None, None, track)

    # dhcp / none — extra fields not allowed.
    if address or subnet is not None or track:
        raise ValueError(
            f"interface_assignment '{name}' ipv6.address/subnet/track only valid for "
            "type 'static' or 'track-interface'"
        )
    return (ipv6_type, None, None, None)


# ---------------------------------------------------------------------------
# Client + REST helpers
# ---------------------------------------------------------------------------


def build_client(credentials: Credentials) -> OPNsenseClient:
    """Construct an OPNsenseClient with auto_detect_version=True.

    Same intentional divergence from the production wrapper as
    ``vlan_direct_api`` — ADR-0014 owns the decision about flipping the flag
    in production.
    """
    return OPNsenseClient(
        base_url=credentials.api_url,
        api_key=credentials.api_key,
        api_secret=credentials.api_secret,
        verify_ssl=credentials.verify_ssl,
        auto_detect_version=True,
    )


def fetch_interfaces_info(client: OPNsenseClient) -> list[LiveInterfaceAssignment]:
    """Pull live interface assignments from interfacesInfo.

    Skips rows whose ``identifier`` is empty — those are unassigned NICs.
    """
    response: Any = client.get(
        INTERFACES_INFO_MODULE, INTERFACES_INFO_CONTROLLER, INTERFACES_INFO_COMMAND
    )

    rows: list[dict[str, Any]] = []
    if isinstance(response, dict):
        raw_rows = response.get("rows")
        if isinstance(raw_rows, list):
            rows = [r for r in raw_rows if isinstance(r, dict)]

    return [_row_to_live_assignment(row) for row in rows if row.get("identifier")]


def _row_to_live_assignment(row: dict[str, Any]) -> LiveInterfaceAssignment:
    """Normalize an interfacesInfo row.

    Mirrors ``services/interface_assignment.py:_row_to_live_assignment`` so
    field semantics stay aligned with the production read path.
    """
    identifier = str(row.get("identifier", ""))
    device = str(row.get("device", ""))
    description = str(row.get("description", "") or "")
    is_physical = bool(row.get("is_physical", False))
    macaddr = str(row.get("macaddr", "") or "")

    ipv4_raw = row.get("ipv4", {})
    ipv4: dict[str, Any] = ipv4_raw if isinstance(ipv4_raw, dict) else {}

    ipv6_raw = row.get("ipv6", {})
    ipv6: dict[str, Any] = ipv6_raw if isinstance(ipv6_raw, dict) else {}

    try:
        mtu = int(row.get("mtu", 0) or 0)
    except (TypeError, ValueError):
        mtu = 0

    return LiveInterfaceAssignment(
        identifier=identifier,
        device=device,
        description=description,
        is_physical=is_physical,
        ipv4=ipv4,
        ipv6=ipv6,
        macaddr=macaddr,
        mtu=mtu,
    )


def add_assignment(client: OPNsenseClient, config: InterfaceAssignmentConfig) -> dict[str, Any]:
    """Create a new interface assignment via the controller's addItem endpoint."""
    response: Any = client.post(
        ASSIGN_MODULE, ASSIGN_CONTROLLER, "addItem", json=config.to_payload()
    )
    return response if isinstance(response, dict) else {"raw": response}


def update_assignment(
    client: OPNsenseClient, identifier: str, config: InterfaceAssignmentConfig
) -> dict[str, Any]:
    """Update an existing assignment via the controller's setItem endpoint."""
    response: Any = client.post(
        ASSIGN_MODULE, ASSIGN_CONTROLLER, "setItem", identifier, json=config.to_payload()
    )
    return response if isinstance(response, dict) else {"raw": response}


def delete_assignment(client: OPNsenseClient, identifier: str) -> dict[str, Any]:
    """Delete an assignment via the controller's delItem endpoint."""
    response: Any = client.post(ASSIGN_MODULE, ASSIGN_CONTROLLER, "delItem", identifier)
    return response if isinstance(response, dict) else {"raw": response}


def get_assignment(client: OPNsenseClient, identifier: str) -> dict[str, Any]:
    """Fetch a single assignment via the controller's getItem endpoint."""
    response: Any = client.get(ASSIGN_MODULE, ASSIGN_CONTROLLER, "getItem", identifier)
    return response if isinstance(response, dict) else {"raw": response}


def search_assignments_via_controller(client: OPNsenseClient) -> list[dict[str, Any]]:
    """List assignments via the controller's searchItem endpoint.

    Used in inspect/verification flows to confirm the extended controller is
    installed and returning rows. The default ``list`` subcommand uses
    ``interfacesInfo`` instead so it works against stock OPNsense too.
    """
    response: Any = client.post(ASSIGN_MODULE, ASSIGN_CONTROLLER, "searchItem")
    rows: list[dict[str, Any]] = []
    if isinstance(response, dict):
        raw_rows = response.get("rows")
        if isinstance(raw_rows, list):
            rows = [r for r in raw_rows if isinstance(r, dict)]
    return rows


# ---------------------------------------------------------------------------
# Backup / rollback helpers
# ---------------------------------------------------------------------------


def list_backup_ids(client: OPNsenseClient) -> list[str]:
    """List available backup snapshots, newest first.

    OPNsense's ``/api/core/backup/backups`` returns a list of strings (or in
    some versions a dict keyed by id). We normalize defensively.
    """
    response: Any = client.get(BACKUP_MODULE, BACKUP_CONTROLLER, BACKUP_LIST_COMMAND)
    if isinstance(response, list):
        return [str(item) for item in response]
    if isinstance(response, dict):
        # Some OPNsense versions return {"backups": [...]} or a flat dict.
        if "backups" in response and isinstance(response["backups"], list):
            return [str(item) for item in response["backups"]]
        return [str(k) for k in response]
    return []


def capture_latest_backup_id(client: OPNsenseClient) -> str | None:
    """Return the id of the newest backup, or ``None`` if no backups exist.

    OPNsense's ``backups`` endpoint returns ids in a stable order; we take
    the first one as "newest" (matches the GUI's display convention).
    """
    ids = list_backup_ids(client)
    return ids[0] if ids else None


def revert_to_backup(client: OPNsenseClient, backup_id: str) -> dict[str, Any]:
    """Revert the OPNsense config to a previously-captured backup snapshot.

    Per the spike's risk register, this likely reverts the WHOLE config
    (not just <interfaces>); acceptable for a spike but flagged in the
    findings doc.
    """
    response: Any = client.post(BACKUP_MODULE, BACKUP_CONTROLLER, BACKUP_REVERT_COMMAND, backup_id)
    return response if isinstance(response, dict) else {"raw": response}


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def compute_diff(
    desired: list[InterfaceAssignmentConfig],
    current: list[LiveInterfaceAssignment],
    *,
    add_only: bool = False,
) -> Diff:
    """Compare desired YAML state to live state, keyed by identifier.

    Locked YAML entries are skipped entirely — recorded in ``Diff.locked``
    but never appearing in ``adds``/``updates``/``deletes``.

    ``add_only`` suppresses deletes but still emits adds and updates — useful
    for partial migrations where the YAML doesn't yet describe everything
    on the box.
    """
    desired_by_key: dict[str, InterfaceAssignmentConfig] = {v.diff_key: v for v in desired}
    current_by_key: dict[str, LiveInterfaceAssignment] = {v.diff_key: v for v in current}
    locked_keys: set[str] = {v.diff_key for v in desired if v.lock}

    adds: list[InterfaceAssignmentConfig] = []
    updates: list[tuple[LiveInterfaceAssignment, InterfaceAssignmentConfig]] = []
    deletes: list[LiveInterfaceAssignment] = []
    locked: list[tuple[InterfaceAssignmentConfig, LiveInterfaceAssignment | None]] = []

    for key, want in desired_by_key.items():
        have = current_by_key.get(key)
        if want.lock:
            locked.append((want, have))
            continue
        if have is None:
            adds.append(want)
        elif _needs_update(have, want):
            updates.append((have, want))

    if not add_only:
        for key, have in current_by_key.items():
            if key in locked_keys:
                continue
            if key not in desired_by_key:
                deletes.append(have)

    return Diff(adds=adds, updates=updates, deletes=deletes, locked=locked)


def _needs_update(have: LiveInterfaceAssignment, want: InterfaceAssignmentConfig) -> bool:
    """Decide whether a live assignment differs enough from desired to warrant setItem.

    The spike checks the fields that the controller can reasonably write
    server-side: ``device`` and ``description``. The IPv4/IPv6 raw dicts
    aren't compared field-for-field here because the live representation
    (from ``interfacesInfo``) and the desired representation (typed config)
    have different schemas; that's a deliberate spike scope choice. The
    findings doc captures this as an open question — ADR-0014 will need a
    decision about deep IPv4/IPv6 equality before this graduates to
    production.
    """
    return (have.device, have.description) != (want.device, want.description)


# ---------------------------------------------------------------------------
# Lockout-prevention
# ---------------------------------------------------------------------------


def find_lockout_conflicts(diff: Diff, current: list[LiveInterfaceAssignment]) -> list[str]:
    """Return human-readable messages for any apply-time lockout risks.

    Refuses to apply if a planned ``add`` targets a ``device`` that is
    already bound to another logical interface (mirrors #714's design).
    The ``setItem`` path already lets the controller server-side check
    do this; we still pre-flight on the spike side so the operator gets a
    coherent failure mode before any REST calls fire.

    For ``setItem`` (updates), we only complain if the device is changing
    AND the new device is bound to a *different* interface than the one
    being updated.
    """
    msgs: list[str] = []
    by_device: dict[str, str] = {entry.device: entry.identifier for entry in current}

    for want in diff.adds:
        existing_holder = by_device.get(want.device)
        if existing_holder is not None:
            msgs.append(
                f"add {want.name!r}: device '{want.device}' is already bound to "
                f"'{existing_holder}'. Refusing to apply."
            )

    for live, want in diff.updates:
        if live.device == want.device:
            continue  # device isn't changing
        existing_holder = by_device.get(want.device)
        if existing_holder is not None and existing_holder != want.name:
            msgs.append(
                f"update {want.name!r}: new device '{want.device}' is already bound "
                f"to '{existing_holder}'. Refusing to apply."
            )

    return msgs


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def cmd_inspect(client: OPNsenseClient) -> int:
    """Detect controller install state, OPNsense version, and REST baseline."""
    version: str = client.detect_version()
    print(f"Detected OPNsense version: {version}")

    # Controller install probe — best effort. SSH credentials are optional
    # for inspect; if they're missing we just skip the checksum check.
    try:
        target = installer.load_ssh_target()
    except RuntimeError as exc:
        print(f"Controller checksum check skipped: {exc}")
    else:
        try:
            matches, remote_sum, local_sum = installer.verify_installed_checksum(target)
            local_short = local_sum[:12]
            if matches:
                print(f"Controller installed and current (sha256 {local_short}…).")
            elif remote_sum is None:
                print(f"Controller NOT installed on {target.host}. Run `install` to deploy.")
            else:
                print(
                    f"Controller checksum mismatch on {target.host}: "
                    f"remote {remote_sum[:12]}… vs local {local_short}…"
                )
        except RuntimeError as exc:
            print(f"Controller checksum probe failed: {exc}")

    # REST baseline — read-only call to interfacesInfo to confirm the API is reachable.
    try:
        live = fetch_interfaces_info(client)
        print(f"Live assignments visible: {len(live)}")
        for entry in live:
            print(f"  {entry.identifier:8s} -> {entry.device}  ({entry.description})")
    except Exception as exc:
        print(f"interfacesInfo probe failed: {exc}")
        return 1

    return 0


def cmd_list(client: OPNsenseClient) -> int:
    """Print the current interface assignments on the box as YAML."""
    live = fetch_interfaces_info(client)
    if not live:
        print("# (no interface assignments found on box)")
        return 0
    payload = [
        {
            "provider": "opnsense",
            "type": "interface_assignments",
            "name": entry.identifier,
            "config": {
                "device": entry.device,
                "description": entry.description,
                "enabled": True,
                "ipv4": entry.ipv4,
                "ipv6": entry.ipv6,
            },
        }
        for entry in live
    ]
    print(yaml.safe_dump(payload, sort_keys=False))
    return 0


def cmd_plan(client: OPNsenseClient, yaml_path: Path, *, add_only: bool = False) -> int:
    """Compute and print the diff between YAML and live state."""
    desired = load_assignments_from_yaml(yaml_path)
    current = fetch_interfaces_info(client)
    diff = compute_diff(desired, current, add_only=add_only)
    _print_diff(diff, add_only=add_only)
    return 0


def cmd_apply(
    client: OPNsenseClient,
    yaml_path: Path,
    *,
    confirm: bool,
    add_only: bool = False,
    print_rollback: bool = False,
    no_rollback: bool = False,
    backup_snapshot_id: str | None = None,
) -> int:
    """Execute the diff via REST. ``--confirm`` is required for actual mutations."""
    desired = load_assignments_from_yaml(yaml_path)
    current = fetch_interfaces_info(client)
    diff = compute_diff(desired, current, add_only=add_only)
    _print_diff(diff, add_only=add_only)

    if diff.is_empty:
        return 0

    # Pre-flight lockout check before mutating.
    conflicts = find_lockout_conflicts(diff, current)
    if conflicts:
        print("\nLockout risk detected — refusing to apply:")
        for msg in conflicts:
            print(f"  ! {msg}")
        return 1

    if not confirm:
        print("\nDry run — pass --confirm to apply these changes.")
        return 0

    # Capture (or accept override) of pre-apply snapshot id for auto-rollback.
    if backup_snapshot_id is not None:
        snapshot_id: str | None = backup_snapshot_id
        print(f"\nUsing operator-supplied backup snapshot id: {snapshot_id}")
    elif no_rollback:
        snapshot_id = None
        print("\nAuto-rollback disabled (--no-rollback).")
    else:
        try:
            snapshot_id = capture_latest_backup_id(client)
        except Exception as exc:
            print(f"WARNING: failed to capture pre-apply backup id: {exc}")
            snapshot_id = None
        if snapshot_id:
            print(f"\nCaptured pre-apply backup id: {snapshot_id}")
        else:
            print("\nWARNING: no backup snapshot captured; auto-rollback unavailable.")

    if print_rollback and snapshot_id:
        print(f"  (rollback command: revert to backup id '{snapshot_id}')")

    print("\nApplying changes via REST...")
    try:
        for cfg in diff.adds:
            result = add_assignment(client, cfg)
            print(
                f"  + add  {cfg.name:8s} device={cfg.device:14s} -> {result.get('result', result)}"
            )
            _raise_on_failure(result, f"add {cfg.name}")

        for live, want in diff.updates:
            result = update_assignment(client, live.identifier, want)
            print(
                f"  ~ set  {want.name:8s} device={want.device:14s} -> "
                f"{result.get('result', result)}"
            )
            _raise_on_failure(result, f"setItem {want.name}")

        for live in diff.deletes:
            result = delete_assignment(client, live.identifier)
            print(
                f"  - del  {live.identifier:8s} device={live.device:14s} -> "
                f"{result.get('result', result)}"
            )
            _raise_on_failure(result, f"delItem {live.identifier}")
    except RuntimeError as exc:
        print(f"\nApply failed: {exc}")
        if snapshot_id and not no_rollback:
            print(f"Auto-rollback: reverting to backup id {snapshot_id}...")
            try:
                rollback_result = revert_to_backup(client, snapshot_id)
                print(f"  rollback -> {rollback_result.get('status', rollback_result)}")
            except Exception as rb_exc:
                print(f"  rollback FAILED: {rb_exc}")
                print("  Manual recovery required.")
        return 1

    print("\nApply complete.")
    return 0


def _raise_on_failure(response: dict[str, Any], action: str) -> None:
    """Convert a controller failure response into a RuntimeError.

    The PHP controller returns ``{"result": "failed", "errorMessage": "..."}``
    on validation failures. We surface that as a Python exception so the
    apply loop can short-circuit and trigger auto-rollback.
    """
    result_value = response.get("result")
    if result_value not in ("saved", "deleted", "ok"):
        msg = response.get("errorMessage", str(response))
        raise RuntimeError(f"{action}: {msg}")


def cmd_install(*, force: bool = False) -> int:
    """Idempotent install of the controller PHP via the bundled installer."""
    target = installer.load_ssh_target()
    installer.install_controller(target, force=force)
    return 0


def cmd_verify_install() -> int:
    """Compare the on-box controller checksum to the local source."""
    target = installer.load_ssh_target()
    matches, remote_sum, local_sum = installer.verify_installed_checksum(target)
    local_short = local_sum[:12]
    if matches:
        print(f"OK: on-box and local checksums match (sha256 {local_short}…).")
        return 0
    if remote_sum is None:
        print(f"MISSING: controller not installed on {target.host}.")
    else:
        print(f"MISMATCH: remote {remote_sum[:12]}… vs local {local_short}…")
    return 1


def _print_diff(diff: Diff, *, add_only: bool = False) -> None:
    """Render a Diff for the operator."""
    if diff.is_empty and not diff.locked:
        print("No changes.")
        return
    mode_suffix = " (add-only mode — deletes suppressed)" if add_only else ""
    print(
        f"Plan: {len(diff.adds)} to add, {len(diff.updates)} to update, "
        f"{len(diff.deletes)} to delete, {len(diff.locked)} locked.{mode_suffix}"
    )
    for cfg in diff.adds:
        print(
            f"  + {cfg.name:8s} device={cfg.device:14s} desc={cfg.description!r} "
            f"ipv4={cfg.ipv4_type} ipv6={cfg.ipv6_type}"
        )
    for live, want in diff.updates:
        print(
            f"  ~ {want.name:8s} device={live.device}->{want.device} "
            f"desc={live.description!r}->{want.description!r}"
        )
    for live in diff.deletes:
        print(f"  - {live.identifier:8s} device={live.device:14s} desc={live.description!r}")
    for want, have in diff.locked:
        if have is None:
            print(f"  L {want.name:8s} (locked, declared but not present on box)")
        else:
            print(
                f"  L {have.identifier:8s} device={have.device} (locked) — no action will be taken"
            )


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse CLI."""
    parser = argparse.ArgumentParser(
        prog="interface_assignment_gist_rest",
        description=(
            "Gist-based REST spike for OPNsense interface_assignments — informs ADR-0014 (#715)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("inspect", help="Detect controller install state, version, REST baseline.")
    sub.add_parser("list", help="Dump current interface assignments via interfacesInfo.")

    plan_parser = sub.add_parser("plan", help="Diff a YAML file against live state.")
    plan_parser.add_argument("yaml_path", type=Path, help="Path to interface-assignments YAML.")
    plan_parser.add_argument(
        "--add-only",
        action="store_true",
        help=(
            "Suppress deletes for live assignments not in the YAML. Useful for "
            "partial migrations where the YAML doesn't yet describe everything."
        ),
    )

    apply_parser = sub.add_parser("apply", help="Apply a YAML file's diff via REST.")
    apply_parser.add_argument("yaml_path", type=Path, help="Path to interface-assignments YAML.")
    apply_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually dispatch mutations. Without this flag, apply is a dry run.",
    )
    apply_parser.add_argument(
        "--add-only",
        action="store_true",
        help="Suppress deletes for live assignments not in the YAML.",
    )
    apply_parser.add_argument(
        "--print-rollback",
        action="store_true",
        help="Print the rollback command/id before applying.",
    )
    apply_parser.add_argument(
        "--no-rollback",
        action="store_true",
        help="Disable the auto-rollback on apply failure.",
    )
    apply_parser.add_argument(
        "--backup-snapshot-id",
        type=str,
        default=None,
        help="Override the auto-captured pre-apply snapshot id.",
    )

    install_parser = sub.add_parser("install", help="Install the controller PHP on the box.")
    install_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-install even when the on-box checksum already matches.",
    )
    sub.add_parser("verify-install", help="Check the on-box controller checksum.")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # ``install`` and ``verify-install`` are SSH-only — no REST credentials needed.
    if args.command == "install":
        return cmd_install(force=bool(args.force))
    if args.command == "verify-install":
        return cmd_verify_install()

    credentials = load_env_credentials()
    client = build_client(credentials)

    try:
        if args.command == "inspect":
            return cmd_inspect(client)
        if args.command == "list":
            return cmd_list(client)
        if args.command == "plan":
            return cmd_plan(client, args.yaml_path, add_only=bool(args.add_only))
        if args.command == "apply":
            return cmd_apply(
                client,
                args.yaml_path,
                confirm=bool(args.confirm),
                add_only=bool(args.add_only),
                print_rollback=bool(args.print_rollback),
                no_rollback=bool(args.no_rollback),
                backup_snapshot_id=args.backup_snapshot_id,
            )
    finally:
        client.close()

    parser.error(f"Unknown command: {args.command}")  # NoReturn — argparse exits


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
