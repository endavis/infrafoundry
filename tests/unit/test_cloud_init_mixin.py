"""Unit tests for CloudInitMixin.

Tests the shared cloud-init snippet loading, variable substitution,
and deep merging logic extracted into the CloudInitMixin.
"""

import logging
from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.provider_mixins import CloudInitMixin


class FakeCloudInitProvider(CloudInitMixin):
    """Minimal provider stub for testing CloudInitMixin."""

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir
        self._current_environment: str | None = None
        self.fail_on_missing_snippets = False
        self._logger = logging.getLogger("FakeCloudInitProvider")

    def set_environment(self, env: str) -> None:
        self._current_environment = env


@pytest.fixture
def provider(tmp_path: Path) -> FakeCloudInitProvider:
    """Create a FakeCloudInitProvider with snippet directories."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    snippet_dir = config_dir / "test" / "files" / "cloud-init-snippets"
    snippet_dir.mkdir(parents=True)

    p = FakeCloudInitProvider(config_dir)
    p.set_environment("test")
    return p


@pytest.fixture
def snippet_dir(tmp_path: Path) -> Path:
    """Return the snippet directory path."""
    return tmp_path / "config" / "test" / "files" / "cloud-init-snippets"


def _write_snippet(snippet_dir: Path, name: str, content: str) -> None:
    """Write a cloud-init snippet YAML file."""
    full_path = snippet_dir / f"{name}.yaml"
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)


class TestMergeCloudInitSnippets:
    """Tests for _merge_cloud_init_snippets."""

    def test_no_snippets_key_returns_none(self, provider: FakeCloudInitProvider) -> None:
        """Config without cloud_init_snippets key returns None."""
        config: dict[str, Any] = {"name": "test-vm"}
        result = provider._merge_cloud_init_snippets(config)
        assert result is None

    def test_empty_snippets_list_returns_none(self, provider: FakeCloudInitProvider) -> None:
        """Empty cloud_init_snippets list returns None."""
        config: dict[str, Any] = {"cloud_init_snippets": []}
        result = provider._merge_cloud_init_snippets(config)
        assert result is None

    def test_single_snippet_loaded(
        self, provider: FakeCloudInitProvider, snippet_dir: Path
    ) -> None:
        """Single snippet is loaded and returned as dict."""
        _write_snippet(snippet_dir, "packages/base", "packages:\n  - nginx\n  - curl\n")
        config: dict[str, Any] = {"cloud_init_snippets": ["packages/base"]}
        result = provider._merge_cloud_init_snippets(config)
        assert result is not None
        assert result["packages"] == ["nginx", "curl"]

    def test_multiple_snippets_merged(
        self, provider: FakeCloudInitProvider, snippet_dir: Path
    ) -> None:
        """Multiple snippets are deep-merged: lists concatenated, dicts merged."""
        _write_snippet(snippet_dir, "packages/a", "packages:\n  - nginx\n")
        _write_snippet(snippet_dir, "packages/b", "packages:\n  - curl\n")
        _write_snippet(snippet_dir, "users/admin", "users:\n  - name: admin\n")
        config: dict[str, Any] = {
            "cloud_init_snippets": ["packages/a", "packages/b", "users/admin"]
        }
        result = provider._merge_cloud_init_snippets(config)
        assert result is not None
        assert result["packages"] == ["nginx", "curl"]
        assert result["users"] == [{"name": "admin"}]

    def test_variable_substitution(
        self, provider: FakeCloudInitProvider, snippet_dir: Path
    ) -> None:
        """Variables in snippets are substituted from cloud_init_vars."""
        _write_snippet(snippet_dir, "system/hostname", "hostname: ${HOSTNAME}\n")
        config: dict[str, Any] = {
            "cloud_init_snippets": ["system/hostname"],
            "cloud_init_vars": {"HOSTNAME": "web-01"},
        }
        result = provider._merge_cloud_init_snippets(config)
        assert result is not None
        assert result["hostname"] == "web-01"

    def test_missing_snippet_warns(
        self, provider: FakeCloudInitProvider, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Missing snippet logs a warning in non-strict mode."""
        config: dict[str, Any] = {"cloud_init_snippets": ["nonexistent/snippet"]}
        provider.fail_on_missing_snippets = False
        with caplog.at_level(logging.WARNING):
            result = provider._merge_cloud_init_snippets(config)
        assert result is None
        assert "Cloud-init snippet not found" in caplog.text

    def test_missing_snippet_strict_raises(self, provider: FakeCloudInitProvider) -> None:
        """Missing snippet in strict mode raises FileNotFoundError."""
        config: dict[str, Any] = {"cloud_init_snippets": ["nonexistent/snippet"]}
        provider.fail_on_missing_snippets = True
        with pytest.raises(FileNotFoundError, match="Cloud-init snippet not found"):
            provider._merge_cloud_init_snippets(config)

    def test_no_environment_uses_direct_path(self, tmp_path: Path) -> None:
        """Without an environment, snippets resolve under config_dir/files/."""
        config_dir = tmp_path / "config"
        snippet_dir = config_dir / "files" / "cloud-init-snippets"
        snippet_dir.mkdir(parents=True)
        _write_snippet(snippet_dir, "base", "packages:\n  - git\n")

        p = FakeCloudInitProvider(config_dir)
        # No environment set (_current_environment is None)
        config: dict[str, Any] = {"cloud_init_snippets": ["base"]}
        result = p._merge_cloud_init_snippets(config)
        assert result is not None
        assert result["packages"] == ["git"]

    def test_empty_snippet_file_skipped(
        self, provider: FakeCloudInitProvider, snippet_dir: Path
    ) -> None:
        """An empty YAML snippet file results in None (no data to merge)."""
        _write_snippet(snippet_dir, "empty", "")
        config: dict[str, Any] = {"cloud_init_snippets": ["empty"]}
        result = provider._merge_cloud_init_snippets(config)
        assert result is None


class TestDeepMerge:
    """Tests for the _deep_merge static method."""

    def test_disjoint_keys(self) -> None:
        """Disjoint keys are combined."""
        base: dict[str, Any] = {"a": 1}
        overlay: dict[str, Any] = {"b": 2}
        CloudInitMixin._deep_merge(base, overlay)
        assert base == {"a": 1, "b": 2}

    def test_list_extend(self) -> None:
        """Lists with the same key are concatenated."""
        base: dict[str, Any] = {"packages": ["nginx"]}
        overlay: dict[str, Any] = {"packages": ["curl"]}
        CloudInitMixin._deep_merge(base, overlay)
        assert base["packages"] == ["nginx", "curl"]

    def test_dict_recursive(self) -> None:
        """Nested dicts are merged recursively."""
        base: dict[str, Any] = {"network": {"version": 2, "ethernets": {"eth0": {"dhcp4": True}}}}
        overlay: dict[str, Any] = {"network": {"ethernets": {"eth1": {"dhcp4": False}}}}
        CloudInitMixin._deep_merge(base, overlay)
        assert base["network"]["version"] == 2
        assert "eth0" in base["network"]["ethernets"]
        assert "eth1" in base["network"]["ethernets"]

    def test_scalar_overwrite(self) -> None:
        """Scalar values are overwritten by overlay."""
        base: dict[str, Any] = {"hostname": "old"}
        overlay: dict[str, Any] = {"hostname": "new"}
        CloudInitMixin._deep_merge(base, overlay)
        assert base["hostname"] == "new"


class TestResolveSnippetPath:
    """Tests for _resolve_snippet_path."""

    def test_with_environment(self, provider: FakeCloudInitProvider) -> None:
        """With an environment, path includes the environment name."""
        path = provider._resolve_snippet_path("storage/nfs")
        assert (
            path
            == provider.config_dir
            / "test"
            / "files"
            / "cloud-init-snippets"
            / "storage"
            / "nfs.yaml"
        )

    def test_without_environment(self, tmp_path: Path) -> None:
        """Without an environment, path is directly under config_dir."""
        config_dir = tmp_path / "config"
        p = FakeCloudInitProvider(config_dir)
        path = p._resolve_snippet_path("base")
        assert path == config_dir / "files" / "cloud-init-snippets" / "base.yaml"
