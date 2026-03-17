"""Mixins providing common functionality for infrastructure providers.

These mixins extract repeated patterns from provider implementations,
reducing code duplication and standardizing provider behavior.
"""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import TemplateError
from infrafoundry.core.provider import ResourceConfig

if TYPE_CHECKING:
    # Type stubs for mixin expectations - not used at runtime
    class _TerraformGeneratorBase(Protocol):
        """Protocol defining attributes expected by TerraformGeneratorMixin."""

        config_dir: Path
        terraform_dir: Path

        def _write_terraform_file(self, filename: str, content: str) -> None: ...

    class _TerraformProviderProtocol(_TerraformGeneratorBase, Protocol):
        """Protocol capturing provider attributes used by TerraformGeneratorMixin helpers."""

        name: str

        def ensure_directories(self) -> None: ...

        def group_resources_by_type(
            self, resources: list[ResourceConfig]
        ) -> dict[str, list[ResourceConfig]]: ...

        def render_template(self, template_name: str, **context: Any) -> str: ...
else:
    _TerraformGeneratorBase = object  # pragma: no cover - runtime stub
    _TerraformProviderProtocol = object  # pragma: no cover - runtime stub


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
        provider_dir = Path(__file__).parent.parent / "providers" / self.name
        if template_subdir:
            self.template_dir = provider_dir / template_subdir
        else:
            self.template_dir = provider_dir / "templates"

        # Set up Jinja2 environment with defaults
        # Pass parameters explicitly for proper type checking
        # env_kwargs can override defaults or provide additional parameters
        extensions = env_kwargs.pop("extensions", [])
        if "jinja2.ext.do" not in extensions:
            extensions.append("jinja2.ext.do")

        # autoescape=False is intentional - we're generating Terraform/Ansible code,
        # not HTML. HTML escaping would break infrastructure configuration syntax.
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            trim_blocks=env_kwargs.pop("trim_blocks", True),
            lstrip_blocks=env_kwargs.pop("lstrip_blocks", True),
            keep_trailing_newline=env_kwargs.pop("keep_trailing_newline", True),
            extensions=extensions,
            autoescape=False,  # nosec B701 - infrastructure code, not HTML
            **env_kwargs,  # Pass through any additional parameters
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
        self.jinja_env.filters["to_snake_case"] = lambda s: (
            str(s).lower().replace("-", "_").replace(" ", "_")
        )

        # Convert to kebab-case
        self.jinja_env.filters["to_kebab_case"] = lambda s: (
            str(s).lower().replace("_", "-").replace(" ", "-")
        )

        # Quote string for YAML/JSON
        self.jinja_env.filters["quote"] = lambda s: f'"{s}"'

        # Python repr for code generation
        self.jinja_env.filters["repr"] = repr

    def get_template(self, template_name: str) -> Template:
        """Load a Jinja2 template by name.

        Args:
            template_name: Template file name (relative to template_dir)

        Returns:
            Loaded Jinja2 template

        Raises:
            TemplateError: If template cannot be loaded
        """
        try:
            return self.jinja_env.get_template(template_name)
        except TemplateNotFound as e:
            if hasattr(self, "_logger"):
                self._logger.error(f"Template not found: {template_name}")
            raise TemplateError(
                f"Template not found: {template_name}",
                context={"template": template_name},
            ) from e
        except Exception as e:
            if hasattr(self, "_logger"):
                self._logger.error(f"Failed to load template {template_name}: {e}")
            raise TemplateError(
                f"Failed to load template: {e}",
                context={"template": template_name},
            ) from e

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

        Raises:
            TemplateError: If template rendering fails
        """
        template = self.get_template(template_name)
        try:
            return template.render(**context)
        except Exception as e:
            if hasattr(self, "_logger"):
                self._logger.error(f"Failed to render template {template_name}: {e}")
            raise TemplateError(
                f"Failed to render template: {e}",
                context={"template": template_name},
            ) from e

    def _write_terraform_file(self, filename: str, content: str) -> None:
        """Write content to a Terraform file.

        Args:
            filename: Name of the .tf file
            content: File content
        """
        if not hasattr(self, "terraform_dir"):
            raise AttributeError("Missing terraform_dir attribute (from ProviderBase)")

        file_path = Path(self.terraform_dir) / filename
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

        file_path = Path(self.ansible_dir) / filename
        file_path.write_text(content)

        if hasattr(self, "_logger"):
            self._logger.debug(f"Wrote Ansible file: {file_path}")

    def _write_pyinfra_file(self, filename: str, content: str) -> None:
        """Write content to a pyinfra file.

        Args:
            filename: Name of the file
            content: File content
        """
        if not hasattr(self, "pyinfra_dir"):
            raise AttributeError("Missing pyinfra_dir attribute (from ProviderBase)")

        file_path = Path(self.pyinfra_dir) / filename
        file_path.write_text(content)

        if hasattr(self, "_logger"):
            self._logger.debug(f"Wrote pyinfra file: {file_path}")


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
    """Mixin providing helpers for generating terraform.tfvars files.

    This mixin expects the following attributes from the mixed-in class:
    - config_dir: Path to configuration directory
    - terraform_dir: Path to terraform output directory
    - _write_terraform_file(filename, content): Method to write terraform files
    """

    _TFVARS_HEADER = "# Configuration from settings.yaml\n"

    if TYPE_CHECKING:
        # Declare expected attributes for type checking
        config_dir: Path
        terraform_dir: Path

        def _write_terraform_file(self, filename: str, content: str) -> None: ...

    def _load_environment_config(self) -> EnvironmentConfig | None:
        """Load current environment configuration if available."""
        env_name = getattr(self, "_current_environment", None)
        if not env_name:
            return None

        # config_dir may be the envs/ directory (CLI) or envs/{env} (tests)
        # Try config_dir first, fall back to config_dir.parent
        settings_path = self.config_dir / env_name / "settings.yaml"
        if settings_path.exists():
            config_manager = ConfigManager(self.config_dir)
        else:
            config_manager = ConfigManager(self.config_dir.parent)
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
        env_config: EnvironmentConfig,
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
        """Generate tfvars content using provided mappings.

        .. deprecated::
            This method writes secrets to disk. Use
            :meth:`build_terraform_env_vars` instead, which returns
            ``TF_VAR_*`` environment variables for the runner.
        """
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

    def build_terraform_env_vars(
        self,
        provider_name: str,
        mapping: dict[str, str],
        *,
        include_ssh: bool = False,
        ssh_prefix: str | None = None,
    ) -> dict[str, str]:
        """Build TF_VAR_* env vars from provider settings.

        This is the environment-variable counterpart of
        ``generate_provider_tfvars``. Instead of writing a file, it
        returns a dict suitable for merging into the subprocess
        environment.

        Args:
            provider_name: Provider name used to look up settings
            mapping: Maps settings.yaml keys to terraform variable names
            include_ssh: Whether to include SSH settings
            ssh_prefix: Prefix for SSH variable names

        Returns:
            Dict mapping ``TF_VAR_<name>`` to string values
        """
        env_config = self._load_environment_config()
        if not env_config:
            return {}

        result: dict[str, str] = {}
        provider_settings = env_config.get_provider_settings(provider_name)
        if provider_settings:
            for source_key, tfvar_name in mapping.items():
                value = provider_settings.get(source_key)
                if value not in (None, ""):
                    result[f"TF_VAR_{tfvar_name}"] = (
                        json.dumps(value) if not isinstance(value, str) else value
                    )

        if include_ssh:
            ssh_config = env_config.get_ssh_config(provider_name)
            if ssh_config:
                prefix = ssh_prefix or provider_name
                if getattr(ssh_config, "user", None):
                    result[f"TF_VAR_{prefix}_ssh_user"] = str(ssh_config.user)
                if getattr(ssh_config, "key_path", None):
                    result[f"TF_VAR_{prefix}_ssh_key_path"] = str(ssh_config.key_path)
                if getattr(ssh_config, "port", None) and ssh_config.port != 22:
                    result[f"TF_VAR_{prefix}_ssh_port"] = str(ssh_config.port)

        return result

    def render_and_write_terraform(
        self,
        template_name: str,
        *,
        context: dict[str, Any] | None = None,
        output_name: str,
    ) -> None:
        """Render a Terraform template and write it to disk in one step.

        This helper eliminates the repetitive pattern of rendering a template and
        immediately writing it to a Terraform file. Providers that mix in both
        TemplateRendererMixin and TerraformGeneratorMixin can call this method to
        keep their generation logic concise.

        Args:
            template_name: Template to render, relative to the provider templates dir.
            context: Template context (defaults to empty dict).
            output_name: Terraform file name to write to within terraform_dir.
        """
        if not hasattr(self, "render_template"):
            raise AttributeError(
                "render_and_write_terraform requires TemplateRendererMixin-style render_template"
            )
        if not hasattr(self, "_write_terraform_file"):
            raise AttributeError(
                "render_and_write_terraform requires TemplateRendererMixin _write_terraform_file"
            )

        rendered = self.render_template(template_name, context or {})
        self._write_terraform_file(output_name, rendered)

    # Files and directories preserved during stale .tf cleanup
    _PRESERVED_TF_FILES: frozenset[str] = frozenset({"terraform.tfvars"})
    _PRESERVED_TF_DIRS: frozenset[str] = frozenset({".terraform"})
    _PRESERVED_TF_PATTERNS: frozenset[str] = frozenset({"terraform.tfstate"})

    def _clean_stale_tf_files(self) -> list[Path]:
        """Remove stale .tf files from the terraform directory before regenerating.

        Preserves terraform.tfvars, .terraform/ directory, and state files.

        Returns:
            List of paths that were removed.
        """
        terraform_dir = Path(self.terraform_dir)
        if not terraform_dir.exists():
            return []

        removed: list[Path] = []
        for tf_file in terraform_dir.glob("*.tf"):
            if tf_file.name in self._PRESERVED_TF_FILES:
                continue
            tf_file.unlink()
            removed.append(tf_file)

        if removed and hasattr(self, "_logger"):
            self._logger.debug("Cleaned %d stale .tf file(s) from %s", len(removed), terraform_dir)

        return removed

    def prepare_terraform_generation(
        self,
        resources: list[ResourceConfig],
    ) -> dict[str, list[ResourceConfig]]:
        """Ensure directories exist, clean stale files, and group resources.

        Removes previously generated ``.tf`` files before regenerating to prevent
        stale resources from persisting when config entries are removed. Files
        like ``terraform.tfvars``, the ``.terraform/`` directory, and state files
        are preserved.

        Args:
            resources: Resources to generate Terraform for.

        Returns:
            Resources grouped by type for downstream template rendering.

        Raises:
            AttributeError: If required provider helpers are missing.
        """
        if not hasattr(self, "ensure_directories"):
            raise AttributeError(
                "prepare_terraform_generation requires ProviderBase.ensure_directories"
            )

        provider = cast("_TerraformProviderProtocol", self)
        provider.ensure_directories()

        # Clean stale .tf files before regenerating
        self._clean_stale_tf_files()

        group_resources = getattr(provider, "group_resources_by_type", None)
        if not group_resources:
            raise AttributeError(
                "prepare_terraform_generation requires ResourceGrouperMixin.group_resources_by_type"
            )

        return cast(dict[str, list[ResourceConfig]], group_resources(resources))

    def render_provider_and_variables(
        self,
        *,
        provider_template: str | None = None,
        variables_template: str | None = None,
        variables_context: dict[str, Any] | None = None,
    ) -> None:
        """Render provider.tf and variables.tf using common defaults.

        Args:
            provider_template: Template name for provider configuration. Defaults to
                ``{self.name}/provider.tf.j2`` when omitted.
            variables_template: Template name for variables. Defaults to
                ``{self.name}/variables.tf.j2`` when omitted.
            variables_context: Context passed to the variables template.
        """
        provider = cast("_TerraformProviderProtocol", self)

        self.render_and_write_terraform(
            provider_template or f"{provider.name}/provider.tf.j2",
            output_name="provider.tf",
        )

        variables_template_name = variables_template or f"{provider.name}/variables.tf.j2"
        self.render_and_write_terraform(
            variables_template_name,
            context=variables_context or {},
            output_name="variables.tf",
        )

    def render_outputs_terraform(
        self,
        resources_by_type: dict[str, list[ResourceConfig]],
        *,
        template_name: str | None = None,
    ) -> None:
        """Render outputs.tf using grouped resources.

        Args:
            resources_by_type: Resources grouped by type for templating.
            template_name: Optional template override. Defaults to
                ``{self.name}/outputs.tf.j2``.
        """
        provider = cast("_TerraformProviderProtocol", self)
        self.render_and_write_terraform(
            template_name or f"{provider.name}/outputs.tf.j2",
            context={"resources_by_type": resources_by_type},
            output_name="outputs.tf",
        )

    def render_backend(self) -> bool:
        """Render backend.tf from environment backend configuration.

        Loads the backend configuration from the current environment's settings.yaml
        and generates a backend.tf file if a remote backend is configured.

        Returns:
            True if backend was rendered, False if no backend config or using local default

        Example:
            >>> provider.set_environment("prod")
            >>> provider.render_backend()  # Generates backend.tf if backend is configured
        """
        # Load environment configuration
        env_config = self._load_environment_config()
        if not env_config:
            return False

        # Check if backend is configured
        backend_config = env_config.backend
        if not backend_config:
            return False

        # Skip rendering for local backend (default)
        if backend_config.type.value == "local":
            return False

        # Validate backend configuration
        is_valid, error = backend_config.validate_backend()
        if not is_valid:
            raise ValueError(f"Invalid backend configuration: {error}")

        # Get backend configuration dict
        backend_dict = backend_config.get_backend_config()

        # Render backend.tf using common template
        # Template is in src/infrafoundry/templates/common/backend.tf.j2
        # We need to use render_template directly since the template is in a common location
        if hasattr(self, "render_template") and hasattr(self, "_write_terraform_file"):
            from pathlib import Path

            from jinja2 import Environment, FileSystemLoader

            # Load from common templates directory
            # autoescape=False is intentional - generating Terraform code, not HTML
            common_templates_dir = Path(__file__).parent.parent / "templates" / "common"
            env = Environment(
                loader=FileSystemLoader(str(common_templates_dir)),
                trim_blocks=True,
                lstrip_blocks=True,
                keep_trailing_newline=True,
                autoescape=False,  # nosec B701 - infrastructure code, not HTML
            )

            template = env.get_template("backend.tf.j2")
            content = template.render(
                backend_type=backend_config.type.value,
                backend_config=backend_dict,
                supports_locking=backend_config.supports_locking(),
            )

            self._write_terraform_file("backend.tf", content)
            return True

        return False
