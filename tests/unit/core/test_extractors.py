"""Unit tests for the extractor registry."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.extractors import (
    Extractor,
    ExtractorRegistry,
    _extractor_registry,
    get_extractor,
    has_extractor,
    list_extractor_providers,
    list_extractor_resource_types,
    register_extractor,
)


class _StubExtractor:
    """Minimal :class:`Extractor` Protocol implementation for tests."""

    def __init__(self, payload: str = "yaml: ok") -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def extract(self, env_name: str, **kwargs: Any) -> str:
        self.calls.append((env_name, dict(kwargs)))
        return self.payload


@pytest.fixture
def fresh_registry() -> ExtractorRegistry:
    """Return an empty :class:`ExtractorRegistry` for isolated tests."""
    return ExtractorRegistry()


def test_register_and_get_round_trip(fresh_registry: ExtractorRegistry) -> None:
    """Round-trip: register an extractor, then retrieve it."""
    stub = _StubExtractor()
    fresh_registry.register("opnsense", "vlans", stub)

    assert fresh_registry.get("opnsense", "vlans") is stub


def test_get_unknown_provider_raises_keyerror_with_provider_list(
    fresh_registry: ExtractorRegistry,
) -> None:
    """Unknown provider produces a KeyError listing registered providers."""
    fresh_registry.register("opnsense", "vlans", _StubExtractor())

    with pytest.raises(KeyError) as excinfo:
        fresh_registry.get("nonexistent", "anything")

    msg = str(excinfo.value)
    assert "nonexistent" in msg
    assert "opnsense" in msg
    assert "Registered providers" in msg


def test_get_unknown_resource_type_raises_keyerror_with_resource_list(
    fresh_registry: ExtractorRegistry,
) -> None:
    """Known provider, unknown resource type lists registered types."""
    fresh_registry.register("opnsense", "vlans", _StubExtractor())
    fresh_registry.register("opnsense", "kea_dhcp", _StubExtractor())

    with pytest.raises(KeyError) as excinfo:
        fresh_registry.get("opnsense", "not_a_resource")

    msg = str(excinfo.value)
    assert "not_a_resource" in msg
    assert "opnsense" in msg
    assert "vlans" in msg
    assert "kea_dhcp" in msg
    assert "Registered resource types" in msg


def test_has_returns_false_for_unknown(fresh_registry: ExtractorRegistry) -> None:
    """``has`` returns False for unregistered combinations."""
    assert fresh_registry.has("opnsense", "vlans") is False


def test_has_returns_true_after_register(fresh_registry: ExtractorRegistry) -> None:
    """``has`` returns True after a matching ``register``."""
    fresh_registry.register("opnsense", "vlans", _StubExtractor())

    assert fresh_registry.has("opnsense", "vlans") is True
    assert fresh_registry.has("opnsense", "different") is False


def test_list_resource_types_returns_sorted(fresh_registry: ExtractorRegistry) -> None:
    """``list_resource_types`` returns a sorted list."""
    fresh_registry.register("opnsense", "vlans", _StubExtractor())
    fresh_registry.register("opnsense", "kea_dhcp", _StubExtractor())
    fresh_registry.register("opnsense", "isc_to_kea", _StubExtractor())

    assert fresh_registry.list_resource_types("opnsense") == [
        "isc_to_kea",
        "kea_dhcp",
        "vlans",
    ]


def test_list_resource_types_unknown_provider_returns_empty(
    fresh_registry: ExtractorRegistry,
) -> None:
    """``list_resource_types`` returns ``[]`` for unknown providers."""
    fresh_registry.register("opnsense", "vlans", _StubExtractor())

    assert fresh_registry.list_resource_types("nope") == []


def test_list_providers_returns_sorted(fresh_registry: ExtractorRegistry) -> None:
    """``list_providers`` returns a sorted list of registered providers."""
    fresh_registry.register("opnsense", "vlans", _StubExtractor())
    fresh_registry.register("aws", "vpc", _StubExtractor())
    fresh_registry.register("gcp", "subnet", _StubExtractor())

    assert fresh_registry.list_providers() == ["aws", "gcp", "opnsense"]


def test_register_overwrites_silently(fresh_registry: ExtractorRegistry) -> None:
    """Re-registering a key silently replaces the old extractor.

    Matches ``RunnerRegistry`` semantics — required so test fixtures
    that re-instantiate providers don't error.
    """
    first = _StubExtractor("first")
    second = _StubExtractor("second")

    fresh_registry.register("opnsense", "vlans", first)
    fresh_registry.register("opnsense", "vlans", second)

    assert fresh_registry.get("opnsense", "vlans") is second


def test_extractor_protocol_acceptance() -> None:
    """``_StubExtractor`` satisfies the :class:`Extractor` Protocol.

    Smoke test: ``Extractor`` is a runtime ``Protocol``; this
    test verifies the structural type-check passes via attribute
    inspection (mypy enforces the static check at type-check time).
    """
    stub = _StubExtractor()
    extractor: Extractor = stub  # would be a static-type error if Protocol unsatisfied

    out = extractor.extract("env", x=1)
    assert out == "yaml: ok"
    assert stub.calls == [("env", {"x": 1})]


def test_module_level_singleton_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """The convenience functions delegate to the module singleton."""
    # Swap the module's singleton for an isolated registry so the test
    # doesn't pollute the global state used by other tests.
    isolated = ExtractorRegistry()
    monkeypatch.setattr("infrafoundry.core.extractors._extractor_registry", isolated)

    stub = _StubExtractor()
    register_extractor("opnsense", "vlans", stub)

    assert isolated.has("opnsense", "vlans") is True
    assert get_extractor("opnsense", "vlans") is stub
    assert has_extractor("opnsense", "vlans") is True
    assert list_extractor_resource_types("opnsense") == ["vlans"]
    assert list_extractor_providers() == ["opnsense"]


def test_module_singleton_is_instance() -> None:
    """The module-level ``_extractor_registry`` is an :class:`ExtractorRegistry`."""
    assert isinstance(_extractor_registry, ExtractorRegistry)
