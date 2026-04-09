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
        """Generates a valid inventory file from a simple raw block."""
        generator = InventoryGenerator()
        raw = (
            "groups:\n"
            "  webservers:\n"
            "    hosts:\n"
            "      web-01:\n"
            "        ansible_host: 192.168.1.10\n"
            "    vars:\n"
            "      ansible_user: root\n"
        )

        output_path = generator.generate(raw, {}, temp_dir)

        assert output_path == temp_dir / GENERATED_INVENTORY_FILENAME
        assert output_path.exists()

        with open(output_path) as f:
            data = yaml.safe_load(f)

        assert data["groups"]["webservers"]["hosts"]["web-01"]["ansible_host"] == "192.168.1.10"
        assert data["groups"]["webservers"]["vars"]["ansible_user"] == "root"

    def test_generate_with_jinja2_variables(self, temp_dir):
        """Jinja2 string interpolation is rendered with variables."""
        generator = InventoryGenerator()
        raw = (
            "groups:\n"
            "  cluster:\n"
            "    hosts:\n"
            "      node-01:\n"
            '        ansible_host: "{{ node01_ip }}"\n'
        )
        variables = {"node01_ip": "10.0.0.1"}

        output_path = generator.generate(raw, variables, temp_dir)

        with open(output_path) as f:
            data = yaml.safe_load(f)

        assert data["groups"]["cluster"]["hosts"]["node-01"]["ansible_host"] == "10.0.0.1"

    def test_generate_undefined_variable_raises(self, temp_dir):
        """Undefined variables raise InvalidConfigurationError."""
        generator = InventoryGenerator()
        raw = (
            "groups:\n"
            "  cluster:\n"
            "    hosts:\n"
            "      node-01:\n"
            '        ansible_host: "{{ missing_var }}"\n'
        )

        with pytest.raises(InvalidConfigurationError, match="Undefined variable"):
            generator.generate(raw, {}, temp_dir)

    def test_generate_overwrites_existing(self, temp_dir):
        """Generating inventory overwrites an existing file."""
        generator = InventoryGenerator()
        existing = temp_dir / GENERATED_INVENTORY_FILENAME
        existing.write_text("old: content\n")

        raw = "groups:\n  new:\n    hosts:\n      h1: {}\n"
        generator.generate(raw, {}, temp_dir)

        with open(existing) as f:
            data = yaml.safe_load(f)

        assert "new" in data["groups"]
        assert "old" not in data

    def test_generate_creates_parent_dirs(self, temp_dir):
        """Parent directories are created if they don't exist."""
        generator = InventoryGenerator()
        output_dir = temp_dir / "deep" / "nested" / "dir"

        raw = "groups:\n  test:\n    hosts: {}\n"
        output_path = generator.generate(raw, {}, output_dir)

        assert output_path.exists()

    def test_generate_multiple_groups(self, temp_dir):
        """Multiple groups are rendered correctly."""
        generator = InventoryGenerator()
        raw = (
            "groups:\n"
            "  proxmox_hosts:\n"
            "    hosts:\n"
            '      pve1: {ansible_host: "{{ pve1_ip }}"}\n'
            '      pve2: {ansible_host: "{{ pve2_ip }}"}\n'
            "    vars:\n"
            "      ansible_user: root\n"
            "  ontap_cluster:\n"
            "    hosts:\n"
            "      ontap-mgmt:\n"
            '        ansible_host: "{{ cluster_mgmt_ip }}"\n'
            "        ansible_connection: local\n"
        )
        variables = {
            "pve1_ip": "192.168.10.1",
            "pve2_ip": "192.168.10.2",
            "cluster_mgmt_ip": "192.168.10.203",
        }

        output_path = generator.generate(raw, variables, temp_dir)

        with open(output_path) as f:
            data = yaml.safe_load(f)

        assert data["groups"]["proxmox_hosts"]["hosts"]["pve1"]["ansible_host"] == "192.168.10.1"
        assert data["groups"]["ontap_cluster"]["hosts"]["ontap-mgmt"]["ansible_connection"] == (
            "local"
        )

    def test_generate_with_for_loop(self, temp_dir):
        """A `{% for %}` loop expands into multiple host entries."""
        generator = InventoryGenerator()
        raw = (
            "groups:\n"
            "  k3s_workers:\n"
            "    hosts:\n"
            "      {% for w in workers %}\n"
            "      {{ w.name }}:\n"
            '        ansible_host: "{{ w.ip }}"\n'
            "      {% endfor %}\n"
        )
        variables = {
            "workers": [
                {"name": "worker-01", "ip": "10.0.0.11"},
                {"name": "worker-02", "ip": "10.0.0.12"},
                {"name": "worker-03", "ip": "10.0.0.13"},
            ]
        }

        output_path = generator.generate(raw, variables, temp_dir)

        with open(output_path) as f:
            data = yaml.safe_load(f)

        hosts = data["groups"]["k3s_workers"]["hosts"]
        assert set(hosts.keys()) == {"worker-01", "worker-02", "worker-03"}
        assert hosts["worker-01"]["ansible_host"] == "10.0.0.11"
        assert hosts["worker-02"]["ansible_host"] == "10.0.0.12"
        assert hosts["worker-03"]["ansible_host"] == "10.0.0.13"

    def test_generate_with_if_conditional(self, temp_dir):
        """`{% if %}` selects between branches."""
        generator = InventoryGenerator()
        raw = (
            "groups:\n"
            "  server:\n"
            "    hosts:\n"
            "      host-01:\n"
            "        {% if use_public_ip %}\n"
            '        ansible_host: "{{ public_ip }}"\n'
            "        {% else %}\n"
            '        ansible_host: "{{ private_ip }}"\n'
            "        {% endif %}\n"
        )
        variables = {
            "use_public_ip": True,
            "public_ip": "203.0.113.5",
            "private_ip": "10.0.0.5",
        }

        output_path = generator.generate(raw, variables, temp_dir)

        with open(output_path) as f:
            data = yaml.safe_load(f)

        assert data["groups"]["server"]["hosts"]["host-01"]["ansible_host"] == "203.0.113.5"

    def test_generate_with_for_loop_zero_iterations(self, temp_dir):
        """A loop over an empty list yields no host entries."""
        generator = InventoryGenerator()
        raw = (
            "groups:\n"
            "  k3s_workers:\n"
            "    hosts:\n"
            "      {% for w in workers %}\n"
            "      {{ w.name }}: {}\n"
            "      {% endfor %}\n"
        )
        variables = {"workers": []}

        output_path = generator.generate(raw, variables, temp_dir)

        with open(output_path) as f:
            data = yaml.safe_load(f)

        hosts = data["groups"]["k3s_workers"]["hosts"]
        assert hosts is None or hosts == {}

    def test_generate_with_for_loop_undefined_variable_raises(self, temp_dir):
        """Looping over an undefined variable raises InvalidConfigurationError."""
        generator = InventoryGenerator()
        raw = (
            "groups:\n"
            "  workers:\n"
            "    hosts:\n"
            "      {% for w in missing_list %}\n"
            "      {{ w }}: {}\n"
            "      {% endfor %}\n"
        )

        with pytest.raises(InvalidConfigurationError, match="Undefined variable"):
            generator.generate(raw, {}, temp_dir)


@pytest.mark.unit
class TestInventoryGeneratorRenderInventory:
    """Tests for InventoryGenerator._render_inventory."""

    def test_render_template_syntax_error(self, temp_dir):
        """Template syntax error raises InvalidConfigurationError."""
        generator = InventoryGenerator()
        raw = 'groups:\n  test:\n    hosts:\n      h1:\n        ip: "{{ broken }"\n'

        with pytest.raises(InvalidConfigurationError, match="Template syntax error"):
            generator._render_inventory(raw, {})

    def test_render_non_dict_result(self, temp_dir):
        """A rendered result that is not a mapping raises InvalidConfigurationError."""
        generator = InventoryGenerator()
        raw = "- item1\n- item2\n"

        with pytest.raises(InvalidConfigurationError, match="must render to a YAML mapping"):
            generator._render_inventory(raw, {})
