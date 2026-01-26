"""Unit tests for Kubernetes provider."""

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.kubernetes import KubernetesProvider


@pytest.fixture
def tmp_dirs(tmp_path):
    """Create temporary config and output directories."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return config_dir, output_dir


@pytest.fixture
def provider(tmp_dirs):
    """Create a KubernetesProvider instance."""
    config_dir, output_dir = tmp_dirs
    return KubernetesProvider(config_dir, output_dir)


def test_provider_init(provider):
    """Test provider initializes with correct name."""
    assert provider.name == "kubernetes"


def test_get_resource_types(provider):
    """Test supported resource types."""
    types = provider.get_resource_types()
    # Core resources
    assert "namespaces" in types
    assert "configmaps" in types
    assert "secrets" in types
    assert "persistentvolumeclaims" in types
    # RBAC
    assert "serviceaccounts" in types
    assert "roles" in types
    assert "rolebindings" in types
    assert "clusterroles" in types
    assert "clusterrolebindings" in types
    # Workloads
    assert "deployments" in types
    assert "services" in types
    assert "ingresses" in types
    assert "jobs" in types
    assert "cronjobs" in types
    # Helm
    assert "helm_releases" in types
    # Custom manifests
    assert "manifests" in types


def test_get_dependencies(provider):
    """Test resource dependency graph."""
    deps = provider.get_dependencies()
    # Namespaces are base
    assert deps["namespaces"] == []
    # Core resources depend on namespaces
    assert "namespaces" in deps["configmaps"]
    assert "namespaces" in deps["secrets"]
    assert "namespaces" in deps["persistentvolumeclaims"]
    # RBAC
    assert deps["clusterroles"] == []
    assert "namespaces" in deps["serviceaccounts"]
    assert "serviceaccounts" in deps["rolebindings"]
    assert "roles" in deps["rolebindings"]
    # Workloads
    assert "configmaps" in deps["deployments"]
    assert "secrets" in deps["deployments"]
    assert "deployments" in deps["services"]
    assert "services" in deps["ingresses"]
    # Manifests depend on namespaces and helm (for CRDs)
    assert "namespaces" in deps["manifests"]
    assert "helm_releases" in deps["manifests"]


def test_validate_config_valid(provider):
    """Test config validation with required fields."""
    assert provider.validate_config({"name": "test"}) is True


def test_validate_config_invalid(provider):
    """Test config validation with missing fields."""
    assert provider.validate_config({}) is False


def test_generate_terraform_creates_files(provider, tmp_dirs):
    """Test that generate_terraform creates expected files."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="my-namespace",
            type="namespaces",
            provider="kubernetes",
            config={},
        ),
        ResourceConfig(
            name="my-deployment",
            type="deployments",
            provider="kubernetes",
            config={
                "replicas": 1,
                "containers": [{"name": "app", "image": "nginx:latest"}],
            },
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "kubernetes"
    assert (terraform_dir / "provider.tf").exists()
    assert (terraform_dir / "variables.tf").exists()
    assert (terraform_dir / "namespaces.tf").exists()
    assert (terraform_dir / "deployments.tf").exists()
    assert (terraform_dir / "outputs.tf").exists()


def test_generate_terraform_secrets(provider, tmp_dirs):
    """Test secrets terraform generation."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="db-credentials",
            type="secrets",
            provider="kubernetes",
            config={
                "namespace": "default",
                "type": "Opaque",
                "data": {"password": "c2VjcmV0"},
            },
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "kubernetes"
    assert (terraform_dir / "secrets.tf").exists()
    content = (terraform_dir / "secrets.tf").read_text()
    assert "kubernetes_secret" in content
    assert "db_credentials" in content
    assert "Opaque" in content


def test_generate_terraform_ingress(provider, tmp_dirs):
    """Test ingress terraform generation."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="my-ingress",
            type="ingresses",
            provider="kubernetes",
            config={
                "namespace": "default",
                "ingress_class_name": "nginx",
                "rules": [
                    {
                        "host": "example.com",
                        "paths": [
                            {
                                "path": "/",
                                "path_type": "Prefix",
                                "backend": {
                                    "service": {
                                        "name": "my-service",
                                        "port": {"number": 80},
                                    }
                                },
                            }
                        ],
                    }
                ],
            },
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "kubernetes"
    assert (terraform_dir / "ingress.tf").exists()
    content = (terraform_dir / "ingress.tf").read_text()
    assert "kubernetes_ingress_v1" in content
    assert "nginx" in content
    assert "example.com" in content


def test_generate_terraform_pvc(provider, tmp_dirs):
    """Test persistent volume claim terraform generation."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="my-pvc",
            type="persistentvolumeclaims",
            provider="kubernetes",
            config={
                "namespace": "default",
                "access_modes": ["ReadWriteOnce"],
                "storage": "10Gi",
                "storage_class_name": "standard",
            },
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "kubernetes"
    assert (terraform_dir / "pvc.tf").exists()
    content = (terraform_dir / "pvc.tf").read_text()
    assert "kubernetes_persistent_volume_claim" in content
    assert "10Gi" in content
    assert "standard" in content


def test_generate_terraform_job(provider, tmp_dirs):
    """Test job terraform generation."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="migration-job",
            type="jobs",
            provider="kubernetes",
            config={
                "namespace": "default",
                "backoff_limit": 3,
                "containers": [
                    {"name": "migrate", "image": "myapp:latest", "command": ["./migrate"]}
                ],
            },
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "kubernetes"
    assert (terraform_dir / "jobs.tf").exists()
    content = (terraform_dir / "jobs.tf").read_text()
    assert "kubernetes_job" in content
    assert "migration_job" in content
    assert "backoff_limit = 3" in content


def test_generate_terraform_cronjob(provider, tmp_dirs):
    """Test cron job terraform generation."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="cleanup-cron",
            type="cronjobs",
            provider="kubernetes",
            config={
                "namespace": "default",
                "schedule": "0 2 * * *",
                "containers": [{"name": "cleanup", "image": "myapp:latest"}],
            },
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "kubernetes"
    assert (terraform_dir / "cronjobs.tf").exists()
    content = (terraform_dir / "cronjobs.tf").read_text()
    assert "kubernetes_cron_job_v1" in content
    assert "0 2 * * *" in content


def test_generate_terraform_rbac(provider, tmp_dirs):
    """Test RBAC terraform generation."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="my-sa",
            type="serviceaccounts",
            provider="kubernetes",
            config={"namespace": "default"},
        ),
        ResourceConfig(
            name="my-role",
            type="roles",
            provider="kubernetes",
            config={
                "namespace": "default",
                "rules": [
                    {
                        "api_groups": [""],
                        "resources": ["pods"],
                        "verbs": ["get", "list"],
                    }
                ],
            },
        ),
        ResourceConfig(
            name="my-binding",
            type="rolebindings",
            provider="kubernetes",
            config={
                "namespace": "default",
                "role_ref": {"kind": "Role", "name": "my-role"},
                "subjects": [{"kind": "ServiceAccount", "name": "my-sa"}],
            },
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "kubernetes"
    assert (terraform_dir / "rbac.tf").exists()
    content = (terraform_dir / "rbac.tf").read_text()
    assert "kubernetes_service_account" in content
    assert "kubernetes_role" in content
    assert "kubernetes_role_binding" in content


def test_generate_terraform_helm_release(provider, tmp_dirs):
    """Test Helm release terraform generation."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="ingress-nginx",
            type="helm_releases",
            provider="kubernetes",
            config={
                "chart": "ingress-nginx",
                "repository": "https://kubernetes.github.io/ingress-nginx",
                "version": "4.8.3",
                "namespace": "ingress-nginx",
                "create_namespace": True,
                "values": {"controller": {"replicaCount": 2}},
            },
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "kubernetes"
    # Check provider includes helm
    provider_content = (terraform_dir / "provider.tf").read_text()
    assert "hashicorp/helm" in provider_content
    assert 'provider "helm"' in provider_content

    # Check helm release file
    assert (terraform_dir / "helm_releases.tf").exists()
    helm_content = (terraform_dir / "helm_releases.tf").read_text()
    assert "helm_release" in helm_content
    assert "ingress-nginx" in helm_content
    assert "4.8.3" in helm_content


def test_generate_terraform_no_helm_provider_without_releases(provider, tmp_dirs):
    """Test that Helm provider is not included when no helm releases."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="my-namespace",
            type="namespaces",
            provider="kubernetes",
            config={},
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "kubernetes"
    provider_content = (terraform_dir / "provider.tf").read_text()
    assert "hashicorp/helm" not in provider_content
    assert 'provider "helm"' not in provider_content


def test_generate_terraform_cluster_role(provider, tmp_dirs):
    """Test cluster role terraform generation."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="cluster-admin",
            type="clusterroles",
            provider="kubernetes",
            config={
                "rules": [
                    {
                        "api_groups": ["*"],
                        "resources": ["*"],
                        "verbs": ["*"],
                    }
                ],
            },
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "kubernetes"
    assert (terraform_dir / "rbac.tf").exists()
    content = (terraform_dir / "rbac.tf").read_text()
    assert "kubernetes_cluster_role" in content
    assert "cluster_admin" in content


def test_generate_terraform_manifest(provider, tmp_dirs):
    """Test custom manifest (CRD) terraform generation."""
    _config_dir, output_dir = tmp_dirs
    provider.set_environment("test")

    resources = [
        ResourceConfig(
            name="oci-subnet-router",
            type="manifests",
            provider="kubernetes",
            config={
                "manifest": {
                    "apiVersion": "tailscale.com/v1alpha1",
                    "kind": "Connector",
                    "metadata": {
                        "name": "oci-subnet-router",
                        "namespace": "tailscale",
                    },
                    "spec": {
                        "hostname": "oci-k3s-subnet-router",
                        "subnetRouter": {
                            "advertiseRoutes": ["10.0.0.0/16"],
                        },
                        "tags": ["tag:k8s"],
                    },
                },
            },
        ),
    ]

    provider.generate_terraform(resources)

    terraform_dir = output_dir / "test" / "terraform" / "kubernetes"
    assert (terraform_dir / "manifests.tf").exists()
    content = (terraform_dir / "manifests.tf").read_text()
    assert "kubernetes_manifest" in content
    assert "oci_subnet_router" in content
    assert "tailscale.com/v1alpha1" in content
    assert "Connector" in content
