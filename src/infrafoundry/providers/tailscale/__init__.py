"""Tailscale control-plane provider for InfraFoundry.

Manages a tailnet (ACL policy, auth keys, device subnet routes and tags, DNS)
through the official ``tailscale/tailscale`` Terraform provider. This is the
control plane; the ``opnsense.tailscale.*`` types configure the node-side
plugin on a firewall.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, override

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import SchemaValidationError
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
)
from infrafoundry.core.validation import ValidationLevel, ValidationReport, run_validators

from .hcl import hcl_list, hcl_string
from .validator import TailscaleValidator, acl_policy_of, detect_auth_mode
from .validators import (
    AclValidator,
    CredentialsValidator,
    DeviceReferenceValidator,
    DnsValidator,
    NamingValidator,
    TailnetKeyValidator,
)
from .validators.context import TailscaleConfigContext, TailscaleCredentialsContext

logger = logging.getLogger(__name__)

#: provider_settings key -> Terraform variable name (``tailscale_<key>``).
_TAILSCALE_TFVARS_MAPPING: dict[str, str] = {
    key: f"tailscale_{key}"
    for key in (
        "api_key",
        "oauth_client_id",
        "oauth_client_secret",
        "scopes",
        "tailnet",
        "base_url",
    )
}

_DNS_TYPES = ("dns_nameservers", "dns_preferences", "dns_search_paths")


class TailscaleProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
):
    """Tailscale provider wrapping the official ``tailscale/tailscale`` Terraform provider.

    Credentials come from ``provider_settings.tailscale`` (``secret://`` URIs are
    resolved) and reach Terraform only as ``TF_VAR_*`` environment variables.
    """

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize Tailscale provider."""
        super().__init__("tailscale", config_dir, output_dir)
        self._setup_template_environment()
        self.jinja_env.filters["hcl_string"] = hcl_string
        self.jinja_env.filters["hcl_list"] = hcl_list

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate Tailscale resource configuration.

        Args:
            config: Configuration dictionary to validate

        Returns:
            True if valid, False otherwise
        """
        return all(field in config for field in ["name"])

    @override
    def validate_connectivity(
        self, env_config: EnvironmentConfig, report: ValidationReport
    ) -> None:
        """Check credential settings (config only, no network call)."""
        TailscaleValidator(env_config, report).validate_connectivity()

    @override
    def validate_references(
        self,
        resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Validate Tailscale resource configuration."""
        TailscaleValidator(env_config, report).validate_references(resources)

    @override
    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return [
            "acl",
            "tailnet_key",
            "device_subnet_routes",
            "device_tags",
            "dns_nameservers",
            "dns_preferences",
            "dns_search_paths",
        ]

    @override
    def get_terraform_resource_types(self) -> dict[str, list[str]]:
        """Map InfraFoundry resource types to terraform resource types."""
        return {rtype: [f"tailscale_{rtype}"] for rtype in self.get_resource_types()}

    @override
    def get_unsupported_resource_types(self) -> dict[str, str]:
        """Report the overlapping DNS resources as deliberately unsupported."""
        reason = (
            "it manages the same tailnet DNS settings as dns_nameservers, dns_preferences "
            "and dns_search_paths, and the two families must not be mixed"
        )
        return {
            "dns_configuration": f"tailscale_dns_configuration is not exposed: {reason}",
            "dns_split_nameservers": f"tailscale_dns_split_nameservers is not exposed: {reason}",
        }

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies: keys, tags and routes need the ACL's tagOwners first."""
        return {
            "acl": [],
            "tailnet_key": ["acl"],
            "device_tags": ["acl"],
            "device_subnet_routes": ["acl"],
            "dns_nameservers": [],
            "dns_preferences": [],
            "dns_search_paths": [],
        }

    @override
    def get_state_addresses_kept_on_destroy(self, resources: list[ResourceConfig]) -> list[str]:
        """Return the ``device_tags`` addresses opted out of destroy (#1349).

        Args:
            resources: The resources this destroy covers.

        Returns:
            Terraform addresses of ``device_tags`` with ``keep_tags_on_destroy: true``.
        """
        return [
            f"tailscale_device_tags.{r.name.replace('-', '_')}"
            for r in resources
            if r.type == "device_tags" and r.config.get("keep_tags_on_destroy") is True
        ]

    @override
    def get_terraform_env_vars(self) -> dict[str, str]:
        """Return TF_VAR_* variables, resolving ``secret://`` URIs in the settings."""
        return self.build_terraform_env_vars(
            "tailscale", _TAILSCALE_TFVARS_MAPPING, resolve_secret_uris=True
        )

    def _provider_settings(self) -> dict[str, Any]:
        """Return ``provider_settings.tailscale`` with URIs left unresolved."""
        env_config = self._load_environment_config()
        if not env_config:
            return {}
        return dict(env_config.get_provider_settings("tailscale") or {})

    def _auth_mode(self) -> str:
        """Return ``"oauth"``, ``"api_key"`` or ``"unset"`` for the current environment."""
        return detect_auth_mode(self._provider_settings())

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration for Tailscale resources."""
        resources_by_type = self.prepare_terraform_generation(resources)
        settings = self._provider_settings()
        self._validate_resource_configs(resources, settings)

        self.render_backend()
        self.render_provider_and_variables()

        acls = resources_by_type.get("acl", [])
        acl_tf = acls[0].name.replace("-", "_") if acls else None

        if acls:
            self.render_and_write_terraform(
                "tailscale/acl.tf.j2",
                context={"acls": acls, "acl_texts": {r.name: self._acl_text(r) for r in acls}},
                output_name="acl.tf",
            )
        if "tailnet_key" in resources_by_type:
            self.render_and_write_terraform(
                "tailscale/tailnet_key.tf.j2",
                context={"keys": resources_by_type["tailnet_key"], "acl_tf": acl_tf},
                output_name="tailnet_key.tf",
            )
        if "device_subnet_routes" in resources_by_type:
            self.render_and_write_terraform(
                "tailscale/device_subnet_routes.tf.j2",
                context={"routes": resources_by_type["device_subnet_routes"], "acl_tf": acl_tf},
                output_name="device_subnet_routes.tf",
            )
        if "device_tags" in resources_by_type:
            self.render_and_write_terraform(
                "tailscale/device_tags.tf.j2",
                context={"device_tags": resources_by_type["device_tags"], "acl_tf": acl_tf},
                output_name="device_tags.tf",
            )
        if any(t in resources_by_type for t in _DNS_TYPES):
            self.render_and_write_terraform(
                "tailscale/dns.tf.j2",
                context={
                    "nameservers": resources_by_type.get("dns_nameservers", []),
                    "preferences": resources_by_type.get("dns_preferences", []),
                    "search_paths": resources_by_type.get("dns_search_paths", []),
                },
                output_name="dns.tf",
            )

        self.render_outputs_terraform(resources_by_type)

    @staticmethod
    def _acl_text(resource: ResourceConfig) -> str:
        """Return the policy text of an ``acl`` resource (JSON dump or verbatim HuJSON)."""
        if "policy" in resource.config:
            return json.dumps(resource.config["policy"], indent=2)
        return str(resource.config["hujson"])

    def _validate_resource_configs(
        self, resources: list[ResourceConfig], settings: dict[str, Any]
    ) -> None:
        """Run the config and credential validators; raise on ERROR-level findings.

        Args:
            resources: All resources being generated.
            settings: ``provider_settings.tailscale`` with URIs unresolved.

        Raises:
            SchemaValidationError: If any check failed at ERROR level. The
                message lists check names and descriptions, never credential values.
        """
        report = ValidationReport()
        run_validators(
            (CredentialsValidator(report),),
            TailscaleCredentialsContext(
                provider_settings=settings,
                env_oauth=bool(os.environ.get("TAILSCALE_OAUTH_CLIENT_ID")),
                env_api_key=bool(os.environ.get("TAILSCALE_API_KEY")),
            ),
        )
        run_validators(
            (
                NamingValidator(report),
                AclValidator(report),
                TailnetKeyValidator(report),
                DeviceReferenceValidator(report),
                DnsValidator(report),
            ),
            TailscaleConfigContext(
                resources=resources,
                auth_mode=detect_auth_mode(settings),
                acl_policy=acl_policy_of(resources),
            ),
        )
        for result in report.results:
            if not result.passed and result.level == ValidationLevel.WARNING:
                logger.warning("[%s] %s", result.check_name, result.message)
        if report.has_errors():
            lines = [
                f"  - [{r.check_name}] {r.message}"
                for r in report.results
                if not r.passed and r.level == ValidationLevel.ERROR
            ]
            raise SchemaValidationError(
                "Tailscale resource configuration validation failed:\n" + "\n".join(lines)
            )

    @override
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Tailscale is Terraform-only; create the output directories."""
        self.ensure_directories()
