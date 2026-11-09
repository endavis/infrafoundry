"""A name shared across two resource types raises DuplicateResourceNameError (#1337)."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import DuplicateResourceNameError, InvalidConfigurationError


def test_duplicate_across_types_names_both_types_and_files(tmp_path: Path) -> None:
    provider_dir = tmp_path / "dev" / "opnsense"
    provider_dir.mkdir(parents=True)
    (provider_dir / "alpha.yaml").write_text("alpha:\n  - name: shared-name\n    size: 1\n")
    (provider_dir / "beta.yaml").write_text("beta:\n  - name: shared-name\n    size: 2\n")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        with pytest.raises(DuplicateResourceNameError) as excinfo:
            ConfigManager(tmp_path).get_all_resources_all_providers("dev")

    error = excinfo.value
    assert isinstance(error, ValueError)
    assert isinstance(error, InvalidConfigurationError)
    message = str(error)
    assert "Duplicate resource names found in environment 'dev'" in message
    assert "opnsense:shared-name" in message
    assert "alpha (" in message and "alpha.yaml" in message
    assert "beta (" in message and "beta.yaml" in message
