"""Move infrastructure packages between environments.

Handles relocating a package's configuration directory, copying terraform
state, removing moved resources from the source state, and updating the
InfraFoundry state database.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.models import PackageManifest
from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import (
    ConfigurationError,
    EnvironmentNotFoundError,
    PackageNotFoundError,
)
from infrafoundry.core.runners.terraform_runner import TerraformRunner

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = PackageLoader.MANIFEST_FILENAME


class PackageMover:
    """Moves a package between environments safely.

    Orchestrates the full move: config directory relocation, terraform
    state copy + selective removal, and state DB updates.
    """

    def __init__(
        self,
        config_dir: Path,
        generated_dir: Path,
        terraform_runner: TerraformRunner | None = None,
    ) -> None:
        """Initialize package mover.

        Args:
            config_dir: Path to config repo root (contains envs/)
            generated_dir: Path to generated/ directory
            terraform_runner: Optional terraform runner instance.
                Creates a default one if not provided.
        """
        self.config_dir = config_dir
        self.generated_dir = generated_dir
        self._terraform_runner = terraform_runner or TerraformRunner()

    @property
    def envs_dir(self) -> Path:
        """Return the envs/ directory path."""
        return self.config_dir / "envs"

    def find_package(self, env_name: str, package_name: str) -> tuple[Path, str]:
        """Find a package in an environment.

        Searches provider subdirectories first, then the env root.

        Args:
            env_name: Environment name
            package_name: Package name to find

        Returns:
            Tuple of (package_path, provider_name)

        Raises:
            PackageNotFoundError: If the package is not found
            EnvironmentNotFoundError: If the environment directory does not exist
        """
        env_dir = self.envs_dir / env_name
        if not env_dir.exists():
            raise EnvironmentNotFoundError(f"Environment '{env_name}' not found at {env_dir}")

        # Search provider subdirectories
        for item in sorted(env_dir.iterdir()):
            if not item.is_dir():
                continue
            if item.name in PackageLoader.EXCLUDED_DIRS | PackageLoader.ENV_ROOT_EXCLUDED_DIRS:
                continue
            # Check if this is a provider directory containing packages
            for sub in sorted(item.iterdir()):
                if not sub.is_dir():
                    continue
                manifest_path = sub / MANIFEST_FILENAME
                if manifest_path.exists():
                    manifest = self._parse_manifest(manifest_path)
                    if manifest.name == package_name:
                        return sub, item.name

        # Search env root packages
        for item in sorted(env_dir.iterdir()):
            if not item.is_dir():
                continue
            if item.name in PackageLoader.EXCLUDED_DIRS | PackageLoader.ENV_ROOT_EXCLUDED_DIRS:
                continue
            manifest_path = item / MANIFEST_FILENAME
            if manifest_path.exists():
                manifest = self._parse_manifest(manifest_path)
                if manifest.name == package_name:
                    provider = manifest.provider or ""
                    if not provider:
                        raise PackageNotFoundError(
                            f"Package '{package_name}' in env root has no provider field "
                            f"in its manifest. Cannot determine provider for state operations."
                        )
                    return item, provider

        raise PackageNotFoundError(
            f"Package '{package_name}' not found in environment '{env_name}'"
        )

    def get_terraform_addresses(
        self, env_name: str, provider_name: str, package_path: Path
    ) -> dict[str, list[str]]:
        """Get terraform state addresses for resources in a package.

        Uses the full PackageLoader rendering pipeline to get actual
        resource names (including those from Jinja2 loops and blueprints),
        then matches against terraform state across all providers.

        Args:
            env_name: Environment name
            provider_name: Provider name (primary provider for the package)
            package_path: Path to the package directory

        Returns:
            Dict mapping provider names to lists of terraform addresses.
            Includes the primary provider and any cross-provider resources.
        """
        resource_names = self._get_rendered_resource_names(env_name, provider_name, package_path)
        if not resource_names:
            return {}

        # Build set of terraform name variants for matching
        tf_names: set[str] = set()
        for name in resource_names:
            tf_names.add(name.replace("-", "_"))

        # Check all provider state directories (handles cross-provider resources)
        terraform_base = self.generated_dir / env_name / "terraform"
        if not terraform_base.exists():
            return {}

        result: dict[str, list[str]] = {}
        for provider_dir in sorted(terraform_base.iterdir()):
            if not provider_dir.is_dir():
                continue
            state_file = provider_dir / "terraform.tfstate"
            if not state_file.exists():
                continue

            all_addresses = self._terraform_runner.state_list(provider_dir)
            if not all_addresses:
                continue

            matched: list[str] = []
            for address in all_addresses:
                parts = address.rsplit(".", 1)
                if len(parts) != 2:
                    continue
                tf_name = parts[1]
                # Match exact name or name as suffix (e.g., cloud_init_user_data_aiqum)
                for expected in tf_names:
                    if tf_name == expected or tf_name.endswith(f"_{expected}"):
                        matched.append(address)
                        break

            if matched:
                result[provider_dir.name] = matched

        return result

    def _get_rendered_resource_names(
        self, env_name: str, provider_name: str, package_path: Path
    ) -> list[str]:
        """Load a package through the full rendering pipeline to get resource names.

        Falls back to manifest name + key variables if rendering fails
        (e.g., missing secrets for Jinja2 StrictUndefined).

        Args:
            env_name: Environment name
            provider_name: Provider name
            package_path: Path to the package directory

        Returns:
            List of resource names
        """
        try:
            resolver = BlueprintResolver(self.envs_dir)
            loader = PackageLoader(
                base_dir=self.envs_dir,
                blueprint_resolver=resolver,
            )
            resources, _, _ = loader.load_package(package_path, provider_name, env_name)
            names = [r.name for r in resources]
            if names:
                return names
        except Exception as exc:
            logger.debug("Full package rendering failed, using fallback: %s", exc)

        # Fallback: use package name + key variables
        manifest = self._parse_manifest(package_path / MANIFEST_FILENAME)
        names = [manifest.name]
        for key in ("vm_name", "server_name", "control_name", "template_name"):
            value = manifest.variables.get(key)
            if value and isinstance(value, str) and value not in names:
                names.append(value)
        return names

    def execute(
        self,
        source_env: str,
        package_name: str,
        target_env: str,
        create_env: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Execute the full package move.

        Args:
            source_env: Source environment name
            package_name: Package name to move
            target_env: Target environment name
            create_env: Create target environment if it doesn't exist
            dry_run: Show what would be done without executing

        Returns:
            Dict with summary of actions taken

        Raises:
            PackageNotFoundError: If the source package is not found
            EnvironmentNotFoundError: If the target env does not exist
                and create_env is False
            ConfigurationError: If the target already contains the package
        """
        actions: list[str] = []

        # 1. Find source package
        source_path, provider_name = self.find_package(source_env, package_name)
        actions.append(
            f"Found package '{package_name}' at {source_path} (provider: {provider_name})"
        )

        # 2. Validate target environment
        target_env_dir = self.envs_dir / target_env
        if not target_env_dir.exists():
            if create_env:
                actions.append(f"Create target environment directory: {target_env_dir}")
                if not dry_run:
                    target_env_dir.mkdir(parents=True, exist_ok=True)
            else:
                raise EnvironmentNotFoundError(
                    f"Target environment '{target_env}' not found. Use --create-env to create it."
                )

        # 3. Determine target package path (flat, no provider subdir)
        target_package_dir = target_env_dir / source_path.name
        if target_package_dir.exists():
            raise ConfigurationError(
                f"Target directory already exists: {target_package_dir}. "
                f"Remove it first or choose a different target."
            )
        actions.append(f"Move config: {source_path} -> {target_package_dir}")

        # 4. Check manifest for provider field
        manifest = self._parse_manifest(source_path / MANIFEST_FILENAME)
        needs_provider_field = manifest.provider is None
        if needs_provider_field:
            actions.append(f"Add 'provider: {provider_name}' to manifest")

        # 5. Terraform state operations
        # Get addresses across ALL providers (handles cross-provider resources)
        addresses_by_provider = self.get_terraform_addresses(source_env, provider_name, source_path)

        # Plan state copy for each provider that has matching resources
        providers_to_copy: list[str] = []
        for prov in sorted(addresses_by_provider):
            source_tf_dir = self.generated_dir / source_env / "terraform" / prov
            target_tf_dir = self.generated_dir / target_env / "terraform" / prov
            source_state_file = source_tf_dir / "terraform.tfstate"
            target_state_file = target_tf_dir / "terraform.tfstate"

            if source_state_file.exists() and not target_state_file.exists():
                providers_to_copy.append(prov)
                actions.append(f"Copy state file: {source_state_file} -> {target_state_file}")
                source_backup = source_tf_dir / "terraform.tfstate.backup"
                if source_backup.exists():
                    actions.append(
                        f"Copy state backup: {source_backup} -> "
                        f"{target_tf_dir / 'terraform.tfstate.backup'}"
                    )
            elif source_state_file.exists():
                actions.append(f"Skip state copy for {prov}: target already has terraform.tfstate")

        # Also copy primary provider state even if no addresses matched
        primary_source = self.generated_dir / source_env / "terraform" / provider_name
        primary_target = self.generated_dir / target_env / "terraform" / provider_name
        if (
            primary_source.exists()
            and (primary_source / "terraform.tfstate").exists()
            and not (primary_target / "terraform.tfstate").exists()
            and provider_name not in providers_to_copy
        ):
            providers_to_copy.append(provider_name)
            actions.append(
                f"Copy state file: {primary_source / 'terraform.tfstate'} -> "
                f"{primary_target / 'terraform.tfstate'}"
            )

        total_addresses = sum(len(addrs) for addrs in addresses_by_provider.values())
        if addresses_by_provider:
            for prov, addrs in sorted(addresses_by_provider.items()):
                for addr in addrs:
                    actions.append(f"terraform state rm (source {prov}): {addr}")
        else:
            has_any_state = any(
                (self.generated_dir / source_env / "terraform" / p / "terraform.tfstate").exists()
                for p in [provider_name]
            )
            if has_any_state:
                actions.append("No matching terraform state addresses found for package resources")
            else:
                actions.append("No source terraform state file found (config-only move)")

        # 6. State DB update
        actions.append(f"Update state DB: move resources from '{source_env}' to '{target_env}'")

        # 7. Remove source directory
        actions.append(f"Remove source directory: {source_path}")

        if dry_run:
            return {
                "dry_run": True,
                "actions": actions,
                "source_path": str(source_path),
                "target_path": str(target_package_dir),
                "provider": provider_name,
                "state_addresses": addresses_by_provider,
            }

        # --- Execute ---

        # Move config directory
        shutil.copytree(source_path, target_package_dir)

        # Add provider field to manifest if needed
        if needs_provider_field:
            self._add_provider_to_manifest(target_package_dir / MANIFEST_FILENAME, provider_name)

        # Copy terraform state for each provider
        for prov in providers_to_copy:
            src_tf = self.generated_dir / source_env / "terraform" / prov
            tgt_tf = self.generated_dir / target_env / "terraform" / prov
            tgt_tf.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_tf / "terraform.tfstate", tgt_tf / "terraform.tfstate")

            backup = src_tf / "terraform.tfstate.backup"
            if backup.exists():
                shutil.copy2(backup, tgt_tf / "terraform.tfstate.backup")

            # Copy .terraform directory for provider plugins
            src_dot_tf = src_tf / ".terraform"
            tgt_dot_tf = tgt_tf / ".terraform"
            if src_dot_tf.exists() and not tgt_dot_tf.exists():
                shutil.copytree(src_dot_tf, tgt_dot_tf)

        # Remove resources from source terraform state (all providers)
        rm_results: list[dict[str, Any]] = []
        for prov, addrs in sorted(addresses_by_provider.items()):
            src_tf = self.generated_dir / source_env / "terraform" / prov
            for addr in addrs:
                success = self._terraform_runner.state_rm(src_tf, addr)
                rm_results.append({"provider": prov, "address": addr, "success": success})

        # Update state DB
        db_updated = self._update_state_db(source_env, target_env, provider_name, package_name)

        # Remove source config directory
        shutil.rmtree(source_path)

        return {
            "dry_run": False,
            "actions": actions,
            "source_path": str(source_path),
            "target_path": str(target_package_dir),
            "provider": provider_name,
            "state_addresses": addresses_by_provider,
            "state_rm_results": rm_results,
            "state_rm_count": total_addresses,
            "state_db_updated": db_updated,
        }

    def _parse_manifest(self, manifest_path: Path) -> PackageManifest:
        """Parse an infrafoundry.yml manifest file.

        Args:
            manifest_path: Path to the manifest file

        Returns:
            PackageManifest instance

        Raises:
            ConfigurationError: If the manifest cannot be parsed
        """
        if not manifest_path.exists():
            raise ConfigurationError(f"Manifest not found: {manifest_path}")

        try:
            text = manifest_path.read_text()
        except OSError as e:
            raise ConfigurationError(f"Failed to read manifest {manifest_path}: {e}") from e

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in {manifest_path}: {e}") from e

        if not data or not isinstance(data, dict):
            raise ConfigurationError(f"Manifest must be a YAML mapping: {manifest_path}")

        # Filter out keys not in PackageManifest to avoid validation errors
        # (e.g. inventory raw text from extraction)
        valid_fields = set(PackageManifest.model_fields.keys())
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return PackageManifest(**filtered)

    def _extract_resource_names(self, package_path: Path, manifest: PackageManifest) -> list[str]:
        """Extract resource names from a package's resource files.

        Reads each resource file listed in the manifest and extracts
        the ``name`` field from resource definitions.

        Args:
            package_path: Path to the package directory
            manifest: Parsed package manifest

        Returns:
            List of resource names
        """
        names: list[str] = []
        for resource_file in manifest.resources:
            resource_path = package_path / resource_file
            if not resource_path.exists():
                continue
            try:
                data = yaml.safe_load(resource_path.read_text())
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(data, dict):
                continue

            # Resource-centric format
            if "resources" in data and isinstance(data["resources"], list):
                for item in data["resources"]:
                    if isinstance(item, dict) and "name" in item:
                        names.append(item["name"])
                continue

            # Provider-centric format: look for list values containing dicts with "name"
            for value in data.values():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and "name" in item:
                            names.append(item["name"])

        return names

    def _add_provider_to_manifest(self, manifest_path: Path, provider_name: str) -> None:
        """Add a provider field to a manifest file.

        Inserts ``provider: <name>`` after the ``name:`` line to preserve
        readability.

        Args:
            manifest_path: Path to the manifest file
            provider_name: Provider name to add
        """
        lines = manifest_path.read_text().splitlines(keepends=True)
        new_lines: list[str] = []
        inserted = False

        for line in lines:
            new_lines.append(line)
            if not inserted and line.strip().startswith("name:"):
                # Insert provider line after name line
                indent = len(line) - len(line.lstrip())
                provider_line = f"{' ' * indent}provider: {provider_name}\n"
                new_lines.append(provider_line)
                inserted = True

        if not inserted:
            # Fallback: prepend provider line
            new_lines.insert(0, f"provider: {provider_name}\n")

        manifest_path.write_text("".join(new_lines))

    def _update_state_db(
        self,
        source_env: str,
        target_env: str,
        provider_name: str,
        package_name: str,
    ) -> bool:
        """Update resource records in the InfraFoundry state DB.

        Moves resources belonging to the package from source to target
        environment. Silently skips if the state DB is not available.

        Args:
            source_env: Source environment name
            target_env: Target environment name
            provider_name: Provider name
            package_name: Package name (used for logging)

        Returns:
            True if resources were updated, False if skipped
        """
        try:
            from infrafoundry.core.state.state_manager import StateManager

            state_mgr = StateManager()
            state_mgr.initialize()

            resources = state_mgr.get_resources(environment=source_env, provider=provider_name)

            updated_count = 0
            for resource in resources:
                # Update environment field directly via session
                with state_mgr.SessionLocal() as session:
                    from infrafoundry.core.state.models import Resource

                    db_resource = session.query(Resource).filter_by(id=resource.id).first()
                    if db_resource:
                        db_resource.environment = target_env
                        session.commit()
                        updated_count += 1

            if updated_count > 0:
                logger.info(
                    "Updated %d resource(s) in state DB from '%s' to '%s' for package '%s'",
                    updated_count,
                    source_env,
                    target_env,
                    package_name,
                )
                return True
            return False

        except Exception as e:
            logger.debug("State DB update skipped: %s", e)
            return False
