"""Direct-API VLAN management spike for OPNsense — informs ADR-0014.

Demonstrates end-to-end VLAN management against the OPNsense REST API using
``opnsense_openapi``'s typed ``.api.<module>.<function>`` surface, with a
``client.get/post(...)`` fallback for endpoints the typed surface fails to
expose. Reads desired state from a YAML file, computes a diff against live
state keyed by ``(device, tag)`` (the natural identity of a VLAN on a box),
and applies changes only when ``--confirm`` is passed.

This script intentionally lives outside ``src/infrafoundry/providers/opnsense/``
so it can ship or be deleted on its own merits. It does NOT modify any
production code path. The findings document at
``docs/development/opnsense-spike-vlan-findings.md`` is filled in after
running this spike against a staging box; ADR-0014 cites that document.

Subcommands:
    inspect   — connect, detect version, report endpoint count + typed-surface readiness
    list      — dump the current VLANs on the box as YAML
    plan      — diff a YAML file against current state, print add/update/delete counts
    apply     — like ``plan``, but dispatches the typed mutations when ``--confirm`` is set

Environment variables (matched against the existing OPNsense validator at
``src/infrafoundry/providers/opnsense/validator.py:208-210``):
    OPNSENSE_API_URL
    OPNSENSE_API_KEY
    OPNSENSE_API_SECRET
    OPNSENSE_VERIFY_SSL    (optional; defaults to "true")

Usage::

    python tools/spikes/vlan_direct_api.py inspect
    python tools/spikes/vlan_direct_api.py list
    python tools/spikes/vlan_direct_api.py plan tools/spikes/example-vlans.yaml
    python tools/spikes/vlan_direct_api.py apply tools/spikes/example-vlans.yaml --confirm
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from opnsense_openapi import OPNsenseClient


def _warn_if_codegen_unavailable() -> None:
    """Warn if ``openapi-python-client`` isn't on ``PATH``.

    The typed ``.api`` surface in ``opnsense_openapi`` is auto-generated on
    first use by shelling out to the ``openapi-python-client`` CLI. Without
    it, ``client.api.<...>`` raises ``RuntimeError`` ("No OpenAPI spec found
    for version ...") and the spike falls back to bare ``client.get/post``
    for every operation. Capturing this as a clear warning at startup is
    itself a finding for ADR-0014: a typed surface gated on an external CLI
    binary is non-trivial to provision in production.
    """
    if shutil.which("openapi-python-client") is None:
        sys.stderr.write(
            "WARNING: openapi-python-client is not on PATH.\n"
            "  The typed .api surface cannot be generated; the spike will\n"
            "  fall back to bare client.get/post(...) for every operation.\n"
            "  Install with: uv tool install openapi-python-client\n"
            "  (See docs/development/opnsense-spike-vlan-findings.md)\n\n"
        )


# ---------------------------------------------------------------------------
# Constants — VLAN endpoint coordinates in the OPNsense REST API
# ---------------------------------------------------------------------------

VLAN_MODULE = "interfaces"
# Live OPNsense 26.1.6_2 routes to ``/api/interfaces/vlan_settings/*`` (with
# underscore). The bundled OpenAPI spec at opnsense-openapi 0.3.0 advertises
# ``vlansettings`` (no underscore). The spec is wrong: the generator does
# naive lowercasing of CamelCase, but OPNsense's URL routing converts
# ``VlanSettingsController`` to snake_case. This is heterogeneous across
# controllers — Kea uses ``dhcpv4``/``dhcpv6`` (no underscore) while
# VlanSettings uses ``vlan_settings``. Fixing this in the upstream spec
# generator is a hard problem (no universal rule); we use the verified-
# correct live path here and capture the finding for ADR-0014.
VLAN_CONTROLLER = "vlan_settings"

# Typed-surface function names follow the generated client's snake_case naming
# convention: ``api.interfaces.<controller>_<action>``. With the spec bug
# above, the typed surface (when generated) would also point at the wrong
# URL and 404. The spike's typed-surface probe in ``_typed_call`` absorbs
# this — but that the typed path is non-functional against current 0.3.0
# specs is itself a finding for ADR-0014. The names below match what the
# generator currently emits; they will need to update to ``vlan_settings_*``
# when the upstream spec is fixed.
TYPED_FN_SEARCH = "vlansettings_search_item"
TYPED_FN_ADD = "vlansettings_add_item"
TYPED_FN_GET = "vlansettings_get_item"
TYPED_FN_SET = "vlansettings_set_item"
TYPED_FN_DEL = "vlansettings_del_item"
TYPED_FN_RECONFIGURE = "vlansettings_reconfigure"

# Required fields on every VLAN config. Matches the OPNsense schema:
#   device       — parent NIC name (e.g. "igb0")
#   tag          — 802.1Q VLAN tag (1-4094)
#   description  — free-form label
#   priority     — 802.1p priority code point (0-7)
VLAN_FIELDS: tuple[str, ...] = ("device", "tag", "description", "priority")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Credentials:
    """Resolved OPNsense API credentials sourced from environment variables."""

    api_url: str
    api_key: str
    api_secret: str
    verify_ssl: bool


@dataclass(frozen=True)
class VlanConfig:
    """Desired-state VLAN configuration loaded from YAML.

    The diff key ``(device, tag)`` is what makes a VLAN unique on an OPNsense
    box; the OPNsense-assigned ``uuid`` is opaque and the resource ``name``
    in the InfraFoundry YAML is operator-facing only.

    ``lock`` is a meta-property — when ``True``, the spike treats the entry as
    "observed but untouchable": the matching live resource is reported in the
    plan but is never added, updated, or deleted. Useful for the partial-
    migration case where the operator wants visibility of a resource (e.g.,
    the WAN trunk) without IaC asserting authority over it. ADR-0014 will
    decide whether the production contract should support locks at all, and
    if so whether they should be granular (per-action) or boolean.
    """

    name: str
    device: str
    tag: int
    description: str
    priority: int
    lock: bool = False

    @property
    def diff_key(self) -> tuple[str, int]:
        """Identity of this VLAN on the box: parent NIC + 802.1Q tag."""
        return (self.device, self.tag)

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the dict shape OPNsense's addItem/setItem expect.

        The payload is wrapped in a top-level ``vlan`` key; OPNsense follows
        a consistent ``{<resource_key>: {<fields>}}`` envelope across modules
        (cf. ``kea/dhcpv6/addSubnet`` which wraps under ``subnet6``).
        """
        return {
            "vlan": {
                "if": self.device,
                "tag": str(self.tag),
                "descr": self.description,
                "pcp": str(self.priority),
            }
        }


@dataclass(frozen=True)
class LiveVlan:
    """A VLAN as currently configured on the OPNsense box."""

    uuid: str
    device: str
    tag: int
    description: str
    priority: int

    @property
    def diff_key(self) -> tuple[str, int]:
        return (self.device, self.tag)


@dataclass
class Diff:
    """Result of comparing desired YAML state to live OPNsense state."""

    adds: list[VlanConfig] = field(default_factory=list)
    updates: list[tuple[LiveVlan, VlanConfig]] = field(default_factory=list)
    deletes: list[LiveVlan] = field(default_factory=list)
    # Locked YAML entries paired with their live counterpart (or ``None`` if
    # declared-but-missing). Always reported in the plan output, never acted
    # on by ``apply``. Tracking these is itself the spike's safety
    # affordance against silent footguns.
    locked: list[tuple[VlanConfig, LiveVlan | None]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Environment / configuration loading
# ---------------------------------------------------------------------------


def load_env_credentials(env: dict[str, str] | None = None) -> Credentials:
    """Read OPNsense credentials from environment variables.

    Args:
        env: Environment mapping; defaults to ``os.environ``. Injectable for tests.

    Returns:
        A ``Credentials`` instance.

    Raises:
        RuntimeError: If any of ``OPNSENSE_API_URL``, ``OPNSENSE_API_KEY``,
            or ``OPNSENSE_API_SECRET`` is missing or empty.
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


def load_vlans_from_yaml(path: Path) -> list[VlanConfig]:
    """Parse a YAML file of VLAN resource definitions.

    Expects the InfraFoundry resource shape::

        - provider: opnsense
          type: vlan
          name: vlan-storage
          config:
            device: igb1
            tag: 100
            description: Storage VLAN
            priority: 0

    Args:
        path: Path to a YAML file.

    Returns:
        Validated list of ``VlanConfig`` instances.

    Raises:
        ValueError: If the YAML is malformed or any VLAN entry is missing a
            required field or has an out-of-range value.
    """
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, list):
        raise ValueError(
            f"Expected top-level list of resources in {path}, got {type(raw).__name__}"
        )

    vlans: list[VlanConfig] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"Resource at index {index} is not a mapping")
        if entry.get("type") != "vlan":
            # Allow non-vlan resources to coexist; they're just ignored here.
            continue

        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"Resource at index {index} missing string 'name'")

        config = entry.get("config")
        if not isinstance(config, dict):
            raise ValueError(f"VLAN '{name}' missing or invalid 'config' mapping")

        missing_fields: list[str] = [f for f in VLAN_FIELDS if f not in config]
        if missing_fields:
            raise ValueError(
                f"VLAN '{name}' missing required field(s): {', '.join(missing_fields)}"
            )

        try:
            tag = int(config["tag"])
            priority = int(config["priority"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"VLAN '{name}' has non-integer tag or priority") from exc

        if not 1 <= tag <= 4094:
            raise ValueError(f"VLAN '{name}' tag {tag} out of range 1-4094")
        if not 0 <= priority <= 7:
            raise ValueError(f"VLAN '{name}' priority {priority} out of range 0-7")

        device = config["device"]
        description = config["description"]
        if not isinstance(device, str) or not device:
            raise ValueError(f"VLAN '{name}' missing string 'device'")
        if not isinstance(description, str):
            raise ValueError(f"VLAN '{name}' description must be a string")

        # ``lock`` is a top-level meta-property, not part of ``config``.
        lock_raw = entry.get("lock", False)
        if not isinstance(lock_raw, bool):
            raise ValueError(f"VLAN '{name}' lock must be a boolean (true/false)")

        vlans.append(
            VlanConfig(
                name=name,
                device=device,
                tag=tag,
                description=description,
                priority=priority,
                lock=lock_raw,
            )
        )

    return vlans


# ---------------------------------------------------------------------------
# Client factory + typed-surface dispatch with fallback
# ---------------------------------------------------------------------------


def build_client(credentials: Credentials) -> OPNsenseClient:
    """Construct an ``OPNsenseClient`` with ``auto_detect_version=True``.

    This is where the spike intentionally diverges from the production wrapper at
    ``src/infrafoundry/providers/opnsense/api_client.py:36`` (which sets
    ``auto_detect_version=False``). Flipping the flag in production is out of
    scope for this spike; ADR-0014 owns that decision.
    """
    return OPNsenseClient(
        base_url=credentials.api_url,
        api_key=credentials.api_key,
        api_secret=credentials.api_secret,
        verify_ssl=credentials.verify_ssl,
        auto_detect_version=True,
    )


def _typed_call(client: OPNsenseClient, function_name: str, **kwargs: Any) -> Any:
    """Invoke a typed-surface function, returning ``None`` if it isn't generated.

    The typed ``GeneratedAPI`` proxies ``__getattr__`` lazily, so attribute
    access alone won't fail — the call only blows up later. There are two
    failure modes to absorb:

    - ``AttributeError`` at ``sync()`` time when ``importlib.import_module(...)``
      can't find the generated function module (typed surface partially
      generated; rare).
    - ``RuntimeError`` at ``client.api`` access time when no generated client
      module exists for the detected version at all (e.g., the upstream
      auto-generator couldn't run because ``openapi-python-client`` isn't on
      ``PATH``, or the version has a security-patch suffix like ``26.1.6_2``
      that doesn't match a generated module path). The spike falls back to
      bare ``client.get/post(...)`` in either case.

    Returns:
        The function's return value, or ``None`` to indicate "not available".
    """
    try:
        module_proxy = client.api.interfaces  # type: ignore[no-any-return]
        function_proxy = getattr(module_proxy, function_name)
        return function_proxy.sync(**kwargs)
    except (AttributeError, RuntimeError):
        # Typed surface didn't expose this function or no generated client
        # for the running version — caller falls back to raw HTTP.
        return None


def search_vlans(client: OPNsenseClient) -> list[LiveVlan]:
    """Fetch the live VLAN list, preferring the typed surface.

    Falls back to ``client.post("interfaces", "vlan_settings", "searchItem")``
    if the typed function isn't generated for the detected version.
    """
    response: Any = _typed_call(client, TYPED_FN_SEARCH)
    if response is None:
        # OPNsense's searchItem is a POST despite being a "search" verb.
        response = client.post(VLAN_MODULE, VLAN_CONTROLLER, "searchItem")

    rows: list[dict[str, Any]] = []
    if isinstance(response, dict):
        raw_rows = response.get("rows")
        if isinstance(raw_rows, list):
            rows = [r for r in raw_rows if isinstance(r, dict)]

    return [_row_to_live_vlan(row) for row in rows]


def _row_to_live_vlan(row: dict[str, Any]) -> LiveVlan:
    """Normalize a search-row dict into a ``LiveVlan``."""
    uuid = str(row.get("uuid", ""))
    device = str(row.get("if", ""))
    try:
        tag = int(row.get("tag", 0))
    except (TypeError, ValueError):
        tag = 0
    try:
        priority = int(row.get("pcp", 0))
    except (TypeError, ValueError):
        priority = 0
    description = str(row.get("descr", ""))
    return LiveVlan(
        uuid=uuid,
        device=device,
        tag=tag,
        description=description,
        priority=priority,
    )


def add_vlan(client: OPNsenseClient, vlan: VlanConfig) -> dict[str, Any]:
    """Create a VLAN via the typed surface, falling back to raw POST."""
    payload = vlan.to_payload()
    response: Any = _typed_call(client, TYPED_FN_ADD, json_body=payload)
    if response is None:
        response = client.post(VLAN_MODULE, VLAN_CONTROLLER, "addItem", json=payload)
    return response if isinstance(response, dict) else {"raw": response}


def update_vlan(client: OPNsenseClient, uuid: str, vlan: VlanConfig) -> dict[str, Any]:
    """Update an existing VLAN by UUID."""
    payload = vlan.to_payload()
    response: Any = _typed_call(client, TYPED_FN_SET, uuid=uuid, json_body=payload)
    if response is None:
        response = client.post(VLAN_MODULE, VLAN_CONTROLLER, "setItem", uuid, json=payload)
    return response if isinstance(response, dict) else {"raw": response}


def delete_vlan(client: OPNsenseClient, uuid: str) -> dict[str, Any]:
    """Delete a VLAN by UUID."""
    response: Any = _typed_call(client, TYPED_FN_DEL, uuid=uuid)
    if response is None:
        response = client.post(VLAN_MODULE, VLAN_CONTROLLER, "delItem", uuid)
    return response if isinstance(response, dict) else {"raw": response}


def reconfigure(client: OPNsenseClient) -> dict[str, Any]:
    """Apply pending VLAN changes (commits the staged config to the running system)."""
    response: Any = _typed_call(client, TYPED_FN_RECONFIGURE)
    if response is None:
        response = client.post(VLAN_MODULE, VLAN_CONTROLLER, "reconfigure")
    return response if isinstance(response, dict) else {"raw": response}


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def compute_diff(
    desired: list[VlanConfig], current: list[LiveVlan], *, add_only: bool = False
) -> Diff:
    """Compare desired YAML state to live state, keyed by ``(device, tag)``.

    Args:
        desired: VLANs the operator wants to exist.
        current: VLANs the OPNsense box currently has.
        add_only: If ``True``, never emit deletes for live resources that
            don't appear in ``desired``. Adds and updates still happen
            normally. Useful for partial migrations where the YAML doesn't
            yet describe everything on the box.

    Returns:
        A ``Diff`` with adds/updates/deletes plus a ``locked`` list of
        observed-but-untouchable pairs. ``updates`` carries the live record
        alongside the desired record so the caller has the UUID.

    Locked entries (``VlanConfig.lock=True``) are skipped entirely — the
    matching live record (if any) is recorded in ``Diff.locked`` and never
    appears in ``adds``/``updates``/``deletes``. A locked-but-missing entry
    (declared in YAML, no live counterpart) is still recorded so the plan
    output can flag it.
    """
    desired_by_key: dict[tuple[str, int], VlanConfig] = {v.diff_key: v for v in desired}
    current_by_key: dict[tuple[str, int], LiveVlan] = {v.diff_key: v for v in current}
    locked_keys: set[tuple[str, int]] = {v.diff_key for v in desired if v.lock}

    adds: list[VlanConfig] = []
    updates: list[tuple[LiveVlan, VlanConfig]] = []
    deletes: list[LiveVlan] = []
    locked: list[tuple[VlanConfig, LiveVlan | None]] = []

    for key, want in desired_by_key.items():
        have = current_by_key.get(key)
        if want.lock:
            locked.append((want, have))
            continue
        if have is None:
            adds.append(want)
        elif (have.description, have.priority) != (want.description, want.priority):
            updates.append((have, want))

    if not add_only:
        for key, have in current_by_key.items():
            if key in locked_keys:
                # Already recorded above as locked; never emit a delete.
                continue
            if key not in desired_by_key:
                deletes.append(have)

    return Diff(adds=adds, updates=updates, deletes=deletes, locked=locked)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def cmd_inspect(client: OPNsenseClient) -> int:
    """Connect, detect version, count endpoints, report typed-surface readiness."""
    version: str = client.detect_version()
    print(f"Detected OPNsense version: {version}")

    endpoints: list[tuple[str, str, str]] = client.list_endpoints()
    # Filter accepts both spellings: the bundled spec at opnsense-openapi 0.3.0
    # uses "vlansettings" (no underscore) due to a generator bug; the live API
    # uses "vlan_settings". Both substrings are matched so this works whether
    # the spec is buggy or fixed upstream.
    vlan_endpoints: list[tuple[str, str, str]] = [
        (path, method, summary)
        for path, method, summary in endpoints
        if "vlansettings" in path or "vlan_settings" in path
    ]
    print(f"Total endpoints in matched spec: {len(endpoints)}")
    print(f"VLAN endpoints (interfaces/vlan_settings/*): {len(vlan_endpoints)}")
    for path, method, _ in vlan_endpoints:
        print(f"  {method:5s} {path}")

    # Typed-surface check — does the generated client expose searchItem?
    probe = _typed_call(client, TYPED_FN_SEARCH)
    typed_search_available = probe is not None
    print(f"Typed-surface search available: {typed_search_available}")
    return 0


def cmd_list(client: OPNsenseClient) -> int:
    """Print the current VLANs on the box as YAML."""
    vlans = search_vlans(client)
    if not vlans:
        print("# (no VLANs found on box)")
        return 0
    payload = [
        {
            "provider": "opnsense",
            "type": "vlan",
            "name": f"live-{v.device}-{v.tag}",
            "config": {
                "device": v.device,
                "tag": v.tag,
                "description": v.description,
                "priority": v.priority,
            },
        }
        for v in vlans
    ]
    print(yaml.safe_dump(payload, sort_keys=False))
    return 0


def cmd_plan(client: OPNsenseClient, yaml_path: Path, *, add_only: bool = False) -> int:
    """Compute and print the diff between YAML and live state."""
    desired = load_vlans_from_yaml(yaml_path)
    current = search_vlans(client)
    diff = compute_diff(desired, current, add_only=add_only)
    _print_diff(diff, add_only=add_only)
    return 0


def cmd_apply(
    client: OPNsenseClient, yaml_path: Path, *, confirm: bool, add_only: bool = False
) -> int:
    """Apply the diff. Without ``--confirm``, prints the plan and exits without mutating."""
    desired = load_vlans_from_yaml(yaml_path)
    current = search_vlans(client)
    diff = compute_diff(desired, current, add_only=add_only)
    _print_diff(diff, add_only=add_only)

    if diff.is_empty:
        return 0

    if not confirm:
        print("\nDry run — pass --confirm to apply these changes.")
        return 0

    print("\nApplying changes...")
    for vlan in diff.adds:
        result = add_vlan(client, vlan)
        print(f"  + add  {vlan.device} tag={vlan.tag}  -> {result.get('result', result)}")

    for live, want in diff.updates:
        result = update_vlan(client, live.uuid, want)
        print(f"  ~ set  {want.device} tag={want.tag}  -> {result.get('result', result)}")

    for live in diff.deletes:
        result = delete_vlan(client, live.uuid)
        print(f"  - del  {live.device} tag={live.tag}  -> {result.get('result', result)}")

    print("Reconfiguring service...")
    reconfigure_result = reconfigure(client)
    print(f"  reconfigure -> {reconfigure_result.get('status', reconfigure_result)}")
    return 0


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
    for vlan in diff.adds:
        print(f"  + {vlan.device} tag={vlan.tag} desc={vlan.description!r} pcp={vlan.priority}")
    for live, want in diff.updates:
        print(
            f"  ~ {want.device} tag={want.tag} "
            f"desc={live.description!r}->{want.description!r} "
            f"pcp={live.priority}->{want.priority} "
            f"(uuid={live.uuid})"
        )
    for live in diff.deletes:
        print(f"  - {live.device} tag={live.tag} desc={live.description!r} (uuid={live.uuid})")
    for want, have in diff.locked:
        if have is None:
            print(f"  L {want.device} tag={want.tag} (locked, declared but not present on box)")
        else:
            print(
                f"  L {have.device} tag={have.tag} (locked, uuid={have.uuid}) — "
                "no action will be taken"
            )


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse CLI."""
    parser = argparse.ArgumentParser(
        prog="vlan_direct_api",
        description="Direct-API VLAN management spike for OPNsense (informs ADR-0014).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "inspect", help="Detect version, list VLAN endpoints, probe typed surface."
    )
    subparsers.add_parser("list", help="Print the current VLANs on the box as YAML.")

    plan_parser = subparsers.add_parser("plan", help="Diff a YAML file against live state.")
    plan_parser.add_argument("yaml_path", type=Path, help="Path to VLAN YAML file.")
    plan_parser.add_argument(
        "--add-only",
        action="store_true",
        help=(
            "Suppress deletes for live VLANs not in the YAML. Useful for partial "
            "migrations where the YAML doesn't yet describe everything on the box."
        ),
    )

    apply_parser = subparsers.add_parser("apply", help="Apply a YAML file's diff to the box.")
    apply_parser.add_argument("yaml_path", type=Path, help="Path to VLAN YAML file.")
    apply_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually dispatch mutations. Without this flag, apply is a dry run.",
    )
    apply_parser.add_argument(
        "--add-only",
        action="store_true",
        help=(
            "Suppress deletes for live VLANs not in the YAML. Useful for partial "
            "migrations where the YAML doesn't yet describe everything on the box."
        ),
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    _warn_if_codegen_unavailable()

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
            )
    finally:
        client.close()

    parser.error(f"Unknown command: {args.command}")  # NoReturn — argparse exits


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
