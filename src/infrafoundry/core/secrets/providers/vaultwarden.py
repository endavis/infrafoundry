import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from infrafoundry.core.exceptions import SecretError, SecretNotFoundError
from infrafoundry.core.secrets.provider import SecretProvider

logger = logging.getLogger(__name__)


class VaultwardenProvider(SecretProvider):
    """
    Secret provider implementation using Bitwarden CLI (bw).
    Connects to Vaultwarden or Bitwarden servers.
    """

    def __init__(self, session_key: str | None = None) -> None:
        """
        Initialize Vaultwarden provider.

        Args:
            session_key: BW_SESSION key. If None, expects it in environment.
        """
        self.session_key = session_key
        self._ensure_bw_installed()

    def _ensure_bw_installed(self) -> None:
        """Check if bw CLI is installed."""
        try:
            subprocess.run(
                ["bw", "--version"],
                capture_output=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise SecretError(
                "Bitwarden CLI (bw) not found. Please install it to use VaultwardenProvider."
            )

    def _run_bw(self, args: list[str], input_data: str | None = None) -> str:
        """Run Bitwarden CLI command."""
        env = os.environ.copy()
        if self.session_key:
            env["BW_SESSION"] = self.session_key

        try:
            result = subprocess.run(
                ["bw", *args, "--nointeraction"],
                input=input_data,
                capture_output=True,
                check=True,
                text=True,
                env=env,
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.lower()
            if "not found" in stderr:
                raise SecretNotFoundError(f"Bitwarden item not found: {args}")
            raise SecretError(f"Bitwarden CLI error: {e.stderr}") from e

    def load_secret(self, location: str | Path) -> dict[str, Any]:
        """
        Load a secret from Bitwarden.

        Args:
            location: The name or ID of the item in Bitwarden.

        Returns:
            Dictionary containing secret data. Maps 'login' fields and custom 'fields'.
        """
        item_name = str(location)
        try:
            output = self._run_bw(["get", "item", item_name])
            item = json.loads(output)

            secret_data = {}

            # Map standard login fields
            if "login" in item:
                if item["login"].get("username"):
                    secret_data["username"] = item["login"]["username"]
                if item["login"].get("password"):
                    secret_data["password"] = item["login"]["password"]

            # Map custom fields
            if "fields" in item:
                for field in item["fields"]:
                    secret_data[field["name"]] = field["value"]

            # Map notes if present
            if item.get("notes"):
                secret_data["notes"] = item["notes"]

            return secret_data

        except SecretNotFoundError:
            raise
        except Exception as e:
            raise SecretError(f"Failed to load secret {location}: {e}") from e

    def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
        """
        Save a secret to Bitwarden.
        Creates a new item or updates existing one.

        Args:
            location: The name of the item.
            data: Dictionary of data to save.
        """
        item_name = str(location)

        # Prepare the item structure
        item_data: dict[str, Any] = {
            "type": 1,  # Login type
            "name": item_name,
            "login": {},
            "fields": [],
        }

        # Extract standard fields
        if "username" in data:
            item_data["login"]["username"] = data["username"]
        if "password" in data:
            item_data["login"]["password"] = data["password"]

        # Everything else goes to fields or notes
        for k, v in data.items():
            if k in ["username", "password"]:
                continue
            if k == "notes":
                item_data["notes"] = v
            else:
                item_data["fields"].append({"name": k, "value": str(v), "type": 0})

        encoded_data = subprocess.run(
            ["bw", "encode"],
            input=json.dumps(item_data),
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()

        try:
            # Try to get existing item to update
            existing_json = self._run_bw(["get", "item", item_name])
            existing = json.loads(existing_json)
            item_id = existing["id"]

            # Update
            self._run_bw(["edit", "item", item_id], input_data=encoded_data)

        except SecretNotFoundError:
            # Create new
            self._run_bw(["create", "item"], input_data=encoded_data)
        except Exception as e:
            raise SecretError(f"Failed to save secret {location}: {e}") from e
