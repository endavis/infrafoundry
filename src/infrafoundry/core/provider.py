"""Base provider interface for infrastructure plugins."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.hooks.models import HooksConfig
from infrafoundry.core.validation import ValidationReport


class ResourceConfig(BaseModel):
    """Base configuration for infrastructure resources."""

    name: str
    type: str
    provider: str
    config: dict[str, Any]
    hooks: HooksConfig | None = None
    events: dict[str, list[dict[str, Any]]] | None = None
    package_variables: dict[str, Any] | None = None
    import_id: str | None = None


def group_by_package_variables(
    resources: Iterable[tuple[str, dict[str, Any] | None]],
) -> list[tuple[list[str], dict[str, Any]]]:
    """Group resource names by equal package variables, in first-seen order.

    Resources without package variables share the ``{}`` group. Duplicate
    names within a group are kept once.

    Args:
        resources: ``(resource_name, package_variables)`` pairs

    Returns:
        ``(names, package_variables)`` per distinct variables mapping
    """
    groups: list[tuple[list[str], dict[str, Any]]] = []
    for name, package_variables in resources:
        variables = package_variables or {}
        for names, group_vars in groups:
            if group_vars == variables:
                if name not in names:
                    names.append(name)
                break
        else:
            groups.append(([name], variables))
    return groups


class ProviderBase(ABC):
    """Base class for infrastructure providers."""

    def __init__(self, name: str, config_dir: Path, output_dir: Path) -> None:
        """Initialize provider.

        Args:
            name: Provider name (e.g., 'proxmox', 'opnsense', 'kubernetes')
            config_dir: Directory containing provider configs
            output_dir: Base directory for generated Terraform/Ansible files
                       (actual paths will be output_dir/{env}/{terraform|ansible}/{provider})
        """
        self.name = name
        self.config_dir = config_dir
        self.base_output_dir = output_dir  # Store base, use set_environment() for actual paths
        self.output_dir = output_dir  # Will be updated by set_environment()
        self.terraform_dir = output_dir / "terraform" / name
        self.ansible_dir = output_dir / "ansible" / name
        self.pyinfra_dir = output_dir / "pyinfra" / name
        self._current_environment: str | None = None
        self.terraform_parallelism: int | None = None

    def set_environment(self, env_name: str) -> None:
        """Set the current environment and update output directories.

        This should be called before generate_terraform(), generate_ansible(),
        or generate_pyinfra() to ensure files are generated in the correct
        environment-specific directory.

        Args:
            env_name: Environment name (e.g., 'dev', 'staging', 'prod')
        """
        self._current_environment = env_name
        self.output_dir = self.base_output_dir / env_name
        self.terraform_dir = self.output_dir / "terraform" / self.name
        self.ansible_dir = self.output_dir / "ansible" / self.name
        self.pyinfra_dir = self.output_dir / "pyinfra" / self.name

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate provider configuration.

        Args:
            config: Configuration dictionary to validate

        Returns:
            True if valid, False otherwise
        """
        pass

    @abstractmethod
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration files.

        Args:
            resources: List of resources to generate Terraform for
        """
        pass

    @abstractmethod
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Generate Ansible playbooks and roles.

        Args:
            resources: List of resources to generate Ansible for
        """
        pass

    def generate_pyinfra(self, resources: list[ResourceConfig]) -> None:
        """Generate pyinfra deploy scripts and inventory.

        Optional method. Providers can override this to support pyinfra.

        Args:
            resources: List of resources to generate pyinfra for
        """
        return

    def ensure_directories(self) -> None:
        """Create necessary output directories."""
        self.terraform_dir.mkdir(parents=True, exist_ok=True)
        self.ansible_dir.mkdir(parents=True, exist_ok=True)
        self.pyinfra_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def get_resource_types(self) -> list[str]:
        """Get list of resource types supported by this provider.

        Returns:
            List of supported resource type names
        """
        pass

    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies for proper ordering.

        Returns:
            Dict mapping resource types to their dependencies
        """
        return {}

    def get_unsupported_resource_types(self) -> dict[str, str]:
        """Get resource types that are deliberately rejected, with the reason.

        Optional hook (#1149). A type listed here is not in
        ``get_resource_types()``; the orchestrator and ``infra doctor`` report
        the reason instead of the generic "does not support" error.

        Returns:
            Dict mapping resource type to a human-readable reason
        """
        return {}

    def get_state_addresses_kept_on_destroy(self, resources: list[ResourceConfig]) -> list[str]:
        """List Terraform addresses to drop from state before a destroy.

        Optional hook (#1349). A Terraform runner removes these addresses from
        state before ``terraform destroy`` so the remote object outlives the
        destroy instead of being deleted.

        Args:
            resources: The resources this destroy covers (already filtered)

        Returns:
            Terraform resource addresses to forget; empty by default
        """
        return []

    def get_plan_notes(self, resources: list[ResourceConfig]) -> list[str]:
        """Return extra lines to show after this provider's plan.

        Optional hook (#1374). Called once per provider on a non-dry-run
        ``infra plan``; implementations must not fail the plan.

        Args:
            resources: The provider's full resource list for this run

        Returns:
            Plain-text lines to print; empty by default
        """
        return []

    def get_terraform_env_vars(self) -> dict[str, str]:
        """Return TF_VAR_* environment variables for this provider.

        Providers override this to supply their settings and credentials
        as Terraform input variables via the environment, eliminating the
        need for terraform.tfvars files on disk.

        Returns:
            Dict mapping TF_VAR_<name> keys to string values
        """
        return {}

    @abstractmethod
    def get_terraform_resource_types(self) -> dict[str, list[str]]:
        """Map InfraFoundry resource types to terraform resource types.

        Returns a dict where keys are InfraFoundry resource type names
        (matching ``get_resource_types()``) and values are lists of
        terraform resource type strings that represent that resource.
        Only terraform types present in this mapping will trigger
        resource lifecycle events (``on_create``, ``on_update``,
        ``on_destroy``).

        Returns:
            Dict mapping resource type names to lists of terraform
            resource type strings.
        """
        pass

    def validate_connectivity(
        self, env_config: EnvironmentConfig, report: ValidationReport
    ) -> None:
        """Validate connectivity to provider API.

        Optional method for providers to implement API connectivity checks.
        Should add results to the validation report.

        Args:
            env_config: Environment configuration including credentials
            report: ValidationReport to add results to
        """
        # Default: no connectivity validation
        return None

    def validate_references(
        self,
        resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Validate that referenced resources exist in the provider.

        Optional method for providers to check that templates, networks,
        aliases, etc. referenced in configs actually exist.

        Args:
            resources: Resources to validate
            env_config: Environment configuration including credentials
            report: ValidationReport to add results to
        """
        # Default: no reference validation
        return None


def unsupported_resource_reason(provider: object, resource_type: str) -> str | None:
    """Return why a provider rejects ``resource_type``, or ``None``.

    Guarded so a provider (or test double) without the optional
    ``get_unsupported_resource_types`` hook, or one returning a non-dict, is
    treated as having no unsupported types.

    Args:
        provider: Provider instance (any object)
        resource_type: Resource type to look up

    Returns:
        The reason string, or ``None`` when the type is not listed
    """
    hook: object = getattr(provider, "get_unsupported_resource_types", None)
    if not callable(hook):
        return None
    table: object = hook()
    if not isinstance(table, dict):
        return None
    reason: object = table.get(resource_type)
    return reason if isinstance(reason, str) and reason else None


def provider_plan_notes(provider: object, resources: list[ResourceConfig]) -> list[str]:
    """Return a provider's plan notes, tolerating a missing or odd hook.

    Guarded so a provider (or test double) without the optional
    ``get_plan_notes`` hook, or one returning a non-list, yields no notes.

    Args:
        provider: Provider instance (any object)
        resources: The provider's full resource list for this run

    Returns:
        The ``str`` items the hook returned
    """
    hook: object = getattr(provider, "get_plan_notes", None)
    if not callable(hook):
        return []
    notes: object = hook(resources)
    if not isinstance(notes, list):
        return []
    return [note for note in notes if isinstance(note, str)]


def unsupported_resource_message(
    provider_name: str, resource: str, resource_type: str, reason: str
) -> str:
    """Build the error message for a resource of an unsupported type.

    Args:
        provider_name: Provider name
        resource: Resource name
        resource_type: The unsupported resource type
        reason: Reason from :func:`unsupported_resource_reason`

    Returns:
        The message text
    """
    return (
        f"Resource '{resource}' has type '{resource_type}', which provider "
        f"'{provider_name}' does not support: {reason}"
    )
