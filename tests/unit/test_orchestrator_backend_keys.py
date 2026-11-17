"""The orchestrator tells each provider which providers share the state (#1464)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.config.backend_config import BackendConfig
from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.provider import ResourceConfig


def _backend(pin: str | None = None) -> BackendConfig:
    return BackendConfig(
        type="s3",  # type: ignore[arg-type]
        s3={"bucket": "example-tfstate", "key": "dev/terraform.tfstate", "region": "r"},  # type: ignore[arg-type]
        bare_key_provider=pin,
    )


def _orchestrator(tmp_path: Path, provider_ids: list[str], backend: BackendConfig | None) -> Any:
    config_manager = Mock(spec=ConfigManager)
    config_manager.base_dir = tmp_path
    config_manager.get_all_resources_all_providers.return_value = [
        ResourceConfig(name=f"r-{i}", type="t", provider=pid, config={})
        for i, pid in enumerate(provider_ids)
    ]
    config_manager.get_package_events.return_value = {}
    config_manager.load_environment.return_value = EnvironmentConfig(name="dev", backend=backend)
    orchestrator = Orchestrator(config_manager=config_manager, output_dir=tmp_path / "out")
    orchestrator.providers = {pid: Mock(renders_terraform_backend=True) for pid in provider_ids}
    return orchestrator


def test_peers_are_set_and_warning_emitted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    warnings_file = tmp_path / "warnings.jsonl"
    monkeypatch.setenv("INFRAFOUNDRY_WARNINGS_FILE", str(warnings_file))
    orchestrator = _orchestrator(tmp_path, ["opnsense", "opnsense@fw-b"], _backend())
    orchestrator.console = Mock()
    orchestrator._load_resources("dev")
    for provider in orchestrator.providers.values():
        assert provider.backend_peer_ids == {"opnsense", "opnsense@fw-b"}
    text = warnings_file.read_text()
    assert "opnsense@fw-b" in text
    assert "dev/opnsense@fw-b/terraform.tfstate" in text
    assert "terraform init -migrate-state" in text
    orchestrator.console.print.assert_called()


def test_no_warning_for_single_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    warnings_file = tmp_path / "warnings.jsonl"
    monkeypatch.setenv("INFRAFOUNDRY_WARNINGS_FILE", str(warnings_file))
    orchestrator = _orchestrator(tmp_path, ["opnsense"], _backend())
    orchestrator._load_resources("dev")
    assert not warnings_file.exists()


def test_no_warning_for_the_pinned_provider_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    warnings_file = tmp_path / "warnings.jsonl"
    monkeypatch.setenv("INFRAFOUNDRY_WARNINGS_FILE", str(warnings_file))
    orchestrator = _orchestrator(tmp_path, ["opnsense", "opnsense@fw-b"], _backend("opnsense"))
    orchestrator._load_resources("dev")
    assert len(warnings_file.read_text().splitlines()) == 1


def test_invalid_pin_fails_loading(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path, ["opnsense"], _backend("missing"))
    with pytest.raises(InvalidConfigurationError):
        orchestrator._load_resources("dev")


def test_no_backend_sets_peers_without_warning(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path, ["opnsense", "opnsense@fw-b"], None)
    orchestrator._load_resources("dev")
    assert orchestrator.providers["opnsense"].backend_peer_ids == {"opnsense", "opnsense@fw-b"}


def test_two_opnsense_instances_render_different_keys(tmp_path: Path) -> None:
    import yaml

    from infrafoundry.providers.opnsense import OPNsenseProvider

    cfg = tmp_path / "cfg"
    (cfg / "dev").mkdir(parents=True)
    (cfg / "dev" / "settings.yaml").write_text(
        yaml.dump(
            {
                "name": "dev",
                "backend": {
                    "type": "s3",
                    "s3": {
                        "bucket": "example-tfstate",
                        "key": "dev/terraform.tfstate",
                        "region": "us-east-1",
                    },
                },
            }
        )
    )
    keys = []
    for firewall in (None, "fw-b"):
        provider = OPNsenseProvider(config_dir=cfg, output_dir=tmp_path / "out", firewall=firewall)
        provider.set_environment("dev")
        provider.backend_peer_ids = frozenset({"opnsense", "opnsense@fw-b"})
        out = tmp_path / "out" / "dev" / "terraform" / provider.name
        out.mkdir(parents=True)
        assert provider.render_backend()
        text = (out / "backend.tf").read_text()
        keys.append(next(line for line in text.splitlines() if line.strip().startswith("key")))
    assert keys[0] != keys[1]
    assert "opnsense@fw-b" in keys[1]
