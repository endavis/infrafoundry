"""The ``cloud_init_snippets_storage`` input of the aiqum, console-connector and
service-vm blueprints (#1303).

Unset, the key stays out of the VM config so ``vms.tf.j2`` keeps its own
default; set, it reaches the rendered snippet file resource.
"""

import textwrap
from pathlib import Path

import pytest

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.proxmox import ProxmoxProvider

VARIABLES = {
    "aiqum": """\
vm_name: demo
vmid: 233
target_node: node1
disk_storage: local-lvm
ip_address: "172.20.99.72"
dhcp_subnet: demonet
aiqum_admin_password: "pw"
aiqum_admin_email: "a@example.com"
aiqum_url_base: "http://web/aiqum"
smtp_server: "smtp.example.com"
smtp_user: "aiqum"
smtp_password: "pw"
ontap_cluster_ip: "172.20.99.80"
ontap_admin_password: "pw"
""",
    "console-connector": f"""\
vm_name: demo
vmid: 230
target_node: node1
disk_storage: local-lvm
ip_address: "192.0.2.60"
dhcp_subnet: s
console_agent_url_base: "http://example.invalid/connector"
console_agent_installer: netapp-console-agent-4.12.0
console_agent_sha256: "{"a" * 64}"
""",
    "service-vm": """\
vm_name: demo
vmid: 220
target_node: node1
mac_address: "02:00:00:00:00:01"
ip_address: "172.20.10.71"
dhcp_subnet: demonet
""",
}


def _vm(tmp_path: Path, blueprint: str, extra: str) -> ResourceConfig:
    envs = tmp_path / "envs"
    package = envs / "test" / "proxmox" / "demo"
    package.mkdir(parents=True)
    (package / "infrafoundry.yml").write_text(
        f"name: demo\nblueprint: {blueprint}\nvariables:\n"
        + textwrap.indent(VARIABLES[blueprint] + extra, "  ")
    )
    loader = PackageLoader(envs, blueprint_resolver=BlueprintResolver(envs))
    resources, _events, _variables = loader.load_package(
        package, provider="proxmox", env_name="test"
    )
    return next(r for r in resources if r.type == "vm")


@pytest.mark.unit
@pytest.mark.parametrize("blueprint", sorted(VARIABLES))
class TestSnippetsStorageInput:
    def test_unset_leaves_the_key_out(self, tmp_path: Path, blueprint: str) -> None:
        assert "cloud_init_snippets_storage" not in _vm(tmp_path, blueprint, "").config

    def test_empty_leaves_the_key_out(self, tmp_path: Path, blueprint: str) -> None:
        extra = 'cloud_init_snippets_storage: ""\n'
        assert "cloud_init_snippets_storage" not in _vm(tmp_path, blueprint, extra).config

    def test_set_reaches_the_vm_config(self, tmp_path: Path, blueprint: str) -> None:
        extra = "cloud_init_snippets_storage: snippets-store\n"
        vm = _vm(tmp_path, blueprint, extra)
        assert vm.config["cloud_init_snippets_storage"] == "snippets-store"

    def test_rendered_datastore_follows_the_input(self, tmp_path: Path, blueprint: str) -> None:
        config_dir = tmp_path / "config"
        snippets = config_dir / "test" / "files" / "cloud-init-snippets"
        for name in ("users/ansible", "network/dhcp", "packages/qemu-agent", "system/hostname"):
            path = snippets / f"{name}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("runcmd:\n  - true\n")
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        provider = ProxmoxProvider(config_dir, output_dir)
        provider.set_environment("test")

        def render(label: str, extra: str) -> str:
            vm = _vm(tmp_path / label, blueprint, extra)
            if blueprint == "service-vm":
                vm.config["cloud_init_snippets"] = ["users/ansible"]
            processed = provider._process_cloud_init_snippets(vm)
            processed = provider._normalize_vm_config(processed)
            return provider.render_template("proxmox/vms.tf.j2", {"vms": [processed]})

        assert 'datastore_id = "snippets-store"' in render(
            "set", "cloud_init_snippets_storage: snippets-store\n"
        )
        unset = render("unset", "")
        assert 'datastore_id = "stor01"' in unset
        assert "snippets-store" not in unset
