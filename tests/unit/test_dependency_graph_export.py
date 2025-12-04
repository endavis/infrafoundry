"""Unit tests for DependencyGraph export."""

from infrafoundry.core.dependencies import DependencyGraph


def test_export_to_mermaid():
    """Ensure mermaid export includes nodes and edges."""
    graph = DependencyGraph()
    graph.add_resource("proxmox", "network", "net1")
    graph.add_resource("proxmox", "vm", "vm1", dependencies=["net1"])

    mermaid = graph.export_to_mermaid()

    assert "proxmox_net1" in mermaid
    assert "proxmox_vm1" in mermaid
    assert "proxmox_vm1 --> proxmox_net1" in mermaid or "proxmox_vm1-->proxmox_net1" in mermaid
