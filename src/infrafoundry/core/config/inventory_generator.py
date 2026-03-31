"""Ansible inventory generator for infrastructure packages.

Renders inventory declarations from package manifests into
``.generated-inventory.yml`` files that Ansible can consume directly.
"""

import logging
from pathlib import Path
from typing import Any

import jinja2
import yaml

from infrafoundry.core.exceptions import InvalidConfigurationError

logger = logging.getLogger(__name__)

GENERATED_INVENTORY_FILENAME = ".generated-inventory.yml"


class InventoryGenerator:
    """Generates Ansible inventory files from manifest declarations.

    The ``inventory`` section of a package manifest (or blueprint) declares
    host groups with optional Jinja2 templating.  This class renders those
    declarations with the merged variable set and writes the result to
    the package directory.
    """

    def generate(
        self,
        inventory_schema: dict[str, Any],
        variables: dict[str, Any],
        output_dir: Path,
    ) -> Path:
        """Render an inventory declaration and write it to disk.

        Args:
            inventory_schema: The ``inventory`` dict from the manifest.
                Expected structure::

                    groups:
                      group_name:
                        hosts:
                          host_name:
                            ansible_host: "{{ some_var }}"
                        vars:
                          key: value

            variables: Merged variables for Jinja2 rendering.
            output_dir: Directory to write the generated inventory file.

        Returns:
            Path to the generated inventory file.

        Raises:
            InvalidConfigurationError: If rendering or writing fails.
        """
        rendered = self._render_inventory(inventory_schema, variables)
        output_path = output_dir / GENERATED_INVENTORY_FILENAME
        self._write_inventory(rendered, output_path)

        logger.info("Generated inventory at %s", output_path)
        return output_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render_inventory(
        self,
        inventory_schema: dict[str, Any],
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        """Render Jinja2 templates in an inventory schema.

        Serialises the inventory dict to YAML, renders Jinja2, then
        parses back to a dict.  This allows templates anywhere in the
        structure (host names, vars, etc.).

        Args:
            inventory_schema: Raw inventory declaration.
            variables: Template variables.

        Returns:
            Rendered inventory as a dict.

        Raises:
            InvalidConfigurationError: On template or YAML errors.
        """
        raw_yaml = yaml.dump(inventory_schema, default_flow_style=False)

        try:
            env = jinja2.Environment(
                undefined=jinja2.StrictUndefined,
            )  # nosec B701 - rendering YAML, not HTML
            template = env.from_string(raw_yaml)
            rendered_yaml = template.render(**variables)
        except jinja2.UndefinedError as e:
            raise InvalidConfigurationError(
                f"Undefined variable in inventory declaration: {e}"
            ) from e
        except jinja2.TemplateSyntaxError as e:
            raise InvalidConfigurationError(
                f"Template syntax error in inventory declaration: {e}"
            ) from e

        try:
            data = yaml.safe_load(rendered_yaml)
        except yaml.YAMLError as e:
            raise InvalidConfigurationError(f"Invalid YAML after rendering inventory: {e}") from e

        if not isinstance(data, dict):
            raise InvalidConfigurationError("Inventory declaration must render to a YAML mapping")

        return data

    @staticmethod
    def _write_inventory(inventory: dict[str, Any], output_path: Path) -> None:
        """Write inventory dict to a YAML file.

        Args:
            inventory: Rendered inventory data.
            output_path: Destination file path.

        Raises:
            InvalidConfigurationError: If writing fails.
        """
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                yaml.dump(inventory, f, default_flow_style=False, sort_keys=False)
        except OSError as e:
            raise InvalidConfigurationError(
                f"Failed to write inventory file {output_path}: {e}"
            ) from e
