"""Backend configuration models for Terraform state management."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class BackendType(str, Enum):
    """Supported Terraform backend types."""

    LOCAL = "local"
    S3 = "s3"
    GCS = "gcs"
    AZURERM = "azurerm"
    POSTGRES = "postgres"
    TERRAFORM_CLOUD = "remote"


class S3BackendConfig(BaseModel):
    """AWS S3 backend configuration with DynamoDB locking."""

    bucket: str = Field(..., description="S3 bucket name for state storage")
    key: str = Field(default="terraform.tfstate", description="Path to state file within bucket")
    region: str = Field(..., description="AWS region for S3 bucket")
    dynamodb_table: str | None = Field(
        default=None, description="DynamoDB table name for state locking"
    )
    encrypt: bool = Field(default=True, description="Enable server-side encryption")
    profile: str | None = Field(default=None, description="AWS CLI profile to use")
    role_arn: str | None = Field(default=None, description="IAM role ARN to assume")
    kms_key_id: str | None = Field(default=None, description="KMS key ID for encryption")


class GCSBackendConfig(BaseModel):
    """Google Cloud Storage backend configuration."""

    bucket: str = Field(..., description="GCS bucket name for state storage")
    prefix: str = Field(default="terraform/state", description="Path prefix within bucket")
    credentials: str | None = Field(
        default=None, description="Path to service account key JSON file"
    )
    encryption_key: str | None = Field(default=None, description="Customer-supplied encryption key")


class AzureBackendConfig(BaseModel):
    """Azure Blob Storage backend configuration."""

    resource_group_name: str = Field(..., description="Azure resource group name")
    storage_account_name: str = Field(..., description="Azure storage account name")
    container_name: str = Field(..., description="Azure blob container name")
    key: str = Field(default="terraform.tfstate", description="Blob name for state file")
    access_key: str | None = Field(default=None, description="Storage account access key")
    sas_token: str | None = Field(default=None, description="SAS token for authentication")
    use_azuread_auth: bool = Field(default=False, description="Use Azure AD authentication")


class PostgresBackendConfig(BaseModel):
    """PostgreSQL backend configuration."""

    conn_str: str = Field(..., description="PostgreSQL connection string")
    schema_name: str = Field(default="terraform_remote_state", description="Database schema name")
    skip_schema_creation: bool = Field(default=False, description="Skip automatic schema creation")


class TerraformCloudBackendConfig(BaseModel):
    """Terraform Cloud/Enterprise backend configuration."""

    organization: str = Field(..., description="Terraform Cloud organization name")
    workspaces: dict[str, str] = Field(
        ...,
        description="Workspace configuration (name or prefix mapping)",
    )
    hostname: str | None = Field(
        default=None, description="Terraform Enterprise hostname (optional)"
    )
    token: str | None = Field(default=None, description="Terraform Cloud API token")


class LocalBackendConfig(BaseModel):
    """Local filesystem backend configuration."""

    path: str | None = Field(
        default=None,
        description="Custom path for state file (defaults to terraform.tfstate in working dir)",
    )


class BackendConfig(BaseModel):
    """Unified backend configuration supporting multiple backend types."""

    type: BackendType = Field(default=BackendType.LOCAL, description="Backend type")

    # Type-specific configurations (only one should be set based on type)
    s3: S3BackendConfig | None = None
    gcs: GCSBackendConfig | None = None
    azurerm: AzureBackendConfig | None = None
    postgres: PostgresBackendConfig | None = None
    remote: TerraformCloudBackendConfig | None = None
    local: LocalBackendConfig | None = None

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, v: str | BackendType) -> BackendType:
        """Normalize backend type string to BackendType enum."""
        if isinstance(v, BackendType):
            return v
        return BackendType(v.lower())

    def get_backend_config(self) -> dict[str, Any]:
        """Get the active backend configuration as a dictionary.

        Returns:
            Backend configuration dict ready for Terraform template rendering

        Raises:
            ValueError: If backend type doesn't match configured backend
        """
        backend_map = {
            BackendType.S3: self.s3,
            BackendType.GCS: self.gcs,
            BackendType.AZURERM: self.azurerm,
            BackendType.POSTGRES: self.postgres,
            BackendType.TERRAFORM_CLOUD: self.remote,
            BackendType.LOCAL: self.local,
        }

        config = backend_map.get(self.type)
        if config is None:
            if self.type == BackendType.LOCAL:
                # Local backend is optional, use default
                return {}
            raise ValueError(
                f"Backend type '{self.type}' specified but no configuration provided. "
                f"Expected '{self.type}' field in backend config."
            )

        return config.model_dump(exclude_none=True, mode="json")

    def validate_backend(self) -> tuple[bool, str | None]:
        """Validate backend configuration is complete and consistent.

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            config = self.get_backend_config()

            # Type-specific validation
            if self.type == BackendType.S3:
                if not config.get("bucket"):
                    return False, "S3 backend requires 'bucket' to be specified"
                if not config.get("region"):
                    return False, "S3 backend requires 'region' to be specified"

            elif self.type == BackendType.GCS:
                if not config.get("bucket"):
                    return False, "GCS backend requires 'bucket' to be specified"

            elif self.type == BackendType.AZURERM:
                required = ["resource_group_name", "storage_account_name", "container_name"]
                for field in required:
                    if not config.get(field):
                        return False, f"Azure backend requires '{field}' to be specified"

            elif self.type == BackendType.POSTGRES:
                if not config.get("conn_str"):
                    return False, "Postgres backend requires 'conn_str' to be specified"

            elif self.type == BackendType.TERRAFORM_CLOUD:
                if not config.get("organization"):
                    return False, "Terraform Cloud backend requires 'organization' to be specified"
                if not config.get("workspaces"):
                    return False, "Terraform Cloud backend requires 'workspaces' to be specified"

            return True, None

        except ValueError as e:
            return False, str(e)

    def supports_locking(self) -> bool:
        """Check if the configured backend supports state locking.

        Returns:
            True if backend supports locking, False otherwise
        """
        # S3 with DynamoDB, GCS, Azure, Postgres, and Terraform Cloud support locking
        if self.type == BackendType.S3:
            return self.s3 is not None and self.s3.dynamodb_table is not None
        elif self.type in {
            BackendType.GCS,
            BackendType.AZURERM,
            BackendType.POSTGRES,
            BackendType.TERRAFORM_CLOUD,
        }:
            return True
        return False
