"""Regression test: the coverage doc's Kea DHCPv4 HA YAML example is valid (#1392)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.services.kea_dhcp4_ha import (
    KeaHASettingsService,
    peer_configs_from_resources,
)
from infrafoundry.providers.opnsense.validators import KeaHAValidator
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

DOC = Path(__file__).resolve().parents[4] / "docs" / "development" / "opnsense-resource-coverage.md"


def _example() -> dict[str, object]:
    text = DOC.read_text(encoding="utf-8")
    section = text.split("## Kea DHCPv4 high availability (#1392)", 1)[1].split("\n## ", 1)[0]
    match = re.search(r"```yaml\n(.*?)```", section, re.DOTALL)
    assert match, "kea ha section has no YAML example"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict)
    return data


def test_docs_example_loads_builds_and_validates(tmp_path: Path) -> None:
    resources = PackageLoader(tmp_path)._parse_resources_from_data(
        _example(), "doc.yaml", "opnsense"
    )
    found = [r for r in resources if r.type.startswith("kea.dhcp4.ha")]
    assert {r.type for r in found} == {"kea.dhcp4.ha", "kea.dhcp4.ha_peers"}

    settings: list[ResourceConfig] = [r for r in found if r.type == "kea.dhcp4.ha"]
    service = KeaHASettingsService.__new__(KeaHASettingsService)
    assert service.build_desired(settings[0]) == {
        "enabled": "1",
        "this_server_name": "",
        "max_unacked_clients": "2",
    }
    peers = peer_configs_from_resources(found)
    assert [(p.name, p.role) for p in peers] == [("fw-a", "primary"), ("fw-b", "standby")]

    report = ValidationReport()
    KeaHAValidator(report).validate(OPNsenseValidationContext(resources=found))
    assert [r.message for r in report.results if r.level == ValidationLevel.ERROR] == []
