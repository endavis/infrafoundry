"""Validation for the OpenWrt provider: schema, settings and device connectivity."""

from __future__ import annotations

import shutil
import subprocess  # nosec B404  # required for the read-only ssh probe
from collections.abc import Callable, Mapping
from pathlib import Path

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.requirements.checker import check_collection, installed_collections
from infrafoundry.core.requirements.models import CollectionRequirement
from infrafoundry.core.validation import ValidationReport

from .devices import device_settings, validate_devices_settings
from .glinet.firmware import FIRMWARE_TYPE, check_firmware_resources
from .glinet.settings import web_settings_problems
from .schema import check_resources
from .settings import (
    PROVIDER_NAME,
    OpenWrtSettings,
    OpenWrtSettingsError,
    device_where,
    load_settings,
    settings_from_mapping,
)

COLLECTION = CollectionRequirement("community.openwrt", ">=1.11.0")
ANSIBLE_BINARY = "ansible-playbook"
UCODE_OK = "INFRAFOUNDRY_UCODE_OK"
PROBE_COMMAND = f"ubus -v list uci; if test -x /usr/bin/ucode; then echo {UCODE_OK}; fi"
"""Read-only: lists the ``uci`` ubus object and checks for ``ucode`` (the modules need it)."""

Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]
Which = Callable[[str], str | None]
CollectionsLookup = Callable[[], Mapping[str, str] | None]


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # list argv, no shell (B603 is skipped project-wide)
        argv, capture_output=True, text=True, check=False, timeout=60
    )


def ssh_argv(
    settings: OpenWrtSettings, remote_cmd: str, host_key_alias: str | None = None
) -> list[str]:
    """Build the ssh command for one fixed remote command.

    Host-key checking stays on and the address follows ``--`` so it is never an option.

    Args:
        settings: Device settings.
        remote_cmd: A fixed command string from this module.
        host_key_alias: When set, the host key is checked strictly under this alias (the
            firmware upgrade's post-reboot probe uses the settings address).
    """
    argv = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={settings.connect_timeout}"]
    if host_key_alias:
        argv += ["-o", "StrictHostKeyChecking=yes", "-o", f"HostKeyAlias={host_key_alias}"]
    argv += ["-p", str(settings.ssh_port)]
    if settings.ssh_private_key_file:
        argv += ["-i", settings.ssh_private_key_file]
    argv += ["-l", settings.ssh_user]
    return [*argv, "--", settings.address, remote_cmd]


class OpenWrtValidator:
    """Validates OpenWrt resources and the device connection for ``infra doctor``."""

    def __init__(
        self,
        env_config: EnvironmentConfig,
        report: ValidationReport,
        config_dir: Path | None = None,
        *,
        run: Runner | None = None,
        which: Which | None = None,
        collections_lookup: CollectionsLookup = installed_collections,
        provider_name: str = PROVIDER_NAME,
    ) -> None:
        """Initialize the validator.

        Args:
            env_config: Environment configuration.
            report: Report to add findings to.
            config_dir: Configuration directory, to load the connection settings.
            run: Runs the ssh probe; replaced in tests.
            which: Locates ``ansible-playbook``; replaced in tests.
            collections_lookup: Returns installed Ansible collections; replaced in tests.
            provider_name: ``openwrt`` or ``openwrt@<device>``: the device this validates.
        """
        self.provider_name = provider_name
        self.env_config = env_config
        self.report = report
        self.config_dir = config_dir
        self._run: Runner = run or _run
        self._which: Which = which or shutil.which
        self._collections_lookup = collections_lookup

    def validate_offline(self, resources: list[ResourceConfig]) -> None:
        """Check schema and settings; no network.

        Args:
            resources: Resources to validate; only OpenWrt types are checked.
        """
        if self.provider_name == PROVIDER_NAME:
            # The shape of the devices map is reported once, on the primary.
            raw_all = self.env_config.provider_settings.get(PROVIDER_NAME)
            for message in validate_devices_settings(
                raw_all if isinstance(raw_all, dict) else None
            ):
                self.report.add_check("openwrt_devices_settings", False, message)
        settings = self._settings_from_env()
        for finding in check_resources(resources, settings):
            self.report.add_check(
                check_name=f"openwrt_schema_{finding.resource}",
                passed=False,
                message=finding.message,
                level=finding.level,
            )
        self._check_firmware(resources)

    def _check_firmware(self, resources: list[ResourceConfig]) -> None:
        """Check the ``glinet.firmware`` resources and, if present, the device's web settings."""
        mine = [r for r in resources if r.type == FIRMWARE_TYPE]
        if not mine:
            return
        for finding in check_firmware_resources(mine):
            self.report.add_check(
                check_name=f"openwrt_schema_{finding.resource}",
                passed=False,
                message=finding.message,
                level=finding.level,
            )
        raw = self.env_config.provider_settings.get(PROVIDER_NAME) or {}
        if validate_devices_settings(raw if isinstance(raw, dict) else None):
            return  # reported as openwrt_devices_settings
        merged = device_settings(raw, self.provider_name)
        if not merged:
            return  # reported as openwrt_settings
        where = device_where(raw, self.provider_name)
        for problem in web_settings_problems(dict(merged), where):
            self.report.add_check("openwrt_firmware_settings", False, problem)

    def _settings_from_env(self) -> OpenWrtSettings | None:
        raw = self.env_config.provider_settings.get(PROVIDER_NAME) or {}
        if validate_devices_settings(raw if isinstance(raw, dict) else None):
            return None  # reported as openwrt_devices_settings
        merged = device_settings(raw, self.provider_name)
        if merged is not None and not merged and raw:
            self.report.add_check(
                "openwrt_settings",
                False,
                f"device '{self.provider_name}' is not declared under "
                "provider_settings.openwrt.devices",
            )
            return None
        try:
            return settings_from_mapping(dict(merged or {}), device_where(raw, self.provider_name))
        except OpenWrtSettingsError as exc:
            self.report.add_check("openwrt_settings", False, str(exc))
            return None

    def validate_references(self, resources: list[ResourceConfig]) -> None:
        """Run the offline checks; the provider has no cross-resource references to resolve."""
        self.validate_offline(resources)

    def validate_connectivity(self) -> None:
        """Check the tools on the controller, then probe the device read-only."""
        if self._which(ANSIBLE_BINARY) is None:
            self.report.add_check(
                "openwrt_ansible", False, f"{ANSIBLE_BINARY} is not on PATH; install ansible"
            )
        status = check_collection(COLLECTION, (), self._collections_lookup(), ())
        self.report.add_check(
            "openwrt_collection",
            status.satisfied,
            f"{COLLECTION.name}{COLLECTION.version} installed ({status.installed})"
            if status.satisfied
            else f"{COLLECTION.name}{COLLECTION.version}: {status.problem}; run foundry deps sync",
        )
        try:
            settings = self._load()
        except InfraFoundryError as exc:
            self.report.add_check("openwrt_connectivity", False, str(exc))
            return
        try:
            result = self._run(ssh_argv(settings, PROBE_COMMAND))
        except (OSError, subprocess.SubprocessError) as exc:
            self.report.add_check("openwrt_connectivity", False, f"ssh probe failed: {exc}")
            return
        if result.returncode != 0:
            self.report.add_check(
                "openwrt_connectivity",
                False,
                f"ssh probe exited {result.returncode}: {result.stderr.strip()[:200]}",
            )
            return
        self.report.add_check("openwrt_connectivity", True, "device reachable over ssh")
        listing = result.stdout
        has_apply = "apply" in listing and "rollback" in listing
        self.report.add_check(
            "openwrt_ubus_rollback",
            has_apply and "confirm" in listing,
            "ubus uci apply with rollback and confirm available"
            if has_apply and "confirm" in listing
            else "the device's ubus uci object lacks apply with rollback or confirm",
        )
        self.report.add_check(
            "openwrt_ucode",
            UCODE_OK in listing,
            "ucode present"
            if UCODE_OK in listing
            else "/usr/bin/ucode is missing; the community.openwrt modules need it",
        )

    def _load(self) -> OpenWrtSettings:
        if self.config_dir is None:
            raise InfraFoundryError("openwrt: no config directory to load settings from")
        return load_settings(self.config_dir, self.env_config.name, self.provider_name)
