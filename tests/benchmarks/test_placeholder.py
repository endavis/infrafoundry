"""Placeholder benchmark to ensure the benchmark suite is discoverable."""

from typing import Any

import pytest


@pytest.mark.benchmark
def test_import_time(benchmark: Any) -> None:
    """Benchmark the import time of the infrafoundry package."""

    def import_package() -> None:
        import importlib

        import infrafoundry

        importlib.reload(infrafoundry)

    benchmark(import_package)
