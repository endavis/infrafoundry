"""``agent_timeout`` renders as the bpg ``agent.timeout`` and is validated (#1623)."""

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.proxmox import ProxmoxProvider
from infrafoundry.providers.proxmox.validators.context import ProxmoxConfigContext
from infrafoundry.providers.proxmox.validators.vm_config_validator import VMConfigValidator


class _Res:
    """Minimal stand-in exposing ``name`` and ``config`` to the templates."""

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name = name
        self.config = config


def _render(tmp_path: Path, **extra: Any) -> str:
    provider = ProxmoxProvider(tmp_path / "config", tmp_path / "output")
    provider.set_environment("test")
    config = {"name": "vm1", "vmid": 1, "target_node": "node1", **extra}
    return provider.render_template("proxmox/vms.tf.j2", {"vms": [_Res("vm1", config)]})


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


def test_timeout_renders_inside_agent_block(tmp_path: Path) -> None:
    rendered = _render(tmp_path, agent=1, agent_timeout="2m")

    assert 'timeout = "2m"' in rendered
    agent_block = rendered.split("agent {", 1)[1].split("}", 1)[0]
    assert "enabled = true" in agent_block
    assert 'timeout = "2m"' in agent_block


def test_no_timeout_line_without_the_field(tmp_path: Path) -> None:
    rendered = _render(tmp_path, agent=1)

    assert "agent {" in rendered
    assert "timeout" not in rendered


@pytest.mark.parametrize("value", ["2m", "90s", "1h", "1m30s", "1h2m3s", "1.5m"])
def test_valid_durations_pass(value: str) -> None:
    assert _errors(agent=1, agent_timeout=value) == []


@pytest.mark.parametrize("value", ["2", "m", "2 m", "2d", "1m30", "abc", "", 120, None])
def test_malformed_durations_fail(value: Any) -> None:
    errors = _errors(agent=1, agent_timeout=value)

    assert len(errors) == 1
    assert "agent_timeout" in errors[0]


@pytest.mark.parametrize("agent", [{}, {"agent": 0}])
def test_timeout_without_agent_enabled_fails(agent: dict[str, Any]) -> None:
    errors = _errors(agent_timeout="2m", **agent)

    assert len(errors) == 1
    assert "requires the guest agent" in errors[0]


def test_agent_true_counts_as_enabled() -> None:
    assert _errors(agent=True, agent_timeout="2m") == []


def test_no_timeout_field_adds_no_check() -> None:
    assert _errors(agent=1) == []
