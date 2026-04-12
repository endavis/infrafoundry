"""Integration test for the k3s-cluster blueprint conversion.

Loads the real example-config k3s-cluster package via PackageLoader and asserts
that the merged configuration (blueprint defaults + package overrides) produces
the expected proxmox VMs and opnsense DHCP reservations, plus the inherited
on_create event handler. Also exercises the new Jinja loop pattern over the
``agents:`` list with multi-instance and zero-agent regression cases.

This is the regression guard for issue #504 and follows the pattern established
by ``test_aiqum_blueprint.py`` (#502, #513) and ``test_rocky9_blueprint.py``
(#503, #511).

The test depends only on files checked into this repository:
  - blueprints/k3s-cluster/                       (the blueprint)
  - example-config/envs/dev/proxmox/k3s-cluster/          (the example consumer)

It does NOT depend on the private endavis-infra/ config repo.
"""

import textwrap
from pathlib import Path

import pytest

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ENVS = REPO_ROOT / "example-config" / "envs"
PACKAGE_DIR = EXAMPLE_ENVS / "dev" / "proxmox" / "k3s-cluster"


@pytest.fixture
def loader() -> PackageLoader:
    """PackageLoader pointed at the real example-config envs/ directory."""
    resolver = BlueprintResolver(EXAMPLE_ENVS)
    return PackageLoader(EXAMPLE_ENVS, blueprint_resolver=resolver)


def test_proxmox_k3s_cluster_example_loads_blueprint(loader: PackageLoader) -> None:
    """The k3s-cluster example package loads via the blueprint resolver and
    merges blueprint defaults with per-instance overrides."""
    _resources, _events, variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    # --- Per-instance overrides come from the package manifest ---
    assert variables["cluster_name"] == "k3s-dev"
    assert variables["disk_storage"] == "local-lvm"
    assert variables["dhcp_subnet"] == "my-subnet"
    assert variables["jumphost"] == "ansible@ansible.example.com"
    assert variables["server_name"] == "k3s-dev-server"
    assert variables["server_vmid"] == 240
    assert variables["server_target"] == "pve1"
    assert variables["server_ip"] == "192.168.10.80"
    assert len(variables["agents"]) == 2
    assert variables["agents"][0]["name"] == "k3s-dev-agent-1"
    assert variables["agents"][1]["name"] == "k3s-dev-agent-2"

    # --- Blueprint defaults flow through unchanged ---
    assert variables["template_vmid"] == 901
    assert variables["template_node"] == "pve1"
    assert variables["cores"] == 2
    assert variables["memory"] == 4096
    assert variables["disk_size"] == 56
    assert variables["bridge"] == "vmbr0"
    assert variables["vlan_tag"] == 10
    assert variables["k3s_server_args"] == "--disable traefik --disable servicelb"
    assert variables["kubeconfig_dir"] == "~/.kube"


def test_proxmox_k3s_cluster_example_renders_correct_resource_count(
    loader: PackageLoader,
) -> None:
    """The merged config produces 6 resources: 1 server VM + 2 agent VMs +
    1 server DHCP + 2 agent DHCP."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    assert len(resources) == 6

    vms = [r for r in resources if r.type == "vm"]
    dhcps = [r for r in resources if r.type == "kea_reservation"]
    assert len(vms) == 3
    assert len(dhcps) == 3
    assert all(r.provider == "proxmox" for r in vms)
    assert all(r.provider == "opnsense" for r in dhcps)


def test_proxmox_k3s_cluster_example_vm_configs(loader: PackageLoader) -> None:
    """Each rendered VM (server + 2 agents) has the right vmid, mac, target_node
    and tags. Validates that the Jinja loop over agents: produces correct
    per-agent values."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    vms_by_name = {r.name: r for r in resources if r.type == "vm"}
    assert set(vms_by_name) == {"k3s-dev-server", "k3s-dev-agent-1", "k3s-dev-agent-2"}

    server = vms_by_name["k3s-dev-server"].config
    assert server["vmid"] == 240
    assert server["target_node"] == "pve1"
    assert server["clone"] == {"vm_id": 901, "node_name": "pve1"}
    assert server["cores"] == 2
    assert server["memory"] == 4096
    assert server["disk"] == {"storage": "local-lvm", "size": 56}
    assert server["network"][0]["bridge"] == "vmbr0"
    assert server["network"][0]["tag"] == 10
    assert server["network"][0]["macaddr"] == "BC:24:11:00:08:00"
    assert server["tags"] == ["k3s", "k3s-server"]
    assert server["onboot"] is True
    assert server["agent"] is True
    assert server["cloud_init_snippets"] == [
        "system/hostname",
        "users/ansible",
        "network/dhcp",
        "packages/qemu-agent",
    ]

    agent1 = vms_by_name["k3s-dev-agent-1"].config
    assert agent1["vmid"] == 241
    assert agent1["target_node"] == "pve1"
    assert agent1["network"][0]["macaddr"] == "BC:24:11:00:08:01"
    assert agent1["tags"] == ["k3s", "k3s-agent"]

    agent2 = vms_by_name["k3s-dev-agent-2"].config
    assert agent2["vmid"] == 242
    assert agent2["target_node"] == "pve1"
    assert agent2["network"][0]["macaddr"] == "BC:24:11:00:08:02"
    assert agent2["tags"] == ["k3s", "k3s-agent"]


def test_proxmox_k3s_cluster_example_sets_per_vm_cloud_init_hostname(
    loader: PackageLoader,
) -> None:
    """Each VM resource carries a ``cloud_init_vars['HOSTNAME']`` matching its own name.

    Regression guard for #526. The blueprint references the shared
    ``system/hostname`` cloud-init snippet which contains a ``${HOSTNAME}``
    placeholder. Before this fix the blueprint never populated
    ``cloud_init_vars`` so the placeholder was never substituted and every VM
    came up with the same broken hostname, causing k3s cluster formation to
    fail with node-name collisions.
    """
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )
    vms = [r for r in resources if r.type == "vm"]
    assert vms, "expected at least one VM resource"
    for vm in vms:
        assert "cloud_init_vars" in vm.config, (
            f"VM {vm.name} is missing cloud_init_vars; system/hostname snippet "
            f"substitution will fail"
        )
        assert vm.config["cloud_init_vars"]["HOSTNAME"] == vm.name, (
            f"VM {vm.name}'s HOSTNAME cloud_init_var must match its own name "
            f"(got {vm.config['cloud_init_vars']['HOSTNAME']!r})"
        )


def test_proxmox_k3s_cluster_example_dhcp_configs(loader: PackageLoader) -> None:
    """Each rendered kea_reservation matches its corresponding VM."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    dhcps_by_name = {r.name: r for r in resources if r.type == "kea_reservation"}
    assert set(dhcps_by_name) == {
        "k3s-dev-server-dhcp",
        "k3s-dev-agent-1-dhcp",
        "k3s-dev-agent-2-dhcp",
    }

    server = dhcps_by_name["k3s-dev-server-dhcp"].config
    assert server["subnet_ref"] == "my-subnet"
    assert server["hw_address"] == "bc:24:11:00:08:00"
    assert server["ip_address"] == "192.168.10.80"
    assert server["hostname"] == "k3s-dev-server"

    agent1 = dhcps_by_name["k3s-dev-agent-1-dhcp"].config
    assert agent1["hw_address"] == "bc:24:11:00:08:01"
    assert agent1["ip_address"] == "192.168.10.81"
    assert agent1["hostname"] == "k3s-dev-agent-1"

    agent2 = dhcps_by_name["k3s-dev-agent-2-dhcp"].config
    assert agent2["hw_address"] == "bc:24:11:00:08:02"
    assert agent2["ip_address"] == "192.168.10.82"
    assert agent2["hostname"] == "k3s-dev-agent-2"


def test_proxmox_k3s_cluster_blueprint_inherits_events(loader: PackageLoader) -> None:
    """The on_create event handler is inherited from the blueprint and its
    requires field is rendered with the per-instance server_name."""
    _resources, events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    assert "on_create" in events
    handlers = events["on_create"]
    assert len(handlers) == 1

    handler = handlers[0]
    assert handler["type"] == "script"
    assert handler["name"] == "k3s-install"
    assert handler["script"].endswith("scripts/proxmox/k3s-post-terraform.sh")
    assert handler["timeout"] == 1800
    assert handler["continue_on_error"] is False
    # Templated requires field rendered with per-instance server_name
    assert handler["requires"] == ["k3s-dev-server"]


def test_proxmox_k3s_cluster_blueprint_supports_multiple_instances(tmp_path: Path) -> None:
    """Two packages instantiating the k3s-cluster blueprint with
    different agent counts must produce distinct resources without colliding.

    Regression guard against #511-style bugs and the new Jinja-loop pattern:
    every outer ``name`` must be templated, and the loop must produce the
    correct number of resources for each instance.
    """
    envs = tmp_path / "envs"
    pkg_a = envs / "test" / "proxmox" / "k3s-a"
    pkg_b = envs / "test" / "proxmox" / "k3s-b"
    pkg_a.mkdir(parents=True)
    pkg_b.mkdir(parents=True)

    (pkg_a / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: k3s-a
            description: "k3s instance A (2 agents)"
            blueprint: k3s-cluster
            variables:
              cluster_name: k3s-a
              disk_storage: local-lvm
              dhcp_subnet: subnet-a
              jumphost: "ansible@host-a"
              server_name: k3s-a-server
              server_vmid: 300
              server_target: pve1
              server_mac: "BC:24:11:00:0A:00"
              server_ip: "10.0.0.10"
              agents:
                - name: k3s-a-agent-1
                  vmid: 301
                  target_node: pve1
                  mac: "BC:24:11:00:0A:01"
                  ip: "10.0.0.11"
                - name: k3s-a-agent-2
                  vmid: 302
                  target_node: pve2
                  mac: "BC:24:11:00:0A:02"
                  ip: "10.0.0.12"
            """
        )
    )
    (pkg_b / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: k3s-b
            description: "k3s instance B (4 agents)"
            blueprint: k3s-cluster
            variables:
              cluster_name: k3s-b
              disk_storage: local-lvm
              dhcp_subnet: subnet-b
              jumphost: "ansible@host-b"
              server_name: k3s-b-server
              server_vmid: 400
              server_target: pve3
              server_mac: "BC:24:11:00:0B:00"
              server_ip: "10.0.1.10"
              agents:
                - name: k3s-b-agent-1
                  vmid: 401
                  target_node: pve1
                  mac: "BC:24:11:00:0B:01"
                  ip: "10.0.1.11"
                - name: k3s-b-agent-2
                  vmid: 402
                  target_node: pve2
                  mac: "BC:24:11:00:0B:02"
                  ip: "10.0.1.12"
                - name: k3s-b-agent-3
                  vmid: 403
                  target_node: pve3
                  mac: "BC:24:11:00:0B:03"
                  ip: "10.0.1.13"
                - name: k3s-b-agent-4
                  vmid: 404
                  target_node: pve1
                  mac: "BC:24:11:00:0B:04"
                  ip: "10.0.1.14"
            """
        )
    )

    resolver = BlueprintResolver(envs)
    loader = PackageLoader(envs, blueprint_resolver=resolver)

    resources_a, events_a, _ = loader.load_package(pkg_a, provider="proxmox", env_name="test")
    resources_b, events_b, _ = loader.load_package(pkg_b, provider="proxmox", env_name="test")

    # A: 1 server + 2 agents = 3 VMs + 3 DHCP reservations = 6
    assert len(resources_a) == 6
    assert sum(1 for r in resources_a if r.type == "vm") == 3
    assert sum(1 for r in resources_a if r.type == "kea_reservation") == 3

    # B: 1 server + 4 agents = 5 VMs + 5 DHCP reservations = 10
    assert len(resources_b) == 10
    assert sum(1 for r in resources_b if r.type == "vm") == 5
    assert sum(1 for r in resources_b if r.type == "kea_reservation") == 5

    # VM names are distinct between instances
    vm_names_a = {r.name for r in resources_a if r.type == "vm"}
    vm_names_b = {r.name for r in resources_b if r.type == "vm"}
    assert vm_names_a.isdisjoint(vm_names_b)
    assert "k3s-a-server" in vm_names_a
    assert "k3s-b-agent-4" in vm_names_b

    # Per-instance vmid + target_node values are correct
    vm_a_server = next(r for r in resources_a if r.name == "k3s-a-server")
    vm_b_server = next(r for r in resources_b if r.name == "k3s-b-server")
    assert vm_a_server.config["vmid"] == 300
    assert vm_b_server.config["vmid"] == 400
    assert vm_a_server.config["target_node"] == "pve1"
    assert vm_b_server.config["target_node"] == "pve3"

    vm_b_agent4 = next(r for r in resources_b if r.name == "k3s-b-agent-4")
    assert vm_b_agent4.config["vmid"] == 404
    assert vm_b_agent4.config["network"][0]["macaddr"] == "BC:24:11:00:0B:04"

    # DHCP reservation names follow the "<vm>-dhcp" template
    dhcp_names_a = {r.name for r in resources_a if r.type == "kea_reservation"}
    assert dhcp_names_a == {"k3s-a-server-dhcp", "k3s-a-agent-1-dhcp", "k3s-a-agent-2-dhcp"}

    # Events are per-instance: requires field references the correct server_name
    assert events_a["on_create"][0]["requires"] == ["k3s-a-server"]
    assert events_b["on_create"][0]["requires"] == ["k3s-b-server"]


def test_proxmox_k3s_cluster_blueprint_with_zero_agents(tmp_path: Path) -> None:
    """A package with ``agents: []`` must render the Jinja loop cleanly and
    produce exactly 2 resources (server VM + server DHCP). Edge-case guard
    for the new Jinja-loop pattern over a list of dicts.
    """
    envs = tmp_path / "envs"
    pkg = envs / "test" / "proxmox" / "k3s-solo"
    pkg.mkdir(parents=True)

    (pkg / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: k3s-solo
            description: "Single-node k3s cluster (no agents)"
            blueprint: k3s-cluster
            variables:
              cluster_name: k3s-solo
              disk_storage: local-lvm
              dhcp_subnet: subnet-solo
              jumphost: "ansible@host"
              server_name: k3s-solo-server
              server_vmid: 500
              server_target: pve1
              server_mac: "BC:24:11:00:0C:00"
              server_ip: "10.0.2.10"
              agents: []
            """
        )
    )

    resolver = BlueprintResolver(envs)
    loader = PackageLoader(envs, blueprint_resolver=resolver)

    resources, events, _variables = loader.load_package(pkg, provider="proxmox", env_name="test")

    assert len(resources) == 2
    vms = [r for r in resources if r.type == "vm"]
    dhcps = [r for r in resources if r.type == "kea_reservation"]
    assert len(vms) == 1
    assert len(dhcps) == 1
    assert vms[0].name == "k3s-solo-server"
    assert dhcps[0].name == "k3s-solo-server-dhcp"
    assert events["on_create"][0]["requires"] == ["k3s-solo-server"]
