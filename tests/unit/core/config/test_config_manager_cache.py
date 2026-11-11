"""Unit tests for ConfigManager per-instance memoization (#244)."""

import logging
import warnings
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from infrafoundry.core.config.config_manager import ConfigManager
from infrafoundry.core.config.models import IaCTool
from infrafoundry.core.exceptions import DuplicateResourceNameError, InvalidConfigurationError

_SYSTEM_YAML = "opnsense:\n  system:\n    tuning:\n      a: 1\n"


def _write_env(base: Path, env: str, extra: str = "") -> Path:
    env_dir = base / env
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / "settings.yaml").write_text(
        f"name: {env}\ndescription: original\nvariables:\n  region: alpha\n{extra}"
    )
    return env_dir


def _write_resource(base: Path, env: str, filename: str = "system.yaml") -> Path:
    provider_dir = base / env / "opnsense"
    provider_dir.mkdir(parents=True, exist_ok=True)
    path = provider_dir / filename
    path.write_text(_SYSTEM_YAML)
    return path


def _write_package(base: Path, env: str) -> None:
    pkg = base / env / "my-pkg"
    pkg.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": "my-pkg",
        "provider": "proxmox",
        "events": {"AFTER_APPLY": [{"type": "script", "script": "scripts/setup.sh"}]},
    }
    (pkg / "infrafoundry.yml").write_text(yaml.dump(manifest))


@pytest.fixture(autouse=True)
def _ignore_deprecation() -> Iterator[None]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        yield


@pytest.fixture(autouse=True)
def _no_iac_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INFRAFOUNDRY_IAC_TOOL", raising=False)


@pytest.mark.unit
class TestEnvironmentCache:
    def test_second_call_is_hit_without_io(self, temp_dir: Path) -> None:
        _write_env(temp_dir, "dev")
        cm = ConfigManager(base_dir=temp_dir)
        with patch.object(cm, "_load_yaml_with_sops", wraps=cm._load_yaml_with_sops) as spy:
            first = cm.load_environment("dev")
            second = cm.load_environment("dev")
        assert spy.call_count == 1
        stats = cm.cache_stats()
        assert stats["environment_misses"] == 1
        assert stats["environment_hits"] == 1
        assert first is not second

    def test_keyed_per_env(self, temp_dir: Path) -> None:
        _write_env(temp_dir, "dev")
        _write_env(temp_dir, "prod")
        cm = ConfigManager(base_dir=temp_dir)
        cm.load_environment("dev")
        cm.load_environment("prod")
        assert cm.cache_stats()["environment_misses"] == 2

    def test_results_are_independent_copies(self, temp_dir: Path) -> None:
        _write_env(temp_dir, "dev")
        cm = ConfigManager(base_dir=temp_dir)
        first = cm.load_environment("dev")
        first.variables["region"] = "changed"  # miss result is not the cached instance
        second = cm.load_environment("dev")
        assert second.variables["region"] == "alpha"
        second.variables["region"] = "changed-again"
        third = cm.load_environment("dev")
        assert third.variables["region"] == "alpha"
        assert second is not third

    def test_missing_env_not_cached(self, temp_dir: Path) -> None:
        cm = ConfigManager(base_dir=temp_dir)
        for _ in range(2):
            with pytest.raises(FileNotFoundError):
                cm.load_environment("nope")
        assert cm.cache_stats()["environment_misses"] == 2
        assert cm.cache_stats()["environment_hits"] == 0

    def test_invalid_yaml_not_cached(self, temp_dir: Path) -> None:
        env_dir = _write_env(temp_dir, "dev")
        (env_dir / "settings.yaml").write_text("name: [unclosed\n")
        cm = ConfigManager(base_dir=temp_dir)
        with pytest.raises(InvalidConfigurationError):
            cm.load_environment("dev")
        _write_env(temp_dir, "dev")
        assert cm.load_environment("dev").name == "dev"

    def test_iac_tool_variable_is_part_of_key(
        self, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_env(temp_dir, "dev", "iac_tool: terraform\n")
        cm = ConfigManager(base_dir=temp_dir)
        monkeypatch.setenv("INFRAFOUNDRY_IAC_TOOL", "opentofu")
        assert cm.load_environment("dev").iac_tool == IaCTool.OPENTOFU
        monkeypatch.delenv("INFRAFOUNDRY_IAC_TOOL")
        assert cm.load_environment("dev").iac_tool == IaCTool.TERRAFORM
        assert cm.cache_stats()["environment_misses"] == 2
        assert cm.load_environment("dev").iac_tool == IaCTool.TERRAFORM
        monkeypatch.setenv("INFRAFOUNDRY_IAC_TOOL", "opentofu")
        assert cm.load_environment("dev").iac_tool == IaCTool.OPENTOFU
        stats = cm.cache_stats()
        assert stats["environment_misses"] == 2
        assert stats["environment_hits"] == 2


@pytest.mark.unit
class TestResourcesCache:
    def test_second_call_is_hit_without_reload(self, temp_dir: Path) -> None:
        _write_env(temp_dir, "dev")
        _write_resource(temp_dir, "dev")
        cm = ConfigManager(base_dir=temp_dir)
        with patch.object(
            cm.provider_centric,
            "discover_providers",
            wraps=cm.provider_centric.discover_providers,
        ) as spy:
            first = cm.get_all_resources_all_providers("dev")
            second = cm.get_all_resources_all_providers("dev")
        assert spy.call_count == 1
        stats = cm.cache_stats()
        assert stats["resources_misses"] == 1
        assert stats["resources_hits"] == 1
        assert [r.name for r in first] == [r.name for r in second]

    def test_keyed_per_env(self, temp_dir: Path) -> None:
        for env in ("dev", "prod"):
            _write_env(temp_dir, env)
            _write_resource(temp_dir, env)
        cm = ConfigManager(base_dir=temp_dir)
        cm.get_all_resources_all_providers("dev")
        cm.get_all_resources_all_providers("prod")
        assert cm.cache_stats()["resources_misses"] == 2

    def test_results_are_independent_copies(self, temp_dir: Path) -> None:
        _write_env(temp_dir, "dev")
        _write_resource(temp_dir, "dev")
        cm = ConfigManager(base_dir=temp_dir)
        first = cm.get_all_resources_all_providers("dev")
        original_len = len(first)
        original_config = dict(first[0].config)
        first[0].config["injected"] = True
        first[0].package_variables = {"x": 1}
        first.append(first[0])
        second = cm.get_all_resources_all_providers("dev")
        assert len(second) == original_len
        assert second[0].config == original_config
        assert second[0].package_variables is None
        second[0].config["injected"] = True
        second.clear()
        third = cm.get_all_resources_all_providers("dev")
        assert len(third) == original_len
        assert third[0].config == original_config

    def test_clear_cache_forces_reload(self, temp_dir: Path) -> None:
        env_dir = _write_env(temp_dir, "dev")
        res_path = _write_resource(temp_dir, "dev")
        cm = ConfigManager(base_dir=temp_dir)
        assert cm.load_environment("dev").description == "original"
        before = cm.get_all_resources_all_providers("dev")

        (env_dir / "settings.yaml").write_text("name: dev\ndescription: edited\n")
        res_path.write_text("opnsense:\n  system:\n    tuning:\n      a: 2\n")

        # No mtime invalidation: stale values until clear_cache().
        assert cm.load_environment("dev").description == "original"
        assert cm.get_all_resources_all_providers("dev")[0].config == before[0].config

        cm.clear_cache()
        assert cm.load_environment("dev").description == "edited"
        after = cm.get_all_resources_all_providers("dev")
        assert after[0].config != before[0].config
        stats = cm.cache_stats()
        assert stats["environment_misses"] == 2
        assert stats["resources_misses"] == 2

    def test_duplicate_error_not_cached(self, temp_dir: Path) -> None:
        _write_env(temp_dir, "dev")
        _write_resource(temp_dir, "dev", "a.yaml")
        dup = _write_resource(temp_dir, "dev", "b.yaml")
        cm = ConfigManager(base_dir=temp_dir)
        with pytest.raises(DuplicateResourceNameError):
            cm.get_all_resources_all_providers("dev")
        dup.unlink()
        assert len(cm.get_all_resources_all_providers("dev")) == 1
        assert cm.cache_stats()["resources_misses"] == 2

    def test_package_events_replayed_on_hit(self, temp_dir: Path) -> None:
        _write_env(temp_dir, "dev")
        _write_package(temp_dir, "dev")
        cm = ConfigManager(base_dir=temp_dir)

        cm.get_all_resources_all_providers("dev")
        first = cm.get_package_events()
        assert "AFTER_APPLY" in first

        # Stale buffer content is replaced, not merged.
        cm.provider_centric._pending_package_events = {"STALE": [{"type": "script"}]}
        cm.get_all_resources_all_providers("dev")
        assert cm.cache_stats()["resources_hits"] == 1
        second = cm.get_package_events()
        assert second == first
        assert "STALE" not in second

        # Mutating a replayed dict does not alter the next replay.
        cm.get_all_resources_all_providers("dev")
        replay: dict[str, Any] = cm.provider_centric._pending_package_events
        replay["AFTER_APPLY"].append({"type": "extra"})
        cm.get_all_resources_all_providers("dev")
        assert cm.get_package_events() == first


@pytest.mark.unit
class TestCacheApi:
    def test_cache_stats_shape_and_copy(self, temp_dir: Path) -> None:
        cm = ConfigManager(base_dir=temp_dir)
        stats = cm.cache_stats()
        assert stats == {
            "environment_hits": 0,
            "environment_misses": 0,
            "resources_hits": 0,
            "resources_misses": 0,
        }
        stats["environment_hits"] = 99
        assert cm.cache_stats()["environment_hits"] == 0

    def test_debug_logging_has_counts_not_contents(
        self, temp_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _write_env(temp_dir, "dev")
        cm = ConfigManager(base_dir=temp_dir)
        caplog.set_level(logging.DEBUG, logger="ConfigManager")
        cm.load_environment("dev")
        cm.load_environment("dev")
        text = caplog.text
        assert "cache miss: load_environment(dev) hits=0 misses=1" in text
        assert "cache hit: load_environment(dev) hits=1 misses=1" in text
        assert "alpha" not in text
        assert "original" not in text

    def test_cleanup_clears_cache(self, temp_dir: Path) -> None:
        _write_env(temp_dir, "dev")
        cm = ConfigManager(base_dir=temp_dir)
        cm.load_environment("dev")
        cm.cleanup()
        cm.load_environment("dev")
        stats = cm.cache_stats()
        assert stats["environment_misses"] == 2
        assert stats["environment_hits"] == 0
