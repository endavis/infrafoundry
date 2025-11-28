"""Configuration blueprints manager."""

import logging
import shutil
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Blueprint(BaseModel):
    """Definition of a configuration blueprint."""

    name: str
    description: str
    version: str
    author: str | None = None
    files: dict[str, str]  # Map of filename -> content (or path relative to blueprint root)


class BlueprintManager:
    """Manages configuration blueprints."""

    def __init__(self, blueprint_dir: Path | None = None) -> None:
        """Initialize blueprint manager.

        Args:
            blueprint_dir: Directory containing local blueprints.
        """
        self.local_blueprint_dir = blueprint_dir or Path(__file__).parent / "blueprints"
        self._external_registries: list[str] = []  # List of external git repos (stubs)

    def list_blueprints(self) -> list[Blueprint]:
        """List available blueprints.

        Returns:
            List of Blueprint objects.
        """
        blueprints = []

        # 1. Scan local blueprints
        if self.local_blueprint_dir.exists():
            for bp_path in self.local_blueprint_dir.iterdir():
                if bp_path.is_dir() and (bp_path / "blueprint.yaml").exists():
                    try:
                        bp = self._load_blueprint(bp_path)
                        blueprints.append(bp)
                    except Exception as e:
                        logger.warning(f"Failed to load blueprint from {bp_path}: {e}")

        # 2. Scan external registries (Stub)
        # for registry in self._external_registries:
        #     blueprints.extend(self._fetch_external_blueprints(registry))

        return blueprints

    def get_blueprint(self, name: str) -> Blueprint | None:
        """Get a specific blueprint by name."""
        for bp in self.list_blueprints():
            if bp.name == name:
                return bp
        return None

    def instantiate_blueprint(
        self, blueprint_name: str, target_dir: Path, context: dict[str, Any]
    ) -> None:
        """Instantiate a blueprint into the target directory.

        Args:
            blueprint_name: Name of the blueprint to use.
            target_dir: Directory to write files to.
            context: Variables for template rendering (future).
        """
        # Find blueprint source
        blueprint_path = self.local_blueprint_dir / blueprint_name

        if not blueprint_path.exists():
            # Check external registries (Stub)
            # blueprint_path = self._fetch_blueprint_from_registry(blueprint_name)
            pass

        if not blueprint_path.exists():
            raise ValueError(f"Blueprint '{blueprint_name}' not found")

        target_dir.mkdir(parents=True, exist_ok=True)

        # Copy files
        # In a real implementation, we would process Jinja2 templates here
        for item in blueprint_path.iterdir():
            if item.name == "blueprint.yaml":
                continue

            if item.is_file():
                shutil.copy2(item, target_dir / item.name)
            elif item.is_dir():
                shutil.copytree(item, target_dir / item.name, dirs_exist_ok=True)

    def _load_blueprint(self, path: Path) -> Blueprint:
        """Load blueprint definition from a directory."""
        with open(path / "blueprint.yaml") as f:
            data = yaml.safe_load(f)
            # If files list is not explicit, assume all files in dir except blueprint.yaml
            if "files" not in data:
                data["files"] = {}
                # We handle actual file discovery in instantiate_blueprint for now
                # Ideally, we would list them here.
            return Blueprint(**data)

    # --- Stubs for External Registries ---

    def register_external_registry(self, repo_url: str) -> None:
        """Register an external git repository as a blueprint source."""
        # In future: git clone this repo to a cache dir
        self._external_registries.append(repo_url)

    def _fetch_external_blueprints(self, repo_url: str) -> list[Blueprint]:
        """Fetch blueprints from an external registry."""
        # Stub implementation
        logger.info(f"Scanning external registry: {repo_url}")
        return []

    def _fetch_blueprint_from_registry(self, name: str) -> Path | None:
        """Find and fetch a blueprint from registered external sources."""
        # Stub implementation
        return None
