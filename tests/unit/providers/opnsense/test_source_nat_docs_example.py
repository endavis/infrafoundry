"""Regression test: the coverage doc's outbound NAT mode YAML example is valid (#1333)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.services.source_nat import SourceNatService
from infrafoundry.providers.opnsense.validators import SourceNatValidator
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

DOC = Path(__file__).resolve().parents[4] / "docs" / "development" / "opnsense-resource-coverage.md"


def _example() -> dict[str, object]:
    text = DOC.read_text(encoding="utf-8")
    section = text.split("## Outbound NAT mode (#1333)", 1)[1].split("\n## ", 1)[0]
    match = re.search(r"```yaml\n(.*?)```", section, re.DOTALL)
    assert match, "outbound NAT mode section has no YAML example"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict)
    return data


def test_docs_example_loads_builds_and_validates(tmp_path: Path) -> None:
    resources = PackageLoader(tmp_path)._parse_resources_from_data(
        _example(), "doc.yaml", "opnsense"
    )
    found = [r for r in resources if r.type == "firewall.source_nat"]
    assert len(found) == 1
    resource = found[0]

    desired = SourceNatService.build_desired(SourceNatService.__new__(SourceNatService), resource)
    assert desired == {"snat_mode": "hybrid"}

    report = ValidationReport()
    SourceNatValidator(report).validate(OPNsenseValidationContext(resources=[resource]))
    assert [r.message for r in report.results if r.level == ValidationLevel.ERROR] == []
