"""Unit tests for Kubernetes template rendering."""

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.kubernetes import KubernetesProvider


@pytest.fixture
def provider(tmp_path):
    """Create a KubernetesProvider for template testing."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    p = KubernetesProvider(config_dir, output_dir)
    p.set_environment("test")
    return p


class TestProviderTemplate:
    """Tests for provider.tf.j2 template."""

    def test_renders_kubernetes_provider_block(self, provider):
        """Test provider template renders Kubernetes provider configuration."""
        content = provider.render_template(
            "kubernetes/provider.tf.j2", {"has_helm_releases": False}
        )
        assert 'provider "kubernetes"' in content
        assert "hashicorp/kubernetes" in content
        assert "~> 2.23" in content

    def test_includes_helm_provider_when_releases_exist(self, provider):
        """Test provider template includes Helm when releases exist."""
        content = provider.render_template("kubernetes/provider.tf.j2", {"has_helm_releases": True})
        assert "hashicorp/helm" in content
        assert 'provider "helm"' in content
        assert "~> 2.12" in content

    def test_excludes_helm_provider_without_releases(self, provider):
        """Test provider template excludes Helm when no releases."""
        content = provider.render_template(
            "kubernetes/provider.tf.j2", {"has_helm_releases": False}
        )
        assert "hashicorp/helm" not in content
        assert 'provider "helm"' not in content


class TestSecretsTemplate:
    """Tests for secrets.tf.j2 template."""

    def test_renders_opaque_secret(self, provider):
        """Test rendering an Opaque secret."""
        secrets = [
            ResourceConfig(
                name="my-secret",
                type="secrets",
                provider="kubernetes",
                config={
                    "namespace": "default",
                    "type": "Opaque",
                    "data": {"key": "dmFsdWU="},
                },
            )
        ]
        content = provider.render_template("kubernetes/secrets.tf.j2", {"secrets": secrets})
        assert 'resource "kubernetes_secret" "my_secret"' in content
        assert 'type = "Opaque"' in content
        assert '"key" = "dmFsdWU="' in content

    def test_renders_tls_secret(self, provider):
        """Test rendering a TLS secret."""
        secrets = [
            ResourceConfig(
                name="tls-secret",
                type="secrets",
                provider="kubernetes",
                config={
                    "namespace": "default",
                    "type": "kubernetes.io/tls",
                    "data": {"tls.crt": "Y2VydA==", "tls.key": "a2V5"},
                },
            )
        ]
        content = provider.render_template("kubernetes/secrets.tf.j2", {"secrets": secrets})
        assert 'type = "kubernetes.io/tls"' in content

    def test_renders_secret_with_labels(self, provider):
        """Test secret with labels and annotations."""
        secrets = [
            ResourceConfig(
                name="labeled-secret",
                type="secrets",
                provider="kubernetes",
                config={
                    "labels": {"app": "myapp"},
                    "annotations": {"managed-by": "infrafoundry"},
                    "data": {"key": "value"},
                },
            )
        ]
        content = provider.render_template("kubernetes/secrets.tf.j2", {"secrets": secrets})
        assert '"app" = "myapp"' in content
        assert '"managed-by" = "infrafoundry"' in content


class TestIngressTemplate:
    """Tests for ingress.tf.j2 template."""

    def test_renders_basic_ingress(self, provider):
        """Test basic ingress rendering."""
        ingresses = [
            ResourceConfig(
                name="web-ingress",
                type="ingresses",
                provider="kubernetes",
                config={
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
                                            "name": "web-svc",
                                            "port": {"number": 80},
                                        }
                                    },
                                }
                            ],
                        }
                    ],
                },
            )
        ]
        content = provider.render_template("kubernetes/ingress.tf.j2", {"ingresses": ingresses})
        assert 'resource "kubernetes_ingress_v1" "web_ingress"' in content
        assert 'ingress_class_name = "nginx"' in content
        assert 'host = "example.com"' in content
        assert 'path      = "/"' in content
        assert "number = 80" in content

    def test_renders_ingress_with_tls(self, provider):
        """Test ingress with TLS configuration."""
        ingresses = [
            ResourceConfig(
                name="tls-ingress",
                type="ingresses",
                provider="kubernetes",
                config={
                    "tls": [{"hosts": ["example.com"], "secret_name": "tls-secret"}],
                    "rules": [
                        {
                            "host": "example.com",
                            "paths": [
                                {
                                    "path": "/",
                                    "backend": {"service": {"name": "svc", "port": {"number": 80}}},
                                }
                            ],
                        }
                    ],
                },
            )
        ]
        content = provider.render_template("kubernetes/ingress.tf.j2", {"ingresses": ingresses})
        assert "tls {" in content
        assert 'secret_name = "tls-secret"' in content


class TestPVCTemplate:
    """Tests for pvc.tf.j2 template."""

    def test_renders_basic_pvc(self, provider):
        """Test basic PVC rendering."""
        pvcs = [
            ResourceConfig(
                name="data-pvc",
                type="persistentvolumeclaims",
                provider="kubernetes",
                config={
                    "storage": "5Gi",
                    "access_modes": ["ReadWriteOnce"],
                },
            )
        ]
        content = provider.render_template("kubernetes/pvc.tf.j2", {"pvcs": pvcs})
        assert 'resource "kubernetes_persistent_volume_claim" "data_pvc"' in content
        assert 'storage = "5Gi"' in content
        assert '"ReadWriteOnce"' in content

    def test_renders_pvc_with_storage_class(self, provider):
        """Test PVC with storage class."""
        pvcs = [
            ResourceConfig(
                name="fast-pvc",
                type="persistentvolumeclaims",
                provider="kubernetes",
                config={
                    "storage": "10Gi",
                    "storage_class_name": "fast-ssd",
                },
            )
        ]
        content = provider.render_template("kubernetes/pvc.tf.j2", {"pvcs": pvcs})
        assert 'storage_class_name = "fast-ssd"' in content


class TestJobTemplate:
    """Tests for jobs.tf.j2 template."""

    def test_renders_basic_job(self, provider):
        """Test basic job rendering."""
        jobs = [
            ResourceConfig(
                name="init-job",
                type="jobs",
                provider="kubernetes",
                config={
                    "containers": [
                        {"name": "init", "image": "busybox", "command": ["echo", "hello"]}
                    ],
                },
            )
        ]
        content = provider.render_template("kubernetes/jobs.tf.j2", {"jobs": jobs})
        assert 'resource "kubernetes_job" "init_job"' in content
        assert 'restart_policy = "Never"' in content
        assert 'image = "busybox"' in content

    def test_renders_job_with_backoff_limit(self, provider):
        """Test job with backoff limit."""
        jobs = [
            ResourceConfig(
                name="retry-job",
                type="jobs",
                provider="kubernetes",
                config={
                    "backoff_limit": 5,
                    "containers": [{"name": "task", "image": "app:latest"}],
                },
            )
        ]
        content = provider.render_template("kubernetes/jobs.tf.j2", {"jobs": jobs})
        assert "backoff_limit = 5" in content


class TestCronJobTemplate:
    """Tests for cronjobs.tf.j2 template."""

    def test_renders_basic_cronjob(self, provider):
        """Test basic cron job rendering."""
        cronjobs = [
            ResourceConfig(
                name="hourly-task",
                type="cronjobs",
                provider="kubernetes",
                config={
                    "schedule": "0 * * * *",
                    "containers": [{"name": "task", "image": "task:latest"}],
                },
            )
        ]
        content = provider.render_template("kubernetes/cronjobs.tf.j2", {"cronjobs": cronjobs})
        assert 'resource "kubernetes_cron_job_v1" "hourly_task"' in content
        assert 'schedule = "0 * * * *"' in content

    def test_renders_cronjob_with_concurrency_policy(self, provider):
        """Test cron job with concurrency policy."""
        cronjobs = [
            ResourceConfig(
                name="serial-task",
                type="cronjobs",
                provider="kubernetes",
                config={
                    "schedule": "*/5 * * * *",
                    "concurrency_policy": "Forbid",
                    "containers": [{"name": "task", "image": "task:latest"}],
                },
            )
        ]
        content = provider.render_template("kubernetes/cronjobs.tf.j2", {"cronjobs": cronjobs})
        assert 'concurrency_policy = "Forbid"' in content


class TestRBACTemplate:
    """Tests for rbac.tf.j2 template."""

    def test_renders_service_account(self, provider):
        """Test service account rendering."""
        content = provider.render_template(
            "kubernetes/rbac.tf.j2",
            {
                "serviceaccounts": [
                    ResourceConfig(
                        name="app-sa",
                        type="serviceaccounts",
                        provider="kubernetes",
                        config={"namespace": "default"},
                    )
                ],
                "roles": [],
                "rolebindings": [],
                "clusterroles": [],
                "clusterrolebindings": [],
            },
        )
        assert 'resource "kubernetes_service_account" "app_sa"' in content

    def test_renders_role_with_rules(self, provider):
        """Test role rendering with rules."""
        content = provider.render_template(
            "kubernetes/rbac.tf.j2",
            {
                "serviceaccounts": [],
                "roles": [
                    ResourceConfig(
                        name="pod-reader",
                        type="roles",
                        provider="kubernetes",
                        config={
                            "namespace": "default",
                            "rules": [
                                {
                                    "api_groups": [""],
                                    "resources": ["pods"],
                                    "verbs": ["get", "list", "watch"],
                                }
                            ],
                        },
                    )
                ],
                "rolebindings": [],
                "clusterroles": [],
                "clusterrolebindings": [],
            },
        )
        assert 'resource "kubernetes_role" "pod_reader"' in content
        assert 'api_groups = [""]' in content
        assert 'resources  = ["pods"]' in content
        assert 'verbs      = ["get", "list", "watch"]' in content

    def test_renders_role_binding(self, provider):
        """Test role binding rendering."""
        content = provider.render_template(
            "kubernetes/rbac.tf.j2",
            {
                "serviceaccounts": [],
                "roles": [],
                "rolebindings": [
                    ResourceConfig(
                        name="read-pods-binding",
                        type="rolebindings",
                        provider="kubernetes",
                        config={
                            "namespace": "default",
                            "role_ref": {"kind": "Role", "name": "pod-reader"},
                            "subjects": [{"kind": "ServiceAccount", "name": "app-sa"}],
                        },
                    )
                ],
                "clusterroles": [],
                "clusterrolebindings": [],
            },
        )
        assert 'resource "kubernetes_role_binding" "read_pods_binding"' in content
        assert "role_ref {" in content
        assert 'kind      = "Role"' in content
        assert 'name      = "pod-reader"' in content
        assert 'kind      = "ServiceAccount"' in content

    def test_renders_cluster_role(self, provider):
        """Test cluster role rendering."""
        content = provider.render_template(
            "kubernetes/rbac.tf.j2",
            {
                "serviceaccounts": [],
                "roles": [],
                "rolebindings": [],
                "clusterroles": [
                    ResourceConfig(
                        name="node-reader",
                        type="clusterroles",
                        provider="kubernetes",
                        config={
                            "rules": [
                                {
                                    "api_groups": [""],
                                    "resources": ["nodes"],
                                    "verbs": ["get", "list"],
                                }
                            ],
                        },
                    )
                ],
                "clusterrolebindings": [],
            },
        )
        assert 'resource "kubernetes_cluster_role" "node_reader"' in content


class TestHelmReleaseTemplate:
    """Tests for helm_releases.tf.j2 template."""

    def test_renders_basic_helm_release(self, provider):
        """Test basic helm release rendering."""
        releases = [
            ResourceConfig(
                name="nginx-ingress",
                type="helm_releases",
                provider="kubernetes",
                config={
                    "chart": "ingress-nginx",
                    "repository": "https://kubernetes.github.io/ingress-nginx",
                    "version": "4.8.3",
                    "namespace": "ingress",
                },
            )
        ]
        content = provider.render_template(
            "kubernetes/helm_releases.tf.j2", {"helm_releases": releases}
        )
        assert 'resource "helm_release" "nginx_ingress"' in content
        assert 'chart      = "ingress-nginx"' in content
        assert 'repository = "https://kubernetes.github.io/ingress-nginx"' in content
        assert 'version    = "4.8.3"' in content

    def test_renders_helm_release_with_values(self, provider):
        """Test helm release with values."""
        releases = [
            ResourceConfig(
                name="cert-manager",
                type="helm_releases",
                provider="kubernetes",
                config={
                    "chart": "cert-manager",
                    "repository": "https://charts.jetstack.io",
                    "namespace": "cert-manager",
                    "create_namespace": True,
                    "values": {"installCRDs": True, "replicaCount": 2},
                },
            )
        ]
        content = provider.render_template(
            "kubernetes/helm_releases.tf.j2", {"helm_releases": releases}
        )
        assert "create_namespace = true" in content
        assert "values = [<<-EOT" in content
        assert "installCRDs:" in content

    def test_renders_helm_release_with_set(self, provider):
        """Test helm release with set values."""
        releases = [
            ResourceConfig(
                name="prometheus",
                type="helm_releases",
                provider="kubernetes",
                config={
                    "chart": "prometheus",
                    "repository": "https://prometheus-community.github.io/helm-charts",
                    "set": [
                        {"name": "server.replicaCount", "value": "2"},
                        {"name": "alertmanager.enabled", "value": "false"},
                    ],
                },
            )
        ]
        content = provider.render_template(
            "kubernetes/helm_releases.tf.j2", {"helm_releases": releases}
        )
        assert "set {" in content
        assert 'name  = "server.replicaCount"' in content
        assert 'value = "2"' in content


class TestManifestsTemplate:
    """Tests for manifests.tf.j2 template."""

    def test_renders_basic_manifest(self, provider):
        """Test basic custom manifest rendering."""
        manifests = [
            ResourceConfig(
                name="my-custom-resource",
                type="manifests",
                provider="kubernetes",
                config={
                    "manifest": {
                        "apiVersion": "example.com/v1",
                        "kind": "CustomResource",
                        "metadata": {
                            "name": "my-resource",
                            "namespace": "default",
                        },
                        "spec": {
                            "key": "value",
                        },
                    },
                },
            )
        ]
        content = provider.render_template("kubernetes/manifests.tf.j2", {"manifests": manifests})
        assert 'resource "kubernetes_manifest" "my_custom_resource"' in content
        assert '"apiVersion" = "example.com/v1"' in content
        assert '"kind"       = "CustomResource"' in content
        assert '"name"      = "my-resource"' in content
        assert '"namespace" = "default"' in content

    def test_renders_tailscale_connector(self, provider):
        """Test Tailscale Connector CRD rendering."""
        manifests = [
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
            )
        ]
        content = provider.render_template("kubernetes/manifests.tf.j2", {"manifests": manifests})
        assert 'resource "kubernetes_manifest" "oci_subnet_router"' in content
        assert '"apiVersion" = "tailscale.com/v1alpha1"' in content
        assert '"kind"       = "Connector"' in content
        assert "hostname:" in content
        assert "oci-k3s-subnet-router" in content
        assert "10.0.0.0/16" in content

    def test_renders_manifest_with_labels(self, provider):
        """Test manifest with labels and annotations."""
        manifests = [
            ResourceConfig(
                name="labeled-resource",
                type="manifests",
                provider="kubernetes",
                config={
                    "manifest": {
                        "apiVersion": "example.com/v1",
                        "kind": "CustomResource",
                        "metadata": {
                            "name": "labeled",
                            "labels": {"app": "myapp", "env": "prod"},
                            "annotations": {"managed-by": "infrafoundry"},
                        },
                        "spec": {"enabled": True},
                    },
                },
            )
        ]
        content = provider.render_template("kubernetes/manifests.tf.j2", {"manifests": manifests})
        assert '"app" = "myapp"' in content
        assert '"env" = "prod"' in content
        assert '"managed-by" = "infrafoundry"' in content

    def test_renders_manifest_without_namespace(self, provider):
        """Test cluster-scoped manifest without namespace."""
        manifests = [
            ResourceConfig(
                name="cluster-resource",
                type="manifests",
                provider="kubernetes",
                config={
                    "manifest": {
                        "apiVersion": "example.com/v1",
                        "kind": "ClusterResource",
                        "metadata": {
                            "name": "global-config",
                        },
                        "spec": {"global": True},
                    },
                },
            )
        ]
        content = provider.render_template("kubernetes/manifests.tf.j2", {"manifests": manifests})
        assert '"name"      = "global-config"' in content
        # Should not have namespace line
        assert '"namespace"' not in content
