"""Tests for the libyaml-backed config YAML loader."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from infrafoundry.core.config.yaml_loader import _safe_loader_class, load_config_yaml

pytestmark = pytest.mark.unit

DOC = """\
name: demo
count: 3
enabled: true
nothing: null
quoted: "a: b"
items:
  - one
  - two: 2
nested:
  key: [1, 2, 3]
text: |
  line one
  line two
"""


@pytest.fixture(params=["libyaml", "python"])
def loader_path(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run a test against the libyaml path and the pure-Python fallback."""
    if request.param == "python":
        monkeypatch.delattr(yaml, "CSafeLoader", raising=False)
        monkeypatch.setattr(yaml, "__with_libyaml__", False)
    elif not yaml.__with_libyaml__:
        pytest.skip("PyYAML built without libyaml")
    return str(request.param)


@pytest.mark.skipif(not yaml.__with_libyaml__, reason="PyYAML built without libyaml")
def test_selects_c_loader_when_available() -> None:
    assert _safe_loader_class() is yaml.CSafeLoader


def test_falls_back_without_libyaml(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(yaml, "CSafeLoader", raising=False)
    monkeypatch.setattr(yaml, "__with_libyaml__", False)
    assert _safe_loader_class() is yaml.SafeLoader
    assert load_config_yaml("a: 1") == {"a": 1}


def test_falls_back_when_c_loader_attribute_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(yaml, "CSafeLoader", raising=False)
    monkeypatch.setattr(yaml, "__with_libyaml__", True)
    assert _safe_loader_class() is yaml.SafeLoader


def test_parity_with_safe_load(loader_path: str) -> None:
    assert load_config_yaml(DOC) == yaml.safe_load(DOC)


@pytest.mark.parametrize("text", ["", "# only a comment\n"])
def test_empty_documents_return_none(loader_path: str, text: str) -> None:
    assert load_config_yaml(text) is None


def test_accepts_file_handle(loader_path: str, tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(DOC)
    with open(path, encoding="utf-8") as f:
        result: Any = load_config_yaml(f)
    assert result == yaml.safe_load(DOC)


def test_rejects_unsafe_tags(loader_path: str) -> None:
    with pytest.raises(yaml.YAMLError):
        load_config_yaml('!!python/object/apply:os.system ["true"]')


def test_malformed_yaml_raises_yaml_error(loader_path: str) -> None:
    with pytest.raises(yaml.YAMLError):
        load_config_yaml("a: 1\n b: [\n")
