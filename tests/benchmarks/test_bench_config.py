"""Benchmark config loading against a synthetic multi-environment config repo."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from infrafoundry.core.config import ConfigManager

ENV_COUNT = 20
PROVIDER_COUNT = 5
FILES_PER_PROVIDER = 10
RESOURCES_PER_FILE = 5


@pytest.fixture
def synthetic_config_repo(tmp_path: Path) -> Path:
    """Build an ``envs/`` tree with many envs, providers and resource files."""
    envs_dir = tmp_path / "envs"
    for e in range(ENV_COUNT):
        env_dir = envs_dir / f"env{e}"
        env_dir.mkdir(parents=True)
        settings = {
            "name": f"env{e}",
            "description": f"Synthetic environment {e}",
            "variables": {"datacenter": "dc1", "network": "vmbr0"},
        }
        (env_dir / "settings.yaml").write_text(yaml.safe_dump(settings))
        for p in range(PROVIDER_COUNT):
            prov_dir = env_dir / f"prov{p}"
            prov_dir.mkdir()
            for f in range(FILES_PER_PROVIDER):
                vms = [
                    {
                        "name": f"p{p}-f{f}-r{r}",
                        "template": "ubuntu-22.04",
                        "cores": 2 + r,
                        "memory": 4096,
                        "disk_size": 50,
                        "tags": ["bench", f"group{f}", f"rank{r}"],
                    }
                    for r in range(RESOURCES_PER_FILE)
                ]
                (prov_dir / f"vm-{f:02d}.yaml").write_text(yaml.safe_dump({"vm": vms}))
    return envs_dir


@pytest.mark.benchmark
def test_bench_config_load_environment(benchmark: Any, synthetic_config_repo: Path) -> None:
    """Benchmark loading one environment from a 20-environment config repo."""
    expected = PROVIDER_COUNT * FILES_PER_PROVIDER * RESOURCES_PER_FILE
    sanity = ConfigManager(synthetic_config_repo)
    assert len(sanity.get_all_resources_all_providers("env3")) == expected

    def load() -> None:
        manager = ConfigManager(synthetic_config_repo)
        manager.load_environment("env3")
        manager.get_all_resources_all_providers("env3")
        manager.list_environments()

    benchmark(load)
