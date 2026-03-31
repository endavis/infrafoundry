"""Infrastructure package loader.

Discovers and loads infrastructure packages from provider subdirectories.
Each package is a directory containing an infrafoundry.yml manifest that
declares variables, resource templates, and event handlers.

Packages may reference a shared blueprint via ``blueprint: <name>`` in
their manifest.  When a blueprint is referenced the loader merges
blueprint defaults, inherits resources/events/inventory if the package
does not declare its own, and resolves file paths with a
package-first / blueprint-fallback strategy.
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jinja2
import yaml

from infrafoundry.core.config.filters import generate_mac
from infrafoundry.core.config.inventory_generator import InventoryGenerator
from infrafoundry.core.config.models import PackageManifest
from infrafoundry.core.config.sops import load_yaml_with_sops
from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig

if TYPE_CHECKING:
    from infrafoundry.core.config.blueprint_resolver import BlueprintResolver

logger = logging.getLogger(__name__)


class PackageLoader:
    """Loads infrastructure packages from provider subdirectories.

    A package is a subdirectory of a provider directory containing an
    ``infrafoundry.yml`` manifest file. The manifest declares variables,
    resource templates (Jinja2), and event handlers.

    Resource template files are rendered with the manifest's variables
    using Jinja2 with StrictUndefined, then parsed as YAML to produce
    ResourceConfig objects.

    Event handler script paths are rewritten to be relative to the
    environment directory so that ScriptHandler resolves them correctly.
    """

    MANIFEST_FILENAME = "infrafoundry.yml"
    EXCLUDED_DIRS: frozenset[str] = frozenset(
        {
            "roles",
            "tasks",
            "handlers",
            "defaults",
            "vars",
            "meta",
            "files",
            "templates",
            "scripts",
        }
    )
    ENV_ROOT_EXCLUDED_DIRS: frozenset[str] = frozenset(
        {
            "resources",
            "secrets",
        }
    )

    def __init__(
        self,
        base_dir: Path,
        blueprint_resolver: BlueprintResolver | None = None,
    ) -> None:
        """Initialize package loader.

        Args:
            base_dir: Base directory for environment configs (e.g., ./envs)
            blueprint_resolver: Optional resolver for blueprint references.
                When ``None``, packages that declare ``blueprint:`` will
                raise an error.
        """
        self.base_dir = base_dir
        self._blueprint_resolver = blueprint_resolver
        self._inventory_generator = InventoryGenerator()

    def discover_packages(self, env_name: str, provider: str) -> list[Path]:
        """Find subdirectories of a provider directory that contain a manifest.

        Only direct subdirectories are scanned (no recursion). Directories
        whose names appear in EXCLUDED_DIRS are skipped.

        Args:
            env_name: Environment name
            provider: Provider name (e.g., 'proxmox')

        Returns:
            List of package directory paths, sorted by name
        """
        provider_dir = self.base_dir / env_name / provider
        if not provider_dir.exists():
            return []

        packages: list[Path] = []
        for item in sorted(provider_dir.iterdir()):
            if not item.is_dir():
                continue
            if item.name in self.EXCLUDED_DIRS:
                continue
            manifest = item / self.MANIFEST_FILENAME
            if manifest.exists():
                packages.append(item)

        return packages

    def discover_env_root_packages(self, env_name: str) -> list[Path]:
        """Find subdirectories of an environment directory that contain a manifest.

        Scans direct subdirectories of ``envs/{env}/`` for ``infrafoundry.yml``,
        skipping directories in EXCLUDED_DIRS and ENV_ROOT_EXCLUDED_DIRS.
        These are "env-root packages" that are not nested under a provider.

        Args:
            env_name: Environment name

        Returns:
            List of package directory paths, sorted by name
        """
        env_dir = self.base_dir / env_name
        if not env_dir.exists():
            return []

        excluded = self.EXCLUDED_DIRS | self.ENV_ROOT_EXCLUDED_DIRS
        packages: list[Path] = []
        for item in sorted(env_dir.iterdir()):
            if not item.is_dir():
                continue
            if item.name in excluded:
                continue
            manifest = item / self.MANIFEST_FILENAME
            if manifest.exists():
                packages.append(item)

        return packages

    def load_package(
        self, package_dir: Path, provider: str, env_name: str
    ) -> tuple[list[ResourceConfig], dict[str, list[dict[str, Any]]], dict[str, Any]]:
        """Load an infrastructure package.

        Parses the manifest, optionally resolves a blueprint reference,
        merges variables (blueprint defaults < package < secrets),
        renders resource templates, rewrites event handler script paths,
        and generates inventory if declared.

        Args:
            package_dir: Path to the package directory
            provider: Provider name
            env_name: Environment name

        Returns:
            Tuple of (resources, events, variables) where events have
            rewritten script paths and variables is the merged manifest
            variables (including secrets from secrets.yaml)

        Raises:
            InvalidConfigurationError: If manifest or resource files are invalid
        """
        manifest_path = package_dir / self.MANIFEST_FILENAME
        manifest = self._parse_manifest(manifest_path)

        # ----- Blueprint resolution -----
        blueprint: dict[str, Any] | None = None
        blueprint_dir: Path | None = None

        if manifest.blueprint:
            if self._blueprint_resolver is None:
                raise InvalidConfigurationError(
                    f"Package '{manifest.name}' references blueprint "
                    f"'{manifest.blueprint}' but no blueprint resolver is configured"
                )
            blueprint = self._blueprint_resolver.resolve(manifest.blueprint)
            blueprint_dir = blueprint["blueprint_dir"]

            # Merge defaults: blueprint defaults < package variables
            merged_vars: dict[str, Any] = {**blueprint["defaults"], **manifest.variables}
            manifest.variables = merged_vars

            # Inherit resources from blueprint if package doesn't declare its own
            if not manifest.resources and blueprint["resources"]:
                manifest.resources = list(blueprint["resources"])

            # Inherit events from blueprint if package doesn't declare its own
            if not manifest.events and blueprint["events"]:
                manifest.events = dict(blueprint["events"])

            # Inherit inventory from blueprint if package doesn't declare its own
            if manifest.inventory is None and blueprint.get("inventory"):
                manifest.inventory = dict(blueprint["inventory"])

        # ----- Secrets -----
        secrets_path = package_dir / "secrets.yaml"
        if secrets_path.exists():
            secrets_data = load_yaml_with_sops(secrets_path)
            secret_vars = secrets_data.get("variables", {})
            if secret_vars:
                manifest.variables.update(secret_vars)
                logger.info(
                    "Loaded %d secret variable(s) from %s",
                    len(secret_vars),
                    secrets_path.name,
                )

        # Use manifest provider with fallback to directory-inferred provider
        effective_provider = manifest.provider or provider

        logger.debug(
            "Loading package '%s' from %s (provider=%s, env=%s, blueprint=%s)",
            manifest.name,
            package_dir,
            effective_provider,
            env_name,
            manifest.blueprint or "none",
        )

        # ----- Resources -----
        resources: list[ResourceConfig] = []
        for resource_file in manifest.resources:
            resource_path = self._resolve_package_file(resource_file, package_dir, blueprint_dir)
            data = self._render_resource_file(resource_path, manifest.variables)
            parsed = self._parse_resources_from_data(data, resource_file, effective_provider)
            resources.extend(parsed)

        # ----- Events -----
        # Render event configs through Jinja2 to resolve variable references
        # (e.g., requires: ["{{ node01_name }}"] → requires: ["ontapcl-test-01"])
        if manifest.events:
            import json

            events_json = json.dumps(manifest.events)
            try:
                events_env = jinja2.Environment(undefined=jinja2.Undefined)  # nosec B701 - rendering JSON, not HTML
                events_env.filters["generate_mac"] = generate_mac
                events_template = events_env.from_string(events_json)
                rendered_events_json = events_template.render(**manifest.variables)
                manifest.events = json.loads(rendered_events_json)
            except (jinja2.TemplateError, json.JSONDecodeError) as e:
                logger.warning("Failed to render event templates: %s", e)

        env_dir = self.base_dir / env_name
        events = self._rewrite_event_scripts(
            manifest.events, package_dir, env_dir, blueprint_dir=blueprint_dir
        )

        # Tag each handler config with its originating package name
        for _event_key, handler_list in events.items():
            for handler_config in handler_list:
                handler_config["_package"] = manifest.name
                if blueprint_dir:
                    handler_config["_blueprint_dir"] = str(blueprint_dir)

        # Rewrite resource-level event script paths
        for resource in resources:
            if resource.events:
                resource.events = self._rewrite_event_scripts(
                    resource.events, package_dir, env_dir, blueprint_dir=blueprint_dir
                )

        # ----- Inventory generation -----
        if manifest.inventory:
            inventory_path = self._inventory_generator.generate(
                manifest.inventory, manifest.variables, package_dir
            )
            logger.info("Generated inventory for package '%s': %s", manifest.name, inventory_path)

        return resources, events, dict(manifest.variables)

    def _parse_manifest(self, manifest_path: Path) -> PackageManifest:
        """Parse an infrafoundry.yml manifest file.

        Args:
            manifest_path: Path to the manifest file

        Returns:
            PackageManifest instance

        Raises:
            InvalidConfigurationError: If the file is missing, invalid YAML,
                or fails validation
        """
        if not manifest_path.exists():
            raise InvalidConfigurationError(f"Package manifest not found: {manifest_path}")

        try:
            with open(manifest_path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise InvalidConfigurationError(
                f"Invalid YAML in package manifest {manifest_path}: {e}"
            ) from e

        if not data or not isinstance(data, dict):
            raise InvalidConfigurationError(
                f"Package manifest must be a YAML mapping: {manifest_path}"
            )

        try:
            return PackageManifest(**data)
        except Exception as e:
            raise InvalidConfigurationError(f"Invalid package manifest {manifest_path}: {e}") from e

    def _render_resource_file(
        self, resource_path: Path, variables: dict[str, Any]
    ) -> dict[str, Any]:
        """Read a resource template file, render with Jinja2, and parse as YAML.

        Args:
            resource_path: Path to the resource template file
            variables: Variables to substitute in the template

        Returns:
            Parsed YAML data as a dictionary

        Raises:
            InvalidConfigurationError: If the file is missing, has undefined
                variables, or contains invalid YAML after rendering
        """
        if not resource_path.exists():
            raise InvalidConfigurationError(f"Resource file not found: {resource_path}")

        content = resource_path.read_text()

        # Render Jinja2 template with StrictUndefined
        try:
            env = jinja2.Environment(undefined=jinja2.StrictUndefined)  # nosec B701 - rendering YAML, not HTML
            env.filters["generate_mac"] = generate_mac
            template = env.from_string(content)
            rendered = template.render(**variables)
        except jinja2.UndefinedError as e:
            raise InvalidConfigurationError(f"Undefined variable in {resource_path}: {e}") from e
        except jinja2.TemplateSyntaxError as e:
            raise InvalidConfigurationError(f"Template syntax error in {resource_path}: {e}") from e

        # Parse rendered content as YAML
        try:
            data = yaml.safe_load(rendered)
        except yaml.YAMLError as e:
            raise InvalidConfigurationError(
                f"Invalid YAML after rendering {resource_path}: {e}"
            ) from e

        if not data or not isinstance(data, dict):
            return {}

        result: dict[str, Any] = data
        return result

    def _parse_resources_from_data(
        self, data: dict[str, Any], resource_file: str, provider: str
    ) -> list[ResourceConfig]:
        """Extract ResourceConfig objects from parsed YAML data.

        Supports two formats:

        1. **Resource-centric** (``resources:`` key): Each item declares its own
           ``provider`` and ``type``. The parent provider is used as fallback.

        2. **Provider-centric** (type-named key like ``ova_vms:``): Resource type
           is derived from the filename stem. Individual items may override
           ``provider`` via an optional ``provider`` field.

        Args:
            data: Parsed YAML data dictionary
            resource_file: Resource filename (e.g., 'vm.yaml')
            provider: Default provider name (from parent directory)

        Returns:
            List of ResourceConfig objects
        """
        if not data:
            return []

        # Check for resource-centric format first
        if "resources" in data and isinstance(data["resources"], list):
            return self._parse_resource_centric(data["resources"], resource_file, provider)

        # Provider-centric: extract resource type from filename
        stem = Path(resource_file).stem
        resource_type = stem.split("-")[0] if "-" in stem else stem

        # Try singular then plural key
        resource_list = data.get(resource_type, [])
        if not resource_list and not resource_type.endswith("s"):
            plural_type = f"{resource_type}s"
            resource_list = data.get(plural_type, [])

        if not isinstance(resource_list, list):
            raise InvalidConfigurationError(
                f"Expected list for '{resource_type}' in {resource_file}, "
                f"got {type(resource_list).__name__}"
            )

        return [
            ResourceConfig(
                name=item["name"],
                type=resource_type,
                provider=item.get("provider", provider),
                config=item,
                events=item.get("events"),
            )
            for item in resource_list
            if isinstance(item, dict) and "name" in item
        ]

    def _parse_resource_centric(
        self, resources: list[Any], resource_file: str, default_provider: str
    ) -> list[ResourceConfig]:
        """Parse resource-centric format where each item has provider and type.

        Args:
            resources: List of resource dicts with provider, type, name, config
            resource_file: Source filename (for error messages)
            default_provider: Fallback provider if item lacks one

        Returns:
            List of ResourceConfig objects
        """
        result: list[ResourceConfig] = []
        for item in resources:
            if not isinstance(item, dict) or "name" not in item:
                continue
            if "type" not in item:
                raise InvalidConfigurationError(
                    f"Resource '{item.get('name', '?')}' in {resource_file} "
                    f"uses resource-centric format but is missing 'type'"
                )
            config = item.get("config", item)
            if "config" in item and "name" not in config:
                config["name"] = item["name"]
            result.append(
                ResourceConfig(
                    name=item["name"],
                    type=item["type"],
                    provider=item.get("provider", default_provider),
                    config=config,
                    events=item.get("events"),
                )
            )
        return result

    def _resolve_package_file(
        self,
        filename: str,
        package_dir: Path,
        blueprint_dir: Path | None,
    ) -> Path:
        """Resolve a file with package-first, blueprint fallback.

        Args:
            filename: Relative filename to locate.
            package_dir: Package directory (checked first).
            blueprint_dir: Blueprint directory (fallback).  ``None``
                means no fallback.

        Returns:
            Absolute path to the resolved file.

        Raises:
            InvalidConfigurationError: If the file is not found.
        """
        if self._blueprint_resolver and blueprint_dir:
            return self._blueprint_resolver.resolve_file(filename, package_dir, blueprint_dir)

        package_path = package_dir / filename
        if not package_path.exists():
            raise InvalidConfigurationError(f"Resource file not found: {package_path}")
        return package_path

    def _rewrite_event_scripts(
        self,
        events: dict[str, list[dict[str, Any]]],
        package_dir: Path,
        env_dir: Path,
        *,
        blueprint_dir: Path | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Rewrite script paths in event handlers.

        For each handler with type=script, the script path is resolved
        using the package-first / blueprint-fallback strategy.  If the
        script lives in the package dir the path is rewritten relative
        to *env_dir*.  If it lives in the blueprint dir an absolute path
        is stored instead (because the blueprint is outside the env tree).

        Args:
            events: Event handler configurations from the manifest
            package_dir: Path to the package directory
            env_dir: Path to the environment directory
            blueprint_dir: Optional blueprint directory for fallback

        Returns:
            Deep copy of events with rewritten script paths
        """
        if not events:
            return {}

        rewritten = copy.deepcopy(events)

        for _, handlers in rewritten.items():
            for handler in handlers:
                if handler.get("type") == "script" and "script" in handler:
                    script_name = handler["script"]

                    # Resolve script file location
                    resolved = self._resolve_script_path(
                        script_name, package_dir, env_dir, blueprint_dir
                    )
                    handler["script"] = resolved

        return rewritten

    def _resolve_script_path(
        self,
        script_name: str,
        package_dir: Path,
        env_dir: Path,
        blueprint_dir: Path | None,
    ) -> str:
        """Resolve a single script path.

        Args:
            script_name: Script filename from the manifest.
            package_dir: Package directory.
            env_dir: Environment directory.
            blueprint_dir: Optional blueprint directory.

        Returns:
            Rewritten path string (relative to env_dir or absolute for
            blueprint scripts).
        """
        package_script = package_dir / script_name
        if package_script.exists():
            rel_path = package_dir.relative_to(env_dir)
            return str(rel_path / script_name)

        if blueprint_dir:
            blueprint_script = blueprint_dir / script_name
            if blueprint_script.exists():
                return str(blueprint_script)

        # Fall back to package-relative (original behaviour)
        rel_path = package_dir.relative_to(env_dir)
        return str(rel_path / script_name)
