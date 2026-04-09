"""Unit tests for manifest_utils.extract_inventory_block."""

import pytest

from infrafoundry.core.config.manifest_utils import extract_inventory_block
from infrafoundry.core.exceptions import InvalidConfigurationError


@pytest.mark.unit
class TestExtractInventoryBlock:
    """Tests for extract_inventory_block."""

    def test_no_inventory_returns_original_text_and_none(self):
        """A manifest without an inventory key returns unchanged text and None."""
        text = "name: pkg\nvariables:\n  foo: bar\n"
        stripped, raw = extract_inventory_block(text)

        assert stripped == text
        assert raw is None

    def test_simple_inventory_is_extracted_and_dedented(self):
        """A basic block is extracted with its leading key stripped and body dedented."""
        text = (
            "name: pkg\n"
            "inventory:\n"
            "  groups:\n"
            "    web:\n"
            "      hosts:\n"
            "        web-01:\n"
            "          ansible_host: 10.0.0.1\n"
        )
        stripped, raw = extract_inventory_block(text)

        assert raw is not None
        # Dedented body: top-level starts at column 0.
        assert raw.startswith("groups:\n")
        assert "  web:\n" in raw
        assert "    hosts:\n" in raw
        assert "      web-01:\n" in raw
        # Stripped text has the block replaced by a null placeholder.
        assert "inventory: null" in stripped
        assert "web-01" not in stripped

    def test_inventory_with_jinja_for_loop_preserved_literally(self):
        """Jinja control-flow tags survive extraction unchanged."""
        text = (
            "name: pkg\n"
            "inventory:\n"
            "  groups:\n"
            "    workers:\n"
            "      hosts:\n"
            "        {% for w in workers %}\n"
            "        {{ w.name }}:\n"
            '          ansible_host: "{{ w.ip }}"\n'
            "        {% endfor %}\n"
        )
        _, raw = extract_inventory_block(text)

        assert raw is not None
        assert "{% for w in workers %}" in raw
        assert "{% endfor %}" in raw
        assert "{{ w.name }}" in raw

    def test_inventory_followed_by_other_keys_stops_at_next_column_0(self):
        """Only the inventory section is captured; trailing top-level keys stay."""
        text = (
            "name: pkg\n"
            "inventory:\n"
            "  groups:\n"
            "    g1:\n"
            "      hosts:\n"
            "        h1: {}\n"
            "variables:\n"
            "  foo: bar\n"
            "events:\n"
            "  AFTER_APPLY: []\n"
        )
        stripped, raw = extract_inventory_block(text)

        assert raw is not None
        assert "groups:" in raw
        assert "variables" not in raw
        assert "events" not in raw
        # Trailing keys remain in the stripped text.
        assert "variables:\n  foo: bar\n" in stripped
        assert "events:\n  AFTER_APPLY: []\n" in stripped

    def test_inventory_at_eof_captures_to_end(self):
        """A trailing inventory block is captured all the way to EOF."""
        text = "name: pkg\ninventory:\n  groups:\n    g1:\n      hosts:\n        h1: {}\n"
        _, raw = extract_inventory_block(text)

        assert raw is not None
        assert "groups:" in raw
        assert "h1: {}" in raw

    def test_preserves_line_count_for_parser_error_messages(self):
        """The stripped text must have the same line count as the original."""
        text = (
            "name: pkg\n"  # line 1
            "description: hi\n"  # line 2
            "inventory:\n"  # line 3
            "  groups:\n"  # line 4
            "    g1:\n"  # line 5
            "      hosts:\n"  # line 6
            "        h1:\n"  # line 7
            "          ansible_host: 1.2.3.4\n"  # line 8
            "variables:\n"  # line 9
            "  foo: bar\n"  # line 10
        )
        stripped, _ = extract_inventory_block(text)

        assert text.count("\n") == stripped.count("\n")

    def test_flow_style_inventory_raises(self):
        """Single-line flow-style inventory declarations are rejected."""
        text = "name: pkg\ninventory: {groups: {g1: {hosts: {h1: {}}}}}\n"
        with pytest.raises(InvalidConfigurationError, match="block style"):
            extract_inventory_block(text)
