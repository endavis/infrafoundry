"""The GL.iNet modules reuse the core TLS pin (no private copy)."""

from __future__ import annotations

from infrafoundry.core import tls_pin
from infrafoundry.providers.openwrt.glinet import rpc, settings
from infrafoundry.providers.openwrt.glinet.settings import GlinetWebSettings


def test_glinet_reuses_core_pin_objects() -> None:
    assert rpc.PinnedHTTPSConnection is tls_pin.PinnedHTTPSConnection
    assert rpc.make_tls_context is tls_pin.make_tls_context
    assert settings.normalize_fingerprint is tls_pin.normalize_fingerprint


def test_default_factory_mismatch_raises_glinet_pin_error() -> None:
    conn = rpc._default_factory(
        GlinetWebSettings(address="192.0.2.1", password="x", fingerprint="0" * 64)
    )
    error = conn._on_mismatch()  # type: ignore[attr-defined]
    assert isinstance(error, rpc.GlinetTlsPinError)
    assert "re-pin tls_fingerprint" in str(error)
