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

from infrafoundry.core.config.filters import create_jinja2_env
from infrafoundry.core.config.inventory_generator import InventoryGenerator
from infrafoundry.core.config.manifest_utils import extract_inventory_block
from infrafoundry.core.config.models import PackageManifest
from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.secrets.provider import SecretProvider
from infrafoundry.core.secrets.providers.sops import SopsSecretProvider

if TYPE_CHECKING:
    from infrafoundry.core.config.blueprint_resolver import BlueprintResolver

logger = logging.getLogger(__name__)

# Map of dotted resource-type paths → declared YAML leaf shape under the
# nested ``opnsense:`` namespace (#793 per ADR-0016).
#
# - ``"list"`` paths must appear as YAML sequences (each entry a dict with a
#   ``name:`` field). Each entry emits one ``ResourceConfig``.
# - ``"dict"`` paths must appear as YAML mappings. The whole mapping becomes
#   a single singleton ``ResourceConfig`` with ``name="settings"``.
#
# Mismatched shape (e.g. operator typo ``firewall: {rules: {...}}`` instead
# of ``firewall: {rules: [...]}``) raises a clear error rather than
# silently round-tripping as a singleton.
#
# Path entries below the divider come from in-flight feature issues
# (#786 to #792); they are accepted by the loader now so operator YAML and
# tests can land alongside each component as it ships, without requiring a
# loader change for every new component.
DOTTED_RESOURCE_SHAPES: dict[str, str] = {
    # Direct-OPNsense components currently shipped (#793).
    "interfaces.vlans": "list",
    "interfaces.assignments": "list",
    "interfaces.virtual_ips": "list",
    "firewall.aliases": "list",
    "firewall.nat": "list",
    "firewall.rules": "list",
    "routing.gateways": "list",
    "routing.static": "list",
    "unbound.host_overrides": "list",
    "unbound.host_aliases": "list",
    "unbound.forwards": "list",
    "kea.dhcp4.subnets": "list",
    "kea.dhcp4.reservations": "list",
    "kea.dhcp6.subnets": "list",
    "kea.dhcp6.reservations": "list",
    # Singletons / surfaces from in-flight feature issues (ADR-0016).
    # #786 firewall_log
    "firewall.log": "dict",
    # #787 tailscale (settings singleton + subnets/auth lists)
    "tailscale.settings": "dict",
    "tailscale.subnets": "list",
    "tailscale.auth": "dict",
    # #788 radvd (singleton; subshape verified at component-land time)
    "radvd": "dict",
    # #789 cron jobs (list)
    "cron.jobs": "list",
    # #790 acmeclient (settings singleton + lists)
    "acmeclient.settings": "dict",
    "acmeclient.accounts": "list",
    "acmeclient.validations": "list",
    "acmeclient.certs": "list",
    "acmeclient.actions": "list",
    # #791 monit (settings singleton + lists)
    "monit.settings": "dict",
    "monit.alerts": "list",
    "monit.services": "list",
    "monit.tests": "list",
    # #792 hostwatch (singleton; subshape verified at component-land time)
    "hostwatch": "dict",
}

# Set of dotted resource-type paths recognised under the nested ``opnsense:``
# namespace. Provided as a separate constant for callers that only need to
# check membership (e.g. cross-reference resolvers in #793 Phase 3).
DOTTED_RESOURCE_TYPES: frozenset[str] = frozenset(DOTTED_RESOURCE_SHAPES)

# YAML namespace key that triggers the nested-format parse branch (#793
# Phase 2). The direct-OPNsense provider is the only consumer; nested format
# under any other top-level key is not currently supported.
NESTED_PROVIDER_NAMESPACE: str = "opnsense"


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
        secret_provider: SecretProvider | None = None,
    ) -> None:
        """Initialize package loader.

        Args:
            base_dir: Base directory for environment configs (e.g., ./envs)
            blueprint_resolver: Optional resolver for blueprint references.
                When ``None``, packages that declare ``blueprint:`` will
                raise an error.
            secret_provider: Provider used to load package secrets.yaml files.
                Defaults to ``SopsSecretProvider`` when ``None``.
        """
        self.base_dir = base_dir
        self._blueprint_resolver = blueprint_resolver
        self._secret_provider = secret_provider or SopsSecretProvider()
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

            # Provider-conditional resource and defaults selection
            bp_providers = blueprint.get("providers")
            effective_provider = manifest.provider or provider
            if bp_providers:
                if not effective_provider:
                    raise InvalidConfigurationError(
                        f"Blueprint '{manifest.blueprint}' declares provider-specific "
                        f"resources but package '{manifest.name}' has no provider"
                    )
                if effective_provider not in bp_providers:
                    available = ", ".join(sorted(bp_providers))
                    raise InvalidConfigurationError(
                        f"Blueprint '{manifest.blueprint}' has no resources for "
                        f"provider '{effective_provider}' "
                        f"(available providers: {available})"
                    )
                provider_block = bp_providers[effective_provider]
                # Merge provider-specific defaults between blueprint defaults
                # and package variables:
                # blueprint.defaults < providers[x].defaults < package.variables
                provider_defaults = provider_block.get("defaults", {})
                merged_vars = {**blueprint["defaults"], **provider_defaults, **manifest.variables}
                # Use provider-specific resources when package doesn't declare its own
                if not manifest.resources and provider_block.get("resources"):
                    manifest.resources = list(provider_block["resources"])

                # Use provider-specific events when package doesn't declare its own
                if not manifest.events and provider_block.get("events"):
                    manifest.events = dict(provider_block["events"])

            manifest.variables = merged_vars

            # Inherit resources from blueprint if package doesn't declare its own
            # (only when no provider-conditional selection occurred above)
            if not manifest.resources and blueprint["resources"]:
                manifest.resources = list(blueprint["resources"])

            # Inherit events from blueprint if package doesn't declare its own
            if not manifest.events and blueprint["events"]:
                manifest.events = dict(blueprint["events"])

            # Inherit inventory from blueprint if package doesn't declare its own
            if manifest.inventory_raw is None and blueprint.get("inventory_raw"):
                manifest.inventory_raw = blueprint["inventory_raw"]

        # ----- Secrets -----
        secrets_path = package_dir / "secrets.yaml"
        if secrets_path.exists():
            secrets_data = self._secret_provider.load_secret(secrets_path)
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
            data = self._render_resource_file(
                resource_path, manifest.variables, provider=effective_provider
            )
            parsed = self._parse_resources_from_data(data, resource_file, effective_provider)
            resources.extend(parsed)

        # ----- Events -----
        # Render event configs through Jinja2 to resolve variable references
        # (e.g., requires: ["{{ node01_name }}"] → requires: ["ontapcl-test-01"])
        if manifest.events:
            import json

            events_json = json.dumps(manifest.events)
            try:
                events_env = create_jinja2_env(undefined=jinja2.Undefined)
                events_template = events_env.from_string(events_json)
                events_context = dict(manifest.variables)
                if effective_provider and "provider" not in events_context:
                    events_context["provider"] = effective_provider
                rendered_events_json = events_template.render(**events_context)
                manifest.events = json.loads(rendered_events_json)
            except (jinja2.TemplateError, json.JSONDecodeError) as e:
                logger.warning("Failed to render event templates: %s", e)

        env_dir = self.base_dir / env_name
        events = self._rewrite_event_scripts(
            manifest.events, package_dir, env_dir, blueprint_dir=blueprint_dir
        )
        self._tag_handler_configs(
            events,
            package_name=manifest.name,
            package_dir=package_dir,
            blueprint_dir=blueprint_dir,
        )

        # Rewrite resource-level event script paths and tag them with the
        # same framework-internal keys as package-level handlers.
        for resource in resources:
            if resource.events:
                resource.events = self._rewrite_event_scripts(
                    resource.events, package_dir, env_dir, blueprint_dir=blueprint_dir
                )
                self._tag_handler_configs(
                    resource.events,
                    package_name=manifest.name,
                    package_dir=package_dir,
                    blueprint_dir=blueprint_dir,
                )

        # ----- Inventory generation -----
        if manifest.inventory_raw:
            inventory_path = self._inventory_generator.generate(
                manifest.inventory_raw, manifest.variables, package_dir
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
            file_text = manifest_path.read_text()
        except OSError as e:
            raise InvalidConfigurationError(
                f"Failed to read package manifest {manifest_path}: {e}"
            ) from e

        text_without_inventory, inventory_raw = extract_inventory_block(file_text)

        try:
            data = yaml.safe_load(text_without_inventory)
        except yaml.YAMLError as e:
            raise InvalidConfigurationError(
                f"Invalid YAML in package manifest {manifest_path}: {e}"
            ) from e

        if not data or not isinstance(data, dict):
            raise InvalidConfigurationError(
                f"Package manifest must be a YAML mapping: {manifest_path}"
            )

        # ``inventory`` is always ``None`` in ``data`` when an inventory
        # block existed (extractor replaced it with ``inventory: null``).
        # The raw text is carried separately for the generator.
        try:
            manifest = PackageManifest(**data)
        except Exception as e:
            raise InvalidConfigurationError(f"Invalid package manifest {manifest_path}: {e}") from e

        manifest.inventory_raw = inventory_raw
        return manifest

    def _render_resource_file(
        self,
        resource_path: Path,
        variables: dict[str, Any],
        *,
        provider: str | None = None,
    ) -> dict[str, Any]:
        """Read a resource template file, render with Jinja2, and parse as YAML.

        Args:
            resource_path: Path to the resource template file
            variables: Variables to substitute in the template
            provider: Optional provider name injected as a built-in template
                variable.  Does not overwrite a user-defined ``provider``
                key already present in *variables*.

        Returns:
            Parsed YAML data as a dictionary

        Raises:
            InvalidConfigurationError: If the file is missing, has undefined
                variables, or contains invalid YAML after rendering
        """
        if not resource_path.exists():
            raise InvalidConfigurationError(f"Resource file not found: {resource_path}")

        content = resource_path.read_text()

        # Build render context: user variables + injected provider
        render_context = dict(variables)
        if provider is not None and "provider" not in render_context:
            render_context["provider"] = provider

        # Render Jinja2 template with StrictUndefined
        try:
            env = create_jinja2_env(undefined=jinja2.StrictUndefined)
            template = env.from_string(content)
            rendered = template.render(**render_context)
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

        Supports three formats:

        1. **Nested provider-namespace** (``opnsense:`` top-level key with a
           dict value): Walk the nested structure under ``opnsense:`` to
           collect leaves; each leaf's dotted path (e.g. ``firewall.aliases``,
           ``kea.dhcp4.subnets``) becomes the ``ResourceConfig.type``. Lists
           emit one resource per entry; dicts emit a single ``settings``
           singleton. Provider is forced to ``opnsense``. Per ADR-0016
           (#793 Phase 2).

        2. **Resource-centric** (``resources:`` key): Each item declares its own
           ``provider`` and ``type``. The parent provider is used as fallback.

        3. **Provider-centric** (type-named key like ``ova_vms:``): Resource type
           is derived from the filename stem. Individual items may override
           ``provider`` via an optional ``provider`` field.

        Mixing formats in the same file is rejected — a top-level
        ``opnsense:`` dict alongside a ``resources:`` list or any flat
        provider-centric key raises ``InvalidConfigurationError``.

        Args:
            data: Parsed YAML data dictionary
            resource_file: Resource filename (e.g., 'vm.yaml')
            provider: Default provider name (from parent directory)

        Returns:
            List of ResourceConfig objects

        Raises:
            InvalidConfigurationError: If the file mixes nested and flat
                formats, contains an unknown nested path, or has a malformed
                leaf (neither list nor dict).
        """
        if not data:
            return []

        # Nested provider-namespace format (#793 Phase 2). Detect and branch
        # before either of the flat parse paths so a top-level ``opnsense:``
        # key always wins. Mixing with other formats is rejected explicitly.
        nested = data.get(NESTED_PROVIDER_NAMESPACE)
        if isinstance(nested, dict):
            extra_keys = [k for k in data if k != NESTED_PROVIDER_NAMESPACE]
            if extra_keys:
                raise InvalidConfigurationError(
                    f"{resource_file}: cannot mix nested '{NESTED_PROVIDER_NAMESPACE}:' "
                    f"format with other top-level keys (found: {sorted(extra_keys)!r}). "
                    "Use one format per file."
                )
            return self._parse_nested_provider_format(
                nested, NESTED_PROVIDER_NAMESPACE, resource_file
            )

        # Check for resource-centric format
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
                import_id=item.get("import_id"),
            )
            for item in resource_list
            if isinstance(item, dict) and "name" in item
        ]

    def _parse_nested_provider_format(
        self,
        namespace_data: dict[str, Any],
        provider: str,
        resource_file: str,
    ) -> list[ResourceConfig]:
        """Walk a nested ``provider:`` block and emit ``ResourceConfig`` items.

        The block mirrors the OPNsense API path tree
        (``/api/<plugin>/<surface>/<action>``). Per ADR-0016, the dotted path
        registered in ``DOTTED_RESOURCE_SHAPES`` declares the expected leaf
        shape:

        - **List-shape** path (e.g. ``firewall.aliases``) — leaf must be a
          YAML sequence; each entry must be a dict with a ``name:`` field.
          Each entry emits one ``ResourceConfig``.
        - **Dict-shape** path (e.g. ``firewall.log``) — leaf must be a YAML
          mapping. Emits a single ``ResourceConfig`` with ``name="settings"``
          and the mapping as ``config``.

        Unknown dotted paths and shape mismatches (operator typo
        ``firewall: {rules: {...}}`` instead of ``firewall: {rules: [...]}``)
        produce a clear error naming the path.

        Args:
            namespace_data: Value of the top-level provider key (e.g. the
                dict under ``opnsense:`` in the YAML).
            provider: Provider name that all emitted ``ResourceConfig`` items
                should carry. For now only ``"opnsense"`` is used by callers.
            resource_file: Source filename for error messages.

        Returns:
            List of ``ResourceConfig`` objects with dotted ``type`` paths.

        Raises:
            InvalidConfigurationError: If a leaf has an unknown dotted path,
                a shape mismatch, a malformed key, or a list entry without a
                ``name:`` field.
        """
        results: list[ResourceConfig] = []
        if not namespace_data:
            return results

        # Walk the tree; ``stack`` holds (current-dotted-path-parts, value).
        # Empty path-parts means we are at the namespace root and have not
        # consumed any key yet.
        stack: list[tuple[tuple[str, ...], Any]] = [((), namespace_data)]
        while stack:
            path_parts, value = stack.pop()
            dotted = ".".join(path_parts)

            if isinstance(value, dict):
                # Discrimination: if the *current* path is a known resource
                # type, the dict is its leaf — validate shape and emit.
                # Otherwise it is an interior node and we recurse.
                if dotted and dotted in DOTTED_RESOURCE_SHAPES:
                    expected_shape = DOTTED_RESOURCE_SHAPES[dotted]
                    if expected_shape != "dict":
                        raise InvalidConfigurationError(
                            f"{resource_file}: '{NESTED_PROVIDER_NAMESPACE}.{dotted}' "
                            f"is declared as a {expected_shape} resource type, "
                            "got a YAML mapping. Use a YAML sequence "
                            "('- name: ...' entries) for collections."
                        )
                    # Singleton leaf — emit one ResourceConfig with
                    # name="settings" and the dict as config.
                    results.append(
                        ResourceConfig(
                            name="settings",
                            type=dotted,
                            provider=provider,
                            config=dict(value),
                        )
                    )
                    continue
                # Interior node — recurse into children.
                for key, child in value.items():
                    if not isinstance(key, str):
                        raise InvalidConfigurationError(
                            f"{resource_file}: nested key under "
                            f"'{NESTED_PROVIDER_NAMESPACE}.{dotted or '<root>'}' "
                            f"must be a string, got {type(key).__name__}: {key!r}"
                        )
                    stack.append(((*path_parts, key), child))
            elif isinstance(value, list):
                # List leaf — collection of resources. Path must be a known
                # dotted list-shape resource type.
                if not dotted:
                    raise InvalidConfigurationError(
                        f"{resource_file}: top-level list directly under "
                        f"'{NESTED_PROVIDER_NAMESPACE}:' is not allowed; "
                        "lists must live at a known dotted resource path."
                    )
                if dotted not in DOTTED_RESOURCE_SHAPES:
                    raise InvalidConfigurationError(
                        f"{resource_file}: unknown nested resource path "
                        f"'{NESTED_PROVIDER_NAMESPACE}.{dotted}'. "
                        f"Known paths: {sorted(DOTTED_RESOURCE_SHAPES)!r}"
                    )
                expected_shape = DOTTED_RESOURCE_SHAPES[dotted]
                if expected_shape != "list":
                    raise InvalidConfigurationError(
                        f"{resource_file}: '{NESTED_PROVIDER_NAMESPACE}.{dotted}' "
                        f"is declared as a {expected_shape} resource type, "
                        "got a YAML sequence. Use a YAML mapping "
                        "(key: value pairs) for singletons."
                    )
                for index, item in enumerate(value):
                    if not isinstance(item, dict):
                        raise InvalidConfigurationError(
                            f"{resource_file}: entry {index} under "
                            f"'{NESTED_PROVIDER_NAMESPACE}.{dotted}' must be a "
                            f"mapping, got {type(item).__name__}"
                        )
                    if "name" not in item:
                        raise InvalidConfigurationError(
                            f"{resource_file}: entry {index} under "
                            f"'{NESTED_PROVIDER_NAMESPACE}.{dotted}' is missing "
                            "the required 'name:' field"
                        )
                    # Mirror ResourceCentricLoader: extract the inner
                    # ``config:`` dict and expose entry ``name`` inside it for
                    # template/component convenience. Components downstream
                    # read fields directly off ``ResourceConfig.config``
                    # (e.g. ``config["device"]`` for VLANs); the nested loader
                    # used to pass ``item`` through unchanged, leaving fields
                    # buried under ``config.config.<field>`` and silently
                    # breaking every direct-API component validator.
                    entry_config = item.get("config", {})
                    if "name" not in entry_config:
                        entry_config["name"] = item["name"]
                    results.append(
                        ResourceConfig(
                            name=item["name"],
                            type=dotted,
                            provider=item.get("provider", provider),
                            config=entry_config,
                            events=item.get("events"),
                            import_id=item.get("import_id"),
                        )
                    )
            else:
                # Scalar or other malformed leaf at a position that demands
                # either a list (collection) or a dict (singleton/interior).
                raise InvalidConfigurationError(
                    f"{resource_file}: leaf at "
                    f"'{NESTED_PROVIDER_NAMESPACE}.{dotted or '<root>'}' must be a "
                    f"list (collection) or a dict (singleton/interior), got "
                    f"{type(value).__name__}: {value!r}"
                )

        return results

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
                    type=str(item["type"]),
                    provider=item.get("provider", default_provider),
                    config=config,
                    events=item.get("events"),
                    import_id=item.get("import_id"),
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

    def _tag_handler_configs(
        self,
        events: dict[str, list[dict[str, Any]]],
        *,
        package_name: str,
        package_dir: Path,
        blueprint_dir: Path | None,
    ) -> None:
        """Inject framework-internal keys onto every handler config in *events*.

        Mutates *events* in place so downstream consumers (e.g. the script
        handler) can introspect the originating package when they run.

        Args:
            events: Event handler configurations, grouped by event name.
            package_name: Name of the originating package.
            package_dir: Directory of the originating package.
            blueprint_dir: Optional blueprint directory when the package
                consumes a blueprint.
        """
        if not events:
            return
        for handler_list in events.values():
            for handler_config in handler_list:
                handler_config["_package"] = package_name
                handler_config["_package_dir"] = str(package_dir)
                if blueprint_dir:
                    handler_config["_blueprint_dir"] = str(blueprint_dir)

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
