"""VM configuration field-level validation for Proxmox."""

from __future__ import annotations

import re
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# Known valid values for advisory warnings
KNOWN_CPU_TYPES = frozenset(
    {
        "host",
        "kvm64",
        "kvm32",
        "qemu64",
        "qemu32",
        "max",
        "x86-64-v2",
        "x86-64-v2-AES",
        "x86-64-v3",
        "x86-64-v4",
    }
)

VALID_MACHINE_TYPES = frozenset({"q35", "i440fx"})
VALID_BIOS_TYPES = frozenset({"seabios", "ovmf"})
VALID_DISK_TYPES = frozenset({"virtio", "scsi", "sata"})
VALID_NIC_MODELS = frozenset({"virtio", "e1000", "e1000e", "rtl8139", "vmxnet3"})

# Pattern: storage_id:iso/filename.iso (e.g., "local:iso/ubuntu.iso")
ISO_PATH_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+:iso/.+\.iso$")


class VMConfigValidator:
    """Validates VM configuration fields before Terraform generation.

    Performs field-level validation with appropriate severity levels:
    - ERROR for invalid values that would cause Terraform failures
    - WARNING for unusual but potentially valid values
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize VM config validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate VM-specific configuration fields.

        Args:
            resources: List of VM resources to validate.
        """
        for resource in resources:
            if resource.type != "vm":
                continue
            config = resource.config or {}
            name = resource.name
            self._validate_cpu_type(name, config)
            self._validate_machine(name, config)
            self._validate_bios(name, config)
            self._validate_balloon(name, config)
            self._validate_iso(name, config)
            self._validate_disk_type(name, config)
            self._validate_network_models(name, config)
            self._validate_ovmf_efi_disk(name, config)

    def _validate_cpu_type(self, name: str, config: dict[str, Any]) -> None:
        """Warn if cpu_type is not in the known set."""
        cpu_type = config.get("cpu_type")
        if cpu_type is not None and cpu_type not in KNOWN_CPU_TYPES:
            self.report.add_check(
                check_name=f"proxmox_vm_{name}_cpu_type",
                passed=True,
                message=(
                    f"VM '{name}': cpu_type '{cpu_type}' is not in the common set "
                    f"{sorted(KNOWN_CPU_TYPES)}. Verify this is a valid QEMU CPU type."
                ),
                level=ValidationLevel.WARNING,
            )

    def _validate_machine(self, name: str, config: dict[str, Any]) -> None:
        """Error if machine type is invalid."""
        machine = config.get("machine")
        if machine is not None and machine not in VALID_MACHINE_TYPES:
            self.report.add_check(
                check_name=f"proxmox_vm_{name}_machine",
                passed=False,
                message=(
                    f"VM '{name}': machine type '{machine}' is invalid. "
                    f"Must be one of: {sorted(VALID_MACHINE_TYPES)}"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_bios(self, name: str, config: dict[str, Any]) -> None:
        """Error if BIOS type is invalid."""
        bios = config.get("bios")
        if bios is not None and bios not in VALID_BIOS_TYPES:
            self.report.add_check(
                check_name=f"proxmox_vm_{name}_bios",
                passed=False,
                message=(
                    f"VM '{name}': bios '{bios}' is invalid. "
                    f"Must be one of: {sorted(VALID_BIOS_TYPES)}"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_balloon(self, name: str, config: dict[str, Any]) -> None:
        """Error if balloon is not a non-negative integer."""
        balloon = config.get("balloon")
        if balloon is None:
            return
        if not isinstance(balloon, int) or balloon < 0:
            self.report.add_check(
                check_name=f"proxmox_vm_{name}_balloon",
                passed=False,
                message=(
                    f"VM '{name}': balloon value '{balloon}' is invalid. "
                    f"Must be a non-negative integer (0 to disable)."
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_iso(self, name: str, config: dict[str, Any]) -> None:
        """Validate ISO path format."""
        iso = config.get("iso")
        if iso is not None and not ISO_PATH_PATTERN.match(iso):
            self.report.add_check(
                check_name=f"proxmox_vm_{name}_iso",
                passed=False,
                message=(
                    f"VM '{name}': iso path '{iso}' does not match expected format "
                    f"'storage:iso/filename.iso'."
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_disk_type(self, name: str, config: dict[str, Any]) -> None:
        """Error if disk type is invalid."""
        disk = config.get("disk")
        if isinstance(disk, dict):
            disk_type = disk.get("type")
            if disk_type is not None and disk_type not in VALID_DISK_TYPES:
                self.report.add_check(
                    check_name=f"proxmox_vm_{name}_disk_type",
                    passed=False,
                    message=(
                        f"VM '{name}': disk type '{disk_type}' is invalid. "
                        f"Must be one of: {sorted(VALID_DISK_TYPES)}"
                    ),
                    level=ValidationLevel.ERROR,
                )

    def _validate_network_models(self, name: str, config: dict[str, Any]) -> None:
        """Warn if NIC model is not in the known valid set."""
        network = config.get("network")
        if network is None:
            return
        nic_list: list[dict[str, Any]] = []
        if isinstance(network, dict):
            nic_list = [network]
        elif isinstance(network, list):
            nic_list = [n for n in network if isinstance(n, dict)]

        for i, nic in enumerate(nic_list):
            model = nic.get("model")
            if model is not None and model not in VALID_NIC_MODELS:
                self.report.add_check(
                    check_name=f"proxmox_vm_{name}_nic{i}_model",
                    passed=True,
                    message=(
                        f"VM '{name}': NIC {i} model '{model}' is not in the known set "
                        f"{sorted(VALID_NIC_MODELS)}. Verify this is valid."
                    ),
                    level=ValidationLevel.WARNING,
                )

    def _validate_ovmf_efi_disk(self, name: str, config: dict[str, Any]) -> None:
        """Warn if OVMF BIOS is used without an EFI disk."""
        if config.get("bios") == "ovmf" and "efi_disk" not in config:
            self.report.add_check(
                check_name=f"proxmox_vm_{name}_ovmf_efi_disk",
                passed=True,
                message=(
                    f"VM '{name}': bios is 'ovmf' but no 'efi_disk' is configured. "
                    f"UEFI boot typically requires an EFI disk."
                ),
                level=ValidationLevel.WARNING,
            )
