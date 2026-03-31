"""Refactored configuration manager - coordinates between loaders."""

import os
import warnings
from pathlib import Path
from typing import Any

import yaml

from infrafoundry.core.base_manager import PathBasedManager
from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.models import EnvironmentConfig, IaCTool
from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.config.provider_centric_loader import ProviderCentricLoader
from infrafoundry.core.config.resource_centric_loader import ResourceCentricLoader
from infrafoundry.core.config.sops import load_yaml_with_sops
from infrafoundry.core.exceptions import InvalidConfigurationError, PackageNotFoundError
from infrafoundry.core.provider import ResourceConfig


class ConfigManager(PathBasedManager):
    """Manages configuration loading and validation.

    Coordinates between ProviderCentricLoader and ResourceCentricLoader
    to support both configuration formats.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        """Initialize configuration manager.

        Args:
            base_dir: Base directory for configs
                (defaults to INFRAFOUNDRY_CONFIG_REPO/envs)

        Raises:
            ValueError: If base_dir is None and INFRAFOUNDRY_CONFIG_REPO is not set
        """
        # Initialize base manager with logging
        super().__init__()

        # Resolve base directory using PathBasedManager pattern
        if base_dir is None:
            config_repo = self._get_env_var("INFRAFOUNDRY_CONFIG_REPO")
            if not config_repo:
                raise ValueError(
                    "INFRAFOUNDRY_CONFIG_REPO environment variable must be set. "
                    "Please point it to your configuration repository. "
                    "See docs/configuration/separate-config-repo.md for setup instructions."
                )
            # Config repo is specified - use its envs subdirectory
            base_dir = Path(config_repo) / "envs"

        self.base_dir: Path = base_dir  # Type assertion - base_dir is always Path here
        self._log_debug(f"Initialized ConfigManager with base_dir: {self.base_dir}")

        # Initialize blueprint resolver and loaders
        self._blueprint_resolver = BlueprintResolver(base_dir)
        self.provider_centric = ProviderCentricLoader(base_dir, self._blueprint_resolver)
        self.resource_centric = ResourceCentricLoader(base_dir)
        self._package_loader = PackageLoader(base_dir, self._blueprint_resolver)

    def load_environment(self, env_name: str) -> EnvironmentConfig:
        """Load environment configuration.

        Args:
            env_name: Environment name (e.g., 'dev', 'prod')

        Returns:
            EnvironmentConfig object

        Raises:
            FileNotFoundError: If environment config doesn't exist
        """
        settings_file = self.base_dir / env_name / "settings.yaml"

        if not settings_file.exists():
            error_msg = f"Environment config not found: {settings_file}"
            self._log_error(error_msg)
            raise FileNotFoundError(error_msg)

        self._log_debug(f"Loading environment config: {env_name}")
        try:
            data = self._load_yaml_with_sops(settings_file)
        except yaml.YAMLError as e:
            error_msg = f"Invalid YAML in {settings_file}: {e}"
            self._log_error(error_msg)
            raise InvalidConfigurationError(error_msg) from e

        if not data:
            # Ensure we return an empty but valid EnvironmentConfig if file is empty
            data = {}

        # Environment variable override for IaC tool selection
        iac_tool_env = os.getenv("INFRAFOUNDRY_IAC_TOOL")
        if iac_tool_env:
            try:
                IaCTool(iac_tool_env)  # Validate the value
                data["iac_tool"] = iac_tool_env
            except ValueError:
                self._log_warning(f"Invalid INFRAFOUNDRY_IAC_TOOL value '{iac_tool_env}', ignoring")

        self._log_debug(f"Loaded environment config: {env_name}")
        return EnvironmentConfig(**data)

    @staticmethod
    def _load_yaml_with_sops(file_path: Path) -> dict[str, Any]:
        """Load a YAML file, decrypting with SOPS if encrypted.

        Delegates to the shared :func:`~infrafoundry.core.config.sops.load_yaml_with_sops`
        utility.

        Args:
            file_path: Path to the YAML file.

        Returns:
            Parsed YAML data as a dictionary.
        """
        return load_yaml_with_sops(file_path)

    def load_resources(
        self, env_name: str, provider: str, resource_file: str
    ) -> list[ResourceConfig]:
        """Load resource configurations for a provider from a specific file.

        Delegates to ProviderCentricLoader.

        Args:
            env_name: Environment name
            provider: Provider name (e.g., 'proxmox')
            resource_file: Resource filename without extension (e.g., 'vm', 'vm-01')

        Returns:
            List of ResourceConfig objects
        """
        return self.provider_centric.load_resources(env_name, provider, resource_file)

    def load_resource_centric_files(self, env_name: str) -> list[ResourceConfig]:
        """Load resource-centric configuration files.

        Delegates to ResourceCentricLoader.

        Args:
            env_name: Environment name

        Returns:
            List of ResourceConfig objects from all resource-centric files
        """
        return self.resource_centric.load_resources(env_name)

    def get_all_resources(self, env_name: str, provider: str) -> list[ResourceConfig]:
        """Load all resources for a provider in an environment.

        Supports both provider-centric and resource-centric formats:
        - Provider-centric: envs/{env}/{provider}/*.yaml
        - Resource-centric: envs/{env}/resources/*.yaml

        Args:
            env_name: Environment name
            provider: Provider name

        Returns:
            List of all ResourceConfig objects for the provider
        """
        all_resources = []

        # Load from provider-centric structure
        all_resources.extend(self.provider_centric.get_all_resources(env_name, provider))

        # Load from resource-centric structure
        all_resources.extend(self.resource_centric.get_resources_for_provider(env_name, provider))

        return all_resources

    def get_all_resources_all_providers(self, env_name: str) -> list[ResourceConfig]:
        """Load all resources from all providers in an environment.

        Supports both provider-centric and resource-centric formats.
        Discovers providers dynamically from available resources.

        Args:
            env_name: Environment name

        Returns:
            List of all ResourceConfig objects from all providers

        Raises:
            ValueError: If duplicate resource names are found
        """
        all_resources = []
        resource_locations: dict[str, list[str]] = {}  # Track where each resource is defined
        loose_resource_files: list[str] = []  # Track loose resource files for deprecation

        # Discover and load from provider-centric directories
        discovered_providers = self.provider_centric.discover_providers(env_name)

        for provider_name in discovered_providers:
            provider_dir = self.base_dir / env_name / provider_name
            for config_file in provider_dir.glob("*.yaml"):
                if config_file.name == "settings.yaml":
                    continue

                resource_file = config_file.stem
                resources = self.provider_centric.load_resources(
                    env_name, provider_name, resource_file
                )

                # Track location for each resource
                for resource in resources:
                    key = f"{resource.provider}:{resource.name}"
                    if key not in resource_locations:
                        resource_locations[key] = []
                    resource_locations[key].append(str(config_file))

                if resources:
                    loose_resource_files.append(str(config_file))

                all_resources.extend(resources)

        # Clear any stale package events from previous calls (e.g., from
        # build_dependency_graph) that did not drain the buffer.
        self.provider_centric._pending_package_events = {}

        # Load from infrastructure packages in provider subdirectories
        for provider_name in discovered_providers:
            for package_dir in self.provider_centric._package_loader.discover_packages(
                env_name, provider_name
            ):
                pkg_resources, pkg_events, pkg_vars = (
                    self.provider_centric._package_loader.load_package(
                        package_dir, provider_name, env_name
                    )
                )
                # Attach package variables to each resource
                for resource in pkg_resources:
                    if pkg_vars:
                        resource.package_variables = pkg_vars
                    key = f"{resource.provider}:{resource.name}"
                    if key not in resource_locations:
                        resource_locations[key] = []
                    resource_locations[key].append(str(package_dir / "infrafoundry.yml"))

                all_resources.extend(pkg_resources)
                for event_type, handlers in pkg_events.items():
                    self.provider_centric._pending_package_events.setdefault(event_type, []).extend(
                        handlers
                    )

        # Load env-root packages (directories at envs/{env}/ with infrafoundry.yml)
        for package_dir in self._package_loader.discover_env_root_packages(env_name):
            manifest = self._package_loader._parse_manifest(
                package_dir / PackageLoader.MANIFEST_FILENAME
            )
            if not manifest.provider:
                raise InvalidConfigurationError(
                    f"Env-root package '{manifest.name}' at {package_dir} "
                    f"must declare a 'provider' field in its manifest. "
                    f"Provider cannot be inferred for packages outside provider directories."
                )
            pkg_resources, pkg_events, pkg_vars = self._package_loader.load_package(
                package_dir, manifest.provider, env_name
            )
            # Attach package variables to each resource
            for resource in pkg_resources:
                if pkg_vars:
                    resource.package_variables = pkg_vars
                key = f"{resource.provider}:{resource.name}"
                if key not in resource_locations:
                    resource_locations[key] = []
                resource_locations[key].append(str(package_dir / "infrafoundry.yml"))

            all_resources.extend(pkg_resources)
            for event_type, handlers in pkg_events.items():
                self.provider_centric._pending_package_events.setdefault(event_type, []).extend(
                    handlers
                )

        # Load from resource-centric files
        resources_dir = self.base_dir / env_name / "resources"
        if resources_dir.exists():
            for config_file in resources_dir.glob("*.yaml"):
                resources = self.resource_centric._load_single_file(config_file)

                # Track location for each resource
                for resource in resources:
                    key = f"{resource.provider}:{resource.name}"
                    if key not in resource_locations:
                        resource_locations[key] = []
                    resource_locations[key].append(str(config_file))

                if resources:
                    loose_resource_files.append(str(config_file))

                all_resources.extend(resources)

        # Emit deprecation warnings for loose resources (not in packages)
        if loose_resource_files:
            file_list = ", ".join(loose_resource_files)
            warnings.warn(
                f"Loose resources (not in packages) are deprecated and will be "
                f"removed in a future release. Migrate these files to infrastructure "
                f"packages with an infrafoundry.yml manifest: {file_list}",
                DeprecationWarning,
                stacklevel=2,
            )

        # Check for duplicate resource names
        duplicates = [
            f"{key} found in: {', '.join(locations)}"
            for key, locations in resource_locations.items()
            if len(locations) > 1
        ]

        if duplicates:
            raise ValueError(
                f"Duplicate resource names found in environment '{env_name}':\n  "
                + "\n  ".join(duplicates)
                + "\n\nEach resource name must be unique within its provider."
            )

        return all_resources

    def get_package_events(self) -> dict[str, list[dict[str, Any]]]:
        """Return accumulated package events from last resource load.

        Package events are discovered during resource loading and buffered
        in the ProviderCentricLoader. This method retrieves and clears them.

        Returns:
            Dict mapping event type names to handler configs
        """
        return self.provider_centric.get_package_events()

    def list_environments(self) -> list[str]:
        """List all available environments.

        Returns:
            List of environment names
        """
        if not self.base_dir.exists():
            return []

        return [d.name for d in self.base_dir.iterdir() if d.is_dir()]

    def validate_environment(self, env_name: str) -> bool:
        """Validate that an environment exists and has proper structure.

        Args:
            env_name: Environment name to validate

        Returns:
            True if valid, False otherwise
        """
        env_dir = self.base_dir / env_name
        if not env_dir.exists():
            self._log_warning(f"Environment directory not found: {env_dir}")
            return False

        env_file = env_dir / "settings.yaml"
        is_valid = env_file.exists()

        if is_valid:
            self._log_debug(f"Environment {env_name} is valid")
        else:
            self._log_warning(f"Environment {env_name} missing settings.yaml")

        return is_valid

    def resolve_package_filter(self, env_name: str, package_name: str) -> list[str]:
        """Resolve a package name to a list of unique resource names.

        Searches both provider-scoped and env-root packages for a package
        whose manifest name matches *package_name*, then returns the names
        of all resources declared by that package.

        Args:
            env_name: Environment name
            package_name: Package name to resolve

        Returns:
            List of unique resource names belonging to the package

        Raises:
            PackageNotFoundError: If no package with the given name is found
        """
        # Check provider-scoped packages
        discovered_providers = self.provider_centric.discover_providers(env_name)
        for provider_name in discovered_providers:
            for package_dir in self._package_loader.discover_packages(env_name, provider_name):
                manifest = self._package_loader._parse_manifest(
                    package_dir / PackageLoader.MANIFEST_FILENAME
                )
                if manifest.name == package_name:
                    effective_provider = manifest.provider or provider_name
                    pkg_resources, _, _pkg_vars = self._package_loader.load_package(
                        package_dir, effective_provider, env_name
                    )
                    return list(dict.fromkeys(r.name for r in pkg_resources))

        # Check env-root packages
        for package_dir in self._package_loader.discover_env_root_packages(env_name):
            manifest = self._package_loader._parse_manifest(
                package_dir / PackageLoader.MANIFEST_FILENAME
            )
            if manifest.name == package_name:
                if not manifest.provider:
                    continue
                pkg_resources, _, _pkg_vars = self._package_loader.load_package(
                    package_dir, manifest.provider, env_name
                )
                return list(dict.fromkeys(r.name for r in pkg_resources))

        raise PackageNotFoundError(
            f"Package '{package_name}' not found in environment '{env_name}'"
        )

    def cleanup(self) -> None:
        """Cleanup resources (required by BaseManager).

        No cleanup needed for ConfigManager as it doesn't maintain
        persistent connections or file handles.
        """
        self._log_debug("ConfigManager cleanup complete")
