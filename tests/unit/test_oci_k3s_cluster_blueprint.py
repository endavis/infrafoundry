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

It does NOT depend on the private infra-config/ config repo.
"""

import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import jinja2
import pytest
import yaml

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.filters import create_jinja2_env
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
    assert variables["vcn_cidr"] == "192.0.2.0/24"
    assert variables["vcn_name"] == "k3s-vcn"
    assert variables["control_subnet_cidr"] == "192.0.2.0/25"
    assert variables["worker_subnet_cidr"] == "192.0.2.128/25"
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
    assert vcn.config["cidr_block"] == "192.0.2.0/24"
    assert vcn.config["dns_label"] == "k3svcn"
    assert vcn.config["internet_gateway"] is True
    assert vcn.config["nat_gateway"] is True
    # Security list must allow intra-VCN traffic
    ingress_sources = {rule["source"] for rule in vcn.config["security_list"]["ingress_rules"]}
    assert "192.0.2.0/24" in ingress_sources

    subnets_by_name = {r.name: r for r in resources if r.type == "subnet"}
    assert set(subnets_by_name) == {"k3s-control-subnet", "k3s-worker-subnet"}

    control_subnet = subnets_by_name["k3s-control-subnet"].config
    assert control_subnet["vcn"] == "k3s-vcn"
    assert control_subnet["cidr_block"] == "192.0.2.0/25"
    assert control_subnet["dns_label"] == "ctrl"
    assert control_subnet["public"] is True

    worker_subnet = subnets_by_name["k3s-worker-subnet"].config
    assert worker_subnet["vcn"] == "k3s-vcn"
    assert worker_subnet["cidr_block"] == "192.0.2.128/25"
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

    assert "before_destroy" not in events

    assert "after_apply" in events
    after_apply = events["after_apply"]
    assert [h["name"] for h in after_apply] == [
        "k3s-bootstrap",
        "k3s-kubeconfig-mode",
        "k3s-dns",
        "verify-cluster",
    ]
    assert after_apply[2]["script"].endswith("scripts/oci/k3s-dns.sh")
    assert after_apply[2]["continue_on_error"] is True
    assert after_apply[3]["script"].endswith("scripts/oci/verify-cluster.sh")
    assert after_apply[3]["continue_on_error"] is True


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


def _verify_cluster_env(tmp_path: Path, extra_vars: str = "") -> dict[str, str]:
    """Render a package and return the env of its verify-cluster handler."""
    envs = tmp_path / "envs"
    pkg = envs / "test" / "example-k3s"
    pkg.mkdir(parents=True)
    (pkg / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: example-k3s
            description: "k3s with a non-default cluster name"
            blueprint: k3s-cluster
            provider: oci
            variables:
              cluster_name: example-k3s
              control_name: example-k3s-control
              image: "ocid1.image.oc1.iad.tttttttt"
              ssh_public_key: "ssh-rsa AAAA-ts"
              tailnet: "example.ts.net"
              ts_tags: ["tag:example"]
            """
        )
        + extra_vars
    )
    loader = PackageLoader(envs, blueprint_resolver=BlueprintResolver(envs))
    _resources, events, _variables = loader.load_package(pkg, provider="oci", env_name="test")
    handler = next(h for h in events["after_apply"] if h["name"] == "verify-cluster")
    return dict(handler["env"])


def test_verify_cluster_handler_uses_overridden_kubeconfig_path(tmp_path: Path) -> None:
    """An overridden kubeconfig_local_path reaches the verify-cluster handler env."""
    env = _verify_cluster_env(tmp_path, '  kubeconfig_local_path: "~/custom/example.yaml"\n')
    assert env["KUBECONFIG"] == "~/custom/example.yaml"


def test_verify_cluster_handler_uses_default_kubeconfig_path(tmp_path: Path) -> None:
    """Without an override, the default path resolves from cluster_name."""
    env = _verify_cluster_env(tmp_path)
    assert env["KUBECONFIG"] == "~/.kube/example-k3s.yaml"


def test_verify_cluster_script_expands_leading_tilde(tmp_path: Path) -> None:
    """A leading ~ in KUBECONFIG is expanded to HOME before the file check."""
    home = tmp_path / "home"
    home.mkdir()
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "KUBECONFIG": "~/x.yaml",
    }
    result = subprocess.run(
        ["bash", str(BLUEPRINT / "scripts" / "oci" / "verify-cluster.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"Using kubeconfig: {home}/x.yaml" in result.stdout
    assert f"Kubeconfig not found at {home}/x.yaml" in result.stdout


def test_verify_cluster_handler_env_carries_control_name_and_tailnet(tmp_path: Path) -> None:
    """The handler env carries what the ssh fallback needs to reach the control node."""
    env = _verify_cluster_env(tmp_path)
    assert env["K3S_CONTROL_NAME"] == "example-k3s-control"
    assert env["K3S_TAILNET"] == "example.ts.net"


def _stub_bin(
    tmp_path: Path, *, kubectl: bool, ssh: bool, ssh_exit: int = 0, nodes: str = "n1 Ready"
) -> Path:
    """Build a PATH directory with the tools the script needs and optional stubs."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("bash", "dirname", "grep", "wc", "cat"):
        found = shutil.which(tool)
        assert found is not None
        (bindir / tool).symlink_to(found)
    body = (
        "#!/bin/bash\n"
        'echo "$0 $*" >> "$STUB_LOG"\n'
        'if [[ "$*" == *"get nodes --no-headers" ]]; then\n'
        f"  echo '{nodes}'\n"
        "fi\n"
    )
    if kubectl:
        (bindir / "kubectl").write_text(body)
        (bindir / "kubectl").chmod(0o755)
    if ssh:
        probe = f'if [ "${{@: -1}}" = true ]; then exit {ssh_exit}; fi\n'
        (bindir / "ssh").write_text(body + probe)
        (bindir / "ssh").chmod(0o755)
    return bindir


def _run_verify(
    tmp_path: Path, bindir: Path, extra_env: dict[str, str] | None = None
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    """Run verify-cluster.sh with only the stub PATH; return result, call log, warnings."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    (home / "kube.yaml").write_text("apiVersion: v1\n")
    log = tmp_path / "stub.log"
    warnings = tmp_path / "warnings.jsonl"
    env = {
        "PATH": str(bindir),
        "HOME": str(home),
        "KUBECONFIG": "~/kube.yaml",
        "STUB_LOG": str(log),
        "INFRAFOUNDRY_WARNINGS_FILE": str(warnings),
        **(extra_env or {}),
    }
    result = subprocess.run(
        [str(bindir / "bash"), str(BLUEPRINT / "scripts" / "oci" / "verify-cluster.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, log, warnings


_PINNED = (
    "example-k3s-control,example-k3s-control.example.ts.net "
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest"
)
_CONTROL_ENV = {
    "K3S_CONTROL_NAME": "example-k3s-control",
    "K3S_TAILNET": "example.ts.net",
    "K3S_KNOWN_HOSTS": _PINNED,
}


def test_verify_cluster_prefers_local_kubectl(tmp_path: Path) -> None:
    """With kubectl on PATH the checks run locally and ssh is never called."""
    bindir = _stub_bin(tmp_path, kubectl=True, ssh=True)
    result, log, _ = _run_verify(tmp_path, bindir, _CONTROL_ENV)
    assert result.returncode == 0, result.stderr + result.stdout
    calls = log.read_text()
    assert "kubectl get nodes -o wide" in calls
    assert "ssh" not in calls


def test_verify_cluster_falls_back_to_remote_kubectl_over_ssh(tmp_path: Path) -> None:
    """Without local kubectl the checks run on the control node via sudo k3s kubectl."""
    bindir = _stub_bin(tmp_path, kubectl=False, ssh=True)
    result, log, warnings = _run_verify(tmp_path, bindir, _CONTROL_ENV)
    assert result.returncode == 0, result.stderr + result.stdout
    calls = log.read_text()
    host = "ansible@example-k3s-control.example.ts.net"
    assert f"-o BatchMode=yes -o ConnectTimeout=10 {host} sudo k3s kubectl get nodes -o wide" in (
        calls
    )
    assert "sudo k3s kubectl get pods -n kube-system" in calls
    assert "sudo k3s kubectl cluster-info" in calls
    assert "Cluster verification complete" in result.stdout
    assert not warnings.exists()


def test_verify_cluster_remote_not_ready_nodes_are_reported(tmp_path: Path) -> None:
    """Remote NotReady nodes are counted and warned about, as for a local kubectl."""
    bindir = _stub_bin(tmp_path, kubectl=False, ssh=True, nodes="n1 NotReady")
    result, _, _ = _run_verify(tmp_path, bindir, _CONTROL_ENV)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "1 node(s) not in Ready state" in result.stdout


def test_verify_cluster_skips_when_ssh_unusable(tmp_path: Path) -> None:
    """A failing ssh probe skips verification with a clear message and a warning."""
    bindir = _stub_bin(tmp_path, kubectl=False, ssh=True, ssh_exit=255)
    result, _, warnings = _run_verify(tmp_path, bindir, _CONTROL_ENV)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Verification skipped" in result.stdout
    assert "verify-cluster" in warnings.read_text()


@pytest.mark.parametrize("with_ssh", [True, False])
def test_verify_cluster_skips_without_kubectl_and_control_or_ssh(
    tmp_path: Path, with_ssh: bool
) -> None:
    """No control name, or no ssh client, skips verification and records a warning."""
    bindir = _stub_bin(tmp_path, kubectl=False, ssh=with_ssh)
    env = {} if with_ssh else _CONTROL_ENV
    result, _, warnings = _run_verify(tmp_path, bindir, env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Verification skipped" in result.stdout
    assert json.loads(warnings.read_text().splitlines()[0])["source"] == "verify-cluster"


def test_oci_k3s_cluster_blueprint_overrides_tailscale_secret_keys(tmp_path: Path) -> None:
    """ts_oauth_client_*_secret variables change the secret keys on every node."""
    envs = tmp_path / "envs"
    pkg = envs / "test" / "k3s-ts"
    pkg.mkdir(parents=True)
    (pkg / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: k3s-ts
            description: "k3s with custom Tailscale secret keys"
            blueprint: k3s-cluster
            provider: oci
            variables:
              cluster_name: k3s-ts
              control_name: k3s-ts-control
              image: "ocid1.image.oc1.iad.tttttttt"
              ssh_public_key: "ssh-rsa AAAA-ts"
              tailnet: "example.ts.net"
              ts_tags: ["tag:example"]
              ts_oauth_client_id_secret: "tailscale.custom_id"
              ts_oauth_client_secret_secret: "tailscale.custom_secret"
            """
        )
    )
    loader = PackageLoader(envs, blueprint_resolver=BlueprintResolver(envs))
    resources, _events, _variables = loader.load_package(pkg, provider="oci", env_name="test")

    instances = [r for r in resources if r.type == "instance"]
    assert len(instances) == 3
    for inst in instances:
        oauth = inst.config["tailscale"]["auth"]["oauth"]
        assert oauth["client_id_secret"] == "tailscale.custom_id"
        assert oauth["client_secret_secret"] == "tailscale.custom_secret"


def test_k3s_install_declares_the_kubeconfig_as_an_output(loader: PackageLoader) -> None:
    """With a jumphost, the framework copies the kubeconfig back to the operator (#672).

    The paths are rendered a second time here, as ``ScriptHandler`` does at run time.
    """
    _resources, events, variables = loader.load_package(
        PACKAGE_DIR, provider="oci", env_name="oci-k3s"
    )
    (handler,) = events["on_create"]
    env = create_jinja2_env(undefined=jinja2.StrictUndefined)

    (output,) = handler["outputs"]
    rendered = {key: env.from_string(output[key]).render(**variables) for key in output}

    assert rendered == {"source": "~/.kube/oci-k3s.yaml", "dest": "~/.kube/oci-k3s.yaml"}


# --- Shipped roles and the post-terraform script (#1522) ---

BLUEPRINT = REPO_ROOT / "blueprints" / "k3s-cluster"
OCI_SCRIPT = BLUEPRINT / "scripts" / "oci" / "k3s-post-terraform.sh"

_FAKE_ANSIBLE = """#!/bin/sh
echo "$ANSIBLE_ROLES_PATH" > "$RECORD_DIR/roles_path"
echo "$@" > "$RECORD_DIR/args"
for arg in "$@"; do
    case "$arg" in
        @*) cp "${arg#@}" "$RECORD_DIR/extra_vars.json" ;;
    esac
done
prev=""
for arg in "$@"; do
    [ "$prev" = "-i" ] && cp "$arg" "$RECORD_DIR/inventory.yml"
    prev="$arg"
done
"""


def _run_script(
    tmp_path: Path,
    *,
    blueprint_dir: Path | None = None,
    config_dir: Path | None = None,
    jumphost: bool = False,
) -> tuple[str, str]:
    """Run the OCI script with stubbed ssh/ansible; return (ANSIBLE_ROLES_PATH, args)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = tmp_path / "record"
    record.mkdir()
    stubs = {
        "ssh": "#!/bin/sh\nexit 0\n",
        "ssh-add": "#!/bin/sh\necho key\n",
        "sleep": "#!/bin/sh\nexit 0\n",
        "ansible-playbook": _FAKE_ANSIBLE,
    }
    for name, body in stubs.items():
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "RECORD_DIR": str(record),
        "INFRAFOUNDRY_VAR_control_name": "ctl",
        "INFRAFOUNDRY_VAR_cluster_name": "c",
        "INFRAFOUNDRY_VAR_ssh_public_key": (
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest test@example.com"
        ),
        "INFRAFOUNDRY_VAR_kubeconfig_local_path": str(tmp_path / "kube.yaml"),
        "INFRAFOUNDRY_VAR_ssh_known_hosts": (
            "ctl,ctl.example.net ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest;"
            "w1,w1.example.net ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest"
        ),
        "INFRAFOUNDRY_PACKAGE_VARS": json.dumps({"workers": [{"name": "w1"}]}),
    }
    if blueprint_dir is not None:
        env["INFRAFOUNDRY_BLUEPRINT_DIR"] = str(blueprint_dir)
    if config_dir is not None:
        env["INFRAFOUNDRY_CONFIG_DIR"] = str(config_dir)
    if jumphost:
        env["INFRAFOUNDRY_ON_JUMPHOST"] = "1"
    result = subprocess.run(
        ["bash", str(OCI_SCRIPT)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr + result.stdout
    return (record / "roles_path").read_text().strip(), (record / "args").read_text().strip()


def test_script_defaults_to_blueprint_roles(tmp_path: Path) -> None:
    """Without an env roles/ directory the blueprint roles and playbook are used."""
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    roles_path, args = _run_script(tmp_path, blueprint_dir=BLUEPRINT, config_dir=env_dir)

    assert roles_path == str(BLUEPRINT / "roles")
    assert args.endswith(str(BLUEPRINT / "playbooks" / "k3s.yml"))


def test_script_env_roles_override_comes_first(tmp_path: Path) -> None:
    """An env roles/ directory is searched before the blueprint's."""
    env_dir = tmp_path / "env"
    (env_dir / "roles").mkdir(parents=True)
    roles_path, _ = _run_script(tmp_path, blueprint_dir=BLUEPRINT, config_dir=env_dir)

    assert roles_path == f"{env_dir / 'roles'}:{BLUEPRINT / 'roles'}"


def test_script_runs_without_config_dir(tmp_path: Path) -> None:
    """INFRAFOUNDRY_CONFIG_DIR is optional now."""
    roles_path, _ = _run_script(tmp_path, blueprint_dir=BLUEPRINT)

    assert roles_path == str(BLUEPRINT / "roles")


def test_script_on_jumphost_ignores_override(tmp_path: Path) -> None:
    """On a jumphost the env roles/ is not there, so only the blueprint roles are used."""
    env_dir = tmp_path / "env"
    (env_dir / "roles").mkdir(parents=True)
    roles_path, _ = _run_script(
        tmp_path, blueprint_dir=BLUEPRINT, config_dir=env_dir, jumphost=True
    )

    assert roles_path == str(BLUEPRINT / "roles")


def test_script_resolves_blueprint_root_without_env_var(tmp_path: Path) -> None:
    """The fallback BLUEPRINT_DIR is the blueprint root, not scripts/."""
    roles_path, args = _run_script(tmp_path)

    assert roles_path == str(BLUEPRINT / "roles")
    assert args.endswith(str(BLUEPRINT / "playbooks" / "k3s.yml"))


@pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="ansible not installed")
def test_real_ansible_prefers_env_override_over_blueprint_roles(tmp_path: Path) -> None:
    """With the playbook in playbooks/, an override listed first wins in real Ansible."""
    override = tmp_path / "ovr"
    (override / "k3s-server" / "tasks").mkdir(parents=True)
    (override / "k3s-server" / "tasks" / "main.yml").write_text(
        "---\n- name: override marker task\n  ansible.builtin.debug:\n    msg: hi\n"
    )
    inventory = tmp_path / "inv.yml"
    inventory.write_text(
        "all:\n  children:\n    k3s_control:\n      hosts:\n        ctl: {}\n"
        "    k3s_workers:\n      hosts: {}\n"
    )
    playbook = BLUEPRINT / "playbooks" / "k3s.yml"

    def list_tasks(roles_path: str) -> str:
        result = subprocess.run(
            ["ansible-playbook", "-i", str(inventory), str(playbook), "--list-tasks"],
            env={**os.environ, "ANSIBLE_ROLES_PATH": roles_path},
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout

    assert "override marker task" in list_tasks(f"{override}:{BLUEPRINT / 'roles'}")
    assert "override marker task" not in list_tasks(str(BLUEPRINT / "roles"))


def test_blueprint_ships_roles_and_playbook_layout() -> None:
    """Roles live in the blueprint; the playbook sits in playbooks/, away from roles/."""
    assert not list(BLUEPRINT.glob("playbook*.yml"))
    assert not (BLUEPRINT / "playbooks" / "roles").exists()
    for role in ("k3s-server", "k3s-agent", "k3s-dns", "k3s-bootstrap"):
        assert (BLUEPRINT / "roles" / role / "tasks" / "main.yml").is_file()
        assert not (REPO_ROOT / "example-config" / "roles" / role).exists()
    assert (BLUEPRINT / "playbooks" / "k3s-dns.yml").is_file()
    assert (BLUEPRINT / "playbooks" / "k3s-bootstrap.yml").is_file()


def test_playbook_and_role_files_are_valid_yaml() -> None:
    """The playbook and every role YAML file parse."""
    files = [BLUEPRINT / "playbooks" / "k3s.yml", *(BLUEPRINT / "roles").rglob("*.yml")]
    assert len(files) > 1
    for path in files:
        assert yaml.safe_load(path.read_text(encoding="utf-8")) is not None, path


_STATEFUL_SSH = """#!/bin/sh
n=$(cat "$RECORD_DIR/ssh_count" 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" > "$RECORD_DIR/ssh_count"
if [ "$n" -le "$SSH_FAIL_TIMES" ]; then
    echo "$SSH_FAIL_MSG" >&2
    exit 255
fi
exit 0
"""


def _run_script_with_failing_ssh(
    tmp_path: Path, *, fail_times: int, fail_msg: str
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run the OCI script with an ssh stub that fails `fail_times` times, then succeeds."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = tmp_path / "record"
    record.mkdir()
    stubs = {
        "ssh": _STATEFUL_SSH,
        "ssh-add": "#!/bin/sh\necho key\n",
        "sleep": '#!/bin/sh\necho x >> "$RECORD_DIR/sleeps"\n',
        "ansible-playbook": _FAKE_ANSIBLE,
    }
    for name, body in stubs.items():
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "RECORD_DIR": str(record),
        "SSH_FAIL_TIMES": str(fail_times),
        "SSH_FAIL_MSG": fail_msg,
        "INFRAFOUNDRY_VAR_control_name": "ctl",
        "INFRAFOUNDRY_VAR_cluster_name": "c",
        "INFRAFOUNDRY_VAR_ssh_public_key": (
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest test@example.com"
        ),
        "INFRAFOUNDRY_VAR_tailnet": "example.net",
        "INFRAFOUNDRY_VAR_kubeconfig_local_path": str(tmp_path / "kube.yaml"),
        "INFRAFOUNDRY_VAR_ssh_known_hosts": (
            "ctl,ctl.example.net ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest;"
            "w1,w1.example.net ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest"
        ),
        "INFRAFOUNDRY_PACKAGE_VARS": json.dumps({"workers": [{"name": "w1"}]}),
    }
    result = subprocess.run(
        ["bash", str(OCI_SCRIPT)], env=env, capture_output=True, text=True, check=False
    )
    return result, record


def test_script_waits_for_control_node_to_resolve(tmp_path: Path) -> None:
    """A name that does not resolve yet (node not on the tailnet) keeps waiting."""
    result, record = _run_script_with_failing_ssh(
        tmp_path,
        fail_times=3,
        fail_msg="ssh: Could not resolve hostname ctl.example.net: Name or service not known",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (record / "args").exists()
    assert len((record / "sleeps").read_text().splitlines()) == 3


@pytest.mark.parametrize(
    "message",
    [
        "ubuntu@ctl.example.net: Permission denied (publickey).",
        "Host key verification failed.",
        "Received disconnect: Too many authentication failures",
    ],
)
def test_script_fails_fast_on_auth_and_host_key_errors(tmp_path: Path, message: str) -> None:
    """Authentication and host-key errors do not retry and never reach ansible."""
    result, record = _run_script_with_failing_ssh(tmp_path, fail_times=1000, fail_msg=message)

    assert result.returncode != 0
    assert message in result.stderr
    assert not (record / "args").exists()
    assert not (record / "sleeps").exists()
    assert (record / "ssh_count").read_text().strip() == "1"


def test_script_fails_fast_when_tailnet_policy_denies_ssh(tmp_path: Path) -> None:
    """A Tailscale SSH policy denial does not retry and points at the ssh rules."""
    message = (
        "tailscale: tailnet policy does not permit you to SSH to this node\n"
        "Connection closed by 100.64.0.1 port 22"
    )
    result, record = _run_script_with_failing_ssh(tmp_path, fail_times=1000, fail_msg=message)

    assert result.returncode != 0
    assert "tailnet policy" in result.stderr
    assert "ssh rules" in result.stderr
    assert re.search(r"\bctl\.example\.net\b", result.stderr)
    assert "tailnet policy does not permit" in result.stderr
    assert not (record / "args").exists()
    assert not (record / "sleeps").exists()
    assert (record / "ssh_count").read_text().strip() == "1"


def test_oci_k3s_cluster_default_subnets_fit_the_default_vcn(loader: PackageLoader) -> None:
    """The default subnets sit inside the default VCN and do not overlap (#1521)."""
    import ipaddress

    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="oci", env_name="oci-k3s"
    )
    vcn = next(r for r in resources if r.type == "vcn")
    vcn_net = ipaddress.IPv4Network(vcn.config["cidr_block"])
    subnet_nets = [
        ipaddress.IPv4Network(r.config["cidr_block"]) for r in resources if r.type == "subnet"
    ]
    assert len(subnet_nets) == 2
    assert all(net.subnet_of(vcn_net) for net in subnet_nets)
    assert not subnet_nets[0].overlaps(subnet_nets[1])
