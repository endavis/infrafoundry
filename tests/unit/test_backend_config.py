"""Unit tests for backend configuration models."""

import pytest
from pydantic import ValidationError

from infrafoundry.core.config.backend_config import (
    AzureBackendConfig,
    BackendConfig,
    BackendType,
    GCSBackendConfig,
    LocalBackendConfig,
    PostgresBackendConfig,
    S3BackendConfig,
    TerraformCloudBackendConfig,
)


@pytest.mark.unit
class TestS3BackendConfig:
    """Tests for S3BackendConfig."""

    def test_minimal_config(self):
        """Test S3 config with minimal required fields."""
        config = S3BackendConfig(bucket="test-bucket", region="us-east-1")
        assert config.bucket == "test-bucket"
        assert config.region == "us-east-1"
        assert config.key == "terraform.tfstate"  # default
        assert config.encrypt is True  # default

    def test_full_config(self):
        """Test S3 config with all fields."""
        config = S3BackendConfig(
            bucket="test-bucket",
            key="custom/path/terraform.tfstate",
            region="us-west-2",
            dynamodb_table="terraform-locks",
            encrypt=True,
            profile="production",
            role_arn="arn:aws:iam::123456789012:role/TerraformRole",
            kms_key_id="arn:aws:kms:us-west-2:123456789012:key/12345678-1234-1234-1234-123456789012",
        )
        assert config.bucket == "test-bucket"
        assert config.key == "custom/path/terraform.tfstate"
        assert config.region == "us-west-2"
        assert config.dynamodb_table == "terraform-locks"
        assert config.encrypt is True
        assert config.profile == "production"
        assert config.role_arn == "arn:aws:iam::123456789012:role/TerraformRole"
        assert config.kms_key_id is not None

    def test_missing_required_field(self):
        """Test S3 config fails without required fields."""
        with pytest.raises(ValidationError):
            S3BackendConfig(bucket="test-bucket")  # missing region

        with pytest.raises(ValidationError):
            S3BackendConfig(region="us-east-1")  # missing bucket


@pytest.mark.unit
class TestGCSBackendConfig:
    """Tests for GCSBackendConfig."""

    def test_minimal_config(self):
        """Test GCS config with minimal required fields."""
        config = GCSBackendConfig(bucket="test-bucket")
        assert config.bucket == "test-bucket"
        assert config.prefix == "terraform/state"  # default

    def test_full_config(self):
        """Test GCS config with all fields."""
        config = GCSBackendConfig(
            bucket="test-bucket",
            prefix="custom/prefix",
            credentials="/path/to/service-account.json",
            encryption_key="base64-encoded-key",
        )
        assert config.bucket == "test-bucket"
        assert config.prefix == "custom/prefix"
        assert config.credentials == "/path/to/service-account.json"
        assert config.encryption_key == "base64-encoded-key"

    def test_missing_required_field(self):
        """Test GCS config fails without bucket."""
        with pytest.raises(ValidationError):
            GCSBackendConfig()  # missing bucket


@pytest.mark.unit
class TestAzureBackendConfig:
    """Tests for AzureBackendConfig."""

    def test_minimal_config(self):
        """Test Azure config with minimal required fields."""
        config = AzureBackendConfig(
            resource_group_name="terraform-rg",
            storage_account_name="tfstatestorage",
            container_name="tfstate",
        )
        assert config.resource_group_name == "terraform-rg"
        assert config.storage_account_name == "tfstatestorage"
        assert config.container_name == "tfstate"
        assert config.key == "terraform.tfstate"  # default
        assert config.use_azuread_auth is False  # default

    def test_full_config(self):
        """Test Azure config with all fields."""
        config = AzureBackendConfig(
            resource_group_name="terraform-rg",
            storage_account_name="tfstatestorage",
            container_name="tfstate",
            key="custom.tfstate",
            access_key="secret-key",
            sas_token="sas-token",
            use_azuread_auth=True,
        )
        assert config.key == "custom.tfstate"
        assert config.access_key == "secret-key"
        assert config.sas_token == "sas-token"
        assert config.use_azuread_auth is True

    def test_missing_required_fields(self):
        """Test Azure config fails without required fields."""
        with pytest.raises(ValidationError):
            AzureBackendConfig(
                storage_account_name="tfstatestorage",
                container_name="tfstate",
            )  # missing resource_group_name

        with pytest.raises(ValidationError):
            AzureBackendConfig(
                resource_group_name="terraform-rg",
                container_name="tfstate",
            )  # missing storage_account_name


@pytest.mark.unit
class TestPostgresBackendConfig:
    """Tests for PostgresBackendConfig."""

    def test_minimal_config(self):
        """Test Postgres config with minimal required fields."""
        config = PostgresBackendConfig(conn_str="postgres://user:pass@localhost:5432/terraform")
        assert config.conn_str == "postgres://user:pass@localhost:5432/terraform"
        assert config.schema_name == "terraform_remote_state"  # default
        assert config.skip_schema_creation is False  # default

    def test_full_config(self):
        """Test Postgres config with all fields."""
        config = PostgresBackendConfig(
            conn_str="postgres://user:pass@localhost:5432/terraform",
            schema_name="custom_schema",
            skip_schema_creation=True,
        )
        assert config.schema_name == "custom_schema"
        assert config.skip_schema_creation is True

    def test_missing_required_field(self):
        """Test Postgres config fails without conn_str."""
        with pytest.raises(ValidationError):
            PostgresBackendConfig()  # missing conn_str


@pytest.mark.unit
class TestTerraformCloudBackendConfig:
    """Tests for TerraformCloudBackendConfig."""

    def test_minimal_config_with_workspace_name(self):
        """Test Terraform Cloud config with workspace name."""
        config = TerraformCloudBackendConfig(
            organization="my-org",
            workspaces={"name": "prod-infrastructure"},
        )
        assert config.organization == "my-org"
        assert config.workspaces == {"name": "prod-infrastructure"}

    def test_minimal_config_with_workspace_prefix(self):
        """Test Terraform Cloud config with workspace prefix."""
        config = TerraformCloudBackendConfig(
            organization="my-org",
            workspaces={"prefix": "prod-"},
        )
        assert config.organization == "my-org"
        assert config.workspaces == {"prefix": "prod-"}

    def test_full_config(self):
        """Test Terraform Cloud config with all fields."""
        config = TerraformCloudBackendConfig(
            organization="my-org",
            workspaces={"name": "prod-infrastructure"},
            hostname="terraform.example.com",
            token="terraform-cloud-token",
        )
        assert config.hostname == "terraform.example.com"
        assert config.token == "terraform-cloud-token"

    def test_missing_required_fields(self):
        """Test Terraform Cloud config fails without required fields."""
        with pytest.raises(ValidationError):
            TerraformCloudBackendConfig(workspaces={"name": "prod"})  # missing organization

        with pytest.raises(ValidationError):
            TerraformCloudBackendConfig(organization="my-org")  # missing workspaces


@pytest.mark.unit
class TestLocalBackendConfig:
    """Tests for LocalBackendConfig."""

    def test_default_config(self):
        """Test Local config with defaults."""
        config = LocalBackendConfig()
        assert config.path is None

    def test_custom_path(self):
        """Test Local config with custom path."""
        config = LocalBackendConfig(path="/custom/path/terraform.tfstate")
        assert config.path == "/custom/path/terraform.tfstate"


@pytest.mark.unit
class TestBackendConfig:
    """Tests for unified BackendConfig."""

    def test_default_local_backend(self):
        """Test default backend is local."""
        config = BackendConfig()
        assert config.type == BackendType.LOCAL

    def test_s3_backend(self):
        """Test S3 backend configuration."""
        config = BackendConfig(
            type=BackendType.S3,
            s3=S3BackendConfig(bucket="test-bucket", region="us-east-1"),
        )
        assert config.type == BackendType.S3
        assert config.s3 is not None
        assert config.s3.bucket == "test-bucket"

    def test_gcs_backend(self):
        """Test GCS backend configuration."""
        config = BackendConfig(
            type=BackendType.GCS,
            gcs=GCSBackendConfig(bucket="test-bucket"),
        )
        assert config.type == BackendType.GCS
        assert config.gcs is not None

    def test_azure_backend(self):
        """Test Azure backend configuration."""
        config = BackendConfig(
            type=BackendType.AZURERM,
            azurerm=AzureBackendConfig(
                resource_group_name="rg",
                storage_account_name="storage",
                container_name="container",
            ),
        )
        assert config.type == BackendType.AZURERM
        assert config.azurerm is not None

    def test_postgres_backend(self):
        """Test Postgres backend configuration."""
        config = BackendConfig(
            type=BackendType.POSTGRES,
            postgres=PostgresBackendConfig(conn_str="postgres://localhost/terraform"),
        )
        assert config.type == BackendType.POSTGRES
        assert config.postgres is not None

    def test_terraform_cloud_backend(self):
        """Test Terraform Cloud backend configuration."""
        config = BackendConfig(
            type=BackendType.TERRAFORM_CLOUD,
            remote=TerraformCloudBackendConfig(
                organization="my-org",
                workspaces={"name": "prod"},
            ),
        )
        assert config.type == BackendType.TERRAFORM_CLOUD
        assert config.remote is not None

    def test_normalize_type_string(self):
        """Test backend type normalization from string."""
        config = BackendConfig(type="s3", s3=S3BackendConfig(bucket="test", region="us-east-1"))
        assert config.type == BackendType.S3

        config = BackendConfig(type="GCS", gcs=GCSBackendConfig(bucket="test"))
        assert config.type == BackendType.GCS

    def test_get_backend_config_s3(self):
        """Test get_backend_config for S3."""
        config = BackendConfig(
            type=BackendType.S3,
            s3=S3BackendConfig(
                bucket="test-bucket",
                key="custom.tfstate",
                region="us-west-2",
                dynamodb_table="locks",
            ),
        )
        backend_dict = config.get_backend_config()
        assert backend_dict["bucket"] == "test-bucket"
        assert backend_dict["key"] == "custom.tfstate"
        assert backend_dict["region"] == "us-west-2"
        assert backend_dict["dynamodb_table"] == "locks"
        assert backend_dict["encrypt"] is True

    def test_get_backend_config_gcs(self):
        """Test get_backend_config for GCS."""
        config = BackendConfig(
            type=BackendType.GCS,
            gcs=GCSBackendConfig(bucket="test-bucket", prefix="custom/prefix"),
        )
        backend_dict = config.get_backend_config()
        assert backend_dict["bucket"] == "test-bucket"
        assert backend_dict["prefix"] == "custom/prefix"

    def test_get_backend_config_local_default(self):
        """Test get_backend_config for local returns empty dict."""
        config = BackendConfig(type=BackendType.LOCAL)
        backend_dict = config.get_backend_config()
        assert backend_dict == {}

    def test_get_backend_config_missing_config(self):
        """Test get_backend_config fails when config is missing."""
        config = BackendConfig(type=BackendType.S3)  # no s3 config provided
        with pytest.raises(ValueError, match="no configuration provided"):
            config.get_backend_config()

    def test_validate_backend_s3_success(self):
        """Test validate_backend for valid S3 config."""
        config = BackendConfig(
            type=BackendType.S3,
            s3=S3BackendConfig(bucket="test-bucket", region="us-east-1"),
        )
        is_valid, error = config.validate_backend()
        assert is_valid is True
        assert error is None

    def test_validate_backend_s3_missing_bucket(self):
        """Test validate_backend for S3 with missing bucket."""
        # This should fail at Pydantic level, but let's test the validation logic
        config = BackendConfig(type=BackendType.S3, s3=None)
        is_valid, error = config.validate_backend()
        assert is_valid is False
        assert "no configuration provided" in error

    def test_validate_backend_gcs_success(self):
        """Test validate_backend for valid GCS config."""
        config = BackendConfig(
            type=BackendType.GCS,
            gcs=GCSBackendConfig(bucket="test-bucket"),
        )
        is_valid, error = config.validate_backend()
        assert is_valid is True
        assert error is None

    def test_validate_backend_azure_success(self):
        """Test validate_backend for valid Azure config."""
        config = BackendConfig(
            type=BackendType.AZURERM,
            azurerm=AzureBackendConfig(
                resource_group_name="rg",
                storage_account_name="storage",
                container_name="container",
            ),
        )
        is_valid, error = config.validate_backend()
        assert is_valid is True
        assert error is None

    def test_validate_backend_postgres_success(self):
        """Test validate_backend for valid Postgres config."""
        config = BackendConfig(
            type=BackendType.POSTGRES,
            postgres=PostgresBackendConfig(conn_str="postgres://localhost/terraform"),
        )
        is_valid, error = config.validate_backend()
        assert is_valid is True
        assert error is None

    def test_validate_backend_terraform_cloud_success(self):
        """Test validate_backend for valid Terraform Cloud config."""
        config = BackendConfig(
            type=BackendType.TERRAFORM_CLOUD,
            remote=TerraformCloudBackendConfig(
                organization="my-org",
                workspaces={"name": "prod"},
            ),
        )
        is_valid, error = config.validate_backend()
        assert is_valid is True
        assert error is None

    def test_supports_locking_s3_with_dynamodb(self):
        """Test supports_locking returns True for S3 with DynamoDB."""
        config = BackendConfig(
            type=BackendType.S3,
            s3=S3BackendConfig(
                bucket="test-bucket",
                region="us-east-1",
                dynamodb_table="locks",
            ),
        )
        assert config.supports_locking() is True

    def test_supports_locking_s3_without_dynamodb(self):
        """Test supports_locking returns False for S3 without DynamoDB."""
        config = BackendConfig(
            type=BackendType.S3,
            s3=S3BackendConfig(bucket="test-bucket", region="us-east-1"),
        )
        assert config.supports_locking() is False

    def test_supports_locking_gcs(self):
        """Test supports_locking returns True for GCS."""
        config = BackendConfig(
            type=BackendType.GCS,
            gcs=GCSBackendConfig(bucket="test-bucket"),
        )
        assert config.supports_locking() is True

    def test_supports_locking_azure(self):
        """Test supports_locking returns True for Azure."""
        config = BackendConfig(
            type=BackendType.AZURERM,
            azurerm=AzureBackendConfig(
                resource_group_name="rg",
                storage_account_name="storage",
                container_name="container",
            ),
        )
        assert config.supports_locking() is True

    def test_supports_locking_postgres(self):
        """Test supports_locking returns True for Postgres."""
        config = BackendConfig(
            type=BackendType.POSTGRES,
            postgres=PostgresBackendConfig(conn_str="postgres://localhost/terraform"),
        )
        assert config.supports_locking() is True

    def test_supports_locking_terraform_cloud(self):
        """Test supports_locking returns True for Terraform Cloud."""
        config = BackendConfig(
            type=BackendType.TERRAFORM_CLOUD,
            remote=TerraformCloudBackendConfig(
                organization="my-org",
                workspaces={"name": "prod"},
            ),
        )
        assert config.supports_locking() is True

    def test_supports_locking_local(self):
        """Test supports_locking returns False for local."""
        config = BackendConfig(type=BackendType.LOCAL)
        assert config.supports_locking() is False
