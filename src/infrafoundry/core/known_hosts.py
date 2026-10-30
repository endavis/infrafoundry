"""Forget destroyed hosts in a jumphost's ``known_hosts`` (#656).

A package that sets ``jumphost`` runs its scripts there, and operators and
tools on the jumphost SSH to the package's VMs with the default
``~/.ssh/known_hosts``. When a VM is destroyed and its IP or name is reused,
the stale host key breaks the next connection with "REMOTE HOST
IDENTIFICATION HAS CHANGED". After a destroy, the framework removes each
destroyed resource's entries from the jumphost.

The entries for a destroyed resource are its name and the ``ip_address`` of
every ``kea.dhcp4.reservations`` resource whose ``hostname`` equals that name;
the blueprints that set ``jumphost`` give each VM a reservation named after it.
FQDN entries are not removed, since the framework does not know the domain.
"""

from __future__ import annotations

import shlex
import subprocess  # nosec B404  # runs ssh with list args; remote hosts are shlex-quoted
from collections.abc import Callable, Iterable
from typing import Any

from infrafoundry.core.provider import ResourceConfig

RESERVATION_TYPE = "kea.dhcp4.reservations"

# BatchMode keeps a missing key or passphrase from hanging the destroy on a prompt.
_SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
_TIMEOUT_SECONDS = 60


def _jumphost(resource: ResourceConfig) -> str:
    return str((resource.package_variables or {}).get("jumphost", "")).strip()


def reservation_ips(all_resources: Iterable[ResourceConfig]) -> dict[str, list[str]]:
    """Map each reserved hostname to its DHCP reservation IPs.

    Args:
        all_resources: Every resource in the environment.

    Returns:
        ``{hostname: [ip, ...]}`` from the ``kea.dhcp4.reservations``
        resources that set both ``hostname`` and ``ip_address``.
    """
    ips_by_hostname: dict[str, list[str]] = {}
    for resource in all_resources:
        if resource.type != RESERVATION_TYPE:
            continue
        hostname = str(resource.config.get("hostname", "")).strip()
        ip = str(resource.config.get("ip_address", "")).strip()
        if hostname and ip:
            ips_by_hostname.setdefault(hostname, []).append(ip)
    return ips_by_hostname


def hosts_to_forget(
    destroyed: Iterable[ResourceConfig],
    all_resources: Iterable[ResourceConfig],
) -> dict[str, list[str]]:
    """Return the ``known_hosts`` entries to remove, grouped by jumphost.

    Args:
        destroyed: Resources the destroy removed.
        all_resources: Every resource in the environment, unfiltered, used to
            find the DHCP reservation that gives a destroyed resource its IP.

    Returns:
        ``{jumphost: [host, ...]}`` with each list de-duplicated in first-seen
        order. Destroyed resources whose package sets no jumphost are left out.
    """
    ips_by_hostname = reservation_ips(all_resources)

    result: dict[str, list[str]] = {}
    for resource in destroyed:
        jumphost = _jumphost(resource)
        if not jumphost:
            continue
        hosts = result.setdefault(jumphost, [])
        for host in [resource.name, *ips_by_hostname.get(resource.name, [])]:
            if host not in hosts:
                hosts.append(host)
    return result


def forget_on_jumphost(
    jumphost: str,
    hosts: list[str],
    run: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> str | None:
    """Run ``ssh-keygen -R`` for each host on *jumphost*, in one SSH call.

    A host missing from ``known_hosts`` is not an error. The destroyed VMs are
    gone whatever happens here, so failures are returned rather than raised.

    Args:
        jumphost: SSH destination, as in the package's ``jumphost`` variable.
        hosts: Names and IPs to remove.
        run: ``subprocess.run`` or a stand-in for tests.

    Returns:
        ``None`` on success, otherwise a short description of the failure.
    """
    if not hosts:
        return None
    remote = "; ".join(f"ssh-keygen -R {shlex.quote(host)} >/dev/null 2>&1" for host in hosts)
    try:
        result = run(
            ["ssh", *_SSH_OPTS, jumphost, f"{remote}; true"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"ssh to {jumphost} timed out after {_TIMEOUT_SECONDS}s"
    except OSError as e:
        return f"could not run ssh: {e}"
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        return f"ssh to {jumphost} exited {result.returncode}" + (
            f": {detail[-1]}" if detail else ""
        )
    return None
