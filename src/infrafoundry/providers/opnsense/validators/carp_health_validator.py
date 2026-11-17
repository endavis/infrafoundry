"""CARP pair health validator for OPNsense, doctor only (#1393).

Evaluates the live CARP VIP state and the HA peer check that
``OPNsenseValidator.validate_ha_health`` fetched. It does no I/O.

InfraFoundry manages the primary node only, so the role is inferred: a node with
``synchronizetoip`` set is the sync source and is expected to be MASTER on every VIP.
A node with CARP VIPs and no sync target has an unknown role (backup, or a primary
that never syncs), so only the checks that hold for any role are applied.

A node that another firewall's entry names as its ``ha_backup`` (#1470) is a declared
backup: every VIP is expected BACKUP, MASTER is an error, and the role is not inferred.

A both-MASTER split cannot be seen from one node. What this reports is a node that
is not MASTER on every VIP, mixed MASTER/BACKUP VIPs, VIPs in INIT or DISABLED,
CARP disabled, and an unreachable peer (where a split cannot be ruled out).

Silent on a single node: no CARP rows and no sync target add nothing.
"""

from __future__ import annotations

from typing import Any, override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.context import (
    HaPeerCheck,
    OPNsenseValidationContext,
)


def _text(value: Any) -> str:
    """Return ``value`` as a stripped string, ``""`` for ``None``."""
    return "" if value is None else str(value).strip()


def _truthy(value: Any) -> bool:
    """Return whether an OPNsense flag value is on."""
    return value is True or _text(value).lower() in {"1", "true"}


def _positive_int(value: Any) -> bool:
    """Return whether ``value`` is a number greater than zero."""
    try:
        return int(_text(value)) > 0
    except ValueError:
        return False


class CarpHealthValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Evaluates CARP VIP state and HA peer reachability (doctor only)."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Report CARP VIP state, the ``carp`` block and the peer check.

        Args:
            context: Context carrying ``live_carp_status``, ``live_sync_target`` and
                ``peer_check``.
        """
        status = context.live_carp_status
        if status is None:
            return
        raw_rows = status.get("rows")
        rows = [r for r in raw_rows if isinstance(r, dict)] if isinstance(raw_rows, list) else []
        target = context.live_sync_target.strip()
        if not rows and not target:
            return

        states = [_text(row.get("status")).upper() for row in rows]
        if rows:
            self._check_vips(rows, states, target, context.ha_primary_label)
            carp = status.get("carp")
            if isinstance(carp, dict):
                self._check_carp_block(carp)
        if target:
            self._check_peer(
                target, context.peer_check, all_master=bool(rows) and set(states) == {"MASTER"}
            )

    def _add(self, name: str, passed: bool, message: str, level: ValidationLevel) -> None:
        self.report.add_check(check_name=name, passed=passed, message=message, level=level)

    def _check_backup_vips(
        self, rows: list[dict[str, Any]], states: list[str], primary: str
    ) -> None:
        self._add(
            "opnsense_carp_role",
            True,
            f"Declared ha_backup of '{primary}': expected BACKUP on every CARP VIP",
            ValidationLevel.INFO,
        )
        for index, (row, state) in enumerate(zip(rows, states, strict=True), start=1):
            label = (
                f"CARP VIP {_text(row.get('subnet'))} vhid {_text(row.get('vhid'))} "
                f"on {_text(row.get('interface'))}"
            )
            name = f"opnsense_carp_vip_{index}"
            if state == "BACKUP":
                self._add(name, True, f"{label}: BACKUP", ValidationLevel.INFO)
            elif state == "MASTER":
                self._add(
                    name,
                    False,
                    f"{label}: MASTER, expected BACKUP on the ha_backup of {primary}",
                    ValidationLevel.ERROR,
                )
            else:
                self._add(
                    name,
                    False,
                    f"{label}: {state or 'unknown'}, expected MASTER or BACKUP",
                    ValidationLevel.ERROR,
                )

    def _check_vips(
        self,
        rows: list[dict[str, Any]],
        states: list[str],
        target: str,
        primary: str = "",
    ) -> None:
        if primary:
            self._check_backup_vips(rows, states, primary)
            return
        if not target:
            self._add(
                "opnsense_carp_role",
                False,
                "CARP VIPs present but no synchronize_to_ip: either this is the backup node "
                "or the pair never syncs; expected state not checked",
                ValidationLevel.WARNING,
            )
        for index, (row, state) in enumerate(zip(rows, states, strict=True), start=1):
            label = (
                f"CARP VIP {_text(row.get('subnet'))} vhid {_text(row.get('vhid'))} "
                f"on {_text(row.get('interface'))}"
            )
            name = f"opnsense_carp_vip_{index}"
            if state == "MASTER" or (state == "BACKUP" and not target):
                self._add(name, True, f"{label}: {state}", ValidationLevel.INFO)
            elif state == "BACKUP":
                self._add(
                    name,
                    False,
                    f"{label}: BACKUP, expected MASTER on the sync source "
                    "(the peer holds it: failover, demotion or a split)",
                    ValidationLevel.ERROR,
                )
            else:
                self._add(
                    name,
                    False,
                    f"{label}: {state or 'unknown'}, expected MASTER or BACKUP",
                    ValidationLevel.ERROR,
                )
        if not target and "MASTER" in states and "BACKUP" in states:
            master = sum(1 for s in states if s == "MASTER")
            self._add(
                "opnsense_carp_split",
                False,
                f"CARP split on this node: {master} VIP(s) MASTER and "
                f"{states.count('BACKUP')} VIP(s) BACKUP",
                ValidationLevel.ERROR,
            )

    def _check_carp_block(self, carp: dict[str, Any]) -> None:
        if _text(carp.get("allow")) == "0":
            self._add(
                "opnsense_carp_allow",
                False,
                "CARP is disabled on this node (net.inet.carp.allow is 0)",
                ValidationLevel.ERROR,
            )
        if _truthy(carp.get("maintenancemode")):
            self._add(
                "opnsense_carp_maintenance",
                False,
                "CARP maintenance mode is on",
                ValidationLevel.WARNING,
            )
        if _positive_int(carp.get("demotion")):
            self._add(
                "opnsense_carp_demotion",
                False,
                f"CARP demotion counter is {_text(carp.get('demotion'))}, expected 0",
                ValidationLevel.WARNING,
            )

    def _check_peer(self, target: str, peer: HaPeerCheck | None, *, all_master: bool) -> None:
        if peer is None:
            return
        name = "opnsense_ha_peer"
        if not peer.ok:
            suffix = "; a both-MASTER split cannot be ruled out" if all_master else ""
            self._add(
                name,
                False,
                f"HA peer check: {peer.message}{suffix}",
                ValidationLevel.ERROR,
            )
        elif not peer.answered:
            self._add(
                name,
                False,
                f"HA peer {target} returned no version",
                ValidationLevel.WARNING,
            )
        else:
            detail = f" (firmware {peer.version})" if peer.version else ""
            self._add(name, True, f"HA peer {target} answers{detail}", ValidationLevel.INFO)
