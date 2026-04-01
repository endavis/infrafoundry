"""Tests for secure file writing utilities."""

import os
import stat

import yaml

from infrafoundry.core.security.file_utils import secure_write, secure_write_yaml


class TestSecureWrite:
    """Tests for secure_write function."""

    def test_creates_file_with_600_permissions(self, tmp_path):
        """Test that secure_write creates files with 0o600 permissions."""
        path = tmp_path / "secret.txt"
        secure_write(path, "secret content")
        assert path.exists()
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

    def test_writes_correct_content(self, tmp_path):
        """Test that secure_write writes the expected content."""
        path = tmp_path / "secret.txt"
        secure_write(path, "secret content")
        assert path.read_text() == "secret content"

    def test_custom_permissions(self, tmp_path):
        """Test that custom permissions are applied."""
        path = tmp_path / "secret.txt"
        secure_write(path, "content", permissions=0o640)
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o640

    def test_overwrites_existing_file(self, tmp_path):
        """Test that existing files are overwritten with correct permissions."""
        path = tmp_path / "secret.txt"
        path.write_text("old content")
        os.chmod(path, 0o644)
        secure_write(path, "new content")
        assert path.read_text() == "new content"
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

    def test_empty_content(self, tmp_path):
        """Test that empty content is handled correctly."""
        path = tmp_path / "empty.txt"
        secure_write(path, "")
        assert path.exists()
        assert path.read_text() == ""
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


class TestSecureWriteYaml:
    """Tests for secure_write_yaml function."""

    def test_creates_file_with_600_permissions(self, tmp_path):
        """Test that secure_write_yaml creates files with 0o600 permissions."""
        path = tmp_path / "secret.yaml"
        secure_write_yaml(path, {"key": "value"})
        assert path.exists()
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

    def test_writes_valid_yaml(self, tmp_path):
        """Test that secure_write_yaml writes valid YAML content."""
        path = tmp_path / "secret.yaml"
        data = {"api_key": "secret123", "api_url": "https://example.com"}
        secure_write_yaml(path, data)
        loaded = yaml.safe_load(path.read_text())
        assert loaded == data

    def test_custom_permissions(self, tmp_path):
        """Test that custom permissions are applied to YAML files."""
        path = tmp_path / "secret.yaml"
        secure_write_yaml(path, {"key": "value"}, permissions=0o640)
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o640

    def test_overwrites_existing_yaml_file(self, tmp_path):
        """Test that existing YAML files are overwritten with correct permissions."""
        path = tmp_path / "secret.yaml"
        path.write_text("old: data\n")
        os.chmod(path, 0o644)
        secure_write_yaml(path, {"new": "data"})
        loaded = yaml.safe_load(path.read_text())
        assert loaded == {"new": "data"}
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

    def test_nested_data(self, tmp_path):
        """Test that nested dictionaries are serialized correctly."""
        path = tmp_path / "nested.yaml"
        data = {"level1": {"level2": {"key": "value"}}, "list": [1, 2, 3]}
        secure_write_yaml(path, data)
        loaded = yaml.safe_load(path.read_text())
        assert loaded == data
