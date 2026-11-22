"""Shared ``import_id`` check for Proxmox VMs and templates (#1613).

Terraform imports a ``proxmox_virtual_environment_vm`` by ``<node>/<vmid>``. The id alone picks
the VM, so a value that disagrees with the config adopts a different VM into the address.
"""

from __future__ import annotations

import re
from typing import Any

IMPORT_ID_PATTERN = re.compile(
    r"^(?P<node>[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)/(?P<vmid>[0-9]+)$"
)
VMID_MIN = 100
VMID_MAX = 999_999_999


def _as_int(value: Any) -> int | None:
    """Return ``value`` as an int when it is an int or a numeric string, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdecimal():
        return int(value.strip())
    return None


def import_id_problems(import_id: str, config: dict[str, Any]) -> list[str]:
    """Check an ``import_id`` against the ``<node>/<vmid>`` form and the resource config.

    Args:
        import_id: The resource's ``import_id`` value.
        config: The resource config, read for ``vmid`` and ``target_node``.

    Returns:
        Problem messages; empty when the value is valid.
    """
    match = IMPORT_ID_PATTERN.match(import_id)
    if match is None:
        return [f"import_id '{import_id}' must be '<node>/<vmid>', e.g. 'pve-a/100'"]
    problems: list[str] = []
    vmid = int(match.group("vmid"))
    node = match.group("node")
    if not VMID_MIN <= vmid <= VMID_MAX:
        problems.append(
            f"import_id '{import_id}' has vmid {vmid}; it must be between {VMID_MIN} and {VMID_MAX}"
        )
    config_vmid = _as_int(config.get("vmid"))
    if config_vmid is not None and config_vmid != vmid:
        problems.append(
            f"import_id '{import_id}' has vmid {vmid} but vmid is {config_vmid}; "
            "the import would adopt a different VM"
        )
    target_node = config.get("target_node")
    if target_node is not None and str(target_node) != node:
        problems.append(
            f"import_id '{import_id}' has node '{node}' but target_node is '{target_node}'; "
            "the import would adopt a different VM"
        )
    return problems
