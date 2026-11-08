"""Structure tests for the OPNsense endpoint registry (#1239)."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrafoundry.providers.opnsense import OPNsenseProvider, endpoints
from infrafoundry.providers.opnsense.endpoints import Endpoint, EndpointKind


def test_methods_are_get_or_post() -> None:
    assert {e.method for e in endpoints.registered_endpoints()} <= {"GET", "POST"}


def test_templates_are_relative_with_a_controller_and_action() -> None:
    for e in endpoints.registered_endpoints():
        assert not e.template.startswith(("/", "api/")), e
        assert len(e.template.split("/")) >= 3, e


def test_no_duplicate_method_template_pairs() -> None:
    pairs = [(e.method, e.template) for e in endpoints.registered_endpoints()]
    assert len(pairs) == len(set(pairs))


def test_path_fills_params() -> None:
    assert Endpoint("POST", "a/b/set/{uuid}").path(uuid="x y") == "a/b/set/x y"


def test_path_rejects_missing_and_extra_params() -> None:
    ep = Endpoint("POST", "a/b/set/{uuid}")
    with pytest.raises(KeyError):
        ep.path()
    with pytest.raises(ValueError, match="unexpected"):
        ep.path(uuid="x", other="y")
    with pytest.raises(ValueError, match="unexpected"):
        Endpoint("GET", "a/b/get").path(uuid="x")


def test_sample_path_has_no_placeholders() -> None:
    assert all("{" not in e.sample_path() for e in endpoints.registered_endpoints())


def test_resource_types_match_the_provider(tmp_path: Path) -> None:
    provider = OPNsenseProvider(config_dir=tmp_path, output_dir=tmp_path)
    direct = set(provider.get_direct_api_resource_types())
    unsupported = set(provider.get_unsupported_resource_types())
    assert set(endpoints.RESOURCE_TYPE_ENDPOINTS) == direct | unsupported
    assert not direct & unsupported


def test_extension_entries_are_exactly_assign_settings() -> None:
    extension = {
        e.template for e in endpoints.registered_endpoints() if e.kind is EndpointKind.EXTENSION
    }
    assert extension
    assert all(t.startswith("interfaces/assign_settings/") for t in extension)
    stock = [e for e in endpoints.registered_endpoints() if e.kind is EndpointKind.STOCK]
    assert not any(e.template.startswith("interfaces/assign_settings/") for e in stock)


def test_uncalled_endpoints_do_not_gate_types() -> None:
    types = endpoints.RESOURCE_TYPE_ENDPOINTS
    assert endpoints.FILTER_SAVEPOINT not in types["firewall.rules"]
    assert endpoints.FIRMWARE_REMOVE not in types["system.firmware"]
    assert endpoints.FIRMWARE_LOCK not in types["system.firmware"]
    assert endpoints.TUNABLES_DEL not in types["system.tuning"]


def test_registered_endpoints_include_uncalled_ones() -> None:
    registered = endpoints.registered_endpoints()
    assert endpoints.FILTER_SAVEPOINT in registered
    assert endpoints.FIRMWARE_REMOVE in registered
    assert endpoints.KEA_CRUD[("dhcpv6", "Reservation")].search in registered


def test_unbound_advanced_registers_the_settings_endpoints() -> None:
    registered = endpoints.RESOURCE_TYPE_ENDPOINTS["unbound.advanced"]
    assert endpoints.UNBOUND_SETTINGS_GET in registered
    assert endpoints.UNBOUND_SETTINGS_SET in registered
    assert endpoints.UNBOUND_RECONFIGURE in registered


def test_interfaces_settings_registers_the_settings_endpoints() -> None:
    registered = endpoints.RESOURCE_TYPE_ENDPOINTS["interfaces.settings"]
    assert endpoints.INTERFACES_SETTINGS_GET in registered
    assert endpoints.INTERFACES_SETTINGS_SET in registered
    assert endpoints.INTERFACES_SETTINGS_RECONFIGURE in registered


def test_trust_types_register_their_endpoints() -> None:
    cas = endpoints.RESOURCE_TYPE_ENDPOINTS["trust.cas"]
    certs = endpoints.RESOURCE_TYPE_ENDPOINTS["trust.certs"]
    assert {e.template for e in cas} == {
        "trust/ca/search",
        "trust/ca/get/{uuid}",
        "trust/ca/add",
        "trust/ca/set/{uuid}",
        "trust/ca/del/{uuid}",
    }
    assert endpoints.TRUST_CA.search in certs
    assert {e.template for e in certs if e.template.startswith("trust/cert/")} == {
        "trust/cert/search",
        "trust/cert/get/{uuid}",
        "trust/cert/add",
        "trust/cert/set/{uuid}",
        "trust/cert/del/{uuid}",
    }


def test_openvpn_instances_register_their_endpoints() -> None:
    registered = endpoints.RESOURCE_TYPE_ENDPOINTS["openvpn.instances"]
    assert {e.template for e in registered} == {
        "openvpn/instances/search",
        "openvpn/instances/get/{uuid}",
        "openvpn/instances/add",
        "openvpn/instances/set/{uuid}",
        "openvpn/instances/del/{uuid}",
        "openvpn/service/reconfigure",
        "trust/ca/search",
    }
    assert endpoints.OPENVPN_INSTANCE.search.method == "GET"


def test_syslog_settings_registers_the_settings_endpoints() -> None:
    registered = endpoints.RESOURCE_TYPE_ENDPOINTS["syslog.settings"]
    assert endpoints.SYSLOG_SETTINGS_GET in registered
    assert endpoints.SYSLOG_SETTINGS_SET in registered
    assert endpoints.SYSLOG_RECONFIGURE in registered
