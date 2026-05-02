"""VLAN validation for OPNsense (ADR-0014 plan-time validation)."""

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class VLANValidator:
    """Validates OPNsense VLAN configurations against the live API.

    Checks:
        - ``device``: must reference an existing NIC on the box.
        - ``tag``: integer in 1-4094.
        - ``priority``: integer in 0-7.
        - ``lock``: bool if present.
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize VLAN validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(
        self,
        vlans: list[ResourceConfig],
        existing_interfaces: dict[str, Any],
    ) -> None:
        """Validate VLANs configuration against live state.

        Args:
            vlans: List of VLAN ``ResourceConfig`` entries.
            existing_interfaces: Map of NIC name -> interface metadata
                returned by ``OPNsenseValidator._get_existing_interfaces``.
        """
        for vlan in vlans:
            self._validate_one(vlan, existing_interfaces)

    def _validate_one(self, vlan: ResourceConfig, existing_interfaces: dict[str, Any]) -> None:
        """Run all checks for a single VLAN entry."""
        self._validate_device(vlan, existing_interfaces)
        self._validate_tag(vlan)
        self._validate_priority(vlan)
        self._validate_lock(vlan)

    def _validate_device(self, vlan: ResourceConfig, existing_interfaces: dict[str, Any]) -> None:
        """Check that ``config.device`` references an existing NIC.

        The previous implementation read ``config.parent`` — that bug was
        latent because the YAML/template surface uses ``device``, so the
        validator never matched real configs. Per ADR-0014 §7, plan-time
        validation must catch a bad NIC name here, before apply blows up.
        """
        device = vlan.config.get("device")
        if device is None:
            return  # absence is caught by the load-time required-field check

        if device not in existing_interfaces:
            self.report.add_check(
                check_name=f"vlan_{vlan.name}_device",
                passed=False,
                message=(f"VLAN '{vlan.name}' references undefined parent interface '{device}'"),
                level=ValidationLevel.ERROR,
            )
        else:
            self.report.add_check(
                check_name=f"vlan_{vlan.name}_device",
                passed=True,
                message=f"Parent interface '{device}' found for VLAN '{vlan.name}'",
                level=ValidationLevel.INFO,
            )

    def _validate_tag(self, vlan: ResourceConfig) -> None:
        """Check ``config.tag`` is in the 802.1Q range 1-4094."""
        if "tag" not in vlan.config:
            return
        tag_raw = vlan.config["tag"]
        try:
            tag = int(tag_raw)
        except (TypeError, ValueError):
            self.report.add_check(
                check_name=f"vlan_{vlan.name}_tag",
                passed=False,
                message=f"VLAN '{vlan.name}' tag must be an integer (got {tag_raw!r})",
                level=ValidationLevel.ERROR,
            )
            return
        if not 1 <= tag <= 4094:
            self.report.add_check(
                check_name=f"vlan_{vlan.name}_tag",
                passed=False,
                message=f"VLAN '{vlan.name}' tag {tag} out of range 1-4094",
                level=ValidationLevel.ERROR,
            )

    def _validate_priority(self, vlan: ResourceConfig) -> None:
        """Check ``config.priority`` is in the 802.1p PCP range 0-7."""
        if "priority" not in vlan.config:
            return
        priority_raw = vlan.config["priority"]
        try:
            priority = int(priority_raw)
        except (TypeError, ValueError):
            self.report.add_check(
                check_name=f"vlan_{vlan.name}_priority",
                passed=False,
                message=(f"VLAN '{vlan.name}' priority must be an integer (got {priority_raw!r})"),
                level=ValidationLevel.ERROR,
            )
            return
        if not 0 <= priority <= 7:
            self.report.add_check(
                check_name=f"vlan_{vlan.name}_priority",
                passed=False,
                message=f"VLAN '{vlan.name}' priority {priority} out of range 0-7",
                level=ValidationLevel.ERROR,
            )

    def _validate_lock(self, vlan: ResourceConfig) -> None:
        """Check ``config.lock`` is a bool if present (ADR-0014 §6 amendment)."""
        if "lock" not in vlan.config:
            return
        lock = vlan.config["lock"]
        if not isinstance(lock, bool):
            self.report.add_check(
                check_name=f"vlan_{vlan.name}_lock",
                passed=False,
                message=(
                    f"VLAN '{vlan.name}' lock must be a boolean (true/false), "
                    f"got {type(lock).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
