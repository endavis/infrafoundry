"""Pytest fixtures and Hypothesis profiles for InfraFoundry tests."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml
from hypothesis import HealthCheck, settings

from infrafoundry.core.config import ConfigManager

# CI profile: fewer examples, relaxed deadline for slow CI runners
settings.register_profile(
    "ci",
    max_examples=50,
    deadline=500,
    suppress_health_check=[HealthCheck.too_slow],
)

# Default profile: more thorough exploration for local development
settings.register_profile(
    "default",
    max_examples=200,
)

settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_config_manager(temp_dir):
    """Create a mock ConfigManager with required attributes for Orchestrator tests."""
    config_manager = Mock(spec=ConfigManager)
    config_manager.base_dir = temp_dir
    config_manager.load_environment.return_value = None
    return config_manager


@pytest.fixture
def mock_config_dir(temp_dir):
    """Create a mock configuration directory structure."""
    config_dir = temp_dir / "config"
    config_dir.mkdir()

    # Create envs directory
    envs_dir = config_dir / "envs"
    envs_dir.mkdir()

    # Create dev environment
    dev_dir = envs_dir / "dev"
    dev_dir.mkdir()

    # Environment config
    env_config = {
        "name": "dev",
        "description": "Development environment",
        "variables": {"datacenter": "dc1", "network": "vmbr0"},
    }
    with open(dev_dir / "settings.yaml", "w") as f:
        yaml.dump(env_config, f)

    # Proxmox provider directory
    proxmox_dir = dev_dir / "proxmox"
    proxmox_dir.mkdir()

    # VM config
    vm_config = {
        "vm": [
            {
                "name": "test-vm-01",
                "template": "ubuntu-22.04",
                "cores": 2,
                "memory": 4096,
                "disk_size": 50,
            }
        ]
    }
    with open(proxmox_dir / "vm.yaml", "w") as f:
        yaml.dump(vm_config, f)

    # Resources directory (resource-centric format)
    resources_dir = dev_dir / "resources"
    resources_dir.mkdir()

    resource_config = {
        "resources": [
            {
                "provider": "proxmox",
                "type": "vm",
                "name": "web-server-01",
                "config": {
                    "template": "ubuntu-22.04",
                    "cores": 4,
                    "memory": 8192,
                    "disk_size": 100,
                },
            }
        ]
    }
    with open(resources_dir / "web-servers.yaml", "w") as f:
        yaml.dump(resource_config, f)

    return config_dir


@pytest.fixture
def mock_secrets_dir(temp_dir):
    """Create a mock secrets directory."""
    secrets_dir = temp_dir / "secrets"
    secrets_dir.mkdir()

    # Create unencrypted secrets for testing
    proxmox_secrets = {
        "proxmox": {"api_url": "https://proxmox.example.com:8006", "api_token": "test-token"}
    }
    with open(secrets_dir / "proxmox.yaml", "w") as f:
        yaml.dump(proxmox_secrets, f)

    return secrets_dir


@pytest.fixture
def mock_policy_dir(temp_dir):
    """Create a mock policy directory."""
    policy_dir = temp_dir / "policies"
    policy_dir.mkdir()

    # Resource limits policy
    resource_limits_file = {
        "policies": [
            {
                "name": "resource_limits",
                "type": "resource_limit",
                "description": "Enforce VM resource limits",
                "level": "warning",
                "rules": {
                    "limits": {
                        "max_cpu": 16,
                        "max_memory_mb": 65536,
                    }
                },
            }
        ]
    }
    with open(policy_dir / "resource_limits.yaml", "w") as f:
        yaml.dump(resource_limits_file, f)

    # Required tags policy
    required_tags_file = {
        "policies": [
            {
                "name": "require_tags",
                "type": "required_tags",
                "description": "Require tags on all resources",
                "level": "error",
                "rules": {"tags": ["environment", "owner", "project"]},
            }
        ]
    }
    with open(policy_dir / "require_tags.yaml", "w") as f:
        yaml.dump(required_tags_file, f)

    return policy_dir


@pytest.fixture
def mock_config():
    """Create mock configuration data for orchestrator tests."""
    from unittest.mock import Mock

    # Mock environment
    environment = {
        "name": "dev",
        "description": "Development environment",
        "variables": {"datacenter": "dc1", "network": "vmbr0"},
    }

    # Mock resources
    resources = []
    for i in range(2):
        resource = Mock()
        resource.provider = "proxmox"
        resource.type = "vm"
        resource.name = f"web-0{i + 1}"
        resource.config = {"cores": 2, "memory": 4096}
        resource.hooks = None  # No lifecycle hooks configured
        resources.append(resource)

    return {"environment": environment, "resources": resources}


@pytest.fixture
def mock_terraform_state():
    """Create a mock Terraform state."""
    return {
        "version": 4,
        "terraform_version": "1.6.0",
        "serial": 1,
        "lineage": "test-lineage",
        "outputs": {},
        "resources": [
            {
                "mode": "managed",
                "type": "proxmox_vm_qemu",
                "name": "test_vm_01",
                "provider": 'provider["registry.terraform.io/telmate/proxmox"]',
                "instances": [
                    {
                        "schema_version": 0,
                        "attributes": {
                            "id": "test-vm-01",
                            "name": "test-vm-01",
                            "cores": 2,
                            "memory": 4096,
                            "disk": {"size": 50, "storage": "local-lvm"},
                        },
                    }
                ],
            }
        ],
    }


@pytest.fixture
def mock_provider_config():
    """Create a mock provider configuration."""
    return {
        "proxmox": {
            "api_url": "https://proxmox.example.com:8006",
            "api_token": "test-token",
            "node": "pve1",
        },
        "opnsense": {"api_url": "https://firewall.example.com", "api_key": "test-key"},
        "kubernetes": {
            "context": "test-cluster",
            "namespace": "default",
        },
    }


@pytest.fixture
def mock_environment_vars(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv("INFRAFOUNDRY_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ANSIBLE_HOST_KEY_CHECKING", "False")


@pytest.fixture
def sample_vm_resource():
    """Sample VM resource configuration."""
    return {
        "name": "test-vm-01",
        "template": "ubuntu-22.04",
        "cores": 4,
        "memory": 8192,
        "disk_size": 100,
        "network": "vmbr0",
        "tags": {"environment": "dev", "owner": "team-infra"},
    }


@pytest.fixture
def sample_firewall_rule():
    """Sample firewall rule configuration."""
    return {
        "name": "allow-http",
        "action": "pass",
        "interface": "wan",
        "protocol": "tcp",
        "source": "any",
        "destination": "web-servers",
        "port": 80,
    }


@pytest.fixture
def sample_k8s_deployment():
    """Sample Kubernetes deployment configuration."""
    return {
        "name": "web-app",
        "replicas": 3,
        "image": "nginx:latest",
        "ports": [{"name": "http", "containerPort": 80}],
        "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}},
    }
