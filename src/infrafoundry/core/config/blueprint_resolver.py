"""Blueprint resolver for infrastructure packages.

Discovers and loads blueprints from ``config_repo/blueprints/``, allowing
packages to reference shared implementation files (roles, playbooks, scripts,
resource templates) via a ``blueprint: <name>`` declaration in their manifest.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from infrafoundry.core.config.manifest_utils import extract_inventory_block
from infrafoundry.core.exceptions import InvalidConfigurationError

logger = logging.getLogger(__name__)

BLUEPRINT_MANIFEST = "blueprint.yaml"

# Allowed keys in an ``inputs:`` entry.
_ALLOWED_INPUT_KEYS = frozenset({"name", "description", "type", "default"})


class BlueprintResolver:
    """Resolves blueprint references for infrastructure packages.

    Blueprints live at ``config_repo_root/blueprints/<name>/`` where
    *config_repo_root* is the parent of the ``envs/`` directory (i.e.
    ``base_dir.parent``).

    A blueprint directory must contain a ``blueprint.yaml`` manifest with
    at minimum a ``name`` field.  Optional fields: ``description``,
    ``version``, ``defaults`` (dict), ``resources`` (list), ``events``
    (dict), ``inventory`` (dict).
    """

    def __init__(self, base_dir: Path) -> None:
        """Initialize the blueprint resolver.

        Args:
            base_dir: The ``envs/`` directory (same as PackageLoader.base_dir).
                Blueprints are resolved from the framework's ``blueprints/``
                directory (relative to the infrafoundry package installation).
        """
        self.base_dir = base_dir.resolve()
        # Blueprints live in the framework repo, not the config repo.
        # Walk up from this file to find the repo root (contains pyproject.toml).
        framework_root = Path(__file__).resolve().parent
        while framework_root != framework_root.parent:
            if (framework_root / "pyproject.toml").exists():
                break
            framework_root = framework_root.parent
        self.blueprints_dir = framework_root / "blueprints"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, blueprint_name: str) -> dict[str, Any]:
        """Load and return a blueprint manifest by name.

        Args:
            blueprint_name: Name of the blueprint (directory name under
                ``blueprints/``).

        Returns:
            Parsed blueprint manifest as a dictionary with keys:
            ``name``, ``description``, ``version``, ``defaults``,
            ``resources``, ``events``, ``inventory``, ``blueprint_dir``.

        Raises:
            InvalidConfigurationError: If the blueprint directory or
                manifest is missing/invalid.
        """
        blueprint_dir = self.blueprints_dir / blueprint_name
        if not blueprint_dir.is_dir():
            raise InvalidConfigurationError(
                f"Blueprint '{blueprint_name}' not found at {blueprint_dir}"
            )

        manifest_path = blueprint_dir / BLUEPRINT_MANIFEST
        if not manifest_path.exists():
            raise InvalidConfigurationError(f"Blueprint manifest not found: {manifest_path}")

        data, inventory_raw = self._load_manifest(manifest_path)
        self._validate_manifest(data, manifest_path)

        # Parse top-level inputs: (authoritative) and synthesize defaults dict.
        top_inputs_raw = data.get("inputs")
        top_defaults, top_input_names = self._parse_inputs_section(
            top_inputs_raw,
            data.get("defaults"),
            manifest_path,
            scope=f"blueprint '{blueprint_name}'",
        )

        # Parse per-provider inputs (if any).
        providers_block: dict[str, Any] | None = data.get("providers")
        normalised_providers: dict[str, Any] | None = None
        if providers_block is not None:
            if not isinstance(providers_block, dict):
                raise InvalidConfigurationError(
                    f"Blueprint manifest 'providers:' must be a mapping: {manifest_path}"
                )
            normalised_providers = {}
            for provider_name, provider_block in providers_block.items():
                if not isinstance(provider_block, dict):
                    raise InvalidConfigurationError(
                        f"Provider '{provider_name}' block must be a mapping "
                        f"in blueprint '{blueprint_name}': {manifest_path}"
                    )
                provider_defaults, provider_input_names = self._parse_inputs_section(
                    provider_block.get("inputs"),
                    provider_block.get("defaults"),
                    manifest_path,
                    scope=f"blueprint '{blueprint_name}' provider '{provider_name}'",
                )
                new_block = dict(provider_block)
                new_block["defaults"] = provider_defaults
                new_block["input_names"] = provider_input_names
                normalised_providers[provider_name] = new_block

        # Normalise optional fields
        result: dict[str, Any] = {
            "name": data["name"],
            "description": data.get("description"),
            "version": data.get("version"),
            "defaults": top_defaults,
            "input_names": top_input_names,
            "resources": data.get("resources", []),
            "events": data.get("events", {}),
            "inventory": data.get("inventory"),
            "inventory_raw": inventory_raw,
            "blueprint_dir": blueprint_dir,
            "providers": normalised_providers,
        }

        logger.debug(
            "Resolved blueprint '%s' from %s",
            blueprint_name,
            blueprint_dir,
        )
        return result

    def exists(self, blueprint_name: str) -> bool:
        """Check whether a named blueprint exists.

        Args:
            blueprint_name: Blueprint directory name.

        Returns:
            ``True`` if the blueprint directory and manifest exist.
        """
        blueprint_dir = self.blueprints_dir / blueprint_name
        return (blueprint_dir / BLUEPRINT_MANIFEST).is_file()

    def list_blueprints(self) -> list[str]:
        """List all available blueprint names.

        Returns:
            Sorted list of blueprint directory names that contain a valid
            ``blueprint.yaml``.
        """
        if not self.blueprints_dir.is_dir():
            return []

        return sorted(
            d.name
            for d in self.blueprints_dir.iterdir()
            if d.is_dir() and (d / BLUEPRINT_MANIFEST).is_file()
        )

    def resolve_file(
        self,
        filename: str,
        package_dir: Path,
        blueprint_dir: Path,
    ) -> Path:
        """Resolve a file path with package-first, blueprint fallback.

        Args:
            filename: Relative filename to look up (e.g. ``vm.yaml`` or
                ``scripts/setup.sh``).
            package_dir: The package directory to check first.
            blueprint_dir: The blueprint directory to check as fallback.

        Returns:
            Resolved absolute path to the file.

        Raises:
            InvalidConfigurationError: If the file is not found in either
                location.
        """
        package_path = package_dir / filename
        if package_path.exists():
            return package_path

        blueprint_path = blueprint_dir / filename
        if blueprint_path.exists():
            return blueprint_path

        raise InvalidConfigurationError(
            f"File '{filename}' not found in package ({package_dir}) or blueprint ({blueprint_dir})"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_manifest(manifest_path: Path) -> tuple[dict[str, Any], str | None]:
        """Load a blueprint.yaml file.

        Extracts the top-level ``inventory:`` block as raw text before
        YAML parsing so that Jinja control-flow tags can survive to the
        inventory generator.

        Args:
            manifest_path: Path to the blueprint.yaml file.

        Returns:
            Tuple of ``(parsed_data, inventory_raw)``.

        Raises:
            InvalidConfigurationError: On YAML errors.
        """
        try:
            file_text = manifest_path.read_text()
        except OSError as e:
            raise InvalidConfigurationError(
                f"Failed to read blueprint manifest {manifest_path}: {e}"
            ) from e

        text_without_inventory, inventory_raw = extract_inventory_block(file_text)

        try:
            data = yaml.safe_load(text_without_inventory)
        except yaml.YAMLError as e:
            raise InvalidConfigurationError(
                f"Invalid YAML in blueprint manifest {manifest_path}: {e}"
            ) from e

        if not data or not isinstance(data, dict):
            raise InvalidConfigurationError(
                f"Blueprint manifest must be a YAML mapping: {manifest_path}"
            )

        result: dict[str, Any] = data
        return result, inventory_raw

    @staticmethod
    def _parse_inputs_section(
        inputs_raw: Any,
        defaults_raw: Any,
        manifest_path: Path,
        scope: str,
    ) -> tuple[dict[str, Any], frozenset[str]]:
        """Parse an ``inputs:`` list and synthesize a ``defaults`` dict.

        Enforces the "clean cutover" rule that a manifest scope (blueprint
        root or a single provider block) cannot declare both ``inputs:`` and
        the legacy ``defaults:`` section. When ``inputs:`` is absent and
        ``defaults:`` is present, falls back to the legacy behaviour so
        migrations can roll out incrementally at the sub-block level.

        Args:
            inputs_raw: Value of the ``inputs:`` key (may be ``None``).
            defaults_raw: Value of the legacy ``defaults:`` key (may be
                ``None``).
            manifest_path: Path to the manifest, used in error messages.
            scope: Human-readable scope for error messages, e.g.
                ``"blueprint 'aiqum'"`` or
                ``"blueprint 'k3s-cluster' provider 'proxmox'"``.

        Returns:
            Tuple of ``(defaults_dict, input_names)``. ``defaults_dict`` is
            synthesised from input entries that carry a ``default:`` key
            (preserving declaration order) so downstream callers that read
            ``blueprint["defaults"]`` keep working unchanged. ``input_names``
            is the frozenset of declared input names (required + optional).

        Raises:
            InvalidConfigurationError: If both ``inputs:`` and ``defaults:``
                are present, if ``inputs:`` is not a list of mappings, if
                any entry is missing ``name``, or if any entry contains
                unknown keys.
        """
        if inputs_raw is not None and defaults_raw is not None:
            raise InvalidConfigurationError(
                f"{scope} declares both 'inputs:' and 'defaults:' in "
                f"{manifest_path}. Use 'inputs:' only — 'defaults:' has "
                "been removed from the blueprint schema."
            )

        if inputs_raw is None:
            # Legacy path: no inputs declared. Use defaults dict verbatim
            # and derive input_names from its keys so validation still
            # works for sub-blocks that haven't been migrated.
            legacy_defaults = defaults_raw if isinstance(defaults_raw, dict) else {}
            return dict(legacy_defaults), frozenset(legacy_defaults.keys())

        if not isinstance(inputs_raw, list):
            raise InvalidConfigurationError(
                f"{scope} has a non-list 'inputs:' value in {manifest_path}; "
                "expected a list of input entries."
            )

        defaults: dict[str, Any] = {}
        names: list[str] = []
        for idx, entry in enumerate(inputs_raw):
            if not isinstance(entry, dict):
                raise InvalidConfigurationError(
                    f"{scope} has a non-mapping input entry at index {idx} "
                    f"in {manifest_path}; each input must be a mapping with "
                    "at least a 'name' key."
                )
            if "name" not in entry:
                raise InvalidConfigurationError(
                    f"{scope} has an input entry missing 'name' at index {idx} in {manifest_path}."
                )
            name = entry["name"]
            if not isinstance(name, str) or not name:
                raise InvalidConfigurationError(
                    f"{scope} has a non-string or empty 'name' at input "
                    f"index {idx} in {manifest_path}."
                )
            unknown = set(entry.keys()) - _ALLOWED_INPUT_KEYS
            if unknown:
                raise InvalidConfigurationError(
                    f"{scope} input '{name}' has unknown keys "
                    f"{sorted(unknown)} in {manifest_path}; allowed keys are "
                    f"{sorted(_ALLOWED_INPUT_KEYS)}."
                )
            if name in names:
                raise InvalidConfigurationError(
                    f"{scope} declares input '{name}' more than once in {manifest_path}."
                )
            names.append(name)
            if "default" in entry:
                defaults[name] = entry["default"]

        return defaults, frozenset(names)

    @staticmethod
    def _validate_manifest(data: dict[str, Any], manifest_path: Path) -> None:
        """Validate required fields in a blueprint manifest.

        Args:
            data: Parsed manifest data.
            manifest_path: Path for error messages.

        Raises:
            InvalidConfigurationError: If required fields are missing.
        """
        if "name" not in data:
            raise InvalidConfigurationError(
                f"Blueprint manifest missing required 'name' field: {manifest_path}"
            )
