"""Unit tests for ``infrafoundry.providers.opnsense.services._category_marker``.

Coverage:
    - Search-finds-existing-category short circuit (no addItem call).
    - Search empty → addItem path (UUID returned and cached).
    - Multi-call cache hit (subsequent calls skip both API round-trips).
    - **Race-closure assertion** — concurrent callers across many threads
      serialize on the module lock and trigger exactly one addItem.
    - Distinct ``base_url``s populate distinct cache entries.
    - ``reset_cache_for_tests`` clears the cache.
    - Error paths: addItem returns no UUID; search returns malformed
      shapes; search finds other categories but not the marker.
    - Helper does not log or print on the success path.
"""

from __future__ import annotations

import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.providers.opnsense.services._category_marker import (
    INFRAFOUNDRY_CATEGORY_NAME,
    ensure_infrafoundry_category,
    reset_cache_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    """Clear the module-level cache before every test in this file."""
    reset_cache_for_tests()


def _make_client(base_url: str = "https://opnsense.example") -> MagicMock:
    """Build a MagicMock client with a deterministic ``base_url`` attribute.

    Using a string ``base_url`` keeps cache-key behavior deterministic
    across tests; without this, ``MagicMock.base_url`` would return a
    fresh sub-mock per access whose ``str()`` includes a unique id.
    """
    client = MagicMock()
    client.base_url = base_url
    return client


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


class TestSearchFindsExisting:
    def test_search_finds_existing_category_uuid(self) -> None:
        client = _make_client()
        client.request.return_value = {
            "rows": [
                {"uuid": "other-uuid", "name": "other"},
                {"uuid": "ifn-uuid", "name": "infrafoundry"},
            ]
        }
        uuid = ensure_infrafoundry_category(client)
        assert uuid == "ifn-uuid"
        # Only one call: searchItem; no addItem because category exists.
        client.request.assert_called_once_with("POST", "firewall/category/searchItem")

    def test_search_empty_then_create(self) -> None:
        client = _make_client()
        client.request.side_effect = [
            {"rows": []},  # searchItem: no match
            {"uuid": "new-uuid"},  # addItem: created
        ]
        uuid = ensure_infrafoundry_category(client)
        assert uuid == "new-uuid"
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert endpoints == ["firewall/category/searchItem", "firewall/category/addItem"]

    def test_add_item_payload_shape(self) -> None:
        client = _make_client()
        client.request.side_effect = [
            {"rows": []},
            {"uuid": "new-uuid"},
        ]
        ensure_infrafoundry_category(client)
        add_call = client.request.call_args_list[1]
        sent = add_call.kwargs.get("data") or add_call.args[2]
        assert sent["category"]["name"] == INFRAFOUNDRY_CATEGORY_NAME
        assert sent["category"]["auto"] == "0"


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


class TestCacheBehavior:
    def test_subsequent_calls_hit_cache(self) -> None:
        client = _make_client()
        client.request.side_effect = [
            {"rows": []},
            {"uuid": "cached-uuid"},
        ]
        first = ensure_infrafoundry_category(client)
        second = ensure_infrafoundry_category(client)
        assert first == second == "cached-uuid"
        # Two calls total: searchItem + addItem from the first invocation.
        # The second invocation hits the cache and triggers no API round-trip.
        assert client.request.call_count == 2

    def test_distinct_base_urls_dont_share_cache(self) -> None:
        client_a = _make_client(base_url="https://box-a.example")
        client_b = _make_client(base_url="https://box-b.example")
        client_a.request.return_value = {"rows": [{"uuid": "uuid-a", "name": "infrafoundry"}]}
        client_b.request.return_value = {"rows": [{"uuid": "uuid-b", "name": "infrafoundry"}]}
        assert ensure_infrafoundry_category(client_a) == "uuid-a"
        assert ensure_infrafoundry_category(client_b) == "uuid-b"
        # Each box gets its own cache entry; second call against A still
        # returns the A-side UUID.
        assert ensure_infrafoundry_category(client_a) == "uuid-a"
        # Total calls: one searchItem against each box.
        assert client_a.request.call_count == 1
        assert client_b.request.call_count == 1

    def test_reset_cache_for_tests_clears_cache(self) -> None:
        client = _make_client()
        client.request.return_value = {"rows": [{"uuid": "first-uuid", "name": "infrafoundry"}]}
        ensure_infrafoundry_category(client)
        assert client.request.call_count == 1

        reset_cache_for_tests()

        # After reset, the next call must hit the API again rather than
        # returning the cached UUID.
        ensure_infrafoundry_category(client)
        assert client.request.call_count == 2


# ---------------------------------------------------------------------------
# Race-closure assertion (the canonical demonstration that the fix works)
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_concurrent_calls_serialize_on_lock(self) -> None:
        """Multiple threads calling helper concurrently see exactly one addItem.

        This is the canonical demonstration of the fix's value (#746).
        Without the lock, each thread's ``searchItem`` would return
        empty rows simultaneously and each thread would issue its own
        ``addItem`` — creating multiple ``infrafoundry`` rows on a
        fresh OPNsense box. With the lock and double-checked cache,
        the first thread to acquire the lock performs the
        search+create; every subsequent thread observes the populated
        cache (either at the cache-miss check before the lock or at
        the double-check inside the lock) and returns the same UUID.
        """
        add_item_count = Counter[str]()
        new_uuid = "shared-new-uuid"

        def fake_request(
            method: str,
            endpoint: str,
            data: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            if endpoint == "firewall/category/searchItem":
                # Always return empty to maximize race pressure: every
                # thread's pre-lock search would conclude the category
                # is absent. Without the lock all of them would proceed
                # to addItem.
                return {"rows": []}
            if endpoint == "firewall/category/addItem":
                add_item_count[endpoint] += 1
                return {"uuid": new_uuid}
            raise AssertionError(f"unexpected endpoint: {endpoint}")

        client = _make_client(base_url="https://race-test.example")
        client.request.side_effect = fake_request

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: ensure_infrafoundry_category(client), range(8)))

        # Every thread received the same UUID.
        assert all(r == new_uuid for r in results)
        # And ``addItem`` fired exactly once across all threads — the
        # lock + double-checked cache closed the race.
        assert add_item_count["firewall/category/addItem"] == 1


# ---------------------------------------------------------------------------
# Defensive / error paths
# ---------------------------------------------------------------------------


class TestErrorAndDefensivePaths:
    def test_add_item_failure_raises_infrafoundry_error(self) -> None:
        client = _make_client()
        client.request.side_effect = [
            {"rows": []},
            {"result": "failed"},  # addItem: no uuid
        ]
        with pytest.raises(InfraFoundryError, match=INFRAFOUNDRY_CATEGORY_NAME) as excinfo:
            ensure_infrafoundry_category(client)
        # The response body is included in the message for debuggability.
        assert "result" in str(excinfo.value)

    def test_search_returns_non_dict_yields_create(self) -> None:
        # Defensive: searchItem returns a list (malformed) — fall through
        # to addItem rather than crashing.
        client = _make_client()
        client.request.side_effect = [
            ["malformed"],
            {"uuid": "fallback-uuid"},
        ]
        assert ensure_infrafoundry_category(client) == "fallback-uuid"

    def test_search_returns_dict_without_rows_yields_create(self) -> None:
        client = _make_client()
        client.request.side_effect = [
            {},
            {"uuid": "fallback-uuid"},
        ]
        assert ensure_infrafoundry_category(client) == "fallback-uuid"

    def test_search_finds_other_category_with_different_name(self) -> None:
        # Search returns rows but none match "infrafoundry" — fall
        # through to addItem.
        client = _make_client()
        client.request.side_effect = [
            {"rows": [{"uuid": "x", "name": "other"}]},
            {"uuid": "new-uuid"},
        ]
        assert ensure_infrafoundry_category(client) == "new-uuid"

    def test_search_row_with_empty_uuid_falls_through(self) -> None:
        # Defensive: matching row has empty UUID — must not cache the
        # empty value and must fall through to addItem.
        client = _make_client()
        client.request.side_effect = [
            {"rows": [{"uuid": "", "name": "infrafoundry"}]},
            {"uuid": "new-uuid"},
        ]
        assert ensure_infrafoundry_category(client) == "new-uuid"


# ---------------------------------------------------------------------------
# Silence on success
# ---------------------------------------------------------------------------


class TestNoIncidentalLogging:
    def test_helper_does_not_log_on_success(self, caplog: pytest.LogCaptureFixture) -> None:
        client = _make_client()
        client.request.side_effect = [
            {"rows": []},
            {"uuid": "new-uuid"},
        ]
        with caplog.at_level(logging.DEBUG):
            ensure_infrafoundry_category(client)
        # The helper itself emits nothing on the success path; downstream
        # service logging is the caller's concern.
        helper_records = [
            r
            for r in caplog.records
            if r.name.startswith("infrafoundry.providers.opnsense.services._category_marker")
        ]
        assert helper_records == []
