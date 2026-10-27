"""An empty or null NIC ``tag`` renders no VLAN, in every Proxmox template (#1138)."""

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.providers.proxmox import ProxmoxProvider


@pytest.fixture
def provider(tmp_path: Path) -> ProxmoxProvider:
    """Create a ProxmoxProvider for template rendering."""
    p = ProxmoxProvider(tmp_path / "config", tmp_path / "output")
    p.set_environment("test")
    return p


class _Res:
    """Minimal stand-in exposing ``name`` and ``config`` to the templates."""

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name = name
        self.config = config


@pytest.mark.parametrize("tag", [None, ""])
def test_vm_template_skips_empty_tag(provider: ProxmoxProvider, tag: Any) -> None:
    vm = _Res(
        "vm1",
        {
            "name": "vm1",
            "vmid": 1,
            "target_node": "pve1",
            "network": [{"bridge": "ntlan", "tag": tag}],
        },
    )

    rendered = provider.render_template("proxmox/vms.tf.j2", {"vms": [vm]})

    assert 'bridge      = "ntlan"' in rendered
    assert "vlan_id" not in rendered


def test_vm_template_keeps_a_real_tag(provider: ProxmoxProvider) -> None:
    vm = _Res(
        "vm1",
        {
            "name": "vm1",
            "vmid": 1,
            "target_node": "pve1",
            "network": [{"bridge": "vmbr0", "tag": 10}],
        },
    )

    assert "vlan_id     = 10" in provider.render_template("proxmox/vms.tf.j2", {"vms": [vm]})


@pytest.mark.parametrize("tag", [None, ""])
def test_container_template_skips_empty_tag(provider: ProxmoxProvider, tag: Any) -> None:
    ct = _Res(
        "ct1",
        {
            "name": "ct1",
            "ctid": 2,
            "target_node": "pve1",
            "ostemplate": "local:vztmpl/x.tar.zst",
            "network": [{"name": "eth0", "bridge": "ntlan", "tag": tag}],
        },
    )

    rendered = provider.render_template("proxmox/containers.tf.j2", {"containers": [ct]})

    assert "vlan_id" not in rendered


@pytest.mark.parametrize("tag", [None, ""])
def test_disk_image_vm_template_skips_empty_tag(provider: ProxmoxProvider, tag: Any) -> None:
    vm = _Res(
        "app",
        {
            "name": "app",
            "vmid": 3,
            "target_node": "pve1",
            "disk_image_source": "/var/lib/vz/images/app.img",
            "network": [{"bridge": "ntlan", "tag": tag}],
        },
    )

    rendered = provider.render_template("proxmox/ova_vms.tf.j2", {"ova_vms": [vm]})

    assert "bridge=ntlan" in rendered
    assert ",tag=" not in rendered
