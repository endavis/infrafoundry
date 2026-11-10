"""Registry of every OPNsense API endpoint the provider calls (#1239).

Every wire path lives here and nowhere else; ``test_endpoint_literal_guard.py``
fails when a path literal appears elsewhere in the provider package. Keeping the
paths in one place lets three checks run over them:

- an offline conformance test asserts that each stock endpoint exists in every
  bundled ``opnsense-openapi`` spec of the supported series
  (:data:`SUPPORTED_SERIES`);
- ``infra plan`` rejects a resource type whose endpoints the box's version lacks
  (:func:`infrafoundry.providers.opnsense.endpoint_support.check_resource_types`);
- ``infra doctor`` reports the same through ``OPNsenseValidator``.

Extension exemption: ``interfaces/assign_settings/*`` is served by an in-tree
OPNsense plugin (see ``providers/opnsense/extensions``), not by stock OPNsense, so
it is absent from the specs. Those entries carry :attr:`EndpointKind.EXTENSION` and
are skipped by the checks; a test asserts they stay absent so the exemption is
dropped if upstream ever ships them.

Plugin exemption (#790): the ``acmeclient/*`` controllers belong to the contrib plugin
``os-acme-client``. The bundled specs cover core only, so those entries carry
:attr:`EndpointKind.PLUGIN` and are skipped by the checks; a test asserts they are
absent from the specs and that no endpoint that contacts a CA or a remote host
(register, sign, revoke, removekey, automation, import, signallcerts, toggle) is ever
registered.

Strict mode of ``opnsense-openapi`` (``validate_endpoints=True``) stays off. It
needs a known box version, but the wrapper builds the client with
``auto_detect_version=False``, and it cannot exempt the extension above.

This module imports only the standard library, so services and clients can import
it without creating import cycles. Templates are formatted with raw parameters;
callers keep ``quote(..., safe="")`` where they encoded the value before.
"""

from __future__ import annotations

import string
from dataclasses import dataclass, fields
from enum import StrEnum
from typing import Literal

Method = Literal["GET", "POST"]


class EndpointKind(StrEnum):
    """Whether an endpoint ships with stock OPNsense."""

    STOCK = "stock"
    EXTENSION = "extension"
    PLUGIN = "plugin"  # served by an installed contrib plugin, absent from the core specs


@dataclass(frozen=True)
class Endpoint:
    """One OPNsense API endpoint: an HTTP method and a path template.

    Attributes:
        method: HTTP method the provider sends.
        template: Path relative to ``/api/`` with ``{name}`` placeholders.
        kind: :attr:`EndpointKind.EXTENSION` for endpoints stock OPNsense lacks,
            :attr:`EndpointKind.PLUGIN` for those a contrib plugin serves.
    """

    method: Method
    template: str
    kind: EndpointKind = EndpointKind.STOCK

    @property
    def params(self) -> tuple[str, ...]:
        """Placeholder names in the template, in order."""
        return tuple(
            name for _, name, _, _ in string.Formatter().parse(self.template) if name is not None
        )

    def path(self, **params: str) -> str:
        """Format the template with raw (unencoded) parameters.

        Args:
            **params: One value per placeholder.

        Returns:
            The path relative to ``/api/``.

        Raises:
            KeyError: A placeholder has no value.
            ValueError: A value was given that the template does not use.
        """
        expected = set(self.params)
        missing = expected - params.keys()
        if missing:
            raise KeyError(f"{self.template}: missing parameters {sorted(missing)}")
        extra = params.keys() - expected
        if extra:
            raise ValueError(f"{self.template}: unexpected parameters {sorted(extra)}")
        return self.template.format(**params)

    def sample_path(self) -> str:
        """Path with every placeholder filled by its own name, for spec lookups."""
        return self.template.format(**{name: name for name in self.params})

    def __str__(self) -> str:
        return f"{self.method} {self.template}"


@dataclass(frozen=True)
class CrudEndpoints:
    """The endpoints of one MVC settings controller.

    Attributes:
        search: Row search.
        get: Single-row read, or ``None`` when the provider never calls it.
        add: Row create.
        update: Row update (takes ``{uuid}``).
        delete: Row delete (takes ``{uuid}``).
        reconfigure: Per-controller apply, or ``None`` when the service applies elsewhere.
    """

    search: Endpoint
    get: Endpoint | None
    add: Endpoint
    update: Endpoint
    delete: Endpoint
    reconfigure: Endpoint | None = None

    @property
    def read(self) -> Endpoint:
        """The single-row read endpoint.

        Raises:
            LookupError: The controller has none the provider calls.
        """
        if self.get is None:
            raise LookupError(f"{self.search.template}: controller has no get endpoint")
        return self.get

    @property
    def apply(self) -> Endpoint:
        """The per-controller reconfigure endpoint.

        Raises:
            LookupError: The controller has none (its service applies elsewhere).
        """
        if self.reconfigure is None:
            raise LookupError(f"{self.search.template}: controller has no reconfigure endpoint")
        return self.reconfigure

    def all(self) -> tuple[Endpoint, ...]:
        """Every defined endpoint of the controller."""
        return tuple(
            e
            for e in (self.search, self.get, self.add, self.update, self.delete, self.reconfigure)
            if e
        )


@dataclass(frozen=True)
class RuleEndpoints:
    """The endpoints of one firewall rule controller (filter, NAT variants)."""

    search: Endpoint
    add: Endpoint
    update: Endpoint
    delete: Endpoint
    apply: Endpoint

    def all(self) -> tuple[Endpoint, ...]:
        """Every endpoint of the controller."""
        return (self.search, self.add, self.update, self.delete, self.apply)


def _crud(
    base: str,
    *,
    search: str,
    get: str | None,
    add: str,
    update: str,
    delete: str,
    reconfigure: str | None = None,
    search_method: Method = "POST",
    kind: EndpointKind = EndpointKind.STOCK,
) -> CrudEndpoints:
    """Build a :class:`CrudEndpoints` from a controller base and action names."""
    return CrudEndpoints(
        search=Endpoint(search_method, f"{base}/{search}", kind),
        get=Endpoint("GET", f"{base}/{get}/{{uuid}}", kind) if get else None,
        add=Endpoint("POST", f"{base}/{add}", kind),
        update=Endpoint("POST", f"{base}/{update}/{{uuid}}", kind),
        delete=Endpoint("POST", f"{base}/{delete}/{{uuid}}", kind),
        reconfigure=Endpoint("POST", f"{base}/{reconfigure}", kind) if reconfigure else None,
    )


def _item_crud(base: str, *, reconfigure: bool = True, get: bool = True) -> CrudEndpoints:
    """CRUD with the ``*Item`` action names most controllers use."""
    return _crud(
        base,
        search="searchItem",
        get="getItem" if get else None,
        add="addItem",
        update="setItem",
        delete="delItem",
        reconfigure="reconfigure" if reconfigure else None,
    )


def _rules(base: str) -> RuleEndpoints:
    """Rule controller endpoints (``*Rule`` actions plus ``apply``)."""
    return RuleEndpoints(
        search=Endpoint("POST", f"{base}/searchRule"),
        add=Endpoint("POST", f"{base}/addRule"),
        update=Endpoint("POST", f"{base}/setRule/{{uuid}}"),
        delete=Endpoint("POST", f"{base}/delRule/{{uuid}}"),
        apply=Endpoint("POST", f"{base}/apply"),
    )


# --- firewall/alias, interfaces/vip_settings, interfaces/vlan_settings --------------
ALIAS = _item_crud("firewall/alias")
VIP = _item_crud("interfaces/vip_settings")
VLAN = _item_crud("interfaces/vlan_settings", get=False)

# --- routing ------------------------------------------------------------------------
GATEWAY = _crud(
    "routing/settings",
    search="searchGateway",
    get="getGateway",
    add="addGateway",
    update="setGateway",
    delete="delGateway",
    reconfigure="reconfigure",
)
STATIC_ROUTE = _crud(
    "routes/routes",
    search="searchroute",
    get="getroute",
    add="addroute",
    update="setroute",
    delete="delroute",
    reconfigure="reconfigure",
)

# --- unbound (all three controllers share one service reconfigure) ------------------
UNBOUND_FORWARD = _crud(
    "unbound/settings",
    search="searchForward",
    get="getForward",
    add="addForward",
    update="setForward",
    delete="delForward",
)
UNBOUND_HOST_ALIAS = _crud(
    "unbound/settings",
    search="searchHostAlias",
    get="getHostAlias",
    add="addHostAlias",
    update="setHostAlias",
    delete="delHostAlias",
)
UNBOUND_HOST_OVERRIDE = _crud(
    "unbound/settings",
    search="searchHostOverride",
    get="getHostOverride",
    add="addHostOverride",
    update="setHostOverride",
    delete="delHostOverride",
)
UNBOUND_RECONFIGURE = Endpoint("POST", "unbound/service/reconfigure")
# Singleton settings document (the ``advanced`` section holds private/insecure domains).
UNBOUND_SETTINGS_GET = Endpoint("GET", "unbound/settings/get")
UNBOUND_SETTINGS_SET = Endpoint("POST", "unbound/settings/set")

# --- radvd, cron ----------------------------------------------------------------------
RADVD = _crud(
    "radvd/settings",
    search="searchEntry",
    get="getEntry",
    add="addEntry",
    update="setEntry",
    delete="delEntry",
)
RADVD_RECONFIGURE = Endpoint("POST", "radvd/service/reconfigure")
RADVD_STATUS = Endpoint("GET", "radvd/service/status")
RADVD_SETTINGS_GET = Endpoint("GET", "radvd/settings/get")
CRON = _crud(
    "cron/settings",
    search="searchJobs",
    get="getJob",
    add="addJob",
    update="setJob",
    delete="delJob",
)
CRON_RECONFIGURE = Endpoint("POST", "cron/service/reconfigure")

# --- auth (system users and groups, #805) ---------------------------------------------
# No reconfigure: the 26.1 specs expose none for the auth controllers.
AUTH_USER = _crud(
    "auth/user",
    search="search",
    get=None,
    add="add",
    update="set",
    delete="del",
    search_method="GET",
)
AUTH_GROUP = _crud(
    "auth/group",
    search="search",
    get=None,
    add="add",
    update="set",
    delete="del",
    search_method="GET",
)

# --- trust (CAs and certificates, #807)---------------------------------------------
TRUST_CA = _crud(
    "trust/ca",
    search="search",
    get="get",
    add="add",
    update="set",
    delete="del",
)
TRUST_CERT = _crud(
    "trust/cert",
    search="search",
    get="get",
    add="add",
    update="set",
    delete="del",
)

# --- openvpn client instances (#808) ------------------------------------------------
OPENVPN_INSTANCE = _crud(
    "openvpn/instances",
    search="search",
    get="get",
    add="add",
    update="set",
    delete="del",
    search_method="GET",
)
OPENVPN_RECONFIGURE = Endpoint("POST", "openvpn/service/reconfigure")

# --- kea ----------------------------------------------------------------------------
KEA_CRUD: dict[tuple[str, str], CrudEndpoints] = {
    (api_version, noun): _crud(
        f"kea/{api_version}",
        search=f"search{noun}",
        get=f"get{noun}",
        add=f"add{noun}",
        update=f"set{noun}",
        delete=f"del{noun}",
        search_method="GET",
    )
    for api_version in ("dhcpv4", "dhcpv6")
    for noun in ("Subnet", "Reservation")
}
KEA_DHCPV4_GET = Endpoint("GET", "kea/dhcpv4/get")
KEA_DHCPV4_SET = Endpoint("POST", "kea/dhcpv4/set")
KEA_DHCPV6_GET = Endpoint("GET", "kea/dhcpv6/get")
KEA_DHCPV6_SET = Endpoint("POST", "kea/dhcpv6/set")
KEA_RECONFIGURE = Endpoint("POST", "kea/service/reconfigure")

# --- firewall rules, NAT, categories --------------------------------------------------
FILTER = _rules("firewall/filter")
FILTER_SAVEPOINT = Endpoint("POST", "firewall/filter/savepoint")
SOURCE_NAT = _rules("firewall/source_nat")
# #1333: the model document (outbound NAT mode) and its write.
SOURCE_NAT_GET = Endpoint("GET", "firewall/source_nat/get")
SOURCE_NAT_SET = Endpoint("POST", "firewall/source_nat/set")
ONE_TO_ONE = _rules("firewall/one_to_one")
# OPNsense routes DNatController as ``d_nat`` (not ``dnat``).
D_NAT = _rules("firewall/d_nat")
CATEGORY_SEARCH = Endpoint("POST", "firewall/category/searchItem")
CATEGORY_ADD = Endpoint("POST", "firewall/category/addItem")

# --- interfaces -----------------------------------------------------------------------
INTERFACES_INFO = Endpoint("GET", "interfaces/overview/interfacesInfo")
INTERFACES_EXPORT = Endpoint("GET", "interfaces/overview/export")
INTERFACES_SETTINGS_GET = Endpoint("GET", "interfaces/settings/get")
INTERFACES_SETTINGS_SET = Endpoint("POST", "interfaces/settings/set")
INTERFACES_SETTINGS_RECONFIGURE = Endpoint("POST", "interfaces/settings/reconfigure")

# --- syslog (#804) ---
SYSLOG_SETTINGS_GET = Endpoint("GET", "syslog/settings/get")
SYSLOG_SETTINGS_SET = Endpoint("POST", "syslog/settings/set")
SYSLOG_RECONFIGURE = Endpoint("POST", "syslog/service/reconfigure")
# In-tree plugin controller: not in stock specs (see the module docstring).
ASSIGN_SETTINGS = _crud(
    "interfaces/assign_settings",
    search="searchItem",
    get="getItem",
    add="addItem",
    update="setItem",
    delete="delItem",
    kind=EndpointKind.EXTENSION,
)

# --- hostdiscovery (#792) -------------------------------------------------------------
HOSTDISCOVERY_SETTINGS_GET = Endpoint("GET", "hostdiscovery/settings/get")
HOSTDISCOVERY_SETTINGS_SET = Endpoint("POST", "hostdiscovery/settings/set")
HOSTDISCOVERY_RECONFIGURE = Endpoint("POST", "hostdiscovery/service/reconfigure")

# --- acmeclient (#790, os-acme-client plugin) -------------------------------------------
# Never registered on purpose: register, sign, revoke, removekey, automation, import,
# signallcerts and toggle. They contact a CA or a remote host; issuance stays with the
# plugin's own cron job or the GUI.
ACMECLIENT_SETTINGS_GET = Endpoint("GET", "acmeclient/settings/get", EndpointKind.PLUGIN)
ACMECLIENT_SETTINGS_SET = Endpoint("POST", "acmeclient/settings/set", EndpointKind.PLUGIN)
ACMECLIENT_FETCH_CRON = Endpoint(
    "POST", "acmeclient/settings/fetchCronIntegration", EndpointKind.PLUGIN
)
ACMECLIENT_RECONFIGURE = Endpoint("POST", "acmeclient/service/reconfigure", EndpointKind.PLUGIN)


def _acme_crud(sub: str) -> CrudEndpoints:
    """CRUD for one ``acmeclient/<sub>`` list controller (update action is ``update``)."""
    return _crud(
        f"acmeclient/{sub}",
        search="search",
        get="get",
        add="add",
        update="update",
        delete="del",
        search_method="GET",
        kind=EndpointKind.PLUGIN,
    )


ACMECLIENT_ACCOUNT = _acme_crud("accounts")
ACMECLIENT_VALIDATION = _acme_crud("validations")
ACMECLIENT_CERTIFICATE = _acme_crud("certificates")
ACMECLIENT_ACTION = _acme_crud("actions")
# Item template: ``get`` without a UUID returns the empty model, i.e. every field name.
ACMECLIENT_ACCOUNT_TEMPLATE = Endpoint("GET", "acmeclient/accounts/get", EndpointKind.PLUGIN)
ACMECLIENT_VALIDATION_TEMPLATE = Endpoint("GET", "acmeclient/validations/get", EndpointKind.PLUGIN)
ACMECLIENT_CERTIFICATE_TEMPLATE = Endpoint(
    "GET", "acmeclient/certificates/get", EndpointKind.PLUGIN
)
ACMECLIENT_ACTION_TEMPLATE = Endpoint("GET", "acmeclient/actions/get", EndpointKind.PLUGIN)

# --- core -----------------------------------------------------------------------------
CORE_MENU_SEARCH = Endpoint("GET", "core/menu/search")
CORE_SYSTEM_STATUS = Endpoint("GET", "core/system/status")
FIRMWARE_INFO = Endpoint("GET", "core/firmware/info")
FIRMWARE_GET = Endpoint("GET", "core/firmware/get")
FIRMWARE_SET = Endpoint("POST", "core/firmware/set")
FIRMWARE_INSTALL = Endpoint("POST", "core/firmware/install/{name}")
FIRMWARE_UPGRADESTATUS = Endpoint("GET", "core/firmware/upgradestatus")
FIRMWARE_REMOVE = Endpoint("POST", "core/firmware/remove/{name}")
FIRMWARE_LOCK = Endpoint("POST", "core/firmware/lock/{name}")
TUNABLES_GET = Endpoint("GET", "core/tunables/get")
TUNABLES_ADD = Endpoint("POST", "core/tunables/addItem")
TUNABLES_SET = Endpoint("POST", "core/tunables/setItem/{uuid}")
TUNABLES_DEL = Endpoint("POST", "core/tunables/delItem/{uuid}")
TUNABLES_RECONFIGURE = Endpoint("POST", "core/tunables/reconfigure")

# --- retired by #1149, implementation removed in #1244: kept so the conformance test
# proves they are absent and the registry still names the retired types ------------
SYSTEM_GENERAL_GET = Endpoint("GET", "system/general/get")
SYSTEM_GENERAL_SET = Endpoint("POST", "system/general/set")
SYSTEM_SETTINGS_GET = Endpoint("GET", "system/settings/get")
SYSTEM_SETTINGS_SET = Endpoint("POST", "system/settings/set")
GDRIVEBACKUP_GET = Endpoint("GET", "gdrivebackup/settings/get")
GDRIVEBACKUP_SET = Endpoint("POST", "gdrivebackup/settings/set")

# --- infra doctor (validator.py) ------------------------------------------------------
# The validator lists aliases with GET; the apply path uses ``ALIAS.search`` (POST).
ALIAS_SEARCH_GET = Endpoint("GET", "firewall/alias/searchItem")

_KEA_V4 = (KEA_DHCPV4_GET, KEA_DHCPV4_SET, KEA_RECONFIGURE)
_KEA_V6 = (KEA_DHCPV6_GET, KEA_DHCPV6_SET, KEA_RECONFIGURE)

#: Endpoints each resource type's plan/apply path calls, keyed like
#: ``OPNsenseProvider.get_direct_api_resource_types()`` plus
#: ``OPNsenseProvider.UNSUPPORTED_RESOURCE_TYPES`` (the retired types, #1244).
#: Registered but uncalled methods (firmware remove/lock, tunables del, filter
#: savepoint) are not listed.
RESOURCE_TYPE_ENDPOINTS: dict[str, tuple[Endpoint, ...]] = {
    "system.hostname": (SYSTEM_GENERAL_GET, SYSTEM_GENERAL_SET),
    "system.dns": (SYSTEM_GENERAL_GET, SYSTEM_GENERAL_SET),
    "system.ssh": (SYSTEM_SETTINGS_GET, SYSTEM_SETTINGS_SET),
    "system.webgui": (SYSTEM_SETTINGS_GET, SYSTEM_SETTINGS_SET),
    "system.firmware": (
        FIRMWARE_INFO,
        FIRMWARE_GET,
        FIRMWARE_SET,
        FIRMWARE_INSTALL,
        FIRMWARE_UPGRADESTATUS,
    ),
    "system.remotebackup": (GDRIVEBACKUP_GET, GDRIVEBACKUP_SET),
    "system.tuning": (TUNABLES_GET, TUNABLES_ADD, TUNABLES_SET, TUNABLES_RECONFIGURE),
    "interfaces.settings": (
        INTERFACES_SETTINGS_GET,
        INTERFACES_SETTINGS_SET,
        INTERFACES_SETTINGS_RECONFIGURE,
    ),
    # #804
    "syslog.settings": (SYSLOG_SETTINGS_GET, SYSLOG_SETTINGS_SET, SYSLOG_RECONFIGURE),
    "interfaces.vlans": VLAN.all(),
    "interfaces.assignments": (*ASSIGN_SETTINGS.all(), INTERFACES_INFO),
    "interfaces.virtual_ips": VIP.all(),
    "firewall.aliases": ALIAS.all(),
    # #1333
    "firewall.source_nat": (SOURCE_NAT_GET, SOURCE_NAT_SET, SOURCE_NAT.apply),
    "firewall.nat": (
        *SOURCE_NAT.all(),
        SOURCE_NAT_GET,
        *ONE_TO_ONE.all(),
        *D_NAT.all(),
        CATEGORY_SEARCH,
        CATEGORY_ADD,
    ),
    "firewall.rules": (*FILTER.all(), CATEGORY_SEARCH, CATEGORY_ADD),
    "routing.gateways": GATEWAY.all(),
    "routing.static": STATIC_ROUTE.all(),
    "unbound.host_overrides": (*UNBOUND_HOST_OVERRIDE.all(), UNBOUND_RECONFIGURE),
    "unbound.host_aliases": (
        *UNBOUND_HOST_ALIAS.all(),
        UNBOUND_HOST_OVERRIDE.search,
        UNBOUND_RECONFIGURE,
    ),
    "unbound.forwards": (*UNBOUND_FORWARD.all(), UNBOUND_RECONFIGURE),
    "unbound.advanced": (UNBOUND_SETTINGS_GET, UNBOUND_SETTINGS_SET, UNBOUND_RECONFIGURE),
    "unbound.settings": (UNBOUND_SETTINGS_GET, UNBOUND_SETTINGS_SET, UNBOUND_RECONFIGURE),
    "kea.dhcp4.subnets": (*KEA_CRUD[("dhcpv4", "Subnet")].all(), *_KEA_V4),
    "kea.dhcp4.reservations": (
        *KEA_CRUD[("dhcpv4", "Reservation")].all(),
        KEA_CRUD[("dhcpv4", "Subnet")].search,
        *_KEA_V4,
    ),
    "kea.dhcp6.subnets": (*KEA_CRUD[("dhcpv6", "Subnet")].all(), *_KEA_V6),
    "kea.dhcp6.reservations": (
        *KEA_CRUD[("dhcpv6", "Reservation")].all(),
        KEA_CRUD[("dhcpv6", "Subnet")].search,
        *_KEA_V6,
    ),
    "radvd": (*RADVD.all(), RADVD_RECONFIGURE),
    "cron.jobs": (*CRON.all(), CRON_RECONFIGURE),
    "system.users": AUTH_USER.all(),
    "system.groups": (*AUTH_GROUP.all(), AUTH_USER.search),
    "trust.cas": TRUST_CA.all(),
    "trust.certs": (*TRUST_CERT.all(), TRUST_CA.search),
    "openvpn.instances": (
        *OPENVPN_INSTANCE.all(),
        OPENVPN_RECONFIGURE,
        TRUST_CA.search,
        TRUST_CERT.search,
    ),
    "hostdiscovery": (
        HOSTDISCOVERY_SETTINGS_GET,
        HOSTDISCOVERY_SETTINGS_SET,
        HOSTDISCOVERY_RECONFIGURE,
    ),
    # #790 (os-acme-client). The templates are the item ``get`` without a UUID.
    "acmeclient.settings": (
        ACMECLIENT_SETTINGS_GET,
        ACMECLIENT_SETTINGS_SET,
        ACMECLIENT_FETCH_CRON,
        ACMECLIENT_RECONFIGURE,
    ),
    "acmeclient.accounts": (
        *ACMECLIENT_ACCOUNT.all(),
        ACMECLIENT_ACCOUNT_TEMPLATE,
        ACMECLIENT_RECONFIGURE,
    ),
    "acmeclient.validations": (
        *ACMECLIENT_VALIDATION.all(),
        ACMECLIENT_VALIDATION_TEMPLATE,
        ACMECLIENT_RECONFIGURE,
    ),
    "acmeclient.actions": (
        *ACMECLIENT_ACTION.all(),
        ACMECLIENT_ACTION_TEMPLATE,
        ACMECLIENT_RECONFIGURE,
    ),
    "acmeclient.certs": (
        *ACMECLIENT_CERTIFICATE.all(),
        ACMECLIENT_CERTIFICATE_TEMPLATE,
        ACMECLIENT_ACCOUNT.search,
        ACMECLIENT_ACCOUNT.read,
        ACMECLIENT_VALIDATION.search,
        ACMECLIENT_VALIDATION.read,
        ACMECLIENT_ACTION.search,
        ACMECLIENT_ACTION.read,
        ACMECLIENT_RECONFIGURE,
    ),
}

#: Endpoints used outside a single resource type (ISC to Kea migration).
SHARED_ENDPOINTS: tuple[Endpoint, ...] = (CORE_MENU_SEARCH,)

#: Endpoints ``OPNsenseValidator`` calls during ``infra doctor``.
DOCTOR_ENDPOINTS: tuple[Endpoint, ...] = (
    CORE_SYSTEM_STATUS,
    ALIAS_SEARCH_GET,
    INTERFACES_EXPORT,
    GATEWAY.search,
    UNBOUND_HOST_OVERRIDE.search,
)

#: Release series (``major.minor``) whose bundled specs the conformance test enforces.
SUPPORTED_SERIES: tuple[str, ...] = ("26.1",)


def registered_endpoints() -> tuple[Endpoint, ...]:
    """Every :class:`Endpoint` reachable from this module's constants, deduplicated."""
    found: dict[Endpoint, None] = {}

    def visit(value: object) -> None:
        if isinstance(value, Endpoint):
            found[value] = None
        elif isinstance(value, CrudEndpoints | RuleEndpoints):
            for f in fields(value):
                visit(getattr(value, f.name))
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, tuple):
            for item in value:
                visit(item)

    for name, value in globals().items():
        if (name.isupper() and not name.startswith("_")) or name in ("_KEA_V4", "_KEA_V6"):
            visit(value)
    return tuple(found)
