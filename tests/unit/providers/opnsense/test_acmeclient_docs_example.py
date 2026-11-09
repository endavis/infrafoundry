"""Regression test: the coverage doc's ACME-client YAML example is valid (#790)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.services import acmeclient as svc
from infrafoundry.providers.opnsense.services.acmeclient_settings import (
    AcmeClientSettingsService,
)
from infrafoundry.providers.opnsense.validators import AcmeClientValidator, build_xref_index
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

DOC = Path(__file__).resolve().parents[4] / "docs" / "development" / "opnsense-resource-coverage.md"


def _example() -> dict[str, object]:
    text = DOC.read_text(encoding="utf-8")
    section = text.split("## ACME client (#790)", 1)[1].split("\n## ", 1)[0]
    match = re.search(r"```yaml\n(.*?)```", section, re.DOTALL)
    assert match, "ACME client section has no YAML example"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict)
    return data


def _load(tmp_path: Path) -> list[ResourceConfig]:
    return PackageLoader(tmp_path)._parse_resources_from_data(_example(), "doc.yaml", "opnsense")


def test_docs_example_loads_all_five_types(tmp_path: Path) -> None:
    resources = _load(tmp_path)
    assert {r.type for r in resources} == {
        "acmeclient.settings",
        "acmeclient.accounts",
        "acmeclient.validations",
        "acmeclient.actions",
        "acmeclient.certs",
    }
    assert all(
        r.config.get("name") == r.name
        for r in resources
        if r.type.endswith("s") and r.type != "acmeclient.settings"
    )


def test_docs_example_builds_and_validates_without_errors(tmp_path: Path) -> None:
    resources = _load(tmp_path)
    (settings,) = [r for r in resources if r.type == "acmeclient.settings"]
    assert AcmeClientSettingsService.build_desired(
        AcmeClientSettingsService.__new__(AcmeClientSettingsService), settings
    )
    for spec in svc.SPECS.values():
        rows = [r for r in resources if r.type == spec.type_name]
        assert len(rows) == 1
        (config,) = svc.configs_from_resources(spec, rows)
        assert config.wire_name

    report = ValidationReport()
    AcmeClientValidator(report).validate(
        OPNsenseValidationContext(resources=resources, index=build_xref_index(resources))
    )
    assert [r.message for r in report.results if r.level == ValidationLevel.ERROR] == []
