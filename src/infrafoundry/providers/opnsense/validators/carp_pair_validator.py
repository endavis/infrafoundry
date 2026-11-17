"""CARP pair validator for OPNsense, doctor only (#1450).

Compares the CARP VIP state of two firewalls declared as a pair
(``firewalls.<name>.ha_backup``). ``OPNsenseValidator.validate_ha_health`` reads
``getVipStatus`` on both nodes, each through its own client, and passes both replies
here. This module does no I/O.

VIPs are matched on ``(vhid, subnet)``. A VIP passes when this node is MASTER and the
peer is BACKUP. Every other combination is an ERROR: the VIP is missing on the peer,
both nodes are MASTER (a split), this node is BACKUP (failed over), or either state is
anything but MASTER or BACKUP.

Silent without a peer reply or without CARP VIPs on this node.
"""

from __future__ import annotations

from typing import Any, override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

_VipKey = tuple[str, str]


def _text(value: Any) -> str:
    """Return ``value`` as a stripped string, ``""`` for ``None``."""
    return "" if value is None else str(value).strip()


def _vip_states(status: dict[str, Any]) -> dict[_VipKey, str]:
    """Map ``(vhid, subnet)`` to the upper-cased CARP state for every VIP row."""
    rows = status.get("rows")
    if not isinstance(rows, list):
        return {}
    return {
        (_text(row.get("vhid")), _text(row.get("subnet"))): _text(row.get("status")).upper()
        for row in rows
        if isinstance(row, dict)
    }


def _counts(states: dict[_VipKey, str]) -> str:
    masters = sum(1 for s in states.values() if s == "MASTER")
    backups = sum(1 for s in states.values() if s == "BACKUP")
    return f"{masters} MASTER, {backups} BACKUP"


class CarpPairValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Compares CARP VIP state across a firewall pair (doctor only)."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Report the state of every VIP on both nodes.

        Args:
            context: Context carrying ``live_carp_status``, ``peer_carp_status``,
                ``node_label`` and ``peer_label``.
        """
        if context.live_carp_status is None or context.peer_carp_status is None:
            return
        mine = _vip_states(context.live_carp_status)
        if not mine:
            return
        theirs = _vip_states(context.peer_carp_status)
        node = context.node_label or "this node"
        peer = context.peer_label or "peer"

        for index, (key, state) in enumerate(mine.items(), start=1):
            vhid, subnet = key
            label = f"CARP VIP {subnet} vhid {vhid}"
            peer_state = theirs.get(key)
            name = f"opnsense_carp_pair_{index}"
            if peer_state is None:
                self._add(
                    name,
                    False,
                    f"{label}: {node} is {state or 'unknown'}, missing on {peer}",
                    ValidationLevel.ERROR,
                )
            elif state == "MASTER" and peer_state == "BACKUP":
                self._add(
                    name,
                    True,
                    f"{label}: {node} MASTER, {peer} BACKUP",
                    ValidationLevel.INFO,
                )
            elif state == "MASTER" and peer_state == "MASTER":
                self._add(
                    name,
                    False,
                    f"{label}: MASTER on both {node} and {peer} (CARP split)",
                    ValidationLevel.ERROR,
                )
            else:
                self._add(
                    name,
                    False,
                    f"{label}: {node} {state or 'unknown'}, {peer} {peer_state or 'unknown'}; "
                    f"expected {node} MASTER and {peer} BACKUP",
                    ValidationLevel.ERROR,
                )
        self._add(
            "opnsense_carp_pair",
            True,
            f"CARP pair {node}/{peer}: {node} {_counts(mine)}; {peer} {_counts(theirs)}",
            ValidationLevel.INFO,
        )

    def _add(self, name: str, passed: bool, message: str, level: ValidationLevel) -> None:
        self.report.add_check(check_name=name, passed=passed, message=message, level=level)
