import json
import logging
from pathlib import Path
from typing import Any, cast

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from infrafoundry.core.exceptions import SecretError, SecretNotFoundError
from infrafoundry.core.secrets.provider import SecretProvider

logger = logging.getLogger(__name__)


class AWSSecretsManagerProvider(SecretProvider):
    """
    Secret provider implementation using AWS Secrets Manager.
    """

    def __init__(self, region_name: str | None = None, profile_name: str | None = None) -> None:
        """
        Initialize AWS Secrets Manager provider.

        Args:
            region_name: AWS region name.
            profile_name: AWS profile name.
        """
        try:
            session = boto3.Session(profile_name=profile_name, region_name=region_name)
            self.client = session.client("secretsmanager")
        except Exception as e:
            raise SecretError(f"Failed to create AWS session: {e}") from e

    def load_secret(self, location: str | Path) -> dict[str, Any]:
        """
        Load a secret from AWS Secrets Manager.

        Args:
            location: The SecretId (name or ARN).

        Returns:
            Dictionary containing secret data.
        """
        secret_id = str(location)
        try:
            response = self.client.get_secret_value(SecretId=secret_id)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "ResourceNotFoundException":
                raise SecretNotFoundError(f"AWS Secret not found: {secret_id}") from e
            raise SecretError(f"Failed to load AWS secret {secret_id}: {e}") from e

        if "SecretString" in response:
            secret_string = response["SecretString"]
            try:
                return cast(dict[str, Any], json.loads(secret_string))
            except json.JSONDecodeError:
                # If secret is a plain string, wrap it
                return {"value": secret_string}
        elif "SecretBinary" in response:
            raise SecretError("Binary secrets are not currently supported.")

        return {}

    def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
        """
        Save a secret to AWS Secrets Manager.
        Creates a new secret or updates value of existing one.

        Args:
            location: The SecretId (name).
            data: Dictionary of data to save.
        """
        secret_id = str(location)
        secret_string = json.dumps(data)

        try:
            # Try to update first
            self.client.put_secret_value(SecretId=secret_id, SecretString=secret_string)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "ResourceNotFoundException":
                # Create new
                try:
                    self.client.create_secret(Name=secret_id, SecretString=secret_string)
                except Exception as create_error:
                    raise SecretError(
                        f"Failed to create AWS secret {secret_id}: {create_error}"
                    ) from create_error
            else:
                raise SecretError(f"Failed to save AWS secret {secret_id}: {e}") from e
