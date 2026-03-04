"""LXC container configuration field-level validation for Proxmox."""

from __future__ import annotations

import re
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# Known valid OS types for LXC containers
KNOWN_OS_TYPES = frozenset(
    {
        "alpine",
        "archlinux",
        "centos",
        "debian",
        "devuan",
        "fedora",
        "gentoo",
        "nixos",
        "opensuse",
        "ubuntu",
        "unmanaged",
    }
)

# Known valid feature mount types
KNOWN_FEATURE_MOUNT_TYPES = frozenset({"cifs", "nfs"})

# Known valid CPU architectures
KNOWN_CPU_ARCHITECTURES = frozenset({"amd64", "arm64", "armhf", "i386"})

# Pattern: storage_id:vztmpl/filename.tar.* (e.g., "nas01:vztmpl/alpine-3.21-default.tar.xz")
OSTEMPLATE_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+:vztmpl/.+\.tar\..+$")


class ContainerConfigValidator:
    """Validates LXC container configuration fields before Terraform generation.

    Performs field-level validation with appropriate severity levels:
    - ERROR for invalid values that would cause Terraform failures
    - WARNING for unusual but potentially valid values
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize container config validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate container-specific configuration fields.

        Args:
            resources: List of resources to validate.
        """
        for resource in resources:
            if resource.type != "container":
                continue
            config = resource.config or {}
            name = resource.name
            self._validate_ostemplate(name, config)
            self._validate_ostype(name, config)
            self._validate_rootfs(name, config)
            self._validate_network_names(name, config)
            self._validate_mount_points(name, config)
            self._validate_features_mount(name, config)
            self._validate_cores(name, config)
            self._validate_memory(name, config)
            self._validate_swap(name, config)
            self._validate_cpu_architecture(name, config)

    def _validate_ostemplate(self, name: str, config: dict[str, Any]) -> None:
        """Error if ostemplate format is invalid (required when not cloning)."""
        ostemplate = config.get("ostemplate")
        has_clone = "clone" in config

        if ostemplate is None:
            if not has_clone:
                self.report.add_check(
                    check_name=f"proxmox_container_{name}_ostemplate_missing",
                    passed=False,
                    message=(
                        f"Container '{name}': 'ostemplate' is required when not cloning. "
                        f"Format: 'storage:vztmpl/template-file.tar.xz'"
                    ),
                    level=ValidationLevel.ERROR,
                )
            return

        if not OSTEMPLATE_PATTERN.match(ostemplate):
            self.report.add_check(
                check_name=f"proxmox_container_{name}_ostemplate",
                passed=False,
                message=(
                    f"Container '{name}': ostemplate '{ostemplate}' does not match expected "
                    f"format 'storage:vztmpl/filename.tar.*'."
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_ostype(self, name: str, config: dict[str, Any]) -> None:
        """Warn if ostype is not in the known set."""
        ostype = config.get("ostype")
        if ostype is not None and ostype not in KNOWN_OS_TYPES:
            self.report.add_check(
                check_name=f"proxmox_container_{name}_ostype",
                passed=True,
                message=(
                    f"Container '{name}': ostype '{ostype}' is not in the known set "
                    f"{sorted(KNOWN_OS_TYPES)}. Verify this is a valid LXC OS type."
                ),
                level=ValidationLevel.WARNING,
            )

    def _validate_rootfs(self, name: str, config: dict[str, Any]) -> None:
        """Error if rootfs.size is not a positive integer."""
        rootfs = config.get("rootfs")
        if not isinstance(rootfs, dict):
            return

        size = rootfs.get("size")
        if size is not None and (not isinstance(size, int) or size <= 0):
            self.report.add_check(
                check_name=f"proxmox_container_{name}_rootfs_size",
                passed=False,
                message=(
                    f"Container '{name}': rootfs size '{size}' is invalid. "
                    f"Must be a positive integer (in GB)."
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_network_names(self, name: str, config: dict[str, Any]) -> None:
        """Error if network entries are missing the required 'name' field."""
        network = config.get("network")
        if network is None:
            return

        nic_list: list[dict[str, Any]] = []
        if isinstance(network, dict):
            nic_list = [network]
        elif isinstance(network, list):
            nic_list = [n for n in network if isinstance(n, dict)]

        for i, nic in enumerate(nic_list):
            if "name" not in nic:
                self.report.add_check(
                    check_name=f"proxmox_container_{name}_nic{i}_name",
                    passed=False,
                    message=(
                        f"Container '{name}': network interface {i} is missing required "
                        f"'name' field (e.g., 'eth0')."
                    ),
                    level=ValidationLevel.ERROR,
                )

    def _validate_mount_points(self, name: str, config: dict[str, Any]) -> None:
        """Error if mount_point entries are missing required fields."""
        mount_points = config.get("mount_point")
        if mount_points is None:
            return

        mp_list: list[dict[str, Any]] = []
        if isinstance(mount_points, dict):
            mp_list = [mount_points]
        elif isinstance(mount_points, list):
            mp_list = [m for m in mount_points if isinstance(m, dict)]

        for i, mp in enumerate(mp_list):
            if "volume" not in mp:
                self.report.add_check(
                    check_name=f"proxmox_container_{name}_mp{i}_volume",
                    passed=False,
                    message=(
                        f"Container '{name}': mount_point {i} is missing required 'volume' field."
                    ),
                    level=ValidationLevel.ERROR,
                )
            if "path" not in mp:
                self.report.add_check(
                    check_name=f"proxmox_container_{name}_mp{i}_path",
                    passed=False,
                    message=(
                        f"Container '{name}': mount_point {i} is missing required 'path' field."
                    ),
                    level=ValidationLevel.ERROR,
                )

    def _validate_features_mount(self, name: str, config: dict[str, Any]) -> None:
        """Warn if features.mount contains unknown mount types."""
        features = config.get("features")
        if not isinstance(features, dict):
            return

        mount_types = features.get("mount")
        if not isinstance(mount_types, list):
            return

        for mount_type in mount_types:
            if mount_type not in KNOWN_FEATURE_MOUNT_TYPES:
                self.report.add_check(
                    check_name=f"proxmox_container_{name}_feature_mount_{mount_type}",
                    passed=True,
                    message=(
                        f"Container '{name}': features.mount type '{mount_type}' is not "
                        f"in the known set {sorted(KNOWN_FEATURE_MOUNT_TYPES)}. "
                        f"Verify this is valid."
                    ),
                    level=ValidationLevel.WARNING,
                )

    def _validate_cores(self, name: str, config: dict[str, Any]) -> None:
        """Error if cores is not a positive integer."""
        cores = config.get("cores")
        if cores is not None and (not isinstance(cores, int) or cores <= 0):
            self.report.add_check(
                check_name=f"proxmox_container_{name}_cores",
                passed=False,
                message=(
                    f"Container '{name}': cores value '{cores}' is invalid. "
                    f"Must be a positive integer."
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_memory(self, name: str, config: dict[str, Any]) -> None:
        """Error if memory is not a positive integer."""
        memory = config.get("memory")
        if memory is not None and (not isinstance(memory, int) or memory <= 0):
            self.report.add_check(
                check_name=f"proxmox_container_{name}_memory",
                passed=False,
                message=(
                    f"Container '{name}': memory value '{memory}' is invalid. "
                    f"Must be a positive integer (in MB)."
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_swap(self, name: str, config: dict[str, Any]) -> None:
        """Error if swap is not a non-negative integer."""
        swap = config.get("swap")
        if swap is not None and (not isinstance(swap, int) or swap < 0):
            self.report.add_check(
                check_name=f"proxmox_container_{name}_swap",
                passed=False,
                message=(
                    f"Container '{name}': swap value '{swap}' is invalid. "
                    f"Must be a non-negative integer (in MB, 0 to disable)."
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_cpu_architecture(self, name: str, config: dict[str, Any]) -> None:
        """Warn if CPU architecture is not in the known set."""
        arch = config.get("arch")
        if arch is not None and arch not in KNOWN_CPU_ARCHITECTURES:
            self.report.add_check(
                check_name=f"proxmox_container_{name}_arch",
                passed=True,
                message=(
                    f"Container '{name}': architecture '{arch}' is not in the known set "
                    f"{sorted(KNOWN_CPU_ARCHITECTURES)}. Verify this is valid."
                ),
                level=ValidationLevel.WARNING,
            )
