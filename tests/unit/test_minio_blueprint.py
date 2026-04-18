"""Integration test for the minio blueprint conversion.

Loads the real example-config minio package via PackageLoader and asserts that
the merged configuration (blueprint defaults + package overrides) produces the
expected kubernetes resources (operator + tenant namespace + credentials
secret + tenant helm release + NodePort service manifest).

This is the regression guard for issue #619 and follows the pattern
established by ``test_aiqum_blueprint.py`` (see #502, #511).

The test depends only on files checked into this repository:
  - blueprints/minio/                          (the blueprint)
  - example-config/envs/dev/proxmox/minio/     (the example consumer)

It does NOT depend on the private endavis-infra/ config repo.
"""

import textwrap
from pathlib import Path

import pytest

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ENVS = REPO_ROOT / "example-config" / "envs"
PACKAGE_DIR = EXAMPLE_ENVS / "dev" / "proxmox" / "minio"


@pytest.fixture
def loader() -> PackageLoader:
    """PackageLoader pointed at the real example-config envs/ directory."""
    resolver = BlueprintResolver(EXAMPLE_ENVS)
    return PackageLoader(EXAMPLE_ENVS, blueprint_resolver=resolver)


def test_minio_example_package_loads_blueprint(loader: PackageLoader) -> None:
    """The minio example package loads via the blueprint resolver and merges
    blueprint defaults with per-instance overrides."""
    _resources, _events, variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    # --- Per-instance overrides come from the package manifest ---
    assert variables["tenant_name"] == "example"
    assert variables["minio_root_password"] == "CHANGE_ME"
    assert variables["tenant_servers"] == 2
    assert variables["tenant_volume_size"] == "5Gi"

    # --- Blueprint defaults flow through unchanged ---
    assert variables["operator_namespace"] == "minio-operator"
    assert variables["operator_chart_version"] == "6.0.4"
    assert variables["tenant_namespace"] == "minio-tenant"
    assert variables["tenant_volumes_per_server"] == 1
    assert variables["tenant_storage_class"] == "local-path"
    assert variables["minio_root_user"] == "minioadmin"
    assert variables["minio_cpu_request"] == "250m"
    assert variables["minio_memory_request"] == "512Mi"
    assert variables["minio_cpu_limit"] == "1"
    assert variables["minio_memory_limit"] == "2Gi"
    assert variables["api_node_port"] == 30900
    assert variables["console_node_port"] == 30909


def test_minio_example_renders_all_kubernetes_resources(loader: PackageLoader) -> None:
    """The merged config produces exactly five kubernetes resources: an
    operator Helm release, a tenant namespace, a credentials secret, a tenant
    Helm release, and a NodePort Service manifest. All outer names templated
    on tenant_name where applicable (multi-instance safety)."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    assert len(resources) == 5
    assert {r.provider for r in resources} == {"kubernetes"}

    # Count resources by type
    types = [r.type for r in resources]
    assert types.count("helm_releases") == 2
    assert types.count("namespaces") == 1
    assert types.count("secrets") == 1
    assert types.count("manifests") == 1

    # Outer names — operator is literal, all tenant-scoped names templated on
    # tenant_name ("example" in the example consumer).
    names = {r.name for r in resources}
    assert names == {
        "minio-operator",
        "example-ns",
        "example-env-configuration",
        "example",
        "example-external",
    }


def test_minio_operator_helm_release_config(loader: PackageLoader) -> None:
    """The operator helm_release uses the MinIO chart, creates its own
    namespace, and pulls its version from blueprint defaults."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    operator = next(r for r in resources if r.name == "minio-operator")
    assert operator.type == "helm_releases"
    assert operator.provider == "kubernetes"

    config = operator.config
    assert config["chart"] == "operator"
    assert config["repository"] == "https://operator.min.io"
    assert config["version"] == "6.0.4"
    assert config["namespace"] == "minio-operator"
    assert config["create_namespace"] is True
    assert config["wait"] is True
    assert config["timeout"] == 300


def test_minio_tenant_helm_release_config(loader: PackageLoader) -> None:
    """The tenant helm_release depends on the operator and the credentials
    secret, and its ``set:`` entries reflect the merged variable values."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    tenant = next(r for r in resources if r.type == "helm_releases" and r.name == "example")
    config = tenant.config

    assert config["chart"] == "tenant"
    assert config["repository"] == "https://operator.min.io"
    assert config["version"] == "6.0.4"
    assert config["namespace"] == "minio-tenant"
    assert config["wait"] is True
    assert config["timeout"] == 600

    # depends_on — templated with tenant_name so multi-tenant setups don't
    # collide on the generated Terraform identifier.
    assert config["depends_on"] == [
        "helm_release.minio_operator",
        "kubernetes_secret.example_env_configuration",
    ]

    # Flatten the set: list into a name -> value map for assertion simplicity.
    set_by_name = {entry["name"]: entry["value"] for entry in config["set"]}
    assert set_by_name["tenant.name"] == "example"
    assert set_by_name["tenant.pools[0].name"] == "pool-0"
    # Helm set values are strings even when the input is an integer.
    assert set_by_name["tenant.pools[0].servers"] == "2"
    assert set_by_name["tenant.pools[0].volumesPerServer"] == "1"
    assert set_by_name["tenant.pools[0].size"] == "5Gi"
    assert set_by_name["tenant.pools[0].storageClassName"] == "local-path"
    assert set_by_name["tenant.pools[0].resources.requests.cpu"] == "250m"
    assert set_by_name["tenant.pools[0].resources.requests.memory"] == "512Mi"
    assert set_by_name["tenant.pools[0].resources.limits.cpu"] == "1"
    assert set_by_name["tenant.pools[0].resources.limits.memory"] == "2Gi"
    assert set_by_name["tenant.pools[0].nodeSelector.minio"] == "true"
    assert set_by_name["tenant.configuration.name"] == "example-env-configuration"
    assert set_by_name["tenant.configSecret.name"] == "example-env-configuration"
    assert set_by_name["tenant.configSecret.existingSecret"] == "true"
    assert set_by_name["tenant.certificate.requestAutoCert"] == "false"

    # The nodeSelector entry carries an explicit ``type: string`` so Helm
    # doesn't coerce "true" into a boolean.
    node_selector_entry = next(
        entry for entry in config["set"] if entry["name"] == "tenant.pools[0].nodeSelector.minio"
    )
    assert node_selector_entry.get("type") == "string"


def test_minio_credentials_secret_config(loader: PackageLoader) -> None:
    """The credentials secret lives in the tenant namespace and its
    ``config.env`` string contains both the rendered MINIO_ROOT_USER and
    MINIO_ROOT_PASSWORD env-var exports."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    secret = next(r for r in resources if r.type == "secrets")
    assert secret.name == "example-env-configuration"

    config = secret.config
    assert config["namespace"] == "minio-tenant"

    config_env = config["string_data"]["config.env"]
    assert "MINIO_ROOT_USER=minioadmin" in config_env
    assert "MINIO_ROOT_PASSWORD=CHANGE_ME" in config_env


def test_minio_nodeport_service_manifest(loader: PackageLoader) -> None:
    """The NodePort Service manifest exposes ports 9000 (API) and 9090
    (console) at the blueprint-default NodePorts, and selects pods via the
    standard MinIO tenant label."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    svc_resource = next(r for r in resources if r.type == "manifests")
    assert svc_resource.name == "example-external"

    manifest = svc_resource.config["manifest"]
    assert manifest["apiVersion"] == "v1"
    assert manifest["kind"] == "Service"
    assert manifest["metadata"]["name"] == "example-external"
    assert manifest["metadata"]["namespace"] == "minio-tenant"

    spec = manifest["spec"]
    assert spec["type"] == "NodePort"
    assert spec["selector"] == {"v1.min.io/tenant": "example"}

    ports_by_name = {p["name"]: p for p in spec["ports"]}
    assert ports_by_name["api"]["port"] == 9000
    assert ports_by_name["api"]["targetPort"] == 9000
    assert ports_by_name["api"]["nodePort"] == 30900
    assert ports_by_name["console"]["port"] == 9090
    assert ports_by_name["console"]["targetPort"] == 9090
    assert ports_by_name["console"]["nodePort"] == 30909


def test_minio_blueprint_supports_multiple_instances(tmp_path: Path) -> None:
    """Two packages instantiating the minio blueprint must produce distinct
    tenant-scoped resources without colliding on the framework resource
    identifier.

    Regression guard against #511-style bugs: every tenant-scoped outer
    ``name`` must be templated on ``tenant_name`` so multi-instance use is
    safe. The operator Helm release is intentionally a literal cluster-global
    name and is shared across tenants.
    """
    envs = tmp_path / "envs"
    pkg_a = envs / "test" / "proxmox" / "minio-a"
    pkg_b = envs / "test" / "proxmox" / "minio-b"
    pkg_a.mkdir(parents=True)
    pkg_b.mkdir(parents=True)

    (pkg_a / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: minio-a
            description: "MinIO instance A"
            provider: proxmox
            blueprint: minio
            variables:
              tenant_name: team-a
              tenant_namespace: minio-team-a
              minio_root_password: "pw-a"
              api_node_port: 30910
              console_node_port: 30919
            """
        )
    )
    (pkg_b / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: minio-b
            description: "MinIO instance B"
            provider: proxmox
            blueprint: minio
            variables:
              tenant_name: team-b
              tenant_namespace: minio-team-b
              minio_root_password: "pw-b"
              api_node_port: 30920
              console_node_port: 30929
            """
        )
    )

    resolver = BlueprintResolver(envs)
    loader = PackageLoader(envs, blueprint_resolver=resolver)

    resources_a, _, _ = loader.load_package(pkg_a, provider="proxmox", env_name="test")
    resources_b, _, _ = loader.load_package(pkg_b, provider="proxmox", env_name="test")

    assert len(resources_a) == 5
    assert len(resources_b) == 5

    names_a = {r.name for r in resources_a}
    names_b = {r.name for r in resources_b}

    # Tenant-scoped outer names are templated and therefore distinct.
    assert names_a == {
        "minio-operator",
        "team-a-ns",
        "team-a-env-configuration",
        "team-a",
        "team-a-external",
    }
    assert names_b == {
        "minio-operator",
        "team-b-ns",
        "team-b-env-configuration",
        "team-b",
        "team-b-external",
    }

    # Operator is intentionally shared (same literal name in both packages);
    # all other names are disjoint.
    tenant_names_a = names_a - {"minio-operator"}
    tenant_names_b = names_b - {"minio-operator"}
    assert tenant_names_a.isdisjoint(tenant_names_b)

    # depends_on references in each tenant helm_release point at that tenant's
    # own credentials secret, not the other tenant's.
    tenant_a = next(r for r in resources_a if r.type == "helm_releases" and r.name == "team-a")
    tenant_b = next(r for r in resources_b if r.type == "helm_releases" and r.name == "team-b")
    assert tenant_a.config["depends_on"] == [
        "helm_release.minio_operator",
        "kubernetes_secret.team_a_env_configuration",
    ]
    assert tenant_b.config["depends_on"] == [
        "helm_release.minio_operator",
        "kubernetes_secret.team_b_env_configuration",
    ]
