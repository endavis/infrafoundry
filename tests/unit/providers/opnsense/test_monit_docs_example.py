"""Regression test: the coverage doc's monit YAML example is valid (#791)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.services import monit as svc
from infrafoundry.providers.opnsense.services.monit_settings import MonitSettingsService
from infrafoundry.providers.opnsense.validators import MonitValidator, build_xref_index
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

DOC = Path(__file__).resolve().parents[4] / "docs" / "development" / "opnsense-resource-coverage.md"


def _example() -> dict[str, object]:
    text = DOC.read_text(encoding="utf-8")
    section = text.split("## Monit (#791)", 1)[1].split("\n## ", 1)[0]
    match = re.search(r"```yaml\n(.*?)```", section, re.DOTALL)
    assert match, "monit section has no YAML example"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict)
    return data


def test_docs_example_loads_builds_and_validates(tmp_path: Path) -> None:
    resources = PackageLoader(tmp_path)._parse_resources_from_data(
        _example(), "doc.yaml", "opnsense"
    )
    found = [r for r in resources if r.type.startswith("monit.")]
    by_type: dict[str, list[ResourceConfig]] = {}
    for r in found:
        by_type.setdefault(r.type, []).append(r)
    assert set(by_type) == {"monit.settings", "monit.alerts", "monit.tests", "monit.services"}
    assert [len(by_type[t]) for t in ("monit.alerts", "monit.tests", "monit.services")] == [1, 3, 3]

    settings = MonitSettingsService.__new__(MonitSettingsService)
    assert settings.build_desired(by_type["monit.settings"][0])
    for spec in svc.SPECS.values():
        configs = svc.configs_from_resources(spec, by_type[spec.type_name])
        assert len(configs) == len(by_type[spec.type_name])
    identities = {
        c.wire_name for c in svc.configs_from_resources(svc.SERVICES, by_type["monit.services"])
    }
    assert identities == {"$HOST", "RootFs", "nightly_check"}

    report = ValidationReport()
    MonitValidator(report).validate(
        OPNsenseValidationContext(resources=found, index=build_xref_index(found))
    )
    assert [r.message for r in report.results if r.level == ValidationLevel.ERROR] == []
    assert [r.message for r in report.results if not r.passed] == []
