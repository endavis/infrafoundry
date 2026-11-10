"""Regression test: the coverage doc's Tailscale YAML example is valid (#787)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.services.tailscale_auth import TailscaleAuthService
from infrafoundry.providers.opnsense.services.tailscale_settings import TailscaleSettingsService
from infrafoundry.providers.opnsense.services.tailscale_subnets import (
    subnet_configs_from_resources,
)
from infrafoundry.providers.opnsense.validators import TailscaleValidator
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

DOC = Path(__file__).resolve().parents[4] / "docs" / "development" / "opnsense-resource-coverage.md"


def _example() -> dict[str, object]:
    text = DOC.read_text(encoding="utf-8")
    section = text.split("## Tailscale (#787)", 1)[1].split("\n## ", 1)[0]
    match = re.search(r"```yaml\n(.*?)```", section, re.DOTALL)
    assert match, "tailscale section has no YAML example"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict)
    return data


def test_docs_example_loads_builds_and_validates(tmp_path: Path) -> None:
    resources = PackageLoader(tmp_path)._parse_resources_from_data(
        _example(), "doc.yaml", "opnsense"
    )
    found = [r for r in resources if r.type.startswith("tailscale.")]
    assert {r.type for r in found} == {"tailscale.settings", "tailscale.auth", "tailscale.subnets"}

    by_type: dict[str, list[ResourceConfig]] = {}
    for r in found:
        by_type.setdefault(r.type, []).append(r)
    assert len(by_type["tailscale.subnets"]) == 2
    assert len(subnet_configs_from_resources(found)) == 2
    service = TailscaleSettingsService
    assert service.build_desired(service.__new__(service), by_type["tailscale.settings"][0])
    auth = TailscaleAuthService.__new__(TailscaleAuthService)
    assert auth.build_desired(by_type["tailscale.auth"][0])

    report = ValidationReport()
    TailscaleValidator(report).validate(OPNsenseValidationContext(resources=found))
    assert [r.message for r in report.results if r.level == ValidationLevel.ERROR] == []
