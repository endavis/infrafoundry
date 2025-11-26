"""Manages age key and SOPS configuration."""

import os
from pathlib import Path

import yaml


def check_age_key() -> None:
    """Check if age key is configured."""
    age_key_file = os.getenv("SOPS_AGE_KEY_FILE")
    if not age_key_file:
        raise ValueError(
            "SOPS_AGE_KEY_FILE not set. Generate a key with: age-keygen -o envs/{env_name}/age.key"
        )

    age_key_path = Path(age_key_file)
    if not age_key_path.exists():
        raise FileNotFoundError(f"Age key file not found: {age_key_file}")


def create_sops_config(secrets_dir: Path, age_public_key: str) -> None:
    """Create .sops.yaml configuration file.

    Args:
        secrets_dir: Directory to create the .sops.yaml file in.
        age_public_key: Age public key for encryption.
    """
    sops_config = {
        "creation_rules": [
            {
                "path_regex": r".*\.yaml$",
                "age": age_public_key,
            }
        ]
    }

    config_file = secrets_dir / ".sops.yaml"
    with open(config_file, "w") as f:
        yaml.dump(sops_config, f)
