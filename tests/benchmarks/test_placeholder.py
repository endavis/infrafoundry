"""Placeholder benchmark to ensure the benchmark suite is discoverable."""

import pytest


@pytest.mark.benchmark
def test_import_time(benchmark):
    """Benchmark the import time of the infrafoundry package."""

    def import_package():
        import importlib

        import infrafoundry

        importlib.reload(infrafoundry)

    benchmark(import_package)
