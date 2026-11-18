"""Collector for OpenWrt and GL.iNet routers over SSH (key authentication only)."""

from __future__ import annotations

import re
import subprocess  # nosec B404  # fixed ssh argv, no shell
from collections.abc import Callable
from typing import Any

from infrafoundry.core.config.models import CollectorDeviceConfig

from .base import Artifact, CollectorError

REDACTED_OPTIONS = frozenset(
    {
        "key",
        "password",
        "sae_password",
        "psk",
        "private_key",
        "preshared_key",
        "auth_secret",
        "acct_secret",
        "priv_key_pwd",
    }
)
UCI_PACKAGES = ("network", "dhcp", "firewall", "wireless")
_OPTION_RE = re.compile(
    r"^(\s*option\s+(?:" + "|".join(sorted(REDACTED_OPTIONS)) + r")\s+).*$", re.MULTILINE
)
_LFT_RE = re.compile(r"\b(valid_lft|preferred_lft)\b")


def redact_uci(text: str) -> str:
    """Replace the values of secret options in ``uci export`` output.

    Args:
        text: Raw ``uci export`` output.
    """
    return _OPTION_RE.sub(r"\1'<redacted>'", text)


def normalize_ip_addr(text: str) -> str:
    """Drop the lease-lifetime lines of ``ip addr`` output, which change every run.

    Args:
        text: Raw ``ip addr`` output.
    """
    return "".join(line for line in text.splitlines(keepends=True) if not _LFT_RE.search(line))


def ssh_argv(device: CollectorDeviceConfig, remote_cmd: str) -> list[str]:
    """Build the ssh command for one fixed remote command.

    Host-key checking stays on; the address follows ``--`` so it is never an option.

    Args:
        device: Device config.
        remote_cmd: A fixed command string from this module.
    """
    argv = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={device.timeout}"]
    argv += ["-p", str(device.port or 22)]
    if device.ssh_key_file:
        argv += ["-i", device.ssh_key_file]
    if device.username:
        argv += ["-l", device.username]
    return [*argv, "--", device.address, remote_cmd]


class OpenWrtSshCollector:
    """Collects UCI config, addresses, routes and system facts over SSH."""

    def __init__(
        self,
        device: CollectorDeviceConfig,
        run: Callable[..., Any] = subprocess.run,
    ) -> None:
        """Initialize the collector.

        Args:
            device: Resolved device config (``address`` is the host).
            run: Subprocess runner; injectable for tests.
        """
        self._device = device
        self._run = run

    def _ssh(self, remote_cmd: str) -> tuple[int, str]:
        result = self._run(  # list argv, no shell
            ssh_argv(self._device, remote_cmd),
            capture_output=True,
            timeout=self._device.timeout * 4,
            check=False,
        )
        return int(result.returncode), bytes(result.stdout or b"").decode("utf-8", "replace")

    def _must(self, remote_cmd: str, label: str) -> str:
        code, out = self._ssh(remote_cmd)
        if code != 0:
            raise CollectorError(f"{self._device.name}: '{label}' failed (exit {code})")
        return out

    def collect(self) -> list[Artifact]:
        """Run the fixed read-only commands and return the artifacts.

        Raises:
            CollectorError: If a command other than ``uci export wireless`` fails.
        """
        artifacts: list[Artifact] = []
        for package in UCI_PACKAGES:
            label = f"uci export {package}"
            if package == "wireless":
                code, out = self._ssh(label)
                if code != 0:
                    continue  # no wireless package on this device
            else:
                out = self._must(label, label)
            artifacts.append(
                Artifact(f"uci-{package}.conf", redact_uci(out).encode(), secret_bearing=True)
            )
        addr = normalize_ip_addr(self._must("ip addr", "ip addr"))
        route = self._must("ip route", "ip route")
        system = self._must("cat /etc/openwrt_release; ubus call system board", "system facts")
        artifacts += [
            Artifact("ip-addr.txt", addr.encode()),
            Artifact("ip-route.txt", route.encode()),
            Artifact("system.txt", system.encode()),
        ]
        return artifacts
