"""Unit tests for BlueprintResolver."""

import pytest
import yaml

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.exceptions import InvalidConfigurationError


def _make_resolver(base_dir):
    """Create a BlueprintResolver with blueprints_dir overridden for testing."""
    resolver = BlueprintResolver(base_dir)
    resolver.blueprints_dir = base_dir.parent / "blueprints"
    return resolver


def _create_blueprint(base_dir, name, manifest_data, extra_files=None):
    """Helper to create a blueprint directory structure.

    Args:
        base_dir: The envs/ directory (blueprints dir is base_dir.parent / "blueprints")
        name: Blueprint name (directory name)
        manifest_data: Dict for blueprint.yaml content
        extra_files: Optional dict of relative_path -> content
    """
    blueprints_dir = base_dir.parent / "blueprints"
    blueprint_dir = blueprints_dir / name
    blueprint_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = blueprint_dir / "blueprint.yaml"
    with open(manifest_path, "w") as f:
        yaml.dump(manifest_data, f)

    if extra_files:
        for rel_path, content in extra_files.items():
            file_path = blueprint_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, str):
                file_path.write_text(content)
            else:
                with open(file_path, "w") as f:
                    yaml.dump(content, f)

    return blueprint_dir


@pytest.mark.unit
class TestBlueprintResolverResolve:
    """Tests for BlueprintResolver.resolve."""

    def test_resolve_full_blueprint(self, temp_dir):
        """All fields are parsed and returned correctly."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        manifest = {
            "name": "ontap-cluster",
            "description": "ONTAP cluster blueprint",
            "version": "1.0.0",
            "defaults": {"cluster_name": "default-cluster", "node_count": 2},
            "resources": ["vm.yaml", "network.yaml"],
            "events": {"AFTER_APPLY": [{"type": "script", "script": "scripts/setup.sh"}]},
            "inventory": {"groups": {"hosts": {"host1": {}}}},
        }
        _create_blueprint(envs_dir, "ontap-cluster", manifest)

        result = resolver.resolve("ontap-cluster")

        assert result["name"] == "ontap-cluster"
        assert result["description"] == "ONTAP cluster blueprint"
        assert result["version"] == "1.0.0"
        assert result["defaults"]["cluster_name"] == "default-cluster"
        assert result["resources"] == ["vm.yaml", "network.yaml"]
        assert len(result["events"]["AFTER_APPLY"]) == 1
        assert result["inventory"]["groups"]["hosts"]["host1"] == {}
        assert result["blueprint_dir"].name == "ontap-cluster"

    def test_resolve_minimal_blueprint(self, temp_dir):
        """Name-only blueprint works with defaults for optional fields."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        _create_blueprint(envs_dir, "minimal", {"name": "minimal"})

        result = resolver.resolve("minimal")

        assert result["name"] == "minimal"
        assert result["description"] is None
        assert result["version"] is None
        assert result["defaults"] == {}
        assert result["resources"] == []
        assert result["events"] == {}
        assert result["inventory"] is None

    def test_resolve_nonexistent_blueprint(self, temp_dir):
        """Resolving a missing blueprint raises InvalidConfigurationError."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        with pytest.raises(InvalidConfigurationError, match="not found"):
            resolver.resolve("nonexistent")

    def test_resolve_missing_manifest(self, temp_dir):
        """Directory without blueprint.yaml raises InvalidConfigurationError."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        # Create directory without manifest
        bp_dir = envs_dir.parent / "blueprints" / "no-manifest"
        bp_dir.mkdir(parents=True)

        with pytest.raises(InvalidConfigurationError, match="manifest not found"):
            resolver.resolve("no-manifest")

    def test_resolve_invalid_yaml(self, temp_dir):
        """Invalid YAML in manifest raises InvalidConfigurationError."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        bp_dir = envs_dir.parent / "blueprints" / "bad-yaml"
        bp_dir.mkdir(parents=True)
        (bp_dir / "blueprint.yaml").write_text("invalid: yaml: content::\n")

        with pytest.raises(InvalidConfigurationError, match="Invalid YAML"):
            resolver.resolve("bad-yaml")

    def test_resolve_missing_name_field(self, temp_dir):
        """Manifest without name field raises InvalidConfigurationError."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        _create_blueprint(envs_dir, "no-name", {"description": "missing name"})

        with pytest.raises(InvalidConfigurationError, match="missing required 'name'"):
            resolver.resolve("no-name")

    def test_resolve_empty_manifest(self, temp_dir):
        """Empty manifest file raises InvalidConfigurationError."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        bp_dir = envs_dir.parent / "blueprints" / "empty"
        bp_dir.mkdir(parents=True)
        (bp_dir / "blueprint.yaml").write_text("")

        with pytest.raises(InvalidConfigurationError, match="must be a YAML mapping"):
            resolver.resolve("empty")


@pytest.mark.unit
class TestBlueprintResolverExists:
    """Tests for BlueprintResolver.exists."""

    def test_exists_returns_true(self, temp_dir):
        """Returns True for valid blueprint."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        _create_blueprint(envs_dir, "test-bp", {"name": "test-bp"})

        assert resolver.exists("test-bp") is True

    def test_exists_returns_false_missing(self, temp_dir):
        """Returns False for non-existent blueprint."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        assert resolver.exists("nonexistent") is False

    def test_exists_returns_false_no_manifest(self, temp_dir):
        """Returns False for directory without blueprint.yaml."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        bp_dir = envs_dir.parent / "blueprints" / "no-manifest"
        bp_dir.mkdir(parents=True)

        assert resolver.exists("no-manifest") is False


@pytest.mark.unit
class TestBlueprintResolverListBlueprints:
    """Tests for BlueprintResolver.list_blueprints."""

    def test_list_blueprints(self, temp_dir):
        """Lists all valid blueprints sorted by name."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        _create_blueprint(envs_dir, "zeta-bp", {"name": "zeta"})
        _create_blueprint(envs_dir, "alpha-bp", {"name": "alpha"})

        result = resolver.list_blueprints()
        assert result == ["alpha-bp", "zeta-bp"]

    def test_list_blueprints_empty(self, temp_dir):
        """Returns empty list when no blueprints directory exists."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        assert resolver.list_blueprints() == []

    def test_list_blueprints_skips_invalid(self, temp_dir):
        """Skips directories without blueprint.yaml."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        _create_blueprint(envs_dir, "valid", {"name": "valid"})
        # Create dir without manifest
        (envs_dir.parent / "blueprints" / "invalid").mkdir(parents=True)

        result = resolver.list_blueprints()
        assert result == ["valid"]


@pytest.mark.unit
class TestBlueprintResolverResolveFile:
    """Tests for BlueprintResolver.resolve_file."""

    def test_resolve_file_from_package(self, temp_dir):
        """File in package dir is preferred over blueprint."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        package_dir = temp_dir / "pkg"
        package_dir.mkdir()
        (package_dir / "vm.yaml").write_text("vm: []\n")

        blueprint_dir = temp_dir / "bp"
        blueprint_dir.mkdir()
        (blueprint_dir / "vm.yaml").write_text("bp_vm: []\n")

        result = resolver.resolve_file("vm.yaml", package_dir, blueprint_dir)
        assert result == package_dir / "vm.yaml"

    def test_resolve_file_fallback_to_blueprint(self, temp_dir):
        """File not in package falls back to blueprint."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        package_dir = temp_dir / "pkg"
        package_dir.mkdir()

        blueprint_dir = temp_dir / "bp"
        blueprint_dir.mkdir()
        (blueprint_dir / "vm.yaml").write_text("bp_vm: []\n")

        result = resolver.resolve_file("vm.yaml", package_dir, blueprint_dir)
        assert result == blueprint_dir / "vm.yaml"

    def test_resolve_file_nested_path(self, temp_dir):
        """Nested paths (scripts/setup.sh) resolve correctly."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        package_dir = temp_dir / "pkg"
        package_dir.mkdir()

        blueprint_dir = temp_dir / "bp"
        scripts_dir = blueprint_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "setup.sh").write_text("#!/bin/bash\n")

        result = resolver.resolve_file("scripts/setup.sh", package_dir, blueprint_dir)
        assert result == blueprint_dir / "scripts" / "setup.sh"

    def test_resolve_file_not_found(self, temp_dir):
        """File in neither location raises InvalidConfigurationError."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        resolver = _make_resolver(envs_dir)

        package_dir = temp_dir / "pkg"
        package_dir.mkdir()

        blueprint_dir = temp_dir / "bp"
        blueprint_dir.mkdir()

        with pytest.raises(InvalidConfigurationError, match="not found"):
            resolver.resolve_file("missing.yaml", package_dir, blueprint_dir)
