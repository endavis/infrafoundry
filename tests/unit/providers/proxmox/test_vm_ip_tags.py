"""Static IPv4 addresses render as VM tags and ``ip_tags`` is validated (#1699)."""

import re
from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.proxmox import ProxmoxProvider, _ipconfig_ipv4
from infrafoundry.providers.proxmox.validators.context import ProxmoxConfigContext
from infrafoundry.providers.proxmox.validators.vm_config_validator import VMConfigValidator


def _generate(tmp_path: Path, config: dict[str, Any]) -> dict[str, str]:
    """Run ``_generate_vms_terraform`` and return the rendered files by name."""
    provider = ProxmoxProvider(tmp_path / "config", tmp_path / "output")
    provider.set_environment("test")
    written: dict[str, str] = {}

    def capture(template: str, context: dict[str, Any], output_name: str) -> None:
        written[output_name] = provider.render_template(template, context)

    provider.render_and_write_terraform = capture  # type: ignore[method-assign, assignment]
    vm = ResourceConfig(
        name="vm1",
        type="vm",
        provider="proxmox",
        config={"name": "vm1", "vmid": 1, "target_node": "node1", **config},
    )
    provider._generate_vms_terraform([vm])
    return written


def _render(tmp_path: Path, **extra: Any) -> str:
    return _generate(tmp_path, extra)["vms.tf"]


def _tags_line(rendered: str) -> str | None:
    match = re.search(r"^\s*tags\s*=.*$", rendered, re.MULTILINE)
    return match.group(0).strip() if match else None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ip=192.0.2.10/24,gw=192.0.2.1", "192.0.2.10"),
        ("ip=192.0.2.10", "192.0.2.10"),
        ("gw=192.0.2.1,ip=198.51.100.7/24", "198.51.100.7"),
        ("ip=dhcp", None),
        ("ip=manual", None),
        ("", None),
        (None, None),
        (42, None),
        ("ip6=2001:db8::1/64", None),
        ("ip=300.0.2.1/24", None),
        ("ip=192.0.2.10/24,ip6=auto", "192.0.2.10"),
    ],
)
def test_ipconfig_ipv4(value: object, expected: str | None) -> None:
    assert _ipconfig_ipv4(value) == expected


def test_static_ip_renders_tag(tmp_path: Path) -> None:
    rendered = _render(tmp_path, ipconfig="ip=192.0.2.10/24,gw=192.0.2.1")

    assert _tags_line(rendered) == 'tags = ["192.0.2.10"]'


def test_user_tags_merged_and_sorted(tmp_path: Path) -> None:
    rendered = _render(tmp_path, ipconfig="ip=192.0.2.10/24", tags=["web", "app"])

    assert _tags_line(rendered) == 'tags = ["192.0.2.10", "app", "web"]'


def test_no_duplicate_tag(tmp_path: Path) -> None:
    rendered = _render(tmp_path, ipconfig="ip=192.0.2.10/24", tags=["192.0.2.10", "web"])

    assert _tags_line(rendered) == 'tags = ["192.0.2.10", "web"]'


def test_dhcp_keeps_original_order(tmp_path: Path) -> None:
    rendered = _render(tmp_path, ipconfig="ip=dhcp", tags=["web", "app"])

    assert _tags_line(rendered) == 'tags = ["web", "app"]'


def test_no_ipconfig_no_tags_line(tmp_path: Path) -> None:
    assert _tags_line(_render(tmp_path)) is None


def test_opt_out(tmp_path: Path) -> None:
    rendered = _render(tmp_path, ipconfig="ip=192.0.2.10/24", tags=["web", "app"], ip_tags=False)

    assert _tags_line(rendered) == 'tags = ["web", "app"]'


def test_opt_out_without_tags(tmp_path: Path) -> None:
    assert _tags_line(_render(tmp_path, ipconfig="ip=192.0.2.10/24", ip_tags=False)) is None


def test_deterministic(tmp_path: Path) -> None:
    kwargs: dict[str, Any] = {"ipconfig": "ip=192.0.2.10/24", "tags": ["b", "a"]}

    assert _render(tmp_path, **kwargs) == _render(tmp_path, **kwargs)


def test_input_not_mutated(tmp_path: Path) -> None:
    tags = ["web"]
    config = {"ipconfig": "ip=192.0.2.10/24", "tags": tags}

    _generate(tmp_path, config)

    assert config["tags"] == ["web"]
    assert tags == ["web"]


def test_ova_vm_unchanged(tmp_path: Path) -> None:
    files = _generate(
        tmp_path,
        {
            "ova_source": "https://example.com/a.ova",
            "ipconfig": "ip=192.0.2.10/24",
            "tags": ["web"],
        },
    )

    assert "vms.tf" not in files
    assert '"192.0.2.10"' not in files["ova_vms.tf"]


def _errors(**config: Any) -> list[str]:
    report = ValidationReport()
    vm = ResourceConfig(
        name="vm1",
        type="vm",
        provider="proxmox",
        config={"name": "vm1", "target_node": "pve01", **config},
    )
    VMConfigValidator(report).validate(ProxmoxConfigContext(vms=[vm]))
    return [r.message for r in report.results if not r.passed and r.level == ValidationLevel.ERROR]


@pytest.mark.parametrize("value", [True, False])
def test_bool_ip_tags_passes(value: bool) -> None:
    assert _errors(ip_tags=value) == []


@pytest.mark.parametrize("value", ["yes", 1, None, []])
def test_non_bool_ip_tags_is_error(value: Any) -> None:
    errors = _errors(ip_tags=value)

    assert len(errors) == 1
    assert "ip_tags" in errors[0]
