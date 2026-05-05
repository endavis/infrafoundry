"""Shared bootstrap helper for the OPNsense ``infrafoundry`` identity-marker category.

Both ``FirewallRuleService`` and ``NATRuleService`` tag their managed rows
with a per-box ``infrafoundry`` OPNsense category as a fleet-wide marker.
The category is resolved (and, on a fresh box, created) on first apply via
``firewall/category/searchItem`` + ``firewall/category/addItem``. OPNsense's
``addItem`` is **not idempotent by category name**: two concurrent first-
apply dispatches against a fresh box would each see an empty
``searchItem``, each call ``addItem``, and create two distinct
``infrafoundry`` rows. The marker invariant ("exactly one ``infrafoundry``
row per box") would silently break, and subsequent applies would tag
arbitrarily-chosen rows.

Today this race is theoretical because ``OPNsenseDirectRunner.apply()``
dispatches services sequentially; the second service's ``searchItem``
finds the first service's just-created row and the invariant holds.
**The race becomes real the moment dispatch becomes concurrent** — a
future change anyone might make without thinking about this contract.
This helper closes the race at the implementation layer regardless of
dispatch order: a process-local lock + per-box UUID cache means only
one ``addItem`` ever fires per box per process, and concurrent callers
serialize on the first attempt then hit the cache on every subsequent
one.

Cache key
---------

The cache is keyed by the OPNsense client's ``base_url``. One entry per
box per process. Different environments (different ``base_url``s) get
distinct cache entries; the same box reached via two service instances
in the same process shares one entry.

Test affordance
---------------

``reset_cache_for_tests()`` clears the module-level cache. Test suites
that exercise the helper (or services that delegate to it) must call
this in a ``setup_method`` / autouse fixture so each test starts from
a clean cache state — without it, cached state from earlier tests
leaks into later ones.

References
----------

- Issue #746: bug — identity-marker race condition between concurrent
  ``firewall_rules`` and ``nat_rules`` first apply.
- ADR-0014 §"Per-component decisions" — records that marker bootstrap
  is process-shared rather than per-service-lazy.
"""

from __future__ import annotations

import threading
from typing import Any

from infrafoundry.core.exceptions import InfraFoundryError

# Name of the OPNsense category created/used as the fleet-wide marker
# for InfraFoundry-managed rules. Both ``FirewallRuleService`` and
# ``NATRuleService`` reference this value.
INFRAFOUNDRY_CATEGORY_NAME = "infrafoundry"

# Module-level lock and cache. The lock serializes the search+create
# critical section so only one ``addItem`` ever fires per box per
# process. The cache is a process-local dict keyed by the OPNsense
# client's ``base_url`` (one entry per box per process).
_lock = threading.Lock()
_cache: dict[str, str] = {}


def _client_base_url(client: Any) -> str:
    """Return the cache key for an OPNsense client.

    The wrapper ``OPNsenseClient`` (in ``api_client.py``) exposes
    ``base_url`` as a top-level attribute; tests using ``MagicMock`` for
    the client auto-generate a per-instance mock attribute when the
    attribute is accessed. Either form is hashable and suitable as a
    dict key.

    Args:
        client: The OPNsense API client (real or mocked).

    Returns:
        The string used as the per-box cache key.
    """
    return str(client.base_url)


def ensure_infrafoundry_category(client: Any) -> str:
    """Return the UUID of the ``infrafoundry`` category, creating it if absent.

    Thread-safe and process-cached. Concurrent callers against the same
    client serialize on a module-level lock and share a single
    ``addItem`` call; subsequent callers (in the same process, against
    the same ``base_url``) hit the cache without any API round-trip.

    The lookup order is:

    1. Cache hit → return immediately (no lock needed).
    2. Acquire lock.
    3. Re-check cache (double-checked locking — another thread may have
       populated it between the cache miss and lock acquisition).
    4. ``firewall/category/searchItem`` → if a row matches
       ``INFRAFOUNDRY_CATEGORY_NAME``, cache and return its UUID.
    5. ``firewall/category/addItem`` → cache and return the new UUID.
    6. If neither yields a UUID, raise ``InfraFoundryError``.

    Args:
        client: An OPNsense API client (or mock) exposing ``request()``
            and ``base_url``. ``request()`` must accept ``(method,
            endpoint)`` for ``searchItem`` and ``(method, endpoint,
            data=...)`` for ``addItem``.

    Returns:
        UUID string for the OPNsense category named ``infrafoundry``.

    Raises:
        InfraFoundryError: If neither ``searchItem`` nor ``addItem``
            returns a usable UUID.
    """
    key = _client_base_url(client)

    cached = _cache.get(key)
    if cached is not None:
        return cached

    with _lock:
        # Double-checked: another thread may have populated the cache
        # while we were waiting for the lock.
        cached = _cache.get(key)
        if cached is not None:
            return cached

        search_response = client.request("POST", "firewall/category/searchItem")
        rows: list[dict[str, Any]] = []
        if isinstance(search_response, dict):
            raw_rows = search_response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]
        for row in rows:
            if row.get("name") == INFRAFOUNDRY_CATEGORY_NAME:
                uuid = str(row.get("uuid", ""))
                if uuid:
                    _cache[key] = uuid
                    return uuid

        add_response = client.request(
            "POST",
            "firewall/category/addItem",
            data={
                "category": {
                    "name": INFRAFOUNDRY_CATEGORY_NAME,
                    "auto": "0",
                    "color": "",
                }
            },
        )
        if isinstance(add_response, dict):
            uuid = str(add_response.get("uuid", ""))
            if uuid:
                _cache[key] = uuid
                return uuid

        raise InfraFoundryError(
            f"Failed to ensure '{INFRAFOUNDRY_CATEGORY_NAME}' category exists on "
            f"OPNsense; addItem response: {add_response!r}"
        )


def reset_cache_for_tests() -> None:
    """Clear the module-level cache.

    Test-only affordance. Call from a ``setup_method`` or autouse
    fixture in test suites that exercise this helper (or services that
    delegate to it) so each test starts from a clean cache state.
    """
    with _lock:
        _cache.clear()
