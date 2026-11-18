"""Shared fakes for the collector tests."""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.config.models import CollectorDeviceConfig

MakeDevice = Callable[..., CollectorDeviceConfig]
FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> bytes:
    """Return a fixture file's bytes."""
    return (FIXTURES / name).read_bytes()


@dataclass
class FakeResponse:
    """Minimal response stand-in."""

    content: bytes = b""
    status_code: int = 200


@dataclass
class FakeSession:
    """Records requests and replies from a queue keyed by (method, path-suffix)."""

    replies: dict[tuple[str, str], list[FakeResponse] | FakeResponse | Exception] = field(
        default_factory=dict
    )
    calls: list[dict[str, Any]] = field(default_factory=list)

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        """Record the call and return the matching reply."""
        self.calls.append({"method": method, "url": url, **kwargs})
        for (m, suffix), reply in self.replies.items():
            if m == method and url.split("?")[0].endswith(suffix):
                if isinstance(reply, Exception):
                    raise reply
                if isinstance(reply, list):
                    return reply.pop(0)
                return reply
        return FakeResponse()

    def paths(self) -> list[tuple[str, str]]:
        """Return (method, url) pairs."""
        return [(c["method"], c["url"]) for c in self.calls]


class ReversibleFakeEncryptor:
    """Non-deterministic reversible 'encryption', like SOPS output varies per call."""

    def __init__(self) -> None:
        self.plaintext_paths: list[Path] = []
        self.fail = False
        self._counter = 0

    def encrypt(self, plaintext_path: Path, final_path: Path) -> bytes:
        """Return JSON with a nonce and base64 plaintext."""
        if self.fail:
            raise RuntimeError("encrypt failed")
        self.plaintext_paths.append(plaintext_path)
        assert "infrafoundry-collect-" in str(plaintext_path)
        self._counter += 1
        data = base64.b64encode(plaintext_path.read_bytes()).decode()
        return json.dumps({"nonce": os.urandom(8).hex(), "data": data}).encode()

    def decrypt(self, path: Path) -> bytes:
        """Reverse ``encrypt``."""
        return base64.b64decode(json.loads(path.read_text(encoding="utf-8"))["data"])


@pytest.fixture
def encryptor() -> ReversibleFakeEncryptor:
    """A fresh fake encryptor."""
    return ReversibleFakeEncryptor()


@pytest.fixture
def make_device() -> MakeDevice:
    """Build a device config with synthetic defaults."""

    def _make(**kw: Any) -> CollectorDeviceConfig:
        base: dict[str, Any] = {
            "name": "ont-isp",
            "type": "huawei-ont-web",
            "address": "http://192.0.2.1",
            "username": "admin",
            "password": "CANARY-LOGIN-0001",
        }
        base.update(kw)
        return CollectorDeviceConfig(**base)

    return _make


class FakeConfigManager:
    """Stands in for ConfigManager: a base_dir and a canned environment."""

    def __init__(self, base_dir: Path, env: Any) -> None:
        self.base_dir = base_dir
        self._env = env

    def load_environment(self, _name: str) -> Any:
        """Return the canned environment."""
        return self._env


def make_env(devices: list[dict[str, Any]], output_dir: str | None = None, **extra: Any) -> Any:
    """Build an EnvironmentConfig with a collectors section."""
    from infrafoundry.core.config.models import CollectorsConfig, EnvironmentConfig

    section = CollectorsConfig.model_validate({"devices": devices, "output_dir": output_dir})
    return EnvironmentConfig(name="test", collectors=section, **extra)
