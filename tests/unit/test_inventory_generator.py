"""Unit tests for InventoryGenerator."""

import pytest
import yaml

from infrafoundry.core.config.inventory_generator import (
    GENERATED_INVENTORY_FILENAME,
    InventoryGenerator,
)
from infrafoundry.core.exceptions import InvalidConfigurationError


@pytest.mark.unit
class TestInventoryGeneratorGenerate:
    """Tests for InventoryGenerator.generate."""

    def test_generate_simple_inventory(self, temp_dir):
        """Generates a valid inventory file from a simple schema."""
        generator = InventoryGenerator()
        schema = {
            "groups": {
                "webservers": {
                    "hosts": {
                        "web-01": {
                            "ansible_host": "192.168.1.10",
                        }
                    },
                    "vars": {
                        "ansible_user": "root",
                    },
                }
            }
        }

        output_path = generator.generate(schema, {}, temp_dir)

        assert output_path == temp_dir / GENERATED_INVENTORY_FILENAME
        assert output_path.exists()

        with open(output_path) as f:
            data = yaml.safe_load(f)

        assert data["groups"]["webservers"]["hosts"]["web-01"]["ansible_host"] == "192.168.1.10"
        assert data["groups"]["webservers"]["vars"]["ansible_user"] == "root"

    def test_generate_with_jinja2_variables(self, temp_dir):
        """Jinja2 templates in schema are rendered with variables."""
        generator = InventoryGenerator()
        schema = {
            "groups": {
                "cluster": {
                    "hosts": {
                        "node-01": {
                            "ansible_host": "{{ node01_ip }}",
                        }
                    }
                }
            }
        }
        variables = {"node01_ip": "10.0.0.1"}

        output_path = generator.generate(schema, variables, temp_dir)

        with open(output_path) as f:
            data = yaml.safe_load(f)

        assert data["groups"]["cluster"]["hosts"]["node-01"]["ansible_host"] == "10.0.0.1"

    def test_generate_undefined_variable_raises(self, temp_dir):
        """Undefined variables in schema raise InvalidConfigurationError."""
        generator = InventoryGenerator()
        schema = {
            "groups": {
                "cluster": {
                    "hosts": {
                        "node-01": {
                            "ansible_host": "{{ missing_var }}",
                        }
                    }
                }
            }
        }

        with pytest.raises(InvalidConfigurationError, match="Undefined variable"):
            generator.generate(schema, {}, temp_dir)

    def test_generate_overwrites_existing(self, temp_dir):
        """Generating inventory overwrites an existing file."""
        generator = InventoryGenerator()
        existing = temp_dir / GENERATED_INVENTORY_FILENAME
        existing.write_text("old: content\n")

        schema = {"groups": {"new": {"hosts": {"h1": {}}}}}
        generator.generate(schema, {}, temp_dir)

        with open(existing) as f:
            data = yaml.safe_load(f)

        assert "new" in data["groups"]
        assert "old" not in data

    def test_generate_creates_parent_dirs(self, temp_dir):
        """Parent directories are created if they don't exist."""
        generator = InventoryGenerator()
        output_dir = temp_dir / "deep" / "nested" / "dir"

        schema = {"groups": {"test": {"hosts": {}}}}
        output_path = generator.generate(schema, {}, output_dir)

        assert output_path.exists()

    def test_generate_multiple_groups(self, temp_dir):
        """Multiple groups are rendered correctly."""
        generator = InventoryGenerator()
        schema = {
            "groups": {
                "proxmox_hosts": {
                    "hosts": {
                        "pve1": {"ansible_host": "{{ pve1_ip }}"},
                        "pve2": {"ansible_host": "{{ pve2_ip }}"},
                    },
                    "vars": {"ansible_user": "root"},
                },
                "ontap_cluster": {
                    "hosts": {
                        "ontap-mgmt": {
                            "ansible_host": "{{ cluster_mgmt_ip }}",
                            "ansible_connection": "local",
                        }
                    },
                },
            }
        }
        variables = {
            "pve1_ip": "192.168.10.1",
            "pve2_ip": "192.168.10.2",
            "cluster_mgmt_ip": "192.168.10.203",
        }

        output_path = generator.generate(schema, variables, temp_dir)

        with open(output_path) as f:
            data = yaml.safe_load(f)

        assert data["groups"]["proxmox_hosts"]["hosts"]["pve1"]["ansible_host"] == "192.168.10.1"
        assert data["groups"]["ontap_cluster"]["hosts"]["ontap-mgmt"]["ansible_connection"] == (
            "local"
        )


@pytest.mark.unit
class TestInventoryGeneratorRenderInventory:
    """Tests for InventoryGenerator._render_inventory."""

    def test_render_template_syntax_error(self, temp_dir):
        """Template syntax error raises InvalidConfigurationError."""
        generator = InventoryGenerator()
        schema = {"groups": {"test": {"hosts": {"h1": {"ip": "{{ broken }"}}}}}

        with pytest.raises(InvalidConfigurationError, match="Template syntax error"):
            generator._render_inventory(schema, {})

    def test_render_non_dict_result(self, temp_dir):
        """Non-dict rendering result raises InvalidConfigurationError."""
        generator = InventoryGenerator()
        # A schema that renders to a list
        schema = ["item1", "item2"]

        with pytest.raises(InvalidConfigurationError, match="must render to a YAML mapping"):
            generator._render_inventory(schema, {})
