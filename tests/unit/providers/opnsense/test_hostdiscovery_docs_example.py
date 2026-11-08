"""Regression test: the coverage doc's host-discovery YAML example is valid (#792)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.services.hostdiscovery import HostDiscoveryService
from infrafoundry.providers.opnsense.validators import HostDiscoveryValidator
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

DOC = Path(__file__).resolve().parents[4] / "docs" / "development" / "opnsense-resource-coverage.md"


def _example() -> dict[str, object]:
    text = DOC.read_text(encoding="utf-8")
    section = text.split("## Host discovery (#792)", 1)[1].split("\n## ", 1)[0]
    match = re.search(r"```yaml\n(.*?)```", section, re.DOTALL)
    assert match, "host-discovery section has no YAML example"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict)
    return data


def test_docs_example_loads_builds_and_validates(tmp_path: Path) -> None:
    resources = PackageLoader(tmp_path)._parse_resources_from_data(
        _example(), "doc.yaml", "opnsense"
    )
    found = [r for r in resources if r.type == "hostdiscovery"]
    assert len(found) == 1
    resource = found[0]

    desired = HostDiscoveryService.build_desired(
        HostDiscoveryService.__new__(HostDiscoveryService), resource
    )
    assert desired["enabled"] == "1"

    report = ValidationReport()
    HostDiscoveryValidator(report).validate(
        OPNsenseValidationContext(resources=[resource], interface_assignment_names={"lan"})
    )
    assert [r.message for r in report.results if r.level == ValidationLevel.ERROR] == []
