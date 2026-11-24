"""Ansible filters that classify the answer of an ONTAP cluster REST probe.

The ``ontap-cluster-probe`` role asks the cluster management address who it is
before anything touches the VMs. The decision lives here, in plain Python with
no ``ansible`` import, so it can be unit-tested directly (#1643).
"""

from __future__ import annotations

from typing import Any

# ``ansible.builtin.uri`` reports status -1 for failures below HTTP. These
# fragments mean nothing answered at the address, so no cluster exists there yet.
_NOTHING_THERE = (
    "connection refused",
    "no route to host",
    "network is unreachable",
    "host is unreachable",
    "timed out",
)


def _result(state: str, reason: str) -> dict[str, str]:
    return {"state": state, "reason": reason}


def ontap_cluster_state(probe: dict[str, Any], expected_name: str) -> dict[str, str]:
    """Classify a ``GET /api/cluster?fields=name`` probe result.

    Args:
        probe: The registered ``ansible.builtin.uri`` result.
        expected_name: The cluster name the blueprint is configured to build.

    Returns:
        ``{"state": ..., "reason": ...}``. ``state`` is ``present`` when the
        configured cluster answers, ``absent`` when nothing answers at the
        address, and ``conflict`` for every answer that cannot be confirmed.
        The reason never contains credentials.
    """
    status = probe.get("status", -1)
    if status == 200:
        body = probe.get("json")
        name = body.get("name") if isinstance(body, dict) else None
        if name == expected_name:
            return _result("present", f"cluster {expected_name} answers")
        if not name:
            return _result("conflict", "the address answered 200 without a cluster name")
        return _result(
            "conflict",
            f"the address belongs to cluster {name}, expected {expected_name}",
        )
    if status in (401, 403):
        return _result(
            "conflict",
            f"HTTP {status}: something answers but rejects the admin password",
        )
    if status == -1:
        message = str(probe.get("msg", "")).lower()
        if any(fragment in message for fragment in _NOTHING_THERE):
            return _result("absent", "nothing answers at the cluster management address")
        if "certificate verify failed" in message:
            return _result(
                "conflict",
                "the cluster certificate is not trusted by ontap_ca_cert "
                "or does not name the cluster management address",
            )
        return _result("conflict", f"the probe failed unexpectedly: {probe.get('msg', '')}")
    return _result("conflict", f"unexpected HTTP {status} from the cluster management address")


def ontap_node_has_mgmt_ip(records: list[dict[str, Any]] | None, mgmt_ip: str) -> bool:
    """Tell whether a cluster node owns the given management IP.

    Args:
        records: ``records`` of ``/api/cluster/nodes?fields=name,management_interfaces``.
        mgmt_ip: The node management IP to look for.

    Returns:
        True when any node has a management interface with that address.
    """
    for record in records or []:
        for interface in record.get("management_interfaces") or []:
            if (interface.get("ip") or {}).get("address") == mgmt_ip:
                return True
    return False


class FilterModule:
    """Registers the filters with Ansible."""

    def filters(self) -> dict[str, Any]:
        """Return the filter table."""
        return {
            "ontap_cluster_state": ontap_cluster_state,
            "ontap_node_has_mgmt_ip": ontap_node_has_mgmt_ip,
        }
