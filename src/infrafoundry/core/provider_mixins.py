"""Mixins providing common functionality for infrastructure providers.

These mixins extract repeated patterns from provider implementations,
reducing code duplication and standardizing provider behavior.
"""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.provider import ResourceConfig


class TemplateRendererMixin:
    """Mixin for providers that use Jinja2 template rendering.

    Provides:
    - Standard Jinja2 environment setup
    - Template loading and caching
    - Common template filters
    - Error handling for template rendering

    Usage:
        class MyProvider(ProviderBase, TemplateRendererMixin):
            def __init__(self, config_dir: Path, output_dir: Path):
                super().__init__("myprovider", config_dir, output_dir)
                self._setup_template_environment()

            def generate_terraform(self, resources):
                template = self.get_template("myprovider/main.tf.j2")
                content = template.render(resources=resources)
                self._write_terraform_file("main.tf", content)
    """

    def _setup_template_environment(
        self,
        template_subdir: str | None = None,
        **env_kwargs: Any,
    ) -> None:
        """Set up Jinja2 template environment.

        Args:
            template_subdir: Subdirectory within provider for templates (default: "templates")
            **env_kwargs: Additional kwargs to pass to Jinja2 Environment
        """
        if not hasattr(self, "name"):
            raise AttributeError(
                "TemplateRendererMixin requires 'name' attribute (from ProviderBase)"
            )

        # Determine template directory
        provider_dir = Path(__file__).parent.parent / "providers" / getattr(self, "name")
        if template_subdir:
            self.template_dir = provider_dir / template_subdir
        else:
            self.template_dir = provider_dir / "templates"

        # Set up Jinja2 environment with defaults
        env_defaults = {
            "trim_blocks": True,
            "lstrip_blocks": True,
            "keep_trailing_newline": True,
        }
        env_defaults.update(env_kwargs)

        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            **env_defaults,
        )

        # Register common filters
        self._register_common_filters()

        # Set up logger if not already present
        if not hasattr(self, "_logger"):
            self._logger = logging.getLogger(f"{self.__class__.__name__}")

    def _register_common_filters(self) -> None:
        """Register common Jinja2 filters used across providers."""
        # Convert hyphens to underscores (for Terraform resource names)
        self.jinja_env.filters["to_terraform_name"] = lambda s: str(s).replace("-", "_")

        # Convert to snake_case
        self.jinja_env.filters["to_snake_case"] = (
            lambda s: str(s).lower().replace("-", "_").replace(" ", "_")
        )

        # Convert to kebab-case
        self.jinja_env.filters["to_kebab_case"] = (
            lambda s: str(s).lower().replace("_", "-").replace(" ", "-")
        )

        # Quote string for YAML/JSON
        self.jinja_env.filters["quote"] = lambda s: f'"{s}"'

    def get_template(self, template_name: str) -> Any:
        """Load a Jinja2 template by name.

        Args:
            template_name: Template file name (relative to template_dir)

        Returns:
            Loaded Jinja2 template

        Raises:
            TemplateNotFound: If template doesn't exist
        """
        try:
            return self.jinja_env.get_template(template_name)
        except Exception as e:
            if hasattr(self, "_logger"):
                self._logger.error(f"Failed to load template {template_name}: {e}")
            raise

    def render_template(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> str:
        """Render a template with given context.

        Args:
            template_name: Template file name
            context: Template variables

        Returns:
            Rendered template content
        """
        template = self.get_template(template_name)
        try:
            return template.render(**context)
        except Exception as e:
            if hasattr(self, "_logger"):
                self._logger.error(f"Failed to render template {template_name}: {e}")
            raise

    def _write_terraform_file(self, filename: str, content: str) -> None:
        """Write content to a Terraform file.

        Args:
            filename: Name of the .tf file
            content: File content
        """
        if not hasattr(self, "terraform_dir"):
            raise AttributeError("Missing terraform_dir attribute (from ProviderBase)")

        file_path = Path(getattr(self, "terraform_dir")) / filename
        file_path.write_text(content)

        if hasattr(self, "_logger"):
            self._logger.debug(f"Wrote Terraform file: {file_path}")

    def _write_ansible_file(self, filename: str, content: str) -> None:
        """Write content to an Ansible file.

        Args:
            filename: Name of the file
            content: File content
        """
        if not hasattr(self, "ansible_dir"):
            raise AttributeError("Missing ansible_dir attribute (from ProviderBase)")

        file_path = Path(getattr(self, "ansible_dir")) / filename
        file_path.write_text(content)

        if hasattr(self, "_logger"):
            self._logger.debug(f"Wrote Ansible file: {file_path}")


class ResourceGrouperMixin:
    """Mixin for grouping resources by type.

    Provides:
    - Resource grouping by type
    - Resource type validation
    - Consistent resource organization

    Usage:
        class MyProvider(ProviderBase, ResourceGrouperMixin):
            def generate_terraform(self, resources):
                grouped = self.group_resources_by_type(resources)

                if "vm" in grouped:
                    self._generate_vms(grouped["vm"])

                if "network" in grouped:
                    self._generate_networks(grouped["network"])
    """

    def group_resources_by_type(
        self,
        resources: list[ResourceConfig],
    ) -> dict[str, list[ResourceConfig]]:
        """Group resources by their type field.

        Args:
            resources: List of resources to group

        Returns:
            Dictionary mapping resource types to lists of resources

        Example:
            >>> resources = [
            ...     ResourceConfig(name="vm1", type="vm", ...),
            ...     ResourceConfig(name="vm2", type="vm", ...),
            ...     ResourceConfig(name="net1", type="network", ...),
            ... ]
            >>> grouped = self.group_resources_by_type(resources)
            >>> grouped.keys()
            dict_keys(['vm', 'network'])
            >>> len(grouped['vm'])
            2
        """
        resources_by_type: dict[str, list[ResourceConfig]] = defaultdict(list)

        for resource in resources:
            resources_by_type[resource.type].append(resource)

        # Log grouping summary
        if hasattr(self, "_logger") and resources:
            summary = {rtype: len(rlist) for rtype, rlist in resources_by_type.items()}
            self._logger.debug(f"Grouped resources by type: {summary}")

        return dict(resources_by_type)

    def validate_resource_types(
        self,
        resources: list[ResourceConfig],
        supported_types: list[str] | None = None,
    ) -> tuple[list[ResourceConfig], list[ResourceConfig]]:
        """Validate that resources have supported types.

        Args:
            resources: Resources to validate
            supported_types: List of supported type names (if None, uses get_resource_types())

        Returns:
            Tuple of (valid_resources, invalid_resources)
        """
        if supported_types is None:
            if hasattr(self, "get_resource_types"):
                supported_types = self.get_resource_types()
            else:
                # No validation if no supported types defined
                return resources, []

        valid = []
        invalid = []

        for resource in resources:
            if resource.type in supported_types:
                valid.append(resource)
            else:
                invalid.append(resource)
                if hasattr(self, "_logger"):
                    self._logger.warning(
                        f"Unsupported resource type: {resource.type} for resource {resource.name}"
                    )

        return valid, invalid

    def get_resource_names_by_type(
        self,
        resources: list[ResourceConfig],
        resource_type: str,
    ) -> set[str]:
        """Get all resource names of a specific type.

        Useful for validation (checking if referenced resources exist).

        Args:
            resources: List of resources
            resource_type: Type to filter by

        Returns:
            Set of resource names with the given type
        """
        return {r.name for r in resources if r.type == resource_type}

    def count_resources_by_type(self, resources: list[ResourceConfig]) -> dict[str, int]:
        """Count resources by type.

        Args:
            resources: List of resources

        Returns:
            Dictionary mapping types to counts
        """
        counts: dict[str, int] = defaultdict(int)
        for resource in resources:
            counts[resource.type] += 1
        return dict(counts)


class TerraformGeneratorMixin:
    """Mixin providing helpers for generating terraform.tfvars files."""

    _TFVARS_HEADER = "# Configuration from settings.yaml\n"

    def _load_environment_config(self) -> Any | None:
        """Load current environment configuration if available."""
        env_name = getattr(self, "_current_environment", None)
        if not env_name:
            return None

        config_manager = ConfigManager(self.config_dir)
        try:
            return config_manager.load_environment(env_name)
        except FileNotFoundError:
            return None

    def _format_tfvar_line(self, name: str, value: Any) -> str:
        """Format a tfvar assignment."""
        return f"{name} = {json.dumps(value)}\n"

    def _append_tfvars_from_mapping(
        self,
        lines: list[str],
        provider_settings: dict[str, Any] | None,
        mapping: dict[str, str],
    ) -> None:
        """Append tfvar lines based on a settings-to-tfvar mapping."""
        if not provider_settings:
            return

        for source_key, tfvar_name in mapping.items():
            value = provider_settings.get(source_key)
            if value not in (None, ""):
                lines.append(self._format_tfvar_line(tfvar_name, value))

    def _append_ssh_tfvars(
        self,
        lines: list[str],
        env_config: Any,
        provider_name: str,
        prefix: str,
    ) -> None:
        """Append SSH-specific tfvar lines if configured."""
        ssh_config = env_config.get_ssh_config(provider_name)
        if not ssh_config:
            return

        if getattr(ssh_config, "user", None):
            lines.append(self._format_tfvar_line(f"{prefix}_ssh_user", ssh_config.user))

        if getattr(ssh_config, "key_path", None):
            lines.append(
                self._format_tfvar_line(f"{prefix}_ssh_key_path", str(ssh_config.key_path))
            )

        if getattr(ssh_config, "port", None) and ssh_config.port != 22:
            lines.append(self._format_tfvar_line(f"{prefix}_ssh_port", ssh_config.port))

    def _write_tfvars_lines(self, lines: list[str]) -> None:
        """Write tfvars lines to terraform.tfvars."""
        if len(lines) <= 1:
            return

        tfvars_path = Path(self.terraform_dir) / "terraform.tfvars"
        tfvars_path.write_text("".join(lines))

    def generate_provider_tfvars(
        self,
        provider_name: str,
        mapping: dict[str, str],
        *,
        include_ssh: bool = False,
        ssh_prefix: str | None = None,
    ) -> None:
        """Generate tfvars content using provided mappings."""
        env_config = self._load_environment_config()
        if not env_config:
            return

        lines = [self._TFVARS_HEADER]
        provider_settings = env_config.get_provider_settings(provider_name)
        self._append_tfvars_from_mapping(lines, provider_settings, mapping)

        if include_ssh:
            self._append_ssh_tfvars(
                lines,
                env_config,
                provider_name,
                prefix=ssh_prefix or provider_name,
            )

        self._write_tfvars_lines(lines)
