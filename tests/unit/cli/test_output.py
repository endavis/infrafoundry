"""Tests for CLI output formatting utilities."""

from __future__ import annotations

import json

import pytest
import yaml

from infrafoundry.cli.output import (
    BULLET,
    OutputFormat,
    format_json,
    format_list,
    format_list_item,
    format_yaml,
    output_data,
)


class TestBulletConstant:
    """Tests for the BULLET constant."""

    def test_bullet_is_string(self) -> None:
        """BULLET should be a string."""
        assert isinstance(BULLET, str)

    def test_bullet_is_not_empty(self) -> None:
        """BULLET should not be empty."""
        assert len(BULLET) > 0

    def test_bullet_is_unicode_bullet(self) -> None:
        """BULLET should be the standard bullet character."""
        assert BULLET == "•"


class TestOutputFormat:
    """Tests for OutputFormat enum."""

    def test_text_format(self) -> None:
        """TEXT format should be 'text'."""
        assert OutputFormat.TEXT == "text"
        assert OutputFormat.TEXT.value == "text"

    def test_json_format(self) -> None:
        """JSON format should be 'json'."""
        assert OutputFormat.JSON == "json"
        assert OutputFormat.JSON.value == "json"

    def test_yaml_format(self) -> None:
        """YAML format should be 'yaml'."""
        assert OutputFormat.YAML == "yaml"
        assert OutputFormat.YAML.value == "yaml"

    def test_table_format(self) -> None:
        """TABLE format should be 'table'."""
        assert OutputFormat.TABLE == "table"
        assert OutputFormat.TABLE.value == "table"

    def test_format_from_string(self) -> None:
        """OutputFormat should be creatable from string."""
        assert OutputFormat("text") == OutputFormat.TEXT
        assert OutputFormat("json") == OutputFormat.JSON
        assert OutputFormat("yaml") == OutputFormat.YAML


class TestFormatJson:
    """Tests for format_json function."""

    def test_format_simple_dict(self) -> None:
        """Should format a simple dict as JSON."""
        data = {"name": "test", "value": 42}
        result = format_json(data)

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed == data

    def test_format_nested_dict(self) -> None:
        """Should format nested structures."""
        data = {"outer": {"inner": {"deep": "value"}}}
        result = format_json(data)

        parsed = json.loads(result)
        assert parsed == data

    def test_format_list(self) -> None:
        """Should format lists."""
        data = [1, 2, 3, "four"]
        result = format_json(data)

        parsed = json.loads(result)
        assert parsed == data

    def test_format_with_custom_indent(self) -> None:
        """Should respect custom indent."""
        data = {"key": "value"}
        result = format_json(data, indent=4)

        # Check indentation is 4 spaces
        lines = result.split("\n")
        assert lines[1].startswith("    ")

    def test_format_with_datetime(self) -> None:
        """Should handle datetime using default=str."""
        from datetime import datetime

        data = {"timestamp": datetime(2024, 1, 15, 12, 0, 0)}
        result = format_json(data)

        # Should not raise, datetime converted to string
        parsed = json.loads(result)
        assert "2024-01-15" in parsed["timestamp"]


class TestFormatYaml:
    """Tests for format_yaml function."""

    def test_format_simple_dict(self) -> None:
        """Should format a simple dict as YAML."""
        data = {"name": "test", "value": 42}
        result = format_yaml(data)

        # Should be valid YAML
        parsed = yaml.safe_load(result)
        assert parsed == data

    def test_format_nested_dict(self) -> None:
        """Should format nested structures."""
        data = {"outer": {"inner": "value"}}
        result = format_yaml(data)

        parsed = yaml.safe_load(result)
        assert parsed == data

    def test_format_list(self) -> None:
        """Should format lists."""
        data = ["one", "two", "three"]
        result = format_yaml(data)

        parsed = yaml.safe_load(result)
        assert parsed == data

    def test_no_flow_style(self) -> None:
        """Should not use flow style for collections."""
        data = {"items": [1, 2, 3]}
        result = format_yaml(data)

        # Flow style would be like {items: [1, 2, 3]}
        # Block style has newlines
        assert "\n" in result


class TestFormatListItem:
    """Tests for format_list_item function."""

    def test_basic_item(self) -> None:
        """Should format item with default indent."""
        result = format_list_item("test item")
        assert result == f"  {BULLET} test item"

    def test_custom_indent(self) -> None:
        """Should respect custom indent."""
        result = format_list_item("test", indent=4)
        assert result == f"    {BULLET} test"

    def test_zero_indent(self) -> None:
        """Should work with zero indent."""
        result = format_list_item("test", indent=0)
        assert result == f"{BULLET} test"


class TestFormatList:
    """Tests for format_list function."""

    def test_empty_list(self) -> None:
        """Should handle empty list."""
        result = format_list([])
        assert result == []

    def test_single_item(self) -> None:
        """Should format single item."""
        result = format_list(["item"])
        assert result == [f"  {BULLET} item"]

    def test_multiple_items(self) -> None:
        """Should format multiple items."""
        result = format_list(["one", "two", "three"])
        assert len(result) == 3
        assert all(item.startswith(f"  {BULLET} ") for item in result)

    def test_custom_indent(self) -> None:
        """Should respect custom indent for all items."""
        result = format_list(["a", "b"], indent=6)
        assert all(item.startswith(f"      {BULLET} ") for item in result)


class TestOutputData:
    """Tests for output_data function."""

    def test_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should output JSON to stdout."""
        data = {"key": "value"}
        output_data(data, OutputFormat.JSON)

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == data

    def test_yaml_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should output YAML to stdout."""
        data = {"key": "value"}
        output_data(data, OutputFormat.YAML)

        captured = capsys.readouterr()
        parsed = yaml.safe_load(captured.out)
        assert parsed == data

    def test_string_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should accept string format."""
        data = {"test": 123}
        output_data(data, "json")

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == data

    def test_text_format_raises(self) -> None:
        """Should raise for text format."""
        with pytest.raises(ValueError, match="Use appropriate display method"):
            output_data({"key": "value"}, OutputFormat.TEXT)

    def test_table_format_raises(self) -> None:
        """Should raise for table format."""
        with pytest.raises(ValueError, match="Use appropriate display method"):
            output_data({"key": "value"}, OutputFormat.TABLE)
