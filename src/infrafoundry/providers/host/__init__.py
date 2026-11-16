"""Host provider: configures machines that already exist and that no provider creates.

InfraFoundry never creates or deletes the machine. ``infra apply`` writes an Ansible
inventory under ``generated/<env>/ansible/host/`` and ``HostRunner`` runs the
host's playbooks (and Tailscale enrollment) against it; ``infra destroy`` only
forgets the host in the state database (ADR-0022).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, override

import yaml

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import SchemaValidationError
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
)
from infrafoundry.core.secrets.secret_manager import SecretManager
from infrafoundry.core.tailscale import process_tailscale_config
from infrafoundry.core.validation import ValidationLevel, ValidationReport

from .schema import DEFAULT_SSH_PORT, check_hosts, tailscale_auth_ref
from .validator import HostValidator

ENROLLMENT_PLAYBOOK = "tailscale.yml"
"""Name of the generated Tailscale enrollment playbook."""


@dataclass(frozen=True)
class HostRun:
    """The playbooks to run against one host, in order."""

    name: str
    playbooks: tuple[str, ...]
    tailscale_auth_ref: str | None = None
    enrollment_playbook: str | None = None


class HostProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
):
    """Provider for existing hosts; generates an Ansible inventory, never creates the machine."""

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize the host provider."""
        super().__init__("host", config_dir, output_dir)
        self._last_hosts: list[ResourceConfig] = []
        self._setup_template_environment()

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate a host resource configuration."""
        return "name" in config

    @override
    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return ["host"]

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies (none)."""
        return {"host": []}

    @override
    def get_terraform_resource_types(self) -> dict[str, list[str]]:
        """Map ``host`` to a pseudo prefix so lifecycle events match ``host.<name>`` outcomes."""
        return {"host": ["host"]}

    @property
    def repo_root(self) -> Path:
        """The config repo root; ``config_dir`` is ``<repo>/envs``."""
        return self.config_dir.parent

    @override
    def validate_connectivity(
        self, env_config: EnvironmentConfig, report: ValidationReport
    ) -> None:
        """Check that ``ansible-playbook`` is installed."""
        HostValidator(env_config, report, repo_root=self.repo_root).validate_connectivity()

    @override
    def validate_references(
        self,
        resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Run schema, secret-reference and SSH reachability checks."""
        HostValidator(env_config, report, repo_root=self.repo_root).validate_references(resources)

    def _validate_resources(self, resources: list[ResourceConfig]) -> None:
        """Raise when any host fails its schema checks.

        Raises:
            SchemaValidationError: If a finding is at ERROR level.
        """
        errors = [
            f.message
            for f in check_hosts(resources, self.repo_root)
            if f.level == ValidationLevel.ERROR
        ]
        if errors:
            raise SchemaValidationError("Host configuration is invalid:\n" + "\n".join(errors))

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Write an empty ``terraform {}`` block; Terraform has nothing to manage on a host."""
        self.prepare_terraform_generation(resources)
        self.render_and_write_terraform("host/main.tf.j2", output_name="main.tf")

    @override
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Create the output directories; ``generate_host_ansible`` writes the files."""
        self.ensure_directories()

    def generate_host_ansible(self, resources: list[ResourceConfig]) -> None:
        """Write the inventory, ``ansible.cfg`` and the Tailscale enrollment playbook.

        Args:
            resources: All provider resources for the environment.

        Raises:
            SchemaValidationError: If a host is invalid.
        """
        hosts = [r for r in resources if r.type == "host"]
        self._validate_resources(hosts)
        self._last_hosts = hosts
        self.ensure_directories()

        roles_dir = self.repo_root / "roles"
        self._write_ansible_file(
            "ansible.cfg",
            self.render_template("host/ansible.cfg.j2", {"roles_path": str(roles_dir.resolve())}),
        )
        self._write_ansible_file("inventory.yml", self._render_inventory(hosts))

        enrollment = self.ansible_dir / ENROLLMENT_PLAYBOOK
        if any((h.config or {}).get("tailscale") is not None for h in hosts):
            self._write_ansible_file(
                ENROLLMENT_PLAYBOOK, self.render_template("host/tailscale.yml.j2", {})
            )
        elif enrollment.exists():
            enrollment.unlink()

    def _render_inventory(self, hosts: list[ResourceConfig]) -> str:
        """Render the Ansible inventory; holds no secret value or reference."""
        all_hosts: dict[str, dict[str, Any]] = {}
        groups: dict[str, dict[str, dict[str, Any]]] = {}
        for host in hosts:
            config = host.config
            entry: dict[str, Any] = {
                "ansible_host": config["address"],
                "ansible_port": config.get("ssh_port", DEFAULT_SSH_PORT),
            }
            if config.get("ssh_user"):
                entry["ansible_user"] = config["ssh_user"]
            if config.get("ssh_private_key_file"):
                entry["ansible_ssh_private_key_file"] = config["ssh_private_key_file"]
            module = process_tailscale_config(copy.deepcopy(host), base64_encode=False)
            if module is not None:
                entry["infrafoundry_tailscale"] = {
                    key: module[key]
                    for key in (
                        "hostname",
                        "enable_ssh",
                        "accept_dns",
                        "accept_routes",
                        "advertise_tags",
                        "advertise_routes",
                        "auth_mode",
                    )
                }
            all_hosts[host.name] = entry
            for group in config.get("groups", []):
                groups.setdefault(group, {})[host.name] = {}
        inventory: dict[str, Any] = {"all": {"hosts": all_hosts}}
        if groups:
            inventory["all"]["children"] = {g: {"hosts": members} for g, members in groups.items()}
        return yaml.safe_dump(inventory, sort_keys=False)

    def get_host_runs(self, names: list[str] | None = None) -> list[HostRun]:
        """Return what to run against each host, from the last ``generate_host_ansible``.

        Args:
            names: Restrict to these host names; ``None`` or empty means every host.
        """
        runs: list[HostRun] = []
        for host in self._last_hosts:
            if names and host.name not in names:
                continue
            ref = tailscale_auth_ref(host)
            playbooks: list[str] = []
            enrollment: str | None = None
            if ref is not None:
                enrollment = str(self.ansible_dir / ENROLLMENT_PLAYBOOK)
                playbooks.append(enrollment)
            for playbook in (host.config.get("ansible") or {}).get("playbooks", []):
                playbooks.append(str((self.repo_root / playbook).resolve()))
            runs.append(HostRun(host.name, tuple(playbooks), ref, enrollment))
        return runs

    def resolve_tailscale_auth(self, ref: str) -> str:
        """Return the secret a ``tailscale:`` auth reference points at.

        Args:
            ref: Dotted secret path from the host's ``tailscale.auth`` block.

        Raises:
            ValueError: If the reference does not resolve. The message holds the
                reference only, never a secret value.
        """
        env_config = self._load_environment_config()
        flat = SecretManager.flatten_dict(env_config.secrets if env_config else None)
        value = flat.get(ref)
        if not value:
            raise ValueError(f"Tailscale auth secret '{ref}' does not resolve in the env secrets")
        return str(value)
