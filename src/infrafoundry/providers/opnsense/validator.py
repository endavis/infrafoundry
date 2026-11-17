"""Validation logic for OPNsense provider.

This module contains all validation methods for checking OPNsense firewall
configurations against live API state before deployment.
"""

import logging
from dataclasses import replace
from typing import Any, TypedDict, cast

import httpx
import urllib3

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import (
    APIError,
    InvalidConfigurationError,
    ReferenceValidationError,
)
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_instances import qualified_provider_id
from infrafoundry.core.types import OPNsenseProviderSettings
from infrafoundry.core.validation import ValidationLevel, ValidationReport, run_validators
from infrafoundry.core.validation_helpers import BaseAPIValidator
from infrafoundry.providers.opnsense import endpoints
from infrafoundry.providers.opnsense.api_client import OPNsenseClient
from infrafoundry.providers.opnsense.firewalls import (
    FIREWALLS_KEY,
    allows_env_override,
    firewall_label,
    firewall_settings,
    ha_backup_name,
    validate_firewalls_settings,
)
from infrafoundry.providers.opnsense.services.carp_status import CarpStatusService  # #1393
from infrafoundry.providers.opnsense.services.hasync_settings import (
    HasyncSettingsService,  # #1393
    live_options,
)
from infrafoundry.providers.opnsense.services.hasync_status import (
    HasyncStatusService,  # #1393
    resolve_ha_sync_options,
)
from infrafoundry.providers.opnsense.services.openvpn_instances import flatten_option  # #1393
from infrafoundry.providers.opnsense.validators import (
    AcmeClientValidator,
    CarpHealthValidator,  # #1393
    CarpPairValidator,  # #1450
    CronJobsValidator,
    FirewallCategoryValidator,  # #1286
    FirewallRuleValidator,
    GatewayValidator,
    HasyncLiveValidator,  # #1389
    HasyncValidator,  # #1389
    HostDiscoveryValidator,
    InterfaceAssignmentValidator,
    InterfacesSettingsValidator,
    KeaHAValidator,  # #1392
    KeaReservationValidator,
    KeaSubnetAutoCollectValidator,  # #1432
    MonitValidator,  # #791
    NATRuleValidator,
    OpenVpnInstanceValidator,
    OpenVpnStaticKeyValidator,  # #1319
    RadvdValidator,
    ResourceNameValidator,
    SourceNatValidator,  # #1333
    StaticRouteValidator,
    SyslogSettingsValidator,  # #804
    SystemFirmwareValidator,
    SystemGroupValidator,
    SystemTuningValidator,
    SystemUserValidator,
    TailscaleValidator,  # #787
    TrustValidator,
    UnboundAdvancedValidator,
    UnboundForwardValidator,
    UnboundHostAliasValidator,
    UnboundSettingsValidator,
    UnboundValidator,
    VirtualIPTopologyValidator,  # #1391
    VirtualIPValidator,
    VLANValidator,
    build_xref_index,
)
from infrafoundry.providers.opnsense.validators._xref import XRefIndex
from infrafoundry.providers.opnsense.validators.context import (
    HaPeerCheck,
    OPNsenseValidationContext,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

_API_SECRET_ENV = "OPNSENSE_API_SECRET"  # nosec B105  # env var name, not a password literal


class AliasRow(TypedDict, total=False):
    """Partial representation of an alias row."""

    name: str


class InterfaceData(TypedDict, total=False):
    """Partial interface data exported by OPNsense."""

    if_type: str
    device: str


class OPNsenseValidator:
    """Validates OPNsense configurations against live API state.

    Performs comprehensive pre-flight validation including:
    - API connectivity and authentication
    - System status and version
    - Existing aliases, VLANs, and interfaces
    - Firewall rule references
    - DHCP configuration validity
    """

    def __init__(
        self,
        env_config: EnvironmentConfig,
        report: ValidationReport,
        provider_name: str = "opnsense",
    ) -> None:
        """Initialize OPNsense validator.

        Args:
            env_config: Environment configuration including provider_settings
            report: ValidationReport to add results to
            provider_name: ``opnsense`` (the primary) or ``opnsense@<firewall>`` (#1450);
                selects which firewall's settings the checks use.
        """
        self.env_config = env_config
        self.report = report
        self.provider_name = provider_name
        self.api_validator = BaseAPIValidator(
            "opnsense",
            env_config,
            report,
            env_prefix="OPNSENSE",
        )
        raw_settings = self.api_validator.provider_settings
        if isinstance(raw_settings, dict) and FIREWALLS_KEY in raw_settings:
            self.api_validator.provider_settings = (
                firewall_settings(raw_settings, provider_name) or {}
            )
        self.provider_settings = cast(
            OPNsenseProviderSettings, self.api_validator.provider_settings
        )

        # Initialize specialized validators
        self.firewall_rule_validator = FirewallRuleValidator(report)
        self.vlan_validator = VLANValidator(report)
        self.unbound_validator = UnboundValidator(report)
        self.resource_name_validator = ResourceNameValidator(report)
        self.interface_assignment_validator = InterfaceAssignmentValidator(report)
        self.nat_rule_validator = NATRuleValidator(report)
        self.gateway_validator = GatewayValidator(report)
        self.static_route_validator = StaticRouteValidator(report)
        self.virtual_ip_validator = VirtualIPValidator(report)
        self.unbound_host_alias_validator = UnboundHostAliasValidator(report)
        self.unbound_forward_validator = UnboundForwardValidator(report)
        self.kea_reservation_validator = KeaReservationValidator(report)
        self.kea_ha_validator = KeaHAValidator(report)  # #1392
        self.kea_subnet_autocollect_validator = KeaSubnetAutoCollectValidator(report)  # #1432
        self.virtual_ip_topology_validator = VirtualIPTopologyValidator(report)  # #1391
        self.radvd_validator = RadvdValidator(report)
        self.cron_jobs_validator = CronJobsValidator(report)
        self.trust_validator = TrustValidator(report)
        self.openvpn_instance_validator = OpenVpnInstanceValidator(report)
        self.openvpn_static_key_validator = OpenVpnStaticKeyValidator(report)  # #1319
        self.firewall_category_validator = FirewallCategoryValidator(report)  # #1286
        self.acmeclient_validator = AcmeClientValidator(report)  # #790
        self.tailscale_validator = TailscaleValidator(report)  # #787
        self.monit_validator = MonitValidator(report)  # #791
        self.system_firmware_validator = SystemFirmwareValidator(report)
        self.system_tuning_validator = SystemTuningValidator(report)
        self.system_user_validator = SystemUserValidator(report)
        self.system_group_validator = SystemGroupValidator(report)
        self.unbound_advanced_validator = UnboundAdvancedValidator(report)
        self.unbound_settings_validator = UnboundSettingsValidator(report)
        self.interfaces_settings_validator = InterfacesSettingsValidator(report)
        self.syslog_settings_validator = SyslogSettingsValidator(report)  # #804
        self.hasync_validator = HasyncValidator(report)  # #1389
        self.hasync_live_validator = HasyncLiveValidator(report)  # #1389
        self.carp_health_validator = CarpHealthValidator(report)  # #1393
        self.carp_pair_validator = CarpPairValidator(report)  # #1450
        self.hostdiscovery_validator = HostDiscoveryValidator(report)
        self.source_nat_validator = SourceNatValidator(report)  # #1333

    def _credential_env_map(self) -> dict[str, str]:
        """Return the env vars credentials may fall back to; none for a non-primary firewall."""
        if not allows_env_override(self.provider_name):
            return {}
        return {
            "api_url": "OPNSENSE_API_URL",
            "api_key": "OPNSENSE_API_KEY",
            "api_secret": _API_SECRET_ENV,
        }

    def validate_endpoint_support(self, resources: list[ResourceConfig]) -> None:
        """Check the in-scope resource types' endpoints against the box's version (#1239).

        Returns silently when credentials are missing; ``validate_connectivity``
        already reports that.

        Args:
            resources: Resources in scope; their types select the endpoints checked.
        """
        from .endpoint_support import check_box
        from .services._credentials import resolve_credentials

        types = sorted({r.type for r in resources})
        if not types:
            return
        provider_settings = firewall_settings(self.env_config, self.provider_name)
        if not provider_settings:
            return
        try:
            api_url, api_key, api_secret, verify_ssl, proxy = resolve_credentials(
                provider_settings, allow_env_override=allows_env_override(self.provider_name)
            )
        except (ValueError, KeyError):
            return
        client = OPNsenseClient(
            api_key=api_key,
            api_secret=api_secret,
            base_url=api_url,
            verify_ssl=verify_ssl,
            proxy=proxy,
        )
        result = check_box(client, types)
        for index, message in enumerate(result.errors, start=1):
            self.api_validator.add_error(
                check_name=f"opnsense_endpoint_support_{index}", message=message
            )
        for index, message in enumerate(result.warnings, start=1):
            self.api_validator.add_error(
                check_name=f"opnsense_endpoint_support_warning_{index}",
                message=message,
                level=ValidationLevel.WARNING,
            )
        if not result.errors and not result.warnings:
            self.api_validator.add_success(
                check_name="opnsense_endpoint_support",
                message=f"OPNsense {result.version}: endpoints for {', '.join(types)} are served",
            )

    def validate_ha_health(self) -> None:
        """Report CARP VIP state and HA peer reachability (#1393, doctor only).

        Read-only: ``getVipStatus``, ``core/hasync/get`` and, when a sync target is
        set, ``core/hasync_status/version``. Returns silently when credentials are
        missing; ``validate_connectivity`` already reports that.
        """
        from .services._credentials import resolve_credentials

        provider_settings = firewall_settings(self.env_config, self.provider_name)
        if not provider_settings:
            return
        try:
            api_url, api_key, api_secret, verify_ssl, proxy = resolve_credentials(
                provider_settings, allow_env_override=allows_env_override(self.provider_name)
            )
        except (ValueError, KeyError):
            return
        try:
            options = resolve_ha_sync_options(provider_settings)
        except InvalidConfigurationError as exc:
            self.api_validator.add_error(check_name="opnsense_ha_sync_settings", message=str(exc))
            return
        client = OPNsenseClient(
            api_key=api_key,
            api_secret=api_secret,
            base_url=api_url,
            verify_ssl=verify_ssl,
            proxy=proxy,
            timeout=options.timeout,
        )
        try:
            carp_status = CarpStatusService(client).vip_status()
            settings_service = HasyncSettingsService(client)
            hasync = settings_service.live_hasync(settings_service.get_settings())
        except (APIError, httpx.HTTPError) as exc:
            self.api_validator.add_error(
                check_name="opnsense_carp_status_read",
                message=f"Could not read CARP or HA sync state: {exc}",
                level=ValidationLevel.WARNING,
            )
            return
        sync_target = flatten_option(hasync.get("synchronizetoip")).strip()
        peer_check: HaPeerCheck | None = None
        if sync_target:
            logger.info(
                "checking HA peer %s; can take up to %s s when it is down",
                sync_target,
                options.timeout,
            )
            peer_check = self._check_ha_peer(client, sync_target, options.timeout)
        self.carp_health_validator.validate(
            OPNsenseValidationContext(
                resources=[],
                live_carp_status=carp_status,
                live_sync_target=sync_target,
                peer_check=peer_check,
            )
        )
        self._validate_carp_pair(carp_status, options.timeout)

    def _validate_carp_pair(self, carp_status: dict[str, Any], timeout: int) -> None:
        """Compare this node's CARP VIPs with its ``ha_backup`` firewall's (#1450).

        Does nothing unless this firewall's entry sets ``ha_backup``. An unreadable
        backup is a WARNING: the pair cannot be judged, which is not a CARP fault.

        Args:
            carp_status: This node's ``getVipStatus`` reply.
            timeout: Per-request timeout for the backup client.
        """
        backup = ha_backup_name(self.env_config, self.provider_name)
        if backup is None:
            return
        backup_id = qualified_provider_id("opnsense", backup)
        try:
            from .services._credentials import resolve_credentials

            settings = firewall_settings(self.env_config, backup_id)
            if not settings:
                raise ValueError(f"no settings for firewall '{backup}'")
            api_url, api_key, api_secret, verify_ssl, proxy = resolve_credentials(
                settings, allow_env_override=False
            )
            backup_client = OPNsenseClient(
                api_key=api_key,
                api_secret=api_secret,
                base_url=api_url,
                verify_ssl=verify_ssl,
                proxy=proxy,
                timeout=timeout,
            )
            peer_status = CarpStatusService(backup_client).vip_status()
        except (APIError, httpx.HTTPError, ValueError, KeyError) as exc:
            self.api_validator.add_error(
                check_name="opnsense_carp_pair_read",
                message=f"Could not read CARP state of ha_backup firewall '{backup}': {exc}",
                level=ValidationLevel.WARNING,
            )
            return
        self.carp_pair_validator.validate(
            OPNsenseValidationContext(
                resources=[],
                live_carp_status=carp_status,
                peer_carp_status=peer_status,
                node_label=firewall_label(self.env_config, self.provider_name) or "this node",
                peer_label=backup,
            )
        )

    @staticmethod
    def _check_ha_peer(client: OPNsenseClient, target: str, timeout: int) -> HaPeerCheck:
        """Call ``core/hasync_status/version`` and turn the outcome into a ``HaPeerCheck``."""
        try:
            reply = HasyncStatusService(client, timeout).version(target)
        except APIError as exc:
            return HaPeerCheck(ok=False, message=str(exc))
        response = reply.get("response")
        version: str | None = None
        if isinstance(response, dict):
            firmware = response.get("firmware")
            candidate = (
                firmware.get("_my_version") if isinstance(firmware, dict) else None
            ) or response.get("product_version")
            version = str(candidate) if candidate else None
        return HaPeerCheck(ok=True, version=version, answered=bool(response))

    def validate_connectivity(self) -> None:
        """Validate connectivity to OPNsense API.

        Checks:
        - API endpoint is reachable
        - Authentication credentials are valid
        - Can retrieve system status
        """
        env_map = self._credential_env_map()
        credentials = self.api_validator.get_credentials(
            ["api_url", "api_key", "api_secret"],
            env_vars=env_map,
        )
        if not credentials:
            return

        api_url = credentials["api_url"]
        api_key = credentials["api_key"]
        api_secret = credentials["api_secret"]

        response = self.api_validator.api_request(
            url=f"{api_url}/api/{endpoints.CORE_SYSTEM_STATUS.path()}",
            auth=(api_key, api_secret),
            verify_ssl=False,
            timeout=10,
            check_name="opnsense_api_connection",
            expect_ok=False,
            error_message="Error connecting to OPNsense: {error}",
        )
        if not response:
            return

        if response.status_code == 200:
            data = response.json()
            self.api_validator.add_success(
                check_name="opnsense_api_connection",
                message=f"Successfully connected to OPNsense API at {api_url}",
            )

            if "product_version" in data:
                version = data.get("product_version", "unknown")
                self.api_validator.add_success(
                    check_name="opnsense_version",
                    message=f"OPNsense version: {version}",
                )
        elif response.status_code == 401:
            self.api_validator.add_error(
                check_name="opnsense_api_connection",
                message="OPNsense API credentials invalid (401 Unauthorized)",
            )
        else:
            self.api_validator.add_error(
                check_name="opnsense_api_connection",
                message=f"OPNsense API returned status {response.status_code}",
                level=ValidationLevel.WARNING,
            )

    def validate_references(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig] | None = None,
    ) -> None:
        """Validate that referenced OPNsense resources exist.

        Checks:
        - Aliases referenced in firewall rules exist
        - VLANs referenced in DHCP maps exist
        - Interfaces are valid
        - Unbound host override fields are valid
        - No duplicate resource names

        Args:
            resources: List of resources to validate
            reference_resources: Resources that references may resolve to.
                Defaults to ``resources``. A filtered run passes every
                OPNsense resource in the environment, so a reservation in
                one package can name a subnet managed by another (#1133).
        """
        env_map = self._credential_env_map()
        credentials = self.api_validator.get_credentials(
            ["api_url", "api_key", "api_secret"],
            env_vars=env_map,
        )
        if not credentials:
            return

        api_url = credentials["api_url"]
        api_key = credentials["api_key"]
        api_secret = credentials["api_secret"]

        # Collect resources by type and build the shared context (#1433).
        resource_refs, reference_refs, xref_index = self._collect_refs(
            resources, reference_resources
        )

        # Validate against live API
        try:
            # Get existing aliases from OPNsense
            existing_aliases = self._get_existing_aliases(api_url, api_key, api_secret)

            # Get existing interfaces/VLANs
            existing_interfaces = self._get_existing_interfaces(api_url, api_key, api_secret)

            # Get existing gateway names (managed + dynamic) for static-route refs
            existing_gateways = self._get_existing_gateways(api_url, api_key, api_secret)

            # Get existing Unbound host overrides (live names) for host-alias refs
            existing_unbound_host_overrides = self._get_existing_unbound_host_overrides(
                api_url, api_key, api_secret
            )

            # #1389: the live pfsync interface and sync-item options, only when in scope
            hasync_interfaces: set[str] = set()
            hasync_items: set[str] = set()
            if resource_refs["hasync"]:
                hasync_interfaces, hasync_items = self._get_existing_hasync_options(
                    api_url, api_key, api_secret
                )

            context = self._build_context(
                resources,
                resource_refs,
                reference_refs,
                xref_index,
                existing_interfaces=existing_interfaces,
                existing_aliases=existing_aliases,
                existing_gateways=existing_gateways,
                existing_host_override_names=existing_unbound_host_overrides,
                existing_hasync_interfaces=hasync_interfaces,
                existing_hasync_sync_items=hasync_items,
            )
            self._run_live_validators(context, resource_refs)
            self._run_offline_validators(context, resource_refs)

        except Exception as exc:
            check_name = "opnsense_validation"
            if isinstance(exc, ReferenceValidationError):
                check_name = "opnsense_reference_validation"
            self.api_validator.handle_validation_exception(
                check_name=check_name,
                error=exc,
                warning_level=ValidationLevel.ERROR,
            )

    @staticmethod
    def _build_context(
        resources: list[ResourceConfig],
        resource_refs: dict[str, Any],
        reference_refs: dict[str, Any],
        xref_index: XRefIndex,
        existing_interfaces: dict[str, Any] | None = None,
        existing_aliases: dict[str, Any] | None = None,
        existing_gateways: set[str] | None = None,
        existing_host_override_names: set[str] | None = None,
        existing_hasync_interfaces: set[str] | None = None,
        existing_hasync_sync_items: set[str] | None = None,
    ) -> OPNsenseValidationContext:
        """Build the validation context; the ``existing_*`` fields stay empty offline."""
        return OPNsenseValidationContext(
            resources=resources,
            firewall_rules=resource_refs["firewall_rules"],
            vlans=resource_refs["vlans"],
            assignments=resource_refs["interface_assignments"],
            nat_rules=resource_refs["nat_rules"],
            gateways=resource_refs["gateways"],
            static_routes=resource_refs["static_routes"],
            virtual_ips=resource_refs["virtual_ips"],
            host_aliases=resource_refs["unbound_host_aliases"],
            dhcp4_reservations=resource_refs["kea_dhcp4_reservations"],
            dhcp6_reservations=resource_refs["kea_dhcp6_reservations"],
            alias_names=reference_refs["alias_names"],
            interface_assignment_names=reference_refs["interface_assignment_names"],
            gateway_names=reference_refs["gateway_names"],
            vlan_names=reference_refs["vlan_names"],
            managed_host_override_names=reference_refs["unbound_host_override_names"],
            dhcp4_subnet_names=reference_refs["kea_dhcp4_subnet_names"],
            dhcp6_subnet_names=reference_refs["kea_dhcp6_subnet_names"],
            existing_interfaces=existing_interfaces or {},
            existing_aliases=existing_aliases or {},
            existing_gateways=existing_gateways or set(),
            existing_host_override_names=existing_host_override_names or set(),
            existing_hasync_interfaces=existing_hasync_interfaces or set(),
            existing_hasync_sync_items=existing_hasync_sync_items or set(),
            managed_gateways=reference_refs["gateways"],
            index=xref_index,
        )

    def _collect_refs(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig] | None,
    ) -> tuple[dict[str, Any], dict[str, Any], XRefIndex]:
        """Collect references for *resources* and the names they resolve against."""
        resource_refs = self._collect_resource_references(resources)
        # Name lookups resolve against the whole environment; only the
        # resources in scope are checked.
        reference_list = reference_resources if reference_resources is not None else resources
        reference_refs = (
            resource_refs
            if reference_resources is None
            else self._collect_resource_references(reference_list)
        )

        # Build the dotted-type cross-reference index once (#793). The
        # nested-dict shape gives O(1) lookup per resolver call inside
        # each per-resource validator. Validators that haven't adopted
        # the resolver yet ignore this argument; that's fine — the
        # parameter is optional and additive.
        xref_index = build_xref_index(reference_list)

        return resource_refs, reference_refs, xref_index

    def _run_live_validators(
        self, context: OPNsenseValidationContext, resource_refs: dict[str, Any]
    ) -> None:
        """Run the validators that read live ``existing_*`` state (doctor only)."""
        run_validators(
            (
                self.firewall_rule_validator,
                self.vlan_validator,
                self.interface_assignment_validator,
                self.nat_rule_validator,
                self.gateway_validator,
                self.static_route_validator,
                self.virtual_ip_validator,
            ),
            context,
        )
        self.unbound_host_alias_validator.validate(
            replace(context, forwards=resource_refs["unbound_forwards"])
        )
        self.hostdiscovery_validator.validate(
            replace(context, resources=resource_refs["hostdiscovery"])
        )
        self.radvd_validator.validate(replace(context, resources=resource_refs["radvd"]))
        self.hasync_live_validator.validate(replace(context, resources=resource_refs["hasync"]))

    def _run_offline_validators(
        self, context: OPNsenseValidationContext, resource_refs: dict[str, Any]
    ) -> None:
        """Run the validators that need no live state; also used on ``infra plan``."""
        self.unbound_validator.validate(
            replace(context, resources=resource_refs["unbound_host_overrides"])
        )
        self.unbound_forward_validator.validate(
            replace(context, forwards=resource_refs["unbound_forwards"])
        )
        self.unbound_advanced_validator.validate(
            replace(context, resources=resource_refs["unbound_advanced"])
        )
        self.unbound_settings_validator.validate(
            replace(context, resources=resource_refs["unbound_settings"])
        )
        self.interfaces_settings_validator.validate(
            replace(context, resources=resource_refs["interfaces_settings"])
        )
        # #804
        self.syslog_settings_validator.validate(
            replace(context, resources=resource_refs["syslog_settings"])
        )
        self.hasync_validator.validate(replace(context, resources=resource_refs["hasync"]))  # #1389
        # #1333
        self.source_nat_validator.validate(replace(context, resources=resource_refs["source_nat"]))
        self.kea_reservation_validator.validate(context)
        self.cron_jobs_validator.validate(replace(context, resources=resource_refs["cron_jobs"]))
        self.trust_validator.validate(replace(context, resources=resource_refs["trust"]))
        self.openvpn_instance_validator.validate(
            replace(context, resources=resource_refs["openvpn_instances"])
        )
        self.openvpn_static_key_validator.validate(
            replace(context, resources=resource_refs["openvpn_static_keys"])
        )
        self.firewall_category_validator.validate(
            replace(context, resources=resource_refs["firewall_categories"])
        )
        self.acmeclient_validator.validate(replace(context, resources=resource_refs["acmeclient"]))
        self.tailscale_validator.validate(replace(context, resources=resource_refs["tailscale"]))
        self.kea_ha_validator.validate(replace(context, resources=resource_refs["kea_ha"]))
        self.kea_subnet_autocollect_validator.validate(
            replace(context, resources=resource_refs["kea_dhcp4_subnets"])
        )
        self.virtual_ip_topology_validator.validate(context)  # #1391
        self.monit_validator.validate(replace(context, resources=resource_refs["monit"]))
        self.system_firmware_validator.validate(
            replace(context, resources=resource_refs["system_firmware"])
        )
        self.system_tuning_validator.validate(
            replace(context, resources=resource_refs["system_tuning"])
        )
        self.system_user_validator.validate(
            replace(context, resources=resource_refs["system_users"])
        )
        self.system_group_validator.validate(
            replace(context, resources=resource_refs["system_groups"])
        )
        self.resource_name_validator.validate(context)

    def validate_offline(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig] | None = None,
    ) -> None:
        """Run the checks that need no credentials or network (#1433).

        Args:
            resources: Resources to validate
            reference_resources: Resources that references may resolve to.
        """
        if self.provider_name == "opnsense":
            for message in validate_firewalls_settings(
                self.env_config.get_provider_settings("opnsense")
            ):
                self.api_validator.add_error(
                    check_name="opnsense_firewalls_settings", message=message
                )
        try:
            resolve_ha_sync_options(firewall_settings(self.env_config, self.provider_name))
        except InvalidConfigurationError as exc:
            self.api_validator.add_error(check_name="opnsense_ha_sync_settings", message=str(exc))
        resource_refs, reference_refs, xref_index = self._collect_refs(
            resources, reference_resources
        )
        try:
            context = self._build_context(resources, resource_refs, reference_refs, xref_index)
            self._run_offline_validators(context, resource_refs)
        except Exception as exc:
            check_name = "opnsense_validation"
            if isinstance(exc, ReferenceValidationError):
                check_name = "opnsense_reference_validation"
            self.api_validator.handle_validation_exception(
                check_name=check_name,
                error=exc,
                warning_level=ValidationLevel.ERROR,
            )

    def _collect_resource_references(self, resources: list[ResourceConfig]) -> dict[str, Any]:
        """Collect all resource references from configurations.

        Args:
            resources: List of resources to scan

        Returns:
            Dict with collected references organized by type
        """
        aliases = [r for r in resources if r.type == "firewall.aliases"]
        vlans = [r for r in resources if r.type == "interfaces.vlans"]
        firewall_rules = [r for r in resources if r.type == "firewall.rules"]
        unbound_host_overrides = [r for r in resources if r.type == "unbound.host_overrides"]
        unbound_host_aliases = [r for r in resources if r.type == "unbound.host_aliases"]
        unbound_forwards = [r for r in resources if r.type == "unbound.forwards"]
        unbound_advanced = [r for r in resources if r.type == "unbound.advanced"]
        unbound_settings = [r for r in resources if r.type == "unbound.settings"]
        interfaces_settings = [r for r in resources if r.type == "interfaces.settings"]
        syslog_settings = [r for r in resources if r.type == "syslog.settings"]  # #804
        hasync = [r for r in resources if r.type == "hasync.settings"]  # #1389
        hostdiscovery = [r for r in resources if r.type == "hostdiscovery"]
        source_nat = [r for r in resources if r.type == "firewall.source_nat"]  # #1333
        interface_assignments = [r for r in resources if r.type == "interfaces.assignments"]
        nat_rules = [r for r in resources if r.type == "firewall.nat"]
        gateways = [r for r in resources if r.type == "routing.gateways"]
        static_routes = [r for r in resources if r.type == "routing.static"]
        virtual_ips = [r for r in resources if r.type == "interfaces.virtual_ips"]
        kea_dhcp4_reservations = [r for r in resources if r.type == "kea.dhcp4.reservations"]
        kea_dhcp6_reservations = [r for r in resources if r.type == "kea.dhcp6.reservations"]
        kea_dhcp4_subnets = [r for r in resources if r.type == "kea.dhcp4.subnets"]
        kea_dhcp6_subnets = [r for r in resources if r.type == "kea.dhcp6.subnets"]
        radvd = [r for r in resources if r.type == "radvd"]
        cron_jobs = [r for r in resources if r.type == "cron.jobs"]
        trust = [r for r in resources if r.type in {"trust.cas", "trust.certs"}]
        openvpn_instances = [r for r in resources if r.type == "openvpn.instances"]
        openvpn_static_keys = [r for r in resources if r.type == "openvpn.static_keys"]
        firewall_categories = [r for r in resources if r.type == "firewall.categories"]
        acmeclient = [r for r in resources if r.type.startswith("acmeclient.")]
        tailscale = [r for r in resources if r.type.startswith("tailscale.")]
        kea_ha = [r for r in resources if r.type in ("kea.dhcp4.ha", "kea.dhcp4.ha_peers")]
        monit = [r for r in resources if r.type.startswith("monit.")]
        system_firmware = [r for r in resources if r.type == "system.firmware"]
        system_tuning = [r for r in resources if r.type == "system.tuning"]
        system_users = [r for r in resources if r.type == "system.users"]
        system_groups = [r for r in resources if r.type == "system.groups"]

        alias_names = {a.name for a in aliases}
        vlan_names = {v.name for v in vlans}
        interface_assignment_names = {a.name for a in interface_assignments}
        nat_rule_names = {r.name for r in nat_rules}
        gateway_names = {g.name for g in gateways}
        static_route_names = {r.name for r in static_routes}
        virtual_ip_names = {v.name for v in virtual_ips}
        kea_dhcp4_subnet_names = {s.name for s in kea_dhcp4_subnets}
        kea_dhcp6_subnet_names = {s.name for s in kea_dhcp6_subnets}
        # ``unbound_host_alias.host`` cross-refs the *name* of a managed
        # ``unbound_host_override`` resource (the alias validator also
        # accepts a live override name from ``searchHostOverride``).
        unbound_host_override_names = {r.name for r in unbound_host_overrides}

        return {
            "aliases": aliases,
            "alias_names": alias_names,
            "vlans": vlans,
            "vlan_names": vlan_names,
            "firewall_rules": firewall_rules,
            "unbound_host_overrides": unbound_host_overrides,
            "unbound_host_override_names": unbound_host_override_names,
            "unbound_host_aliases": unbound_host_aliases,
            "unbound_forwards": unbound_forwards,
            "unbound_advanced": unbound_advanced,
            "unbound_settings": unbound_settings,
            "interfaces_settings": interfaces_settings,
            "syslog_settings": syslog_settings,  # #804
            "hasync": hasync,  # #1389
            "hostdiscovery": hostdiscovery,
            "source_nat": source_nat,  # #1333
            "interface_assignments": interface_assignments,
            "interface_assignment_names": interface_assignment_names,
            "nat_rules": nat_rules,
            "nat_rule_names": nat_rule_names,
            "gateways": gateways,
            "gateway_names": gateway_names,
            "static_routes": static_routes,
            "static_route_names": static_route_names,
            "virtual_ips": virtual_ips,
            "virtual_ip_names": virtual_ip_names,
            "kea_dhcp4_reservations": kea_dhcp4_reservations,
            "kea_dhcp6_reservations": kea_dhcp6_reservations,
            "kea_dhcp4_subnets": kea_dhcp4_subnets,
            "kea_dhcp6_subnets": kea_dhcp6_subnets,
            "kea_dhcp4_subnet_names": kea_dhcp4_subnet_names,
            "kea_dhcp6_subnet_names": kea_dhcp6_subnet_names,
            "radvd": radvd,
            "cron_jobs": cron_jobs,
            "trust": trust,
            "openvpn_instances": openvpn_instances,
            "openvpn_static_keys": openvpn_static_keys,
            "firewall_categories": firewall_categories,
            "acmeclient": acmeclient,
            "tailscale": tailscale,
            "kea_ha": kea_ha,
            "monit": monit,
            "system_firmware": system_firmware,
            "system_tuning": system_tuning,
            "system_users": system_users,
            "system_groups": system_groups,
        }

    def _get_existing_aliases(
        self, api_url: str, api_key: str, api_secret: str
    ) -> dict[str, AliasRow]:
        """Get existing aliases from OPNsense API.

        Args:
            api_url: OPNsense API base URL
            api_key: API key
            api_secret: API secret

        Returns:
            Dict of existing alias names
        """
        data = self.api_validator.fetch_json(
            url=f"{api_url}/api/{endpoints.ALIAS_SEARCH_GET.path()}",
            auth=(api_key, api_secret),
            verify_ssl=False,
            timeout=10,
            check_name="opnsense_get_aliases",
            error_message="Could not retrieve existing aliases (status {status})",
            error_level=ValidationLevel.WARNING,
        )
        if not data:
            return {}

        aliases: dict[str, AliasRow] = {}
        for row in data.get("rows", []):
            name = row.get("name")
            if name:
                aliases[name] = row
        return aliases

    def _normalize_interface_data(self, data: Any) -> list[dict[str, Any]]:
        """Normalize interface data to list format.

        The OPNsense API may return interface data in different formats:
        - As a dict keyed by interface name
        - As a list of interface dicts

        This method normalizes both formats to a consistent list format.

        Args:
            data: Raw interface data from API

        Returns:
            List of interface dicts
        """
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            return [
                {"name": name, **iface_data}
                for name, iface_data in data.items()
                if isinstance(iface_data, dict)
            ]
        return []

    def _extract_interface_name(self, iface_data: dict[str, Any]) -> str | None:
        """Extract interface name from various possible fields.

        Different interface types may store the name in different fields:
        - name: Standard field
        - device: Physical device name
        - if: Short form
        - interface: Full form

        Args:
            iface_data: Interface data dict

        Returns:
            Interface name if found, None otherwise
        """
        return (
            iface_data.get("name")
            or iface_data.get("device")
            or iface_data.get("if")
            or iface_data.get("interface")
        )

    def _interface_keys(self, iface_data: dict[str, Any]) -> list[str]:
        """Return every non-empty key an interface can be referenced by.

        OPNsense 26.1 export rows carry ``identifier`` (wan, lan, opt1) and ``device``
        (em1) but no ``name``; older shapes use ``name``, ``if`` or ``interface``.

        Args:
            iface_data: Interface data dict

        Returns:
            Unique non-empty keys, identifier first.
        """
        keys: list[str] = []
        for field in ("identifier", "name", "device", "if", "interface"):
            value = iface_data.get(field)
            if isinstance(value, str) and value and value not in keys:
                keys.append(value)
        return keys

    def _get_existing_interfaces(
        self, api_url: str, api_key: str, api_secret: str
    ) -> dict[str, InterfaceData]:
        """Get existing interfaces and VLANs from OPNsense API.

        Args:
            api_url: OPNsense API base URL
            api_key: API key
            api_secret: API secret

        Returns:
            Dict of existing interface names
        """
        data = cast(
            Any,
            self.api_validator.fetch_json(
                url=f"{api_url}/api/{endpoints.INTERFACES_EXPORT.path()}",
                auth=(api_key, api_secret),
                verify_ssl=False,
                timeout=10,
                check_name="opnsense_get_interfaces",
                error_message="Could not retrieve existing interfaces (status {status})",
                error_level=ValidationLevel.WARNING,
            ),
        )
        if not data:
            return {}

        # Normalize to list of interface dicts
        interface_list = self._normalize_interface_data(data)

        # Register each interface under every identifying key, so references by
        # identifier (wan), device (em1) or legacy name all resolve.
        existing: dict[str, InterfaceData] = {}
        for iface in interface_list:
            for name in self._interface_keys(iface):
                existing.setdefault(name, cast(InterfaceData, iface))
        return existing

    def _get_existing_gateways(self, api_url: str, api_key: str, api_secret: str) -> set[str]:
        """Get the set of live gateway names from OPNsense API.

        Returns the union of managed and dynamic gateways (e.g.,
        ``WAN_DHCP``, ``WAN_DHCP6``). Used by the static-route validator
        to accept references to live system gateways without first
        declaring them as managed.

        Args:
            api_url: OPNsense API base URL
            api_key: API key
            api_secret: API secret

        Returns:
            Set of gateway names; empty if the API call fails.
        """
        data = self.api_validator.fetch_json(
            url=f"{api_url}/api/{endpoints.GATEWAY.search.path()}",
            auth=(api_key, api_secret),
            verify_ssl=False,
            timeout=10,
            method="POST",
            check_name="opnsense_get_gateways",
            error_message="Could not retrieve existing gateways (status {status})",
            error_level=ValidationLevel.WARNING,
        )
        if not data:
            return set()
        names: set[str] = set()
        for row in data.get("rows", []):
            if not isinstance(row, dict):
                continue
            name = row.get("name")
            if isinstance(name, str) and name:
                names.add(name)
        return names

    def _get_existing_hasync_options(
        self, api_url: str, api_key: str, api_secret: str
    ) -> tuple[set[str], set[str]]:
        """Get the live pfsync interface and sync-item option keys (#1389).

        Used by the HA sync live validator, which checks ``pfsync_interface`` and
        ``sync_items`` against them.

        Args:
            api_url: OPNsense API base URL
            api_key: API key
            api_secret: API secret

        Returns:
            ``(interface keys, sync item keys)``; both empty if the API call fails.
        """
        data = self.api_validator.fetch_json(
            url=f"{api_url}/api/{endpoints.HASYNC_GET.path()}",
            auth=(api_key, api_secret),
            verify_ssl=False,
            timeout=10,
            method="GET",
            check_name="opnsense_get_hasync",
            error_message="Could not retrieve HA sync settings (status {status})",
            error_level=ValidationLevel.WARNING,
        )
        hasync = data.get("hasync") if isinstance(data, dict) else None
        if not isinstance(hasync, dict):
            return set(), set()
        return live_options(hasync, "pfsyncinterface"), live_options(hasync, "syncitems")

    def _get_existing_unbound_host_overrides(
        self, api_url: str, api_key: str, api_secret: str
    ) -> set[str]:
        """Get the set of live Unbound host-override names from OPNsense API.

        Returns a set with both ``hostname.domain`` and bare ``hostname``
        forms so the ``unbound_host_alias`` validator can accept either
        cross-reference shape (matches the resolver in
        ``components/unbound_host_alias.py``).

        Args:
            api_url: OPNsense API base URL
            api_key: API key
            api_secret: API secret

        Returns:
            Set of host-override names; empty if the API call fails.
        """
        data = self.api_validator.fetch_json(
            url=f"{api_url}/api/{endpoints.UNBOUND_HOST_OVERRIDE.search.path()}",
            auth=(api_key, api_secret),
            verify_ssl=False,
            timeout=10,
            method="POST",
            check_name="opnsense_get_unbound_host_overrides",
            error_message=("Could not retrieve existing Unbound host overrides (status {status})"),
            error_level=ValidationLevel.WARNING,
        )
        if not data:
            return set()
        names: set[str] = set()
        for row in data.get("rows", []):
            if not isinstance(row, dict):
                continue
            hostname = row.get("hostname")
            domain = row.get("domain")
            if isinstance(hostname, str) and hostname:
                names.add(hostname)
                if isinstance(domain, str) and domain:
                    names.add(f"{hostname}.{domain}")
        return names
