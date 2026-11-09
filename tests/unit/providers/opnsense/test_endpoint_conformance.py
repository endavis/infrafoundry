"""Check the endpoint registry against the specs bundled with opnsense-openapi (#1239).

Runs offline: ``opnsense-openapi`` ships the OPNsense OpenAPI specs, so no box is
contacted.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

import pytest
from opnsense_openapi import endpoint_exists, list_available_specs, newest_spec_version

from infrafoundry.providers.opnsense import OPNsenseProvider, endpoints
from infrafoundry.providers.opnsense.endpoints import Endpoint, EndpointKind


def _series(version: str) -> str:
    return ".".join(version.split(".")[:2])


def _supported_specs() -> list[str]:
    return [v for v in list_available_specs() if _series(v) in endpoints.SUPPORTED_SERIES]


def _provider(tmp_path: Path) -> OPNsenseProvider:
    return OPNsenseProvider(config_dir=tmp_path, output_dir=tmp_path)


def _stock(items: list[Endpoint] | tuple[Endpoint, ...]) -> list[Endpoint]:
    return [e for e in items if e.kind is EndpointKind.STOCK]


def _supported_endpoints(provider: OPNsenseProvider) -> list[Endpoint]:
    found: dict[Endpoint, None] = {}
    for resource_type in provider.get_resource_types():
        for e in endpoints.RESOURCE_TYPE_ENDPOINTS[resource_type]:
            found[e] = None
    for e in (*endpoints.SHARED_ENDPOINTS, *endpoints.DOCTOR_ENDPOINTS):
        found[e] = None
    return _stock(tuple(found))


def _unsupported_only_endpoints(provider: OPNsenseProvider) -> list[Endpoint]:
    supported = set(_supported_endpoints(provider))
    found: dict[Endpoint, None] = {}
    for resource_type in provider.UNSUPPORTED_RESOURCE_TYPES:
        for e in endpoints.RESOURCE_TYPE_ENDPOINTS[resource_type]:
            if e not in supported:
                found[e] = None
    return list(found)


def test_supported_series_have_bundled_specs() -> None:
    assert _supported_specs()


@pytest.mark.parametrize("version", _supported_specs())
def test_supported_endpoints_exist_in_every_supported_spec(version: str, tmp_path: Path) -> None:
    missing = [
        f"{e} in {version}"
        for e in _supported_endpoints(_provider(tmp_path))
        if not endpoint_exists(e.sample_path(), e.method, version=version)
    ]
    assert not missing, "endpoints absent from the spec:\n" + "\n".join(missing)


@pytest.mark.parametrize("version", _supported_specs())
def test_every_registered_stock_endpoint_is_accounted_for(version: str, tmp_path: Path) -> None:
    """Stock endpoints either exist or belong only to a type rejected as unsupported."""
    retired = set(_unsupported_only_endpoints(_provider(tmp_path)))
    missing = [
        f"{e} in {version}"
        for e in _stock(endpoints.registered_endpoints())
        if e not in retired and not endpoint_exists(e.sample_path(), e.method, version=version)
    ]
    assert not missing, "\n".join(missing)


@pytest.mark.parametrize("version", _supported_specs())
def test_extension_endpoints_are_absent(version: str) -> None:
    present = [
        f"{e} in {version}"
        for e in endpoints.registered_endpoints()
        if e.kind is EndpointKind.EXTENSION
        and endpoint_exists(e.sample_path(), e.method, version=version)
    ]
    assert not present, "upstream now ships these; drop the EXTENSION exemption:\n" + "\n".join(
        present
    )


@pytest.mark.parametrize("version", _supported_specs())
def test_retired_endpoints_are_absent(version: str, tmp_path: Path) -> None:
    """The check would have caught #1149: the unsupported types' endpoints are not served."""
    present = [
        f"{e} in {version}"
        for e in _unsupported_only_endpoints(_provider(tmp_path))
        if endpoint_exists(e.sample_path(), e.method, version=version)
    ]
    assert not present, "\n".join(present)


def test_newer_series_gaps_are_reported_not_failed() -> None:
    newer = sorted(
        {_series(v) for v in list_available_specs()} - set(endpoints.SUPPORTED_SERIES),
        key=lambda s: tuple(int(p) for p in s.split(".")),
    )
    newest_supported = max(endpoints.SUPPORTED_SERIES, key=lambda s: tuple(map(int, s.split("."))))
    for series in newer:
        if tuple(map(int, series.split("."))) <= tuple(map(int, newest_supported.split("."))):
            continue
        version = newest_spec_version(series)
        for e in _stock(endpoints.registered_endpoints()):
            if re.match(r"^(system/(general|settings)|gdrivebackup)/", e.template):
                continue
            if not endpoint_exists(e.sample_path(), e.method, version=version):
                warnings.warn(f"{e} is absent from OPNsense {version}", stacklevel=1)


@pytest.mark.parametrize("version", _supported_specs())
def test_plugin_endpoints_are_absent_from_the_core_specs(version: str) -> None:
    """The PLUGIN exemption stands: the specs cover core only (#790)."""
    plugin = [e for e in endpoints.registered_endpoints() if e.kind is EndpointKind.PLUGIN]
    assert plugin
    present = [
        f"{e} in {version}"
        for e in plugin
        if endpoint_exists(e.sample_path(), e.method, version=version)
    ]
    assert not present, "upstream now ships these; drop the PLUGIN exemption:\n" + "\n".join(
        present
    )
