"""Interface-assignment validation for OPNsense (ADR-0014 §7, #711).

Mirrors ``DHCPValidator``'s pattern of cross-referencing a logical name
against the live interface list AND the managed VLAN list. The validator
runs at ``infra plan`` time so a bad ``device:`` surfaces before the
operator hits the (no-op) apply path.

Schema fields validated:

- ``device``: must resolve to a physical NIC, a managed VLAN by name, or
  a VLAN child notation ``<nic>_vlan<tag>`` (split on ``_vlan``; both
  parts validated separately).
- ``description``: string if present.
- ``enabled``: bool if present.
- ``lock``: bool if present.
- ``ipv4`` / ``ipv6``: dicts if present (deep validation deferred until
  the write path lands; ADR-0013/0014 forward-compat).
"""

from __future__ import annotations

import re
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# ``<nic>_vlan<tag>`` — capture the parent NIC and tag separately. The
# OPNsense convention is e.g. ``ixl0_vlan4000``; the underscore between
# nic and "vlan" prefix is mandatory.
_VLAN_CHILD_PATTERN = re.compile(r"^(?P<nic>[A-Za-z0-9_]+?)_vlan(?P<tag>\d+)$")


class InterfaceAssignmentValidator:
    """Validates OPNsense interface assignments against live + managed state."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(
        self,
        assignments: list[ResourceConfig],
        vlan_names: set[str],
        existing_interfaces: dict[str, Any],
    ) -> None:
        """Validate interface-assignment resources.

        Args:
            assignments: ``interface_assignments`` ``ResourceConfig`` entries.
            vlan_names: Set of VLAN resource names declared in the config —
                a ``device:`` may reference a managed VLAN by name.
            existing_interfaces: Map of NIC name -> interface metadata
                returned by ``OPNsenseValidator._get_existing_interfaces``.
        """
        for assignment in assignments:
            self._validate_one(assignment, vlan_names, existing_interfaces)

    def _validate_one(
        self,
        assignment: ResourceConfig,
        vlan_names: set[str],
        existing_interfaces: dict[str, Any],
    ) -> None:
        """Run all checks for one assignment."""
        self._validate_device(assignment, vlan_names, existing_interfaces)
        self._validate_description(assignment)
        self._validate_enabled(assignment)
        self._validate_lock(assignment)
        self._validate_ipv4_ipv6(assignment)

    # ------------------------------------------------------------------
    # device
    # ------------------------------------------------------------------

    def _validate_device(
        self,
        assignment: ResourceConfig,
        vlan_names: set[str],
        existing_interfaces: dict[str, Any],
    ) -> None:
        """Check ``config.device`` resolves to a known NIC, managed VLAN, or VLAN child."""
        device = assignment.config.get("device")
        if device is None:
            return  # absence handled by the load-time required-field check

        if not isinstance(device, str) or not device:
            self.report.add_check(
                check_name=f"interface_assignment_{assignment.name}_device",
                passed=False,
                message=(
                    f"interface_assignment '{assignment.name}' device must be a non-empty string"
                ),
                level=ValidationLevel.ERROR,
            )
            return

        if self._device_resolves(device, vlan_names, existing_interfaces):
            self.report.add_check(
                check_name=f"interface_assignment_{assignment.name}_device",
                passed=True,
                message=(
                    f"Device '{device}' resolved for interface_assignment '{assignment.name}'"
                ),
                level=ValidationLevel.INFO,
            )
            return

        self.report.add_check(
            check_name=f"interface_assignment_{assignment.name}_device",
            passed=False,
            message=(
                f"interface_assignment '{assignment.name}' references unknown device '{device}'; "
                f"expected a physical NIC, a managed VLAN name, or '<nic>_vlan<tag>' notation"
            ),
            level=ValidationLevel.ERROR,
        )

    def _device_resolves(
        self,
        device: str,
        vlan_names: set[str],
        existing_interfaces: dict[str, Any],
    ) -> bool:
        """Return True if ``device`` matches a NIC, VLAN name, or VLAN child."""
        # 1. Direct match against a physical NIC reported by the live API.
        if device in existing_interfaces:
            return True

        # 2. Match against a managed VLAN by its operator-facing name.
        if device in vlan_names:
            return True

        # 3. VLAN-child notation: split on '_vlan' and validate parts.
        match = _VLAN_CHILD_PATTERN.match(device)
        if match is None:
            return False
        nic = match.group("nic")
        tag_str = match.group("tag")
        # Parent NIC must exist; tag must be a valid 802.1Q tag.
        if nic not in existing_interfaces:
            return False
        try:
            tag = int(tag_str)
        except ValueError:  # pragma: no cover  # regex guarantees integer
            return False
        return 1 <= tag <= 4094

    # ------------------------------------------------------------------
    # description / enabled / lock
    # ------------------------------------------------------------------

    def _validate_description(self, assignment: ResourceConfig) -> None:
        if "description" not in assignment.config:
            return
        description = assignment.config["description"]
        if not isinstance(description, str):
            self.report.add_check(
                check_name=f"interface_assignment_{assignment.name}_description",
                passed=False,
                message=(
                    f"interface_assignment '{assignment.name}' description must be a string, "
                    f"got {type(description).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_enabled(self, assignment: ResourceConfig) -> None:
        if "enabled" not in assignment.config:
            return
        enabled = assignment.config["enabled"]
        if not isinstance(enabled, bool):
            self.report.add_check(
                check_name=f"interface_assignment_{assignment.name}_enabled",
                passed=False,
                message=(
                    f"interface_assignment '{assignment.name}' enabled must be a boolean "
                    f"(true/false), got {type(enabled).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_lock(self, assignment: ResourceConfig) -> None:
        if "lock" not in assignment.config:
            return
        lock = assignment.config["lock"]
        if not isinstance(lock, bool):
            self.report.add_check(
                check_name=f"interface_assignment_{assignment.name}_lock",
                passed=False,
                message=(
                    f"interface_assignment '{assignment.name}' lock must be a boolean "
                    f"(true/false), got {type(lock).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # ipv4 / ipv6 (forward-compat shape check only)
    # ------------------------------------------------------------------

    def _validate_ipv4_ipv6(self, assignment: ResourceConfig) -> None:
        """Confirm ``ipv4``/``ipv6`` are dicts; deep validation is deferred.

        Per ADR-0013/0014 forward-compat schema (#711), these fields are
        accepted in YAML even though writes are no-op; we still want to
        catch a fundamentally wrong shape (string instead of mapping)
        early.
        """
        for field_name in ("ipv4", "ipv6"):
            if field_name not in assignment.config:
                continue
            value = assignment.config[field_name]
            # YAML "ipv4:" with no value parses to None — treat as empty.
            if value is None:
                continue
            if not isinstance(value, dict):
                self.report.add_check(
                    check_name=f"interface_assignment_{assignment.name}_{field_name}",
                    passed=False,
                    message=(
                        f"interface_assignment '{assignment.name}' {field_name} must be a "
                        f"mapping, got {type(value).__name__}"
                    ),
                    level=ValidationLevel.ERROR,
                )
