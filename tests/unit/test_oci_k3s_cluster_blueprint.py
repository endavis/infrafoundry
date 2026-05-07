"""Integration test for the k3s-cluster blueprint conversion.

Loads the real example-config oci-k3s env-root package via PackageLoader and
asserts that the merged configuration (blueprint defaults + package overrides)
produces the expected OCI VCN, subnets, and compute instances, plus the
inherited on_create / before_destroy / after_apply event handlers. Also
exercises the Jinja loop pattern over the ``workers:`` list with multi-
instance and zero-worker regression cases.

This is the regression guard for issue #505 and follows the pattern established
by ``test_proxmox_k3s_cluster_blueprint.py`` (#504, #514), the closest
structural reference (multi-VM blueprint with Jinja loops).

The test depends only on files checked into this repository:
  - blueprints/k3s-cluster/                       (the blueprint)
  - example-config/envs/oci-k3s/k3s-cluster/          (the example consumer)

It does NOT depend on the private endavis-infra/ config repo.
"""

import textwrap
from pathlib import Path

import pytest

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ENVS = REPO_ROOT / "example-config" / "envs"
PACKAGE_DIR = EXAMPLE_ENVS / "oci-k3s" / "k3s-cluster"


@pytest.fixture
def loader() -> PackageLoader:
    """PackageLoader pointed at the real example-config envs/ directory."""
    resolver = BlueprintResolver(EXAMPLE_ENVS)
    return PackageLoader(EXAMPLE_ENVS, blueprint_resolver=resolver)


def test_oci_k3s_cluster_example_loads_blueprint(loader: PackageLoader) -> None:
    """The oci-k3s example package loads via the blueprint resolver and
    merges blueprint defaults with per-tenancy overrides."""
    _resources, _events, variables = loader.load_package(
        PACKAGE_DIR, provider="oci", env_name="oci-k3s"
    )

    # --- Per-tenancy overrides come from the package manifest ---
    assert variables["cluster_name"] == "oci-k3s"
    assert variables["control_name"] == "k3s-control"
    assert variables["image"].startswith("ocid1.image.oc1.")
    assert variables["ssh_public_key"].startswith("ssh-rsa ")
    assert variables["tailnet"] == "your-tailnet.ts.net"

    # --- Blueprint defaults flow through unchanged ---
    assert variables["instance_shape"] == "VM.Standard.A1.Flex"
    assert variables["control_ocpus"] == 2
    assert variables["control_memory_gb"] == 8
    assert variables["control_boot_volume_gb"] == 50
    assert variables["worker_boot_volume_gb"] == 50
    assert variables["vcn_cidr"] == "10.0.0.0/16"
    assert variables["vcn_name"] == "k3s-vcn"
    assert variables["control_subnet_cidr"] == "10.0.0.0/24"
    assert variables["worker_subnet_cidr"] == "10.0.1.0/24"
    assert variables["k3s_oci_firewall_fix"] is True

    # Default workers list has 2 entries
    assert len(variables["workers"]) == 2
    assert variables["workers"][0]["name"] == "k3s-worker-0"
    assert variables["workers"][0]["ocpus"] == 1
    assert variables["workers"][0]["memory_gb"] == 8
    assert variables["workers"][1]["name"] == "k3s-worker-1"

    # kubeconfig_local_path default contains a Jinja expression; just assert set
    assert "kubeconfig_local_path" in variables


def test_oci_k3s_cluster_example_renders_correct_resource_count(
    loader: PackageLoader,
) -> None:
    """The merged config produces 6 resources: 1 VCN + 2 subnets + 1 control
    instance + 2 worker instances."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="oci", env_name="oci-k3s"
    )

    assert len(resources) == 6

    vcns = [r for r in resources if r.type == "vcn"]
    subnets = [r for r in resources if r.type == "subnet"]
    instances = [r for r in resources if r.type == "instance"]
    assert len(vcns) == 1
    assert len(subnets) == 2
    assert len(instances) == 3
    assert all(r.provider == "oci" for r in resources)


def test_oci_k3s_cluster_example_network_configs(loader: PackageLoader) -> None:
    """Rendered VCN and subnets have the expected CIDRs and routing flags."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="oci", env_name="oci-k3s"
    )

    vcn = next(r for r in resources if r.type == "vcn")
    assert vcn.name == "k3s-vcn"
    assert vcn.config["cidr_block"] == "10.0.0.0/16"
    assert vcn.config["dns_label"] == "k3svcn"
    assert vcn.config["internet_gateway"] is True
    assert vcn.config["nat_gateway"] is True
    # Security list must allow intra-VCN traffic
    ingress_sources = {rule["source"] for rule in vcn.config["security_list"]["ingress_rules"]}
    assert "10.0.0.0/16" in ingress_sources

    subnets_by_name = {r.name: r for r in resources if r.type == "subnet"}
    assert set(subnets_by_name) == {"k3s-control-subnet", "k3s-worker-subnet"}

    control_subnet = subnets_by_name["k3s-control-subnet"].config
    assert control_subnet["vcn"] == "k3s-vcn"
    assert control_subnet["cidr_block"] == "10.0.0.0/24"
    assert control_subnet["dns_label"] == "ctrl"
    assert control_subnet["public"] is True

    worker_subnet = subnets_by_name["k3s-worker-subnet"].config
    assert worker_subnet["vcn"] == "k3s-vcn"
    assert worker_subnet["cidr_block"] == "10.0.1.0/24"
    assert worker_subnet["dns_label"] == "work"
    assert worker_subnet["public"] is False


def test_oci_k3s_cluster_example_instance_configs(loader: PackageLoader) -> None:
    """Rendered instances have the expected shape, sizing, and tags.
    Validates that the Jinja loop over workers: produces correct per-worker
    values and differentiates control vs worker."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="oci", env_name="oci-k3s"
    )

    instances_by_name = {r.name: r for r in resources if r.type == "instance"}
    assert set(instances_by_name) == {"k3s-control", "k3s-worker-0", "k3s-worker-1"}

    control = instances_by_name["k3s-control"].config
    assert control["shape"] == "VM.Standard.A1.Flex"
    assert control["shape_config"]["ocpus"] == 2
    assert control["shape_config"]["memory_in_gbs"] == 8
    assert control["subnet"] == "k3s-control-subnet"
    assert control["assign_public_ip"] is True
    assert control["boot_volume_size_in_gbs"] == 50
    assert control["freeform_tags"]["role"] == "control-plane"
    assert control["freeform_tags"]["cluster"] == "oci-k3s"
    assert control["freeform_tags"]["managed_by"] == "infrafoundry"
    assert "tailscale" in control
    assert control["tailscale"]["hostname"] == "k3s-control"

    worker0 = instances_by_name["k3s-worker-0"].config
    assert worker0["shape"] == "VM.Standard.A1.Flex"
    assert worker0["shape_config"]["ocpus"] == 1
    assert worker0["shape_config"]["memory_in_gbs"] == 8
    assert worker0["subnet"] == "k3s-worker-subnet"
    assert worker0["assign_public_ip"] is False
    assert worker0["freeform_tags"]["role"] == "worker"
    assert worker0["tailscale"]["hostname"] == "k3s-worker-0"

    worker1 = instances_by_name["k3s-worker-1"].config
    assert worker1["shape_config"]["ocpus"] == 1
    assert worker1["subnet"] == "k3s-worker-subnet"
    assert worker1["assign_public_ip"] is False
    assert worker1["freeform_tags"]["role"] == "worker"
    assert worker1["tailscale"]["hostname"] == "k3s-worker-1"


def test_oci_k3s_cluster_blueprint_inherits_events(loader: PackageLoader) -> None:
    """The on_create, before_destroy, and after_apply event handlers are
    inherited from the blueprint. The on_create requires field is rendered
    with the per-tenancy control_name."""
    _resources, events, _variables = loader.load_package(
        PACKAGE_DIR, provider="oci", env_name="oci-k3s"
    )

    assert "on_create" in events
    on_create = events["on_create"]
    assert len(on_create) == 1
    handler = on_create[0]
    assert handler["type"] == "script"
    assert handler["name"] == "k3s-install"
    assert handler["script"].endswith("scripts/oci/k3s-post-terraform.sh")
    assert handler["timeout"] == 1800
    assert handler["continue_on_error"] is False
    assert handler["requires"] == ["k3s-control"]

    assert "before_destroy" in events
    before_destroy = events["before_destroy"]
    assert len(before_destroy) == 1
    assert before_destroy[0]["name"] == "tailscale-cleanup"
    assert before_destroy[0]["script"].endswith("scripts/oci/cleanup-tailscale-devices.sh")
    assert before_destroy[0]["continue_on_error"] is True

    assert "after_apply" in events
    after_apply = events["after_apply"]
    assert len(after_apply) == 1
    assert after_apply[0]["name"] == "verify-cluster"
    assert after_apply[0]["script"].endswith("scripts/oci/verify-cluster.sh")
    assert after_apply[0]["continue_on_error"] is True


def test_oci_k3s_cluster_example_uses_tailscale_module(loader: PackageLoader) -> None:
    """Every instance declares a tailscale: block referencing the OAuth
    secrets in the env's secrets.tailscale.* dict. Issue #212 phase 2
    replaced the custom cloud-init snippet with the official
    tailscale/tailscale/cloudinit Terraform module; this test verifies
    every blueprint instance opted into the new schema."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="oci", env_name="oci-k3s"
    )

    instances = [r for r in resources if r.type == "instance"]
    assert len(instances) == 3
    for inst in instances:
        ts = inst.config.get("tailscale")
        assert ts is not None, f"{inst.name} missing tailscale: block"
        assert ts["hostname"] == inst.name
        assert ts["enable_ssh"] is True
        # OAuth credentials come from secrets.tailscale.{client_id,client_secret}
        # via the framework's secrets→TF_VAR_* bridge.
        assert ts["auth"]["oauth"]["client_id_secret"] == "tailscale.oauth_client_id"
        assert ts["auth"]["oauth"]["client_secret_secret"] == "tailscale.oauth_client_secret"
        # Should NOT have the legacy cloud_init_snippets path
        assert "cloud_init_snippets" not in inst.config


def test_oci_k3s_cluster_blueprint_supports_multiple_worker_counts(tmp_path: Path) -> None:
    """Two packages instantiating the k3s-cluster blueprint with different
    worker counts must produce distinct resources without colliding.

    Regression guard for the Jinja-loop pattern: every outer name must be
    templated and the loop must produce the correct number of resources
    for each instance.
    """
    envs = tmp_path / "envs"
    pkg_a = envs / "test-a" / "k3s"
    pkg_b = envs / "test-b" / "k3s"
    pkg_a.mkdir(parents=True)
    pkg_b.mkdir(parents=True)

    (pkg_a / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: k3s-a
            description: "k3s cluster A (1 worker)"
            blueprint: k3s-cluster
            provider: oci
            variables:
              cluster_name: k3s-a
              control_name: k3s-a-control
              image: "ocid1.image.oc1.iad.aaaaaaaa"
              ssh_public_key: "ssh-rsa AAAA-a"
              tailnet: "a.ts.net"
              workers:
                - name: k3s-a-worker-0
                  ocpus: 1
                  memory_gb: 8
            """
        )
    )
    (pkg_b / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: k3s-b
            description: "k3s cluster B (4 workers)"
            blueprint: k3s-cluster
            provider: oci
            variables:
              cluster_name: k3s-b
              control_name: k3s-b-control
              image: "ocid1.image.oc1.iad.bbbbbbbb"
              ssh_public_key: "ssh-rsa AAAA-b"
              tailnet: "b.ts.net"
              vcn_name: k3s-b-vcn
              control_subnet_name: k3s-b-control-subnet
              worker_subnet_name: k3s-b-worker-subnet
              workers:
                - name: k3s-b-worker-0
                  ocpus: 1
                  memory_gb: 6
                - name: k3s-b-worker-1
                  ocpus: 1
                  memory_gb: 6
                - name: k3s-b-worker-2
                  ocpus: 1
                  memory_gb: 6
                - name: k3s-b-worker-3
                  ocpus: 1
                  memory_gb: 6
            """
        )
    )

    resolver = BlueprintResolver(envs)
    loader = PackageLoader(envs, blueprint_resolver=resolver)

    resources_a, events_a, _ = loader.load_package(pkg_a, provider="oci", env_name="test-a")
    resources_b, events_b, _ = loader.load_package(pkg_b, provider="oci", env_name="test-b")

    # A: 1 vcn + 2 subnets + 1 control + 1 worker = 5
    assert len(resources_a) == 5
    assert sum(1 for r in resources_a if r.type == "instance") == 2
    assert sum(1 for r in resources_a if r.type == "subnet") == 2
    assert sum(1 for r in resources_a if r.type == "vcn") == 1

    # B: 1 vcn + 2 subnets + 1 control + 4 workers = 8
    assert len(resources_b) == 8
    assert sum(1 for r in resources_b if r.type == "instance") == 5

    # Instance names are distinct between the two consumers
    inst_names_a = {r.name for r in resources_a if r.type == "instance"}
    inst_names_b = {r.name for r in resources_b if r.type == "instance"}
    assert inst_names_a.isdisjoint(inst_names_b)
    assert "k3s-a-control" in inst_names_a
    assert "k3s-b-worker-3" in inst_names_b

    # Per-consumer worker memory overrides are honored
    worker_b3 = next(r for r in resources_b if r.name == "k3s-b-worker-3")
    assert worker_b3.config["shape_config"]["memory_in_gbs"] == 6

    # VCN names are distinct (B overrides vcn_name)
    vcn_names_a = {r.name for r in resources_a if r.type == "vcn"}
    vcn_names_b = {r.name for r in resources_b if r.type == "vcn"}
    assert vcn_names_a == {"k3s-vcn"}
    assert vcn_names_b == {"k3s-b-vcn"}

    # Events are per-instance: requires references the correct control_name
    assert events_a["on_create"][0]["requires"] == ["k3s-a-control"]
    assert events_b["on_create"][0]["requires"] == ["k3s-b-control"]


def test_oci_k3s_cluster_blueprint_with_zero_workers(tmp_path: Path) -> None:
    """A package with ``workers: []`` must render the Jinja loop cleanly and
    produce exactly 4 resources (1 vcn + 2 subnets + 1 control instance).
    Edge-case guard for the Jinja-loop pattern over a list of dicts.
    """
    envs = tmp_path / "envs"
    pkg = envs / "test" / "k3s-solo"
    pkg.mkdir(parents=True)

    (pkg / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: k3s-solo
            description: "Single-node k3s cluster (no workers)"
            blueprint: k3s-cluster
            provider: oci
            variables:
              cluster_name: k3s-solo
              control_name: k3s-solo-control
              image: "ocid1.image.oc1.iad.ssssssss"
              ssh_public_key: "ssh-rsa AAAA-solo"
              tailnet: "solo.ts.net"
              workers: []
            """
        )
    )

    resolver = BlueprintResolver(envs)
    loader = PackageLoader(envs, blueprint_resolver=resolver)

    resources, events, _variables = loader.load_package(pkg, provider="oci", env_name="test")

    assert len(resources) == 4
    instances = [r for r in resources if r.type == "instance"]
    subnets = [r for r in resources if r.type == "subnet"]
    vcns = [r for r in resources if r.type == "vcn"]
    assert len(instances) == 1
    assert len(subnets) == 2
    assert len(vcns) == 1
    assert instances[0].name == "k3s-solo-control"
    assert events["on_create"][0]["requires"] == ["k3s-solo-control"]
