"""Export existing ESXi configuration to InfraFoundry YAML."""

from __future__ import annotations

import contextlib
import logging
import subprocess  # nosec B404 - required for SSH commands to ESXi hosts
from typing import Any

import yaml

from infrafoundry.core.types import EnvironmentData

logger = logging.getLogger(__name__)


class EsxiConfigExporter:
    """Exports ESXi resources into InfraFoundry YAML format.

    Connects via SSH to ESXi hosts and runs esxcli/vim-cmd commands
    to discover vswitches, portgroups, and VMs.
    """

    def __init__(self, env_config: EnvironmentData) -> None:
        """Initialize the ESXi config exporter.

        Args:
            env_config: Environment configuration containing ESXi host settings
        """
        self.env_config = env_config
        provider_settings = env_config.get("provider_settings", {}).get("esxi", {})
        self.hosts_config: dict[str, dict[str, Any]] = provider_settings.get("hosts", {})
        self.timeout = provider_settings.get("timeout", 30)

    def export(
        self,
        host_filter: str | None = None,
        resource_filter: str | None = None,
    ) -> dict[str, str]:
        """Export ESXi vswitches, portgroups, and VMs to YAML strings.

        Args:
            host_filter: Optional host name to filter exports
            resource_filter: Optional resource type ('vswitch', 'portgroup', 'vm')

        Returns:
            Dictionary mapping filenames to YAML content strings

        Raises:
            ValueError: If no hosts are configured
        """
        if not self.hosts_config:
            raise ValueError("No ESXi hosts configured in provider_settings.esxi.hosts")

        hosts = self.hosts_config
        if host_filter:
            hosts = {k: v for k, v in hosts.items() if k == host_filter}

        exports: dict[str, str] = {}

        for host_name, host_settings in hosts.items():
            hostname = host_settings.get("hostname", host_name)
            username = host_settings.get("username", "root")

            if resource_filter in (None, "vswitch"):
                logger.info("Exporting vswitches from %s...", host_name)
                exports.update(self._export_vswitches(host_name, hostname, username))

            if resource_filter in (None, "portgroup"):
                logger.info("Exporting portgroups from %s...", host_name)
                exports.update(self._export_portgroups(host_name, hostname, username))

            if resource_filter in (None, "vm"):
                logger.info("Exporting VMs from %s...", host_name)
                exports.update(self._export_vms(host_name, hostname, username))

        return exports

    def _ssh_command(self, hostname: str, username: str, command: str) -> str:
        """Execute a command on an ESXi host via SSH.

        Args:
            hostname: Host to connect to
            username: SSH username
            command: Command to execute

        Returns:
            Command stdout output

        Raises:
            subprocess.CalledProcessError: If SSH command fails
        """
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                f"ConnectTimeout={self.timeout}",
                f"{username}@{hostname}",
                command,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=self.timeout + 10,
        )
        return result.stdout

    def _export_vswitches(self, host_name: str, hostname: str, username: str) -> dict[str, str]:
        """Export vswitch configurations from an ESXi host.

        Args:
            host_name: Logical host name for resource config
            hostname: SSH hostname/IP
            username: SSH username

        Returns:
            Dictionary mapping filenames to YAML content
        """
        exports: dict[str, str] = {}
        try:
            output = self._ssh_command(hostname, username, "esxcli network vswitch standard list")
            vswitches = self._parse_vswitch_list(output, host_name)
            if vswitches:
                logger.info("Exported %d vswitches from %s", len(vswitches), host_name)
                exports[f"{host_name}-vswitches.yaml"] = yaml.safe_dump(
                    {"resources": vswitches}, sort_keys=False
                )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            logger.error("Failed to export vswitches from %s: %s", host_name, exc)
        return exports

    def _export_portgroups(self, host_name: str, hostname: str, username: str) -> dict[str, str]:
        """Export portgroup configurations from an ESXi host.

        Args:
            host_name: Logical host name for resource config
            hostname: SSH hostname/IP
            username: SSH username

        Returns:
            Dictionary mapping filenames to YAML content
        """
        exports: dict[str, str] = {}
        try:
            output = self._ssh_command(
                hostname, username, "esxcli network vswitch standard portgroup list"
            )
            portgroups = self._parse_portgroup_list(output, host_name)
            if portgroups:
                logger.info("Exported %d portgroups from %s", len(portgroups), host_name)
                exports[f"{host_name}-portgroups.yaml"] = yaml.safe_dump(
                    {"resources": portgroups}, sort_keys=False
                )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            logger.error("Failed to export portgroups from %s: %s", host_name, exc)
        return exports

    def _export_vms(self, host_name: str, hostname: str, username: str) -> dict[str, str]:
        """Export VM configurations from an ESXi host.

        Args:
            host_name: Logical host name for resource config
            hostname: SSH hostname/IP
            username: SSH username

        Returns:
            Dictionary mapping filenames to YAML content
        """
        exports: dict[str, str] = {}
        try:
            output = self._ssh_command(hostname, username, "vim-cmd vmsvc/getallvms")
            vms = self._parse_vm_list(output, host_name)
            if vms:
                logger.info("Exported %d VMs from %s", len(vms), host_name)
                exports[f"{host_name}-vms.yaml"] = yaml.safe_dump(
                    {"resources": vms}, sort_keys=False
                )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            logger.error("Failed to export VMs from %s: %s", host_name, exc)
        return exports

    @staticmethod
    def _parse_vswitch_list(output: str, host_name: str) -> list[dict[str, Any]]:
        """Parse esxcli vswitch standard list output.

        Args:
            output: Raw command output
            host_name: Host name for resource config

        Returns:
            List of vswitch resource dicts
        """
        resources: list[dict[str, Any]] = []
        current_name: str | None = None
        current_uplinks: list[str] = []
        current_mtu: int | None = None

        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("Name:"):
                if current_name:
                    resources.append(
                        {
                            "name": current_name,
                            "type": "vswitch",
                            "provider": "esxi",
                            "config": {
                                "host": host_name,
                                "uplink": current_uplinks,
                                "mtu": current_mtu,
                            },
                        }
                    )
                current_name = stripped.split(":", 1)[1].strip()
                current_uplinks = []
                current_mtu = None
            elif stripped.startswith("MTU:"):
                with contextlib.suppress(ValueError):
                    current_mtu = int(stripped.split(":", 1)[1].strip())
            elif stripped.startswith("Uplinks:"):
                uplink_str = stripped.split(":", 1)[1].strip()
                if uplink_str:
                    current_uplinks = [u.strip() for u in uplink_str.split(",") if u.strip()]

        # Don't forget the last one
        if current_name:
            resources.append(
                {
                    "name": current_name,
                    "type": "vswitch",
                    "provider": "esxi",
                    "config": {
                        "host": host_name,
                        "uplink": current_uplinks,
                        "mtu": current_mtu,
                    },
                }
            )

        return resources

    @staticmethod
    def _parse_portgroup_list(output: str, host_name: str) -> list[dict[str, Any]]:
        """Parse esxcli portgroup list output.

        Args:
            output: Raw command output
            host_name: Host name for resource config

        Returns:
            List of portgroup resource dicts
        """
        resources: list[dict[str, Any]] = []
        lines = output.strip().splitlines()

        # Skip header line
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 2:
                pg_name = parts[0]
                vswitch = parts[1]
                resources.append(
                    {
                        "name": pg_name,
                        "type": "portgroup",
                        "provider": "esxi",
                        "config": {
                            "host": host_name,
                            "vswitch": vswitch,
                        },
                    }
                )

        return resources

    @staticmethod
    def _parse_vm_list(output: str, host_name: str) -> list[dict[str, Any]]:
        """Parse vim-cmd vmsvc/getallvms output.

        Args:
            output: Raw command output
            host_name: Host name for resource config

        Returns:
            List of VM resource dicts
        """
        resources: list[dict[str, Any]] = []
        lines = output.strip().splitlines()

        # Skip header line
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 2:
                vm_name = parts[1]
                resources.append(
                    {
                        "name": vm_name,
                        "type": "vm",
                        "provider": "esxi",
                        "config": {
                            "host": host_name,
                        },
                    }
                )

        return resources
