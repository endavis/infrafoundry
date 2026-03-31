"""Blueprint resolver for infrastructure packages.

Discovers and loads blueprints from ``config_repo/blueprints/``, allowing
packages to reference shared implementation files (roles, playbooks, scripts,
resource templates) via a ``blueprint: <name>`` declaration in their manifest.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from infrafoundry.core.exceptions import InvalidConfigurationError

logger = logging.getLogger(__name__)

BLUEPRINT_MANIFEST = "blueprint.yaml"


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

        data = self._load_manifest(manifest_path)
        self._validate_manifest(data, manifest_path)

        # Normalise optional fields
        result: dict[str, Any] = {
            "name": data["name"],
            "description": data.get("description"),
            "version": data.get("version"),
            "defaults": data.get("defaults", {}),
            "resources": data.get("resources", []),
            "events": data.get("events", {}),
            "inventory": data.get("inventory"),
            "blueprint_dir": blueprint_dir,
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
    def _load_manifest(manifest_path: Path) -> dict[str, Any]:
        """Load a blueprint.yaml file.

        Args:
            manifest_path: Path to the blueprint.yaml file.

        Returns:
            Parsed YAML data.

        Raises:
            InvalidConfigurationError: On YAML errors.
        """
        try:
            with open(manifest_path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise InvalidConfigurationError(
                f"Invalid YAML in blueprint manifest {manifest_path}: {e}"
            ) from e

        if not data or not isinstance(data, dict):
            raise InvalidConfigurationError(
                f"Blueprint manifest must be a YAML mapping: {manifest_path}"
            )

        result: dict[str, Any] = data
        return result

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
