"""Integration tests for backend rendering."""

import pytest
import yaml

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.config.backend_config import BackendType
from infrafoundry.providers.proxmox import ProxmoxProvider


@pytest.fixture
def mock_config_dir_with_backend(temp_dir):
    """Create a mock configuration directory with backend configuration."""
    config_dir = temp_dir / "config"
    config_dir.mkdir()

    envs_dir = config_dir / "envs"
    envs_dir.mkdir()

    dev_dir = envs_dir / "dev"
    dev_dir.mkdir()

    # Environment config with S3 backend
    env_config = {
        "name": "dev",
        "description": "Development environment with S3 backend",
        "variables": {"datacenter": "dc1"},
        "backend": {
            "type": "s3",
            "s3": {
                "bucket": "test-terraform-state",
                "key": "dev/terraform.tfstate",
                "region": "us-east-1",
                "dynamodb_table": "terraform-locks",
                "encrypt": True,
            },
        },
    }
    with open(dev_dir / "settings.yaml", "w") as f:
        yaml.dump(env_config, f)

    # Proxmox provider directory
    proxmox_dir = dev_dir / "proxmox"
    proxmox_dir.mkdir()

    # VM config
    vm_config = {"vm": [{"name": "test-vm-01", "template": "ubuntu-22.04"}]}
    with open(proxmox_dir / "vm.yaml", "w") as f:
        yaml.dump(vm_config, f)

    return config_dir


@pytest.fixture
def mock_config_dir_with_gcs_backend(temp_dir):
    """Create a mock configuration directory with GCS backend."""
    config_dir = temp_dir / "config"
    config_dir.mkdir()

    envs_dir = config_dir / "envs"
    envs_dir.mkdir()

    prod_dir = envs_dir / "prod"
    prod_dir.mkdir()

    env_config = {
        "name": "prod",
        "description": "Production environment with GCS backend",
        "backend": {
            "type": "gcs",
            "gcs": {
                "bucket": "my-tf-state-bucket",
                "prefix": "prod/terraform/state",
                "credentials": "/path/to/service-account.json",
            },
        },
    }
    with open(prod_dir / "settings.yaml", "w") as f:
        yaml.dump(env_config, f)

    # Proxmox provider directory
    proxmox_dir = prod_dir / "proxmox"
    proxmox_dir.mkdir()

    vm_config = {"vm": [{"name": "prod-vm-01", "template": "ubuntu-22.04"}]}
    with open(proxmox_dir / "vm.yaml", "w") as f:
        yaml.dump(vm_config, f)

    return config_dir


@pytest.fixture
def mock_config_dir_with_azure_backend(temp_dir):
    """Create a mock configuration directory with Azure backend."""
    config_dir = temp_dir / "config"
    config_dir.mkdir()

    envs_dir = config_dir / "envs"
    envs_dir.mkdir()

    prod_dir = envs_dir / "prod"
    prod_dir.mkdir()

    env_config = {
        "name": "prod",
        "description": "Production environment with Azure backend",
        "backend": {
            "type": "azurerm",
            "azurerm": {
                "resource_group_name": "terraform-state-rg",
                "storage_account_name": "tfstatestorage",
                "container_name": "tfstate",
                "key": "prod.terraform.tfstate",
                "use_azuread_auth": True,
            },
        },
    }
    with open(prod_dir / "settings.yaml", "w") as f:
        yaml.dump(env_config, f)

    # Proxmox provider directory
    proxmox_dir = prod_dir / "proxmox"
    proxmox_dir.mkdir()

    vm_config = {"vm": [{"name": "prod-vm-01", "template": "ubuntu-22.04"}]}
    with open(proxmox_dir / "vm.yaml", "w") as f:
        yaml.dump(vm_config, f)

    return config_dir


@pytest.fixture
def mock_config_dir_with_postgres_backend(temp_dir):
    """Create a mock configuration directory with Postgres backend."""
    config_dir = temp_dir / "config"
    config_dir.mkdir()

    envs_dir = config_dir / "envs"
    envs_dir.mkdir()

    staging_dir = envs_dir / "staging"
    staging_dir.mkdir()

    env_config = {
        "name": "staging",
        "description": "Staging environment with Postgres backend",
        "backend": {
            "type": "postgres",
            "postgres": {
                "conn_str": "postgres://tfstate:password@db.example.com:5432/terraform_backend",
                "schema_name": "staging_state",
            },
        },
    }
    with open(staging_dir / "settings.yaml", "w") as f:
        yaml.dump(env_config, f)

    # Proxmox provider directory
    proxmox_dir = staging_dir / "proxmox"
    proxmox_dir.mkdir()

    vm_config = {"vm": [{"name": "staging-vm-01", "template": "ubuntu-22.04"}]}
    with open(proxmox_dir / "vm.yaml", "w") as f:
        yaml.dump(vm_config, f)

    return config_dir


@pytest.fixture
def mock_config_dir_with_terraform_cloud_backend(temp_dir):
    """Create a mock configuration directory with Terraform Cloud backend."""
    config_dir = temp_dir / "config"
    config_dir.mkdir()

    envs_dir = config_dir / "envs"
    envs_dir.mkdir()

    prod_dir = envs_dir / "prod"
    prod_dir.mkdir()

    env_config = {
        "name": "prod",
        "description": "Production environment with Terraform Cloud backend",
        "backend": {
            "type": "remote",
            "remote": {
                "organization": "my-organization",
                "workspaces": {"name": "prod-infrastructure"},
                "hostname": "app.terraform.io",
            },
        },
    }
    with open(prod_dir / "settings.yaml", "w") as f:
        yaml.dump(env_config, f)

    # Proxmox provider directory
    proxmox_dir = prod_dir / "proxmox"
    proxmox_dir.mkdir()

    vm_config = {"vm": [{"name": "prod-vm-01", "template": "ubuntu-22.04"}]}
    with open(proxmox_dir / "vm.yaml", "w") as f:
        yaml.dump(vm_config, f)

    return config_dir


@pytest.fixture
def mock_config_dir_no_backend(temp_dir):
    """Create a mock configuration directory without backend configuration."""
    config_dir = temp_dir / "config"
    config_dir.mkdir()

    envs_dir = config_dir / "envs"
    envs_dir.mkdir()

    dev_dir = envs_dir / "dev"
    dev_dir.mkdir()

    env_config = {
        "name": "dev",
        "description": "Development environment without backend",
        "variables": {"datacenter": "dc1"},
    }
    with open(dev_dir / "settings.yaml", "w") as f:
        yaml.dump(env_config, f)

    # Proxmox provider directory
    proxmox_dir = dev_dir / "proxmox"
    proxmox_dir.mkdir()

    vm_config = {"vm": [{"name": "test-vm-01", "template": "ubuntu-22.04"}]}
    with open(proxmox_dir / "vm.yaml", "w") as f:
        yaml.dump(vm_config, f)

    return config_dir


@pytest.mark.integration
class TestBackendRendering:
    """Integration tests for backend rendering."""

    def test_s3_backend_rendering(self, mock_config_dir_with_backend, temp_dir):
        """Test S3 backend.tf is rendered correctly."""
        config_manager = ConfigManager(mock_config_dir_with_backend / "envs")
        output_dir = temp_dir / "output"

        # Load environment and verify backend config
        env = config_manager.load_environment("dev")
        assert env.backend is not None
        assert env.backend.type == BackendType.S3
        assert env.backend.s3 is not None
        assert env.backend.s3.bucket == "test-terraform-state"
        assert env.backend.supports_locking() is True

        # Create provider and generate terraform
        provider = ProxmoxProvider(
            config_dir=mock_config_dir_with_backend / "envs" / "dev",
            output_dir=output_dir,
        )
        provider.set_environment("dev")

        resources = config_manager.get_all_resources("dev", "proxmox")
        provider.generate_terraform(resources)

        # Verify backend.tf was created
        backend_file = output_dir / "dev" / "terraform" / "proxmox" / "backend.tf"
        assert backend_file.exists()

        # Read and verify content
        content = backend_file.read_text()
        assert "terraform {" in content
        assert 'backend "s3" {' in content
        assert 'bucket         = "test-terraform-state"' in content
        assert 'key            = "dev/terraform.tfstate"' in content
        assert 'region         = "us-east-1"' in content
        assert 'dynamodb_table = "terraform-locks"' in content
        assert "encrypt        = true" in content
        assert "# State Locking: Enabled" in content

    def test_gcs_backend_rendering(self, mock_config_dir_with_gcs_backend, temp_dir):
        """Test GCS backend.tf is rendered correctly."""
        config_manager = ConfigManager(mock_config_dir_with_gcs_backend / "envs")
        output_dir = temp_dir / "output"

        env = config_manager.load_environment("prod")
        assert env.backend is not None
        assert env.backend.type == BackendType.GCS
        assert env.backend.supports_locking() is True

        provider = ProxmoxProvider(
            config_dir=mock_config_dir_with_gcs_backend / "envs" / "prod",
            output_dir=output_dir,
        )
        provider.set_environment("prod")

        resources = config_manager.get_all_resources("prod", "proxmox")
        provider.generate_terraform(resources)

        backend_file = output_dir / "prod" / "terraform" / "proxmox" / "backend.tf"
        assert backend_file.exists()

        content = backend_file.read_text()
        assert 'backend "gcs" {' in content
        assert 'bucket      = "my-tf-state-bucket"' in content
        assert 'prefix      = "prod/terraform/state"' in content
        assert 'credentials = "/path/to/service-account.json"' in content
        assert "# State Locking: Enabled" in content

    def test_azure_backend_rendering(self, mock_config_dir_with_azure_backend, temp_dir):
        """Test Azure backend.tf is rendered correctly."""
        config_manager = ConfigManager(mock_config_dir_with_azure_backend / "envs")
        output_dir = temp_dir / "output"

        env = config_manager.load_environment("prod")
        assert env.backend is not None
        assert env.backend.type == BackendType.AZURERM
        assert env.backend.supports_locking() is True

        provider = ProxmoxProvider(
            config_dir=mock_config_dir_with_azure_backend / "envs" / "prod",
            output_dir=output_dir,
        )
        provider.set_environment("prod")

        resources = config_manager.get_all_resources("prod", "proxmox")
        provider.generate_terraform(resources)

        backend_file = output_dir / "prod" / "terraform" / "proxmox" / "backend.tf"
        assert backend_file.exists()

        content = backend_file.read_text()
        assert 'backend "azurerm" {' in content
        assert 'resource_group_name  = "terraform-state-rg"' in content
        assert 'storage_account_name = "tfstatestorage"' in content
        assert 'container_name       = "tfstate"' in content
        assert 'key                  = "prod.terraform.tfstate"' in content
        assert "use_azuread_auth     = true" in content
        assert "# State Locking: Enabled" in content

    def test_postgres_backend_rendering(self, mock_config_dir_with_postgres_backend, temp_dir):
        """Test Postgres backend.tf is rendered correctly."""
        config_manager = ConfigManager(mock_config_dir_with_postgres_backend / "envs")
        output_dir = temp_dir / "output"

        env = config_manager.load_environment("staging")
        assert env.backend is not None
        assert env.backend.type == BackendType.POSTGRES
        assert env.backend.supports_locking() is True

        provider = ProxmoxProvider(
            config_dir=mock_config_dir_with_postgres_backend / "envs" / "staging",
            output_dir=output_dir,
        )
        provider.set_environment("staging")

        resources = config_manager.get_all_resources("staging", "proxmox")
        provider.generate_terraform(resources)

        backend_file = output_dir / "staging" / "terraform" / "proxmox" / "backend.tf"
        assert backend_file.exists()

        content = backend_file.read_text()
        assert 'backend "postgres" {' in content
        assert (
            'conn_str             = "postgres://tfstate:password@db.example.com:5432/terraform_backend"'
            in content
        )
        assert 'schema_name          = "staging_state"' in content
        assert "# State Locking: Enabled" in content

    def test_terraform_cloud_backend_rendering(
        self, mock_config_dir_with_terraform_cloud_backend, temp_dir
    ):
        """Test Terraform Cloud backend.tf is rendered correctly."""
        config_manager = ConfigManager(mock_config_dir_with_terraform_cloud_backend / "envs")
        output_dir = temp_dir / "output"

        env = config_manager.load_environment("prod")
        assert env.backend is not None
        assert env.backend.type == BackendType.TERRAFORM_CLOUD
        assert env.backend.supports_locking() is True

        provider = ProxmoxProvider(
            config_dir=mock_config_dir_with_terraform_cloud_backend / "envs" / "prod",
            output_dir=output_dir,
        )
        provider.set_environment("prod")

        resources = config_manager.get_all_resources("prod", "proxmox")
        provider.generate_terraform(resources)

        backend_file = output_dir / "prod" / "terraform" / "proxmox" / "backend.tf"
        assert backend_file.exists()

        content = backend_file.read_text()
        assert 'backend "remote" {' in content
        assert 'organization = "my-organization"' in content
        assert "workspaces {" in content
        assert 'name   = "prod-infrastructure"' in content
        assert 'hostname     = "app.terraform.io"' in content
        assert "# State Locking: Enabled" in content

    def test_no_backend_no_file_generated(self, mock_config_dir_no_backend, temp_dir):
        """Test that backend.tf is not generated when no backend configured."""
        config_manager = ConfigManager(mock_config_dir_no_backend / "envs")
        output_dir = temp_dir / "output"

        env = config_manager.load_environment("dev")
        assert env.backend is None

        provider = ProxmoxProvider(
            config_dir=mock_config_dir_no_backend / "envs" / "dev",
            output_dir=output_dir,
        )
        provider.set_environment("dev")

        resources = config_manager.get_all_resources("dev", "proxmox")
        provider.generate_terraform(resources)

        # Verify backend.tf was NOT created
        backend_file = output_dir / "dev" / "terraform" / "proxmox" / "backend.tf"
        assert not backend_file.exists()

    def test_local_backend_no_file_generated(self, temp_dir):
        """Test that backend.tf is not generated for local backend."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()

        envs_dir = config_dir / "envs"
        envs_dir.mkdir()

        dev_dir = envs_dir / "dev"
        dev_dir.mkdir()

        env_config = {
            "name": "dev",
            "description": "Development environment with local backend",
            "backend": {"type": "local"},
        }
        with open(dev_dir / "settings.yaml", "w") as f:
            yaml.dump(env_config, f)

        proxmox_dir = dev_dir / "proxmox"
        proxmox_dir.mkdir()

        vm_config = {"vm": [{"name": "test-vm-01", "template": "ubuntu-22.04"}]}
        with open(proxmox_dir / "vm.yaml", "w") as f:
            yaml.dump(vm_config, f)

        config_manager = ConfigManager(config_dir / "envs")
        output_dir = temp_dir / "output"

        env = config_manager.load_environment("dev")
        assert env.backend is not None
        assert env.backend.type == BackendType.LOCAL
        assert env.backend.supports_locking() is False

        provider = ProxmoxProvider(
            config_dir=config_dir / "envs" / "dev",
            output_dir=output_dir,
        )
        provider.set_environment("dev")

        resources = config_manager.get_all_resources("dev", "proxmox")
        provider.generate_terraform(resources)

        # Verify backend.tf was NOT created for local backend
        backend_file = output_dir / "dev" / "terraform" / "proxmox" / "backend.tf"
        assert not backend_file.exists()

    def test_backend_validation_in_rendering(self, temp_dir):
        """Test that invalid backend configuration is caught during rendering."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()

        envs_dir = config_dir / "envs"
        envs_dir.mkdir()

        dev_dir = envs_dir / "dev"
        dev_dir.mkdir()

        # Invalid S3 backend config (missing region)
        env_config = {
            "name": "dev",
            "description": "Development environment with invalid backend",
            "backend": {"type": "s3", "s3": {"bucket": "test-bucket"}},
        }
        with open(dev_dir / "settings.yaml", "w") as f:
            yaml.dump(env_config, f)

        proxmox_dir = dev_dir / "proxmox"
        proxmox_dir.mkdir()

        vm_config = {"vm": [{"name": "test-vm-01", "template": "ubuntu-22.04"}]}
        with open(proxmox_dir / "vm.yaml", "w") as f:
            yaml.dump(vm_config, f)

        config_manager = ConfigManager(config_dir / "envs")

        # Loading environment should fail validation
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            config_manager.load_environment("dev")
