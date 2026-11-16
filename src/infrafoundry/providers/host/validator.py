"""Validation for the host provider: schema, secret references and SSH reachability."""

from __future__ import annotations

import shutil
import subprocess  # nosec B404  # SSH reachability probe, list argv, no shell
from collections.abc import Callable
from pathlib import Path

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import validate_terraform_secrets_references

from .schema import DEFAULT_SSH_PORT, check_hosts, is_valid_address

SSH_TIMEOUT_SECONDS = 30

SshProbe = Callable[[list[str]], int]
"""Runs an ssh argv and returns its exit code; raises ``subprocess.TimeoutExpired`` or
``FileNotFoundError`` like ``subprocess.run``."""


def _run_ssh(argv: list[str]) -> int:
    """Run an ssh command and return its exit code."""
    result = subprocess.run(  # list argv, no shell
        argv, capture_output=True, timeout=SSH_TIMEOUT_SECONDS, check=False
    )
    return result.returncode


def ssh_argv(resource: ResourceConfig) -> list[str]:
    """Build the reachability probe command for a host.

    The address follows ``--`` so it can never be read as an option.

    Args:
        resource: A host resource with a valid address.
    """
    config = resource.config
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    argv += ["-p", str(config.get("ssh_port", DEFAULT_SSH_PORT))]
    if config.get("ssh_private_key_file"):
        argv += ["-i", str(config["ssh_private_key_file"])]
    if config.get("ssh_user"):
        argv += ["-l", str(config["ssh_user"])]
    return [*argv, "--", str(config["address"]), "true"]


class HostValidator:
    """Validates host resources for ``infra doctor``."""

    def __init__(
        self,
        env_config: EnvironmentConfig,
        report: ValidationReport,
        ssh_probe: SshProbe | None = None,
        repo_root: Path | None = None,
    ) -> None:
        """Initialize the validator.

        Args:
            env_config: Environment configuration (holds the decrypted secrets).
            report: Report to add findings to.
            ssh_probe: Replacement for the ssh runner, for tests.
            repo_root: Config repo root playbook paths are relative to.
        """
        self.env_config = env_config
        self.report = report
        self.ssh_probe: SshProbe = ssh_probe or _run_ssh
        self.repo_root = repo_root

    def validate_connectivity(self) -> None:
        """Warn when ``ansible-playbook`` is not installed."""
        found = shutil.which("ansible-playbook") is not None
        self.report.add_check(
            check_name="host_ansible_playbook",
            passed=found,
            message=(
                "ansible-playbook found"
                if found
                else "ansible-playbook not found on PATH; hosts cannot be configured"
            ),
            level=ValidationLevel.WARNING,
        )

    def validate_references(self, resources: list[ResourceConfig]) -> None:
        """Check each host's schema, secret references and SSH reachability.

        Args:
            resources: Resources to validate; only ``host`` resources are checked.
        """
        hosts = [r for r in resources if r.type == "host"]
        for finding in check_hosts(hosts, self.repo_root):
            self.report.add_check(
                check_name=f"host_schema_{finding.resource}",
                passed=False,
                message=finding.message,
                level=finding.level,
            )
        validate_terraform_secrets_references("host", hosts, self.env_config, self.report)
        for host in hosts:
            if is_valid_address(host.config.get("address")):
                self._probe(host)

    def _probe(self, host: ResourceConfig) -> None:
        """Record whether the host answers an SSH login."""
        check = f"host_ssh_{host.name}"
        try:
            code = self.ssh_probe(ssh_argv(host))
        except subprocess.TimeoutExpired:
            self.report.add_check(check, False, f"SSH to host '{host.name}' timed out")
            return
        except FileNotFoundError:
            self.report.add_check(
                check, False, "ssh not found on PATH", level=ValidationLevel.WARNING
            )
            return
        self.report.add_check(
            check,
            code == 0,
            f"SSH to host '{host.name}' succeeded"
            if code == 0
            else f"SSH to host '{host.name}' failed (exit {code})",
        )
