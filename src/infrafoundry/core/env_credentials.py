"""Environment-specific credential loading."""

import os
import subprocess
from pathlib import Path
from typing import Any

import yaml


def load_environment_credentials(env_name: str, config_dir: Path | None = None) -> dict[str, str]:
    """Load environment-specific credentials from encrypted secrets.

    Automatically loads credentials for the specified environment from:
    - secrets/{env}/proxmox.yaml
    - secrets/{env}/opnsense.yaml
    - secrets/{env}/kubernetes.yaml

    Credentials are decrypted using SOPS and returned as environment variables
    that can be set for the current process.

    Args:
        env_name: Environment name (e.g., 'dev', 'staging', 'prod')
        config_dir: Configuration directory (defaults to INFRAFOUNDRY_CONFIG_REPO or cwd)

    Returns:
        Dictionary of environment variables to set (e.g., {'PROXMOX_API_URL': '...', ...})

    Example:
        >>> env_vars = load_environment_credentials('dev')
        >>> os.environ.update(env_vars)
        # Now PROXMOX_API_URL, PROXMOX_API_TOKEN_ID, etc. are set for dev environment
    """
    # Determine secrets directory
    if config_dir is None:
        config_repo = os.getenv("INFRAFOUNDRY_CONFIG_REPO")
        config_dir = Path(config_repo) if config_repo else Path.cwd()

    secrets_dir = config_dir / "secrets" / env_name

    if not secrets_dir.exists():
        # No environment-specific secrets, fall back to environment variables
        return {}

    env_vars = {}

    # Load Proxmox credentials
    proxmox_file = secrets_dir / "proxmox.yaml"
    if proxmox_file.exists():
        try:
            proxmox_creds = _decrypt_sops_file(proxmox_file)
            if proxmox_creds:
                env_vars["PROXMOX_API_URL"] = proxmox_creds.get("proxmox_api_url", "")
                env_vars["PROXMOX_API_TOKEN_ID"] = proxmox_creds.get("proxmox_token_id", "")
                env_vars["PROXMOX_API_TOKEN_SECRET"] = proxmox_creds.get("proxmox_token_secret", "")
        except Exception:
            # If decryption fails, skip (credentials may be in env vars already)
            pass

    # Load OPNsense credentials
    opnsense_file = secrets_dir / "opnsense.yaml"
    if opnsense_file.exists():
        try:
            opnsense_creds = _decrypt_sops_file(opnsense_file)
            if opnsense_creds:
                env_vars["OPNSENSE_API_URL"] = opnsense_creds.get("opnsense_api_url", "")
                env_vars["OPNSENSE_API_KEY"] = opnsense_creds.get("opnsense_api_key", "")
                env_vars["OPNSENSE_API_SECRET"] = opnsense_creds.get("opnsense_api_secret", "")
        except Exception:
            pass

    # Load Kubernetes credentials
    kubernetes_file = secrets_dir / "kubernetes.yaml"
    if kubernetes_file.exists():
        try:
            k8s_creds = _decrypt_sops_file(kubernetes_file)
            if k8s_creds:
                env_vars["KUBECONFIG"] = k8s_creds.get("kubeconfig", "")
        except Exception:
            pass

    return env_vars


def _decrypt_sops_file(file_path: Path) -> dict[str, Any]:
    """Decrypt a SOPS-encrypted YAML file.

    Args:
        file_path: Path to encrypted file

    Returns:
        Decrypted data as dictionary

    Raises:
        subprocess.CalledProcessError: If SOPS decryption fails
        FileNotFoundError: If sops command not found
    """
    try:
        result = subprocess.run(
            ["sops", "--decrypt", str(file_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        return yaml.safe_load(result.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError):
        # If SOPS fails, return empty dict (will use env vars)
        return {}
