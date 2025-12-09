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
            session_key: BW_SESSION key. If None, tries environment BW_SESSION,
                         or attempts auto-login if credentials are present.
        """
        self.session_key = session_key or os.getenv("BW_SESSION")
        self._ensure_bw_installed()
        self._authenticate_if_needed()

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

    def _authenticate_if_needed(self) -> None:
        """
        Check status and authenticate/unlock if necessary.
        """
        try:
            status_json = self._run_bw(["status"])
            status = json.loads(status_json).get("status")
        except Exception:
            # If status fails, assume unauthenticated
            status = "unauthenticated"

        if status == "unlocked":
            return

        if status == "unauthenticated":
            self._login()
            status = "locked"

        if status == "locked":
            self._unlock()

    def _login(self) -> None:
        """Log in using API Key."""
        client_id = os.getenv("BW_CLIENTID")
        client_secret = os.getenv("BW_CLIENTSECRET")

        if not client_id or not client_secret:
            logger.debug("Cannot auto-login: BW_CLIENTID or BW_CLIENTSECRET missing")
            return

        logger.info("Logging into Bitwarden/Vaultwarden...")
        try:
            # bw login --apikey uses the env vars
            self._run_bw(["login", "--apikey"])
        except Exception as e:
            raise SecretError(f"Failed to login to Bitwarden: {e}") from e

    def _unlock(self) -> None:
        """Unlock the vault using password."""
        if self.session_key:
            # If we have a session key but status says locked, maybe key is invalid?
            # Or we are just checking.
            return

        password = os.getenv("BW_PASSWORD")
        if not password:
            if os.getenv("CI"):
                raise SecretError(
                    "Vault is locked and BW_PASSWORD is not set. Cannot unlock in CI environment."
                )
            logger.debug("Vault is locked and BW_PASSWORD missing. Skipping auto-unlock.")
            return

        logger.info("Unlocking Bitwarden/Vaultwarden vault...")
        try:
            # bw unlock <password> --raw returns just the session key
            key = self._run_bw(["unlock", password, "--raw"])
            self.session_key = key.strip()
            # Export to env so subsequent calls use it
            os.environ["BW_SESSION"] = self.session_key
        except Exception as e:
            raise SecretError(f"Failed to unlock vault: {e}") from e

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
