"""Tests for schema export commands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from infrafoundry.cli.commands.schema import (
    SCHEMA_MODELS,
    _generate_schema,
    schema,
)


class TestGenerateSchema:
    """Tests for schema generation."""

    def test_generate_settings_schema(self) -> None:
        """Should generate valid JSON Schema for settings."""
        model = SCHEMA_MODELS["settings"]
        schema_data = _generate_schema(model)

        assert "$defs" in schema_data or "properties" in schema_data
        assert schema_data.get("type") == "object"

    def test_generate_resources_schema(self) -> None:
        """Should generate valid JSON Schema for resources."""
        model = SCHEMA_MODELS["resources"]
        schema_data = _generate_schema(model)

        assert "properties" in schema_data
        assert "resources" in schema_data["properties"]

    def test_generate_all_schemas(self) -> None:
        """Should generate valid schemas for all models."""
        for name, model in SCHEMA_MODELS.items():
            schema_data = _generate_schema(model)

            # All schemas should be objects
            assert schema_data.get("type") == "object", f"Schema {name} should be object type"
            # All schemas should have a title
            assert "title" in schema_data, f"Schema {name} should have title"

    def test_custom_title(self) -> None:
        """Should allow custom title override."""
        model = SCHEMA_MODELS["settings"]
        schema_data = _generate_schema(model, title="Custom Title")

        assert schema_data["title"] == "Custom Title"


class TestSchemaExportCommand:
    """Tests for 'foundry schema export' command."""

    def test_export_creates_files(self, tmp_path: Path) -> None:
        """Should create schema files in output directory."""
        runner = CliRunner()
        result = runner.invoke(schema, ["export", "--output", str(tmp_path)])

        assert result.exit_code == 0
        assert "Exported" in result.output

        # Check files were created
        for name in SCHEMA_MODELS:
            schema_file = tmp_path / f"{name}.schema.json"
            assert schema_file.exists(), f"Schema file {name}.schema.json should exist"

            # Verify it's valid JSON
            with open(schema_file) as f:
                data = json.load(f)
                assert "type" in data

    def test_export_shows_vscode_config(self, tmp_path: Path) -> None:
        """Should show VS Code configuration hint."""
        runner = CliRunner()
        result = runner.invoke(schema, ["export", "--output", str(tmp_path)])

        assert result.exit_code == 0
        assert "yaml.schemas" in result.output
        assert "settings.schema.json" in result.output


class TestSchemaListCommand:
    """Tests for 'foundry schema list' command."""

    def test_list_shows_all_schemas(self) -> None:
        """Should list all available schemas."""
        runner = CliRunner()
        result = runner.invoke(schema, ["list"])

        assert result.exit_code == 0
        for name in SCHEMA_MODELS:
            assert name in result.output


class TestSchemaShowCommand:
    """Tests for 'foundry schema show' command."""

    def test_show_settings_schema(self) -> None:
        """Should output settings schema as JSON."""
        runner = CliRunner()
        result = runner.invoke(schema, ["show", "settings"])

        assert result.exit_code == 0

        # Should be valid JSON
        data = json.loads(result.output)
        assert "type" in data
        assert data["type"] == "object"

    def test_show_resources_schema(self) -> None:
        """Should output resources schema."""
        runner = CliRunner()
        result = runner.invoke(schema, ["show", "resources"])

        assert result.exit_code == 0

        data = json.loads(result.output)
        assert "properties" in data
        assert "resources" in data["properties"]

    def test_show_yaml_format(self) -> None:
        """Should output schema as YAML when requested."""
        runner = CliRunner()
        result = runner.invoke(schema, ["show", "settings", "--format", "yaml"])

        assert result.exit_code == 0
        # YAML output should contain type: object (without JSON quotes)
        assert "type: object" in result.output

    def test_show_invalid_schema(self) -> None:
        """Should error on invalid schema name."""
        runner = CliRunner()
        result = runner.invoke(schema, ["show", "nonexistent"])

        assert result.exit_code != 0


class TestSchemaContent:
    """Tests for schema content correctness."""

    def test_settings_schema_has_required_fields(self) -> None:
        """Settings schema should include key fields."""
        model = SCHEMA_MODELS["settings"]
        schema_data = _generate_schema(model)

        props = schema_data.get("properties", {})
        assert "name" in props
        assert "providers" in props
        assert "variables" in props

    def test_resources_schema_structure(self) -> None:
        """Resources schema should have correct structure."""
        model = SCHEMA_MODELS["resources"]
        schema_data = _generate_schema(model)

        props = schema_data.get("properties", {})
        assert "resources" in props

        # Resources should be an array
        resources_prop = props["resources"]
        assert resources_prop.get("type") == "array"

    def test_backend_schema_has_types(self) -> None:
        """Backend schema should include backend type options."""
        model = SCHEMA_MODELS["backend"]
        schema_data = _generate_schema(model)

        props = schema_data.get("properties", {})
        assert "type" in props
        assert "s3" in props
        assert "gcs" in props

    def test_resource_schema_has_required_fields(self) -> None:
        """Resource schema should include required fields."""
        model = SCHEMA_MODELS["resource"]
        schema_data = _generate_schema(model)

        props = schema_data.get("properties", {})
        assert "name" in props
        assert "type" in props
        assert "provider" in props
        assert "config" in props
