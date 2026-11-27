"""Credential and TLS injection for pynetappfoundry clients, held in memory (ADR-0042).

``Config.__init__`` parses every TOML file under its config directory and creates
``data/<script>/...`` directories under the current directory. pynetappfoundry's API
clients read only a handful of members from the config, so :class:`InMemoryConfig`
supplies exactly those and never calls the parent constructor. No secret is written to
disk and no directory is created.

This module imports pynetappfoundry at module level: import it only from inside a
function (``connect_ontap``), never from package import time.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, override

from pynetappfoundry.clients.trust import HostTrustStore, TlsFingerprintStore
from pynetappfoundry.core.config import Config
from pynetappfoundry.core.models import ONTAPAPISettings

_IN_MEMORY = Path("in-memory")
"""Placeholder path of the in-memory stores; never read or written."""

TlsFetcher = Callable[[str, int], bytes]


class PinnedFingerprintStore(TlsFingerprintStore):
    """A TLS fingerprint store that never touches the disk.

    With a pin the store answers it for every host. Without one (the unverified opt-out)
    it records the certificate the host presents on first use and keeps it for this
    object's lifetime only.
    """

    def __init__(self, pin: str | None, fetcher: TlsFetcher | None = None) -> None:
        """Initialize the store.

        Args:
            pin: The configured SHA-256 fingerprint (64 lowercase hex), or ``None``.
            fetcher: Returns the DER certificate a host presents; replaced in tests.
        """
        super().__init__(_IN_MEMORY, fetcher)
        self._pin = pin

    @override
    def get_fingerprint(self, host: str, port: int = 443) -> str:
        """Return the pin, or the fingerprint this run saw first (never persisted)."""
        if self._pin is not None:
            return self._pin
        key = f"{host}:{port}"
        cached = self._cache.get(key)
        if cached is None:
            cached = hashlib.sha256(self._fetcher(host, port)).hexdigest()
            self._cache[key] = cached
        return cached


class _MemoryTrustStore(HostTrustStore):
    """The trust directory the client reads; only its in-memory TLS store is ever used."""

    def __init__(self, tls: PinnedFingerprintStore) -> None:
        super().__init__(_IN_MEMORY)
        self.tls = tls


class InMemoryConfig(Config):
    """The part of ``Config`` the API clients read, built from values in memory."""

    def __init__(  # deliberately does not call Config.__init__ (see module doc)
        self,
        *,
        cluster: str,
        username: str,
        password: str,
        spec_dir: Path,
        timeout: float,
        trust: PinnedFingerprintStore,
        verify: bool | None,
        ca_bundle: str | None,
    ) -> None:
        self._cluster = cluster
        self._username = username
        self._password = password
        self._spec_dir = spec_dir
        self._timeout = timeout
        self._memory_trust = _MemoryTrustStore(trust)
        entry: dict[str, Any] = {}
        if ca_bundle is not None:
            entry["ca_bundle"] = ca_bundle
        elif verify is not None:
            entry["verify_ssl"] = verify
        self.data = {"clusters": {cluster: entry}}
        self.settings: dict[str, Any] = {}
        self.config_dir = Path.cwd()
        self.no_cache = True

    @override
    def get_user(
        self, _utype: str = "clusters", _uobject: str = "", *, scope: str | None = None
    ) -> tuple[str, str]:
        """Return the injected credentials.

        pynetappfoundry calls this positionally (``get_user("clusters", name)``); one
        connection holds one cluster's credentials, so the arguments are not consulted.
        """
        return self._username, self._password

    @override
    def get_schema_location(self, api_name: str) -> Path:
        """Return ``<api_spec_dir>/<api_name>``, where ``all.json`` lives."""
        return self._spec_dir / api_name

    @override
    def get_trust_store(self) -> HostTrustStore:
        """Return the in-memory trust store."""
        return self._memory_trust

    @override
    def get_ontap_api_settings(self) -> ONTAPAPISettings:
        """Return the REST settings with the configured timeout."""
        return ONTAPAPISettings(base_api_path="/api", timeout=self._timeout)
