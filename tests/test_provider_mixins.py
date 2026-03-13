"""Tests for provider mixin functionality."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_mixins import (
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
)


class FakeProvider(TerraformGeneratorMixin, ResourceGrouperMixin):
    """Minimal fake provider for testing TerraformGeneratorMixin."""

    def __init__(self, terraform_dir: Path) -> None:
        self.name = "test"
        self.terraform_dir = terraform_dir
        self.config_dir = terraform_dir.parent
        self._logger = MagicMock()

    def ensure_directories(self) -> None:
        self.terraform_dir.mkdir(parents=True, exist_ok=True)

    def _write_terraform_file(self, filename: str, content: str) -> None:
        (self.terraform_dir / filename).write_text(content)

    def render_template(self, template_name: str, context: dict[str, Any]) -> str:
        return f"# rendered {template_name} with {len(context)} vars"


class TestCleanStaleTfFiles:
    """Tests for _clean_stale_tf_files in TerraformGeneratorMixin."""

    @pytest.fixture
    def provider(self, tmp_path: Path) -> FakeProvider:
        """Create a FakeProvider with a temporary terraform directory."""
        tf_dir = tmp_path / "terraform" / "test"
        tf_dir.mkdir(parents=True)
        return FakeProvider(tf_dir)

    def test_removes_stale_tf_files(self, provider: FakeProvider) -> None:
        """Stale .tf files are removed."""
        stale = provider.terraform_dir / "old_resource.tf"
        stale.write_text("# stale")
        another = provider.terraform_dir / "another.tf"
        another.write_text("# also stale")

        removed = provider._clean_stale_tf_files()

        assert not stale.exists()
        assert not another.exists()
        assert len(removed) == 2

    def test_preserves_terraform_tfvars(self, provider: FakeProvider) -> None:
        """terraform.tfvars is preserved during cleanup."""
        tfvars = provider.terraform_dir / "terraform.tfvars"
        tfvars.write_text("key = value")
        stale = provider.terraform_dir / "stale.tf"
        stale.write_text("# stale")

        provider._clean_stale_tf_files()

        assert tfvars.exists()
        assert not stale.exists()

    def test_preserves_terraform_directory(self, provider: FakeProvider) -> None:
        """.terraform/ directory and its contents are untouched."""
        dot_tf = provider.terraform_dir / ".terraform"
        dot_tf.mkdir()
        lock_file = dot_tf / "terraform.lock.hcl"
        lock_file.write_text("lock")

        provider._clean_stale_tf_files()

        assert dot_tf.exists()
        assert lock_file.exists()

    def test_preserves_state_files(self, provider: FakeProvider) -> None:
        """State files (*.tfstate) are not .tf files, so they are untouched."""
        state_file = provider.terraform_dir / "terraform.tfstate"
        state_file.write_text("{}")
        backup = provider.terraform_dir / "terraform.tfstate.backup"
        backup.write_text("{}")

        provider._clean_stale_tf_files()

        assert state_file.exists()
        assert backup.exists()

    def test_nonexistent_directory_returns_empty(self, tmp_path: Path) -> None:
        """Returns empty list when terraform_dir does not exist."""
        provider = FakeProvider(tmp_path / "nonexistent" / "test")
        removed = provider._clean_stale_tf_files()
        assert removed == []

    def test_empty_directory_returns_empty(self, provider: FakeProvider) -> None:
        """Returns empty list when no .tf files exist."""
        removed = provider._clean_stale_tf_files()
        assert removed == []

    def test_preserves_non_tf_files(self, provider: FakeProvider) -> None:
        """Non-.tf files (like .json, .yaml) are untouched."""
        json_file = provider.terraform_dir / "config.json"
        json_file.write_text("{}")

        provider._clean_stale_tf_files()

        assert json_file.exists()


class TestPrepareTerraformGeneration:
    """Tests for prepare_terraform_generation including stale file cleanup."""

    @pytest.fixture
    def provider(self, tmp_path: Path) -> FakeProvider:
        """Create a FakeProvider with a temporary terraform directory."""
        tf_dir = tmp_path / "terraform" / "test"
        return FakeProvider(tf_dir)

    def test_cleans_stale_files_before_grouping(self, provider: FakeProvider) -> None:
        """Stale .tf files are cleaned before resources are grouped."""
        provider.ensure_directories()
        stale = provider.terraform_dir / "old_resource.tf"
        stale.write_text("# stale resource")

        resources = [
            ResourceConfig(name="vm1", type="vm", provider="test", config={"name": "vm1"}),
        ]

        result = provider.prepare_terraform_generation(resources)

        assert not stale.exists()
        assert "vm" in result
        assert len(result["vm"]) == 1

    def test_groups_resources_by_type(self, provider: FakeProvider) -> None:
        """Resources are correctly grouped by type."""
        resources = [
            ResourceConfig(name="vm1", type="vm", provider="test", config={"name": "vm1"}),
            ResourceConfig(name="vm2", type="vm", provider="test", config={"name": "vm2"}),
            ResourceConfig(name="net1", type="network", provider="test", config={"name": "net1"}),
        ]

        result = provider.prepare_terraform_generation(resources)

        assert len(result["vm"]) == 2
        assert len(result["network"]) == 1

    def test_creates_directories(self, provider: FakeProvider) -> None:
        """Terraform directory is created if it does not exist."""
        assert not provider.terraform_dir.exists()

        resources = [
            ResourceConfig(name="vm1", type="vm", provider="test", config={"name": "vm1"}),
        ]
        provider.prepare_terraform_generation(resources)

        assert provider.terraform_dir.exists()

    def test_missing_ensure_directories_raises(self, tmp_path: Path) -> None:
        """Raises AttributeError if ensure_directories is missing."""
        mixin = TerraformGeneratorMixin()
        mixin.terraform_dir = tmp_path  # type: ignore[attr-defined]

        with pytest.raises(AttributeError, match="ensure_directories"):
            mixin.prepare_terraform_generation([])

    def test_missing_group_resources_raises(self, tmp_path: Path) -> None:
        """Raises AttributeError if group_resources_by_type is missing."""

        class NoGrouper(TerraformGeneratorMixin):
            def __init__(self, td: Path) -> None:
                self.terraform_dir = td
                self._logger = MagicMock()

            def ensure_directories(self) -> None:
                self.terraform_dir.mkdir(parents=True, exist_ok=True)

        obj = NoGrouper(tmp_path / "tf")
        with pytest.raises(AttributeError, match="group_resources_by_type"):
            obj.prepare_terraform_generation([])
