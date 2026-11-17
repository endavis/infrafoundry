"""Regression test: the coverage doc's HA sync YAML example is valid (#1389)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.services.hasync_settings import HasyncSettingsService
from infrafoundry.providers.opnsense.validators import HasyncValidator
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

DOC = Path(__file__).resolve().parents[4] / "docs" / "development" / "opnsense-resource-coverage.md"


def _example() -> dict[str, object]:
    text = DOC.read_text(encoding="utf-8")
    section = text.split("## HA sync settings (#1389)", 1)[1].split("\n## ", 1)[0]
    match = re.search(r"```yaml\n(.*?)```", section, re.DOTALL)
    assert match, "hasync section has no YAML example"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict)
    return data


def test_docs_example_loads_builds_and_validates(tmp_path: Path) -> None:
    resources = PackageLoader(tmp_path)._parse_resources_from_data(
        _example(), "doc.yaml", "opnsense"
    )
    found = [r for r in resources if r.type == "hasync.settings"]
    assert len(found) == 1

    service = HasyncSettingsService.__new__(HasyncSettingsService)
    desired = service.build_desired(found[0])
    assert desired["pfsync_version"] == "1400"
    assert desired["sync_items"] == "aliases,rules,virtualip"
    assert desired["disable_preempt"] == "0"

    report = ValidationReport()
    HasyncValidator(report).validate(OPNsenseValidationContext(resources=found))
    assert [r.message for r in report.results if r.level == ValidationLevel.ERROR] == []
    assert [r.message for r in report.results if r.level == ValidationLevel.WARNING] == []
