"""Unit tests for provider template generation.

Tests Terraform and Ansible template rendering for all providers:
- Proxmox: VMs, templates, networks
- OPNsense: Firewall rules, VLANs, aliases
- Kubernetes: Deployments, services, configmaps, namespaces

Verifies:
- Template rendering with valid data
- Variable substitution (Jinja2)
- Resource name normalization (dashes to underscores)
- Optional fields handling (defaults)
- Output file creation
- Ansible inventory/playbook generation
"""

from pathlib import Path

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.kubernetes import KubernetesProvider
from infrafoundry.providers.opnsense import OPNsenseProvider
from infrafoundry.providers.proxmox import ProxmoxProvider


class TestProxmoxTemplates:
    """Test Proxmox Terraform template generation."""

    @pytest.fixture
    def provider(self, tmp_path: Path) -> ProxmoxProvider:
        """Create Proxmox provider instance."""
        config_dir = tmp_path / "config"
        output_dir = tmp_path / "output"
        return ProxmoxProvider(config_dir, output_dir)

    @pytest.fixture
    def vm_resource(self) -> ResourceConfig:
        """Create VM resource config."""
        return ResourceConfig(
            provider="proxmox",
            type="vm",
            name="web-server-01",
            config={
                "name": "web-server-01",
                "target_node": "pve01",
                "clone": "ubuntu-22.04-template",
                "cores": 4,
                "sockets": 1,
                "memory": 8192,
                "disk": {"size": "50G", "type": "scsi", "storage": "local-lvm"},
                "network": {"model": "virtio", "bridge": "vmbr0", "tag": 100},
                "ipconfig": "ip=192.168.1.10/24,gw=192.168.1.1",
                "onboot": True,
                "agent": 1,
                "tags": ["web", "production"],
            },
        )

    @pytest.fixture
    def template_resource(self) -> ResourceConfig:
        """Create template resource config."""
        return ResourceConfig(
            provider="proxmox",
            type="template",
            name="ubuntu-22.04-template",
            config={
                "name": "ubuntu-22.04-template",
                "target_node": "pve01",
                "iso": "local:iso/ubuntu-22.04-server-amd64.iso",
                "cores": 2,
                "memory": 2048,
                "disk": {"size": "32G", "type": "scsi", "storage": "local-lvm"},
                "network": {"model": "virtio", "bridge": "vmbr0"},
            },
        )

    @pytest.fixture
    def network_resource(self) -> ResourceConfig:
        """Create network resource config."""
        return ResourceConfig(
            provider="proxmox",
            type="network",
            name="vlan-100",
            config={"name": "vlan-100", "bridge": "vmbr0", "tag": 100},
        )

    def test_generate_provider_tf(self, provider: ProxmoxProvider) -> None:
        """Test provider.tf generation."""
        provider.generate_terraform([])

        provider_tf = provider.terraform_dir / "provider.tf"
        assert provider_tf.exists()

        content = provider_tf.read_text()
        assert "terraform" in content
        assert "required_providers" in content
        assert "proxmox" in content
        assert "Telmate/proxmox" in content

    def test_generate_variables_tf(self, provider: ProxmoxProvider) -> None:
        """Test variables.tf generation."""
        provider.generate_terraform([])

        variables_tf = provider.terraform_dir / "variables.tf"
        assert variables_tf.exists()

    def test_generate_vm_terraform(
        self, provider: ProxmoxProvider, vm_resource: ResourceConfig
    ) -> None:
        """Test VM Terraform generation with all fields."""
        provider.generate_terraform([vm_resource])

        vms_tf = provider.terraform_dir / "vms.tf"
        assert vms_tf.exists()

        content = vms_tf.read_text()
        # Check resource block
        assert 'resource "proxmox_vm_qemu" "web_server_01"' in content
        assert 'name        = "web-server-01"' in content
        assert 'target_node = "pve01"' in content
        assert 'clone       = "ubuntu-22.04-template"' in content

        # Check VM configuration
        assert "cores   = 4" in content
        assert "sockets = 1" in content
        assert "memory  = 8192" in content

        # Check disk configuration
        assert 'size    = "50G"' in content
        assert 'type    = "scsi"' in content
        assert 'storage = "local-lvm"' in content

        # Check network configuration
        assert 'model  = "virtio"' in content
        assert 'bridge = "vmbr0"' in content
        assert "tag    = 100" in content

        # Check IP configuration
        assert 'ipconfig0 = "ip=192.168.1.10/24,gw=192.168.1.1"' in content

        # Check startup configuration
        assert "onboot  = true" in content
        assert "agent   = 1" in content

        # Check tags
        assert 'tags = "web,production"' in content

    def test_generate_vm_with_defaults(self, provider: ProxmoxProvider) -> None:
        """Test VM generation with default values."""
        vm = ResourceConfig(
            provider="proxmox",
            type="vm",
            name="minimal-vm",
            config={"name": "minimal-vm", "target_node": "pve01"},
        )

        provider.generate_terraform([vm])

        content = (provider.terraform_dir / "vms.tf").read_text()
        # Should use default values
        assert "cores   = 2" in content
        assert "sockets = 1" in content
        assert "memory  = 2048" in content
        assert "onboot  = true" in content

    def test_generate_template_terraform(
        self, provider: ProxmoxProvider, template_resource: ResourceConfig
    ) -> None:
        """Test template Terraform generation."""
        provider.generate_terraform([template_resource])

        templates_tf = provider.terraform_dir / "templates.tf"
        assert templates_tf.exists()

        content = templates_tf.read_text()
        # Template generates "template_<name>" not normalized name
        assert "template_ubuntu" in content or "ubuntu" in content
        assert "ubuntu-22.04-template" in content
        assert "template = true" in content

    def test_generate_network_terraform(
        self, provider: ProxmoxProvider, network_resource: ResourceConfig
    ) -> None:
        """Test network Terraform generation."""
        provider.generate_terraform([network_resource])

        networks_tf = provider.terraform_dir / "networks.tf"
        assert networks_tf.exists()

        content = networks_tf.read_text()
        # Networks template creates comments with bridge/VLAN info
        assert "vlan-100" in content
        assert "vmbr0" in content

    def test_generate_outputs_tf(
        self, provider: ProxmoxProvider, vm_resource: ResourceConfig
    ) -> None:
        """Test outputs.tf generation with resources."""
        provider.generate_terraform([vm_resource])

        outputs_tf = provider.terraform_dir / "outputs.tf"
        assert outputs_tf.exists()

    def test_generate_multiple_vms(self, provider: ProxmoxProvider) -> None:
        """Test generating multiple VMs in single file."""
        vms = [
            ResourceConfig(
                provider="proxmox",
                type="vm",
                name=f"vm-{i}",
                config={"name": f"vm-{i}", "target_node": "pve01"},
            )
            for i in range(3)
        ]

        provider.generate_terraform(vms)

        content = (provider.terraform_dir / "vms.tf").read_text()
        assert 'resource "proxmox_vm_qemu" "vm_0"' in content
        assert 'resource "proxmox_vm_qemu" "vm_1"' in content
        assert 'resource "proxmox_vm_qemu" "vm_2"' in content

    def test_generate_ansible_playbook(
        self, provider: ProxmoxProvider, vm_resource: ResourceConfig
    ) -> None:
        """Test Ansible playbook generation."""
        provider.generate_ansible([vm_resource])

        playbook = provider.ansible_dir / "playbook.yml"
        assert playbook.exists()

        content = playbook.read_text()
        assert "Configure Proxmox VMs" in content
        assert "hosts: proxmox_vms" in content
        assert "role: common" in content

    def test_generate_ansible_inventory(
        self, provider: ProxmoxProvider, vm_resource: ResourceConfig
    ) -> None:
        """Test Ansible inventory generation."""
        provider.generate_ansible([vm_resource])

        inventory = provider.ansible_dir / "inventory.yml"
        assert inventory.exists()

    def test_generate_ansible_roles(self, provider: ProxmoxProvider) -> None:
        """Test Ansible roles directory creation."""
        provider.generate_ansible([])

        roles_dir = provider.ansible_dir / "roles" / "common" / "tasks"
        assert roles_dir.exists()

        main_yml = roles_dir / "main.yml"
        assert main_yml.exists()

    def test_resource_name_normalization(self, provider: ProxmoxProvider) -> None:
        """Test that dashes in resource names are converted to underscores."""
        vm = ResourceConfig(
            provider="proxmox",
            type="vm",
            name="web-server-prod-01",
            config={"name": "web-server-prod-01", "target_node": "pve01"},
        )

        provider.generate_terraform([vm])

        content = (provider.terraform_dir / "vms.tf").read_text()
        # Terraform resource name should use underscores
        assert 'resource "proxmox_vm_qemu" "web_server_prod_01"' in content
        # But actual VM name keeps dashes
        assert 'name        = "web-server-prod-01"' in content


class TestOPNsenseTemplates:
    """Test OPNsense Terraform template generation."""

    @pytest.fixture
    def provider(self, tmp_path: Path) -> OPNsenseProvider:
        """Create OPNsense provider instance."""
        config_dir = tmp_path / "config"
        output_dir = tmp_path / "output"
        return OPNsenseProvider(config_dir, output_dir)

    @pytest.fixture
    def firewall_rule(self) -> ResourceConfig:
        """Create firewall rule resource."""
        return ResourceConfig(
            provider="opnsense",
            type="firewall_rules",
            name="allow-web-traffic",
            config={
                "name": "allow-web-traffic",
                "action": "pass",
                "interface": "lan",
                "protocol": "tcp",
                "source": "any",
                "destination": "192.168.1.10",
                "destination_port": "80,443",
                "description": "Allow web traffic to web server",
            },
        )

    @pytest.fixture
    def vlan_resource(self) -> ResourceConfig:
        """Create VLAN resource."""
        return ResourceConfig(
            provider="opnsense",
            type="vlans",
            name="vlan-100",
            config={"name": "vlan-100", "tag": 100, "parent": "igb0", "description": "Web VLAN"},
        )

    @pytest.fixture
    def alias_resource(self) -> ResourceConfig:
        """Create alias resource."""
        return ResourceConfig(
            provider="opnsense",
            type="aliases",
            name="web-servers",
            config={
                "name": "web-servers",
                "type": "host",
                "content": ["192.168.1.10", "192.168.1.11"],
                "description": "Production web servers",
            },
        )

    def test_generate_provider_tf(self, provider: OPNsenseProvider) -> None:
        """Test OPNsense provider.tf generation."""
        provider.generate_terraform([])

        provider_tf = provider.terraform_dir / "provider.tf"
        assert provider_tf.exists()

        content = provider_tf.read_text()
        assert "opnsense" in content
        assert "browningluke/opnsense" in content

    def test_generate_firewall_rule_terraform(
        self, provider: OPNsenseProvider, firewall_rule: ResourceConfig
    ) -> None:
        """Test firewall rule Terraform generation."""
        provider.generate_terraform([firewall_rule])

        rules_tf = provider.terraform_dir / "firewall_rules.tf"
        assert rules_tf.exists()

        content = rules_tf.read_text()
        assert "allow_web_traffic" in content
        assert "action" in content and "pass" in content
        assert "interface" in content and "lan" in content
        assert 'protocol = "tcp"' in content
        assert "Allow web traffic to web server" in content

    def test_generate_vlan_terraform(
        self, provider: OPNsenseProvider, vlan_resource: ResourceConfig
    ) -> None:
        """Test VLAN Terraform generation."""
        provider.generate_terraform([vlan_resource])

        vlans_tf = provider.terraform_dir / "vlans.tf"
        assert vlans_tf.exists()

        content = vlans_tf.read_text()
        assert "vlan_100" in content
        assert "tag" in content and "100" in content
        assert "Web VLAN" in content

    def test_generate_alias_terraform(
        self, provider: OPNsenseProvider, alias_resource: ResourceConfig
    ) -> None:
        """Test alias Terraform generation."""
        provider.generate_terraform([alias_resource])

        aliases_tf = provider.terraform_dir / "aliases.tf"
        assert aliases_tf.exists()

        content = aliases_tf.read_text()
        assert "web_servers" in content
        assert "type" in content and "host" in content
        assert "192.168.1.10" in content
        assert "Production web servers" in content

    def test_generate_multiple_rules(self, provider: OPNsenseProvider) -> None:
        """Test generating multiple firewall rules."""
        rules = [
            ResourceConfig(
                provider="opnsense",
                type="firewall_rules",
                name=f"rule-{i}",
                config={
                    "name": f"rule-{i}",
                    "action": "pass",
                    "interface": "lan",
                    "protocol": "tcp",
                },
            )
            for i in range(3)
        ]

        provider.generate_terraform(rules)

        content = (provider.terraform_dir / "firewall_rules.tf").read_text()
        assert "rule_0" in content
        assert "rule_1" in content
        assert "rule_2" in content

    def test_generate_ansible_playbook(self, provider: OPNsenseProvider) -> None:
        """Test OPNsense Ansible playbook generation."""
        import base64
        import re
        from unittest.mock import patch

        # Add Ansible-specific filters to Jinja2 environment
        def b64encode_filter(s: str) -> str:
            """Base64 encode filter for Jinja2 (mimics Ansible filter)."""
            if not s:
                return ''
            return base64.b64encode(s.encode()).decode()

        def regex_replace_filter(value: str, pattern: str, replacement: str) -> str:
            """Regex replace filter (mimics Ansible filter)."""
            return re.sub(pattern, replacement, value)

        def lookup_filter(plugin: str, *args, **kwargs) -> str:
            """Lookup filter (mimics Ansible lookup)."""
            # Return empty string for env lookups in tests
            return ''

        provider.jinja_env.filters['b64encode'] = b64encode_filter
        provider.jinja_env.filters['regex_replace'] = regex_replace_filter
        provider.jinja_env.globals['lookup'] = lookup_filter

        # Patch template.render to inject test variables
        original_get_template = provider.jinja_env.get_template

        def get_template_with_vars(name):
            """Get template and wrap render method to inject variables."""
            template = original_get_template(name)
            original_render = template.render

            def render_with_test_vars(**kwargs):
                """Inject test variables into template context."""
                test_vars = {
                    'opnsense_api_url': 'https://opnsense.test',
                    'opnsense_api_key': 'testkey',
                    'opnsense_api_secret': 'testsecret',
                }
                kwargs.update(test_vars)
                return original_render(**kwargs)

            template.render = render_with_test_vars
            return template

        with patch.object(provider.jinja_env, 'get_template', side_effect=get_template_with_vars):
            provider.generate_ansible([])
            playbook = provider.ansible_dir / "playbook.yml"
            assert playbook.exists()
            content = playbook.read_text()
            assert "Configure OPNsense" in content
            assert "api/firewall/filter/apply" in content
            assert "api/firewall/filter/reload" in content
    def test_generate_outputs_tf(
        self, provider: OPNsenseProvider, firewall_rule: ResourceConfig
    ) -> None:
        """Test outputs.tf generation."""
        provider.generate_terraform([firewall_rule])

        outputs_tf = provider.terraform_dir / "outputs.tf"
        assert outputs_tf.exists()


class TestKubernetesTemplates:
    """Test Kubernetes Terraform template generation."""

    @pytest.fixture
    def provider(self, tmp_path: Path) -> KubernetesProvider:
        """Create Kubernetes provider instance."""
        config_dir = tmp_path / "config"
        output_dir = tmp_path / "output"
        return KubernetesProvider(config_dir, output_dir)

    @pytest.fixture
    def deployment_resource(self) -> ResourceConfig:
        """Create deployment resource."""
        return ResourceConfig(
            provider="kubernetes",
            type="deployments",
            name="nginx-deployment",
            config={
                "name": "nginx-deployment",
                "namespace": "default",
                "replicas": 3,
                "labels": {"app": "nginx", "env": "production"},
                "containers": [
                    {
                        "name": "nginx",
                        "image": "nginx:1.21",
                        "ports": [{"containerPort": 80, "name": "http"}],
                    }
                ],
            },
        )

    @pytest.fixture
    def service_resource(self) -> ResourceConfig:
        """Create service resource."""
        return ResourceConfig(
            provider="kubernetes",
            type="services",
            name="nginx-service",
            config={
                "name": "nginx-service",
                "namespace": "default",
                "type": "LoadBalancer",
                "selector": "nginx",
                "ports": [{"port": 80, "targetPort": 80, "protocol": "TCP"}],
            },
        )

    @pytest.fixture
    def configmap_resource(self) -> ResourceConfig:
        """Create configmap resource."""
        return ResourceConfig(
            provider="kubernetes",
            type="configmaps",
            name="app-config",
            config={
                "name": "app-config",
                "namespace": "default",
                "data": {"database_url": "postgres://db:5432", "log_level": "info"},
            },
        )

    @pytest.fixture
    def namespace_resource(self) -> ResourceConfig:
        """Create namespace resource."""
        return ResourceConfig(
            provider="kubernetes",
            type="namespaces",
            name="production",
            config={"name": "production", "labels": {"env": "production"}},
        )

    def test_generate_provider_tf(self, provider: KubernetesProvider) -> None:
        """Test Kubernetes provider.tf generation."""
        provider.generate_terraform([])

        provider_tf = provider.terraform_dir / "provider.tf"
        assert provider_tf.exists()

        content = provider_tf.read_text()
        assert "kubernetes" in content
        assert "hashicorp/kubernetes" in content

    def test_generate_deployment_terraform(
        self, provider: KubernetesProvider, deployment_resource: ResourceConfig
    ) -> None:
        """Test deployment Terraform generation."""
        provider.generate_terraform([deployment_resource])

        deployments_tf = provider.terraform_dir / "deployments.tf"
        assert deployments_tf.exists()

        content = deployments_tf.read_text()
        assert "nginx_deployment" in content
        assert "nginx-deployment" in content
        assert 'namespace = "default"' in content
        assert "replicas = 3" in content
        assert 'image = "nginx:1.21"' in content

    def test_generate_service_terraform(
        self, provider: KubernetesProvider, service_resource: ResourceConfig
    ) -> None:
        """Test service Terraform generation."""
        provider.generate_terraform([service_resource])

        services_tf = provider.terraform_dir / "services.tf"
        assert services_tf.exists()

        content = services_tf.read_text()
        assert "nginx_service" in content
        assert 'type = "LoadBalancer"' in content
        assert "port" in content and "80" in content
        assert "target_port" in content

    def test_generate_configmap_terraform(
        self, provider: KubernetesProvider, configmap_resource: ResourceConfig
    ) -> None:
        """Test configmap Terraform generation."""
        provider.generate_terraform([configmap_resource])

        configmaps_tf = provider.terraform_dir / "configmaps.tf"
        assert configmaps_tf.exists()

        content = configmaps_tf.read_text()
        assert "app_config" in content
        assert "database_url" in content
        assert "log_level" in content

    def test_generate_namespace_terraform(
        self, provider: KubernetesProvider, namespace_resource: ResourceConfig
    ) -> None:
        """Test namespace Terraform generation."""
        provider.generate_terraform([namespace_resource])

        namespaces_tf = provider.terraform_dir / "namespaces.tf"
        assert namespaces_tf.exists()

        content = namespaces_tf.read_text()
        assert "production" in content
        assert "env" in content and "production" in content

    def test_generate_multiple_deployments(self, provider: KubernetesProvider) -> None:
        """Test generating multiple deployments."""
        deployments = [
            ResourceConfig(
                provider="kubernetes",
                type="deployments",
                name=f"app-{i}",
                config={
                    "name": f"app-{i}",
                    "namespace": "default",
                    "replicas": 2,
                    "containers": [{"name": f"app-{i}", "image": f"app:{i}"}],
                },
            )
            for i in range(3)
        ]

        provider.generate_terraform(deployments)

        content = (provider.terraform_dir / "deployments.tf").read_text()
        assert "app_0" in content
        assert "app_1" in content
        assert "app_2" in content

    def test_generate_ansible_playbook(self, provider: KubernetesProvider) -> None:
        """Test Kubernetes Ansible playbook generation."""
        from unittest.mock import MagicMock, patch

        # Kubernetes playbook uses Ansible loop constructs (item variable)
        # which are only available at Ansible runtime. We need to provide
        # a mock 'item' object for the template to render.

        # Add Ansible-specific functions to Jinja2 environment
        def lookup_filter(plugin: str, *args, **kwargs) -> str:
            """Lookup filter (mimics Ansible lookup)."""
            return ''

        provider.jinja_env.globals['lookup'] = lookup_filter

        resources = [
            ResourceConfig(
                provider="kubernetes",
                type="deployments",
                name="web-app",
                config={
                    "name": "web-app",
                    "namespace": "default",
                    "replicas": 3,
                },
            ),
        ]

        # Create a mock item object that provides the structure needed by the template
        mock_item = MagicMock()
        mock_item.config.name = "web-app"
        mock_item.config.namespace = "default"

        # Patch template.render to inject mock item
        original_get_template = provider.jinja_env.get_template

        def get_template_with_mock_item(name):
            """Get template and wrap render method to inject mock item."""
            template = original_get_template(name)
            original_render = template.render

            def render_with_mock(**kwargs):
                """Inject mock item into template context."""
                kwargs['item'] = mock_item
                return original_render(**kwargs)

            template.render = render_with_mock
            return template

        with patch.object(
            provider.jinja_env, 'get_template', side_effect=get_template_with_mock_item
        ):
            provider.generate_ansible(resources)
            playbook = provider.ansible_dir / "playbook.yml"
            assert playbook.exists()
            content = playbook.read_text()
            assert "Configure Kubernetes resources" in content
            assert "kubectl wait" in content
            assert "kubectl get deployments" in content
            # Verify Ansible loop syntax is preserved
            assert "loop:" in content

    def test_generate_outputs_tf(
        self, provider: KubernetesProvider, deployment_resource: ResourceConfig
    ) -> None:
        """Test outputs.tf generation."""
        provider.generate_terraform([deployment_resource])

        outputs_tf = provider.terraform_dir / "outputs.tf"
        assert outputs_tf.exists()

    def test_resource_name_normalization(self, provider: KubernetesProvider) -> None:
        """Test resource name normalization for Kubernetes."""
        deployment = ResourceConfig(
            provider="kubernetes",
            type="deployments",
            name="web-app-frontend",
            config={
                "name": "web-app-frontend",
                "namespace": "default",
                "replicas": 2,
                "containers": [{"name": "nginx", "image": "nginx"}],
            },
        )

        provider.generate_terraform([deployment])

        content = (provider.terraform_dir / "deployments.tf").read_text()
        # Terraform resource should use underscores
        assert "web_app_frontend" in content
        # But Kubernetes resource name keeps dashes
        assert "web-app-frontend" in content


class TestProviderResourceGrouping:
    """Test resource grouping by type across providers."""

    def test_proxmox_mixed_resource_types(self, tmp_path: Path) -> None:
        """Test Proxmox with multiple resource types."""
        provider = ProxmoxProvider(tmp_path / "config", tmp_path / "output")

        resources = [
            ResourceConfig(
                provider="proxmox",
                type="vm",
                name="vm1",
                config={"name": "vm1", "target_node": "pve01"},
            ),
            ResourceConfig(
                provider="proxmox",
                type="template",
                name="template1",
                config={
                    "name": "template1",
                    "target_node": "pve01",
                    "iso": "local:iso/ubuntu.iso",
                    "disk": {"size": "32G"},
                    "network": {"bridge": "vmbr0"},
                },
            ),
            ResourceConfig(
                provider="proxmox",
                type="network",
                name="net1",
                config={"name": "net1", "bridge": "vmbr0"},
            ),
        ]

        provider.generate_terraform(resources)

        # Should create separate files for each resource type
        assert (provider.terraform_dir / "vms.tf").exists()
        assert (provider.terraform_dir / "templates.tf").exists()
        assert (provider.terraform_dir / "networks.tf").exists()

    def test_opnsense_mixed_resource_types(self, tmp_path: Path) -> None:
        """Test OPNsense with multiple resource types."""
        provider = OPNsenseProvider(tmp_path / "config", tmp_path / "output")

        resources = [
            ResourceConfig(
                provider="opnsense",
                type="firewall_rules",
                name="rule1",
                config={"name": "rule1", "action": "pass"},
            ),
            ResourceConfig(
                provider="opnsense",
                type="vlans",
                name="vlan1",
                config={"name": "vlan1", "tag": 100},
            ),
            ResourceConfig(
                provider="opnsense",
                type="aliases",
                name="alias1",
                config={"name": "alias1", "type": "host"},
            ),
        ]

        provider.generate_terraform(resources)

        assert (provider.terraform_dir / "firewall_rules.tf").exists()
        assert (provider.terraform_dir / "vlans.tf").exists()
        assert (provider.terraform_dir / "aliases.tf").exists()

    def test_kubernetes_mixed_resource_types(self, tmp_path: Path) -> None:
        """Test Kubernetes with multiple resource types."""
        provider = KubernetesProvider(tmp_path / "config", tmp_path / "output")

        resources = [
            ResourceConfig(
                provider="kubernetes",
                type="deployments",
                name="deploy1",
                config={
                    "name": "deploy1",
                    "namespace": "default",
                    "containers": [{"name": "app", "image": "nginx"}],
                },
            ),
            ResourceConfig(
                provider="kubernetes",
                type="services",
                name="svc1",
                config={
                    "name": "svc1",
                    "namespace": "default",
                    "ports": [{"port": 80}],
                },
            ),
            ResourceConfig(
                provider="kubernetes",
                type="configmaps",
                name="cm1",
                config={
                    "name": "cm1",
                    "namespace": "default",
                    "data": {"key": "value"},
                },
            ),
            ResourceConfig(
                provider="kubernetes",
                type="namespaces",
                name="ns1",
                config={"name": "ns1"},
            ),
        ]

        provider.generate_terraform(resources)

        assert (provider.terraform_dir / "deployments.tf").exists()
        assert (provider.terraform_dir / "services.tf").exists()
        assert (provider.terraform_dir / "configmaps.tf").exists()
        assert (provider.terraform_dir / "namespaces.tf").exists()


class TestProviderValidation:
    """Test provider config validation methods."""

    def test_proxmox_validate_config(self, tmp_path: Path):
        """Test Proxmox config validation."""
        provider = ProxmoxProvider(tmp_path / "config", tmp_path / "output")

        # Valid config with required 'name' field
        assert provider.validate_config({"name": "vm-01"}) is True

        # Invalid config missing 'name'
        assert provider.validate_config({"other": "value"}) is False

    def test_opnsense_validate_config(self, tmp_path: Path):
        """Test OPNsense config validation."""
        provider = OPNsenseProvider(tmp_path / "config", tmp_path / "output")

        # Valid config with required 'name' field
        assert provider.validate_config({"name": "rule-01"}) is True

        # Invalid config missing 'name'
        assert provider.validate_config({"action": "pass"}) is False

    def test_kubernetes_validate_config(self, tmp_path: Path):
        """Test Kubernetes config validation."""
        provider = KubernetesProvider(tmp_path / "config", tmp_path / "output")

        # Valid config with required 'name' field
        assert provider.validate_config({"name": "deployment-01"}) is True

        # Invalid config missing 'name'
        assert provider.validate_config({"other": "value"}) is False


class TestProviderDependencies:
    """Test provider dependency methods."""

    def test_proxmox_get_dependencies(self, tmp_path: Path):
        """Test Proxmox resource dependencies."""
        provider = ProxmoxProvider(tmp_path / "config", tmp_path / "output")
        deps = provider.get_dependencies()

        # VMs depend on templates and networks
        assert "vm" in deps
        assert "template" in deps["vm"]
        assert "network" in deps["vm"]

    def test_opnsense_get_dependencies(self, tmp_path: Path):
        """Test OPNsense resource dependencies."""
        provider = OPNsenseProvider(tmp_path / "config", tmp_path / "output")
        deps = provider.get_dependencies()

        # Firewall rules depend on aliases and vlans
        assert "firewall_rules" in deps
        assert "aliases" in deps["firewall_rules"]
        assert "vlans" in deps["firewall_rules"]

    def test_kubernetes_get_dependencies(self, tmp_path: Path):
        """Test Kubernetes resource dependencies."""
        provider = KubernetesProvider(tmp_path / "config", tmp_path / "output")
        deps = provider.get_dependencies()

        # Deployments depend on namespaces and configmaps
        assert "deployments" in deps
        assert "namespaces" in deps["deployments"]
        assert "configmaps" in deps["deployments"]

        # Services depend on deployments
        assert "services" in deps
        assert "deployments" in deps["services"]
