"""The GL.iNet RPC client against a local fake TLS server (#1655)."""

from __future__ import annotations

import logging
from dataclasses import replace

import pytest

from infrafoundry.providers.openwrt.glinet.rpc import (
    GlinetApiDriftError,
    GlinetAuthError,
    GlinetRpcClient,
    GlinetRpcError,
    GlinetTlsPinError,
    GlinetUnreachableError,
)
from infrafoundry.providers.openwrt.glinet.settings import GlinetWebSettings

from .glinet_fake import CIPHER, NONCE, PASSWORD, SID, ServedGlinet, expected_hash

pytestmark = pytest.mark.unit


def _settings(served: ServedGlinet, **overrides: object) -> GlinetWebSettings:
    base = GlinetWebSettings(
        address="127.0.0.1",
        password=PASSWORD,
        port=served.port,
        fingerprint=served.fingerprint,
        connect_timeout=5,
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def test_login_call_and_logout(served_glinet: ServedGlinet) -> None:
    client = GlinetRpcClient(_settings(served_glinet))
    with client.session() as sid:
        assert sid == SID
        reply = client.call(sid, "upgrade", "check_firmware_online")
    assert reply["current_version"] == "4.8.7"
    state = served_glinet.state
    assert (state.logins, state.logouts) == (1, 1)
    assert state.login_bodies == [f'{{"username": "root", "hash": "{expected_hash()}"}}']


def test_hash_uses_the_challenge_hash_method(served_glinet: ServedGlinet) -> None:
    served_glinet.state.hash_method = "md5"
    client = GlinetRpcClient(_settings(served_glinet))
    with client.session() as sid:
        assert sid == SID


def test_logout_is_sent_when_the_body_raises(served_glinet: ServedGlinet) -> None:
    client = GlinetRpcClient(_settings(served_glinet))
    with pytest.raises(RuntimeError), client.session():
        raise RuntimeError("boom")
    assert served_glinet.state.logouts == 1


def test_pin_mismatch_raises_and_nothing_is_sent(served_glinet: ServedGlinet) -> None:
    client = GlinetRpcClient(_settings(served_glinet, fingerprint=served_glinet.other_fingerprint))
    with pytest.raises(GlinetTlsPinError, match="re-pin"), client.session():
        pass
    assert served_glinet.state.requests == 0


def test_probe_tls_checks_the_pin_without_a_request(served_glinet: ServedGlinet) -> None:
    GlinetRpcClient(_settings(served_glinet)).probe_tls()
    bad = GlinetRpcClient(_settings(served_glinet, fingerprint=served_glinet.other_fingerprint))
    with pytest.raises(GlinetTlsPinError):
        bad.probe_tls()
    assert served_glinet.state.requests == 0


def test_verify_ssl_false_connects_and_warns(
    served_glinet: ServedGlinet, caplog: pytest.LogCaptureFixture
) -> None:
    client = GlinetRpcClient(_settings(served_glinet, fingerprint=None, verify_ssl=False))
    with caplog.at_level(logging.WARNING), client.session() as sid:
        assert sid == SID
    assert "verify_ssl is false" in caplog.text


def test_wrong_password_is_one_login_and_leaks_nothing(
    served_glinet: ServedGlinet, caplog: pytest.LogCaptureFixture
) -> None:
    client = GlinetRpcClient(_settings(served_glinet, password="not-the-password"))
    with (
        caplog.at_level(logging.DEBUG),
        pytest.raises(GlinetAuthError) as exc,
        client.session(),
    ):
        pass
    assert served_glinet.state.logins == 1
    secrets = ["not-the-password", CIPHER, NONCE, expected_hash(), SID]
    for secret in secrets:
        assert secret not in str(exc.value)
        assert secret not in caplog.text
        assert secret not in repr(client)
    assert "not-the-password" not in repr(client._settings)


def test_unknown_alg_raises_before_login(served_glinet: ServedGlinet) -> None:
    served_glinet.state.alg = "2b"
    client = GlinetRpcClient(_settings(served_glinet))
    with pytest.raises(GlinetApiDriftError), client.session():
        pass
    assert served_glinet.state.logins == 0


def test_jsonrpc_error_object_raises(served_glinet: ServedGlinet) -> None:
    client = GlinetRpcClient(_settings(served_glinet))
    with client.session() as sid, pytest.raises(GlinetRpcError, match="error code -1"):
        client.call(sid, "upgrade", "boom")


def test_non_json_reply_is_api_drift(served_glinet: ServedGlinet) -> None:
    client = GlinetRpcClient(_settings(served_glinet))
    with pytest.raises(GlinetApiDriftError):
        client._post("garbage", {})


def test_dropped_connection_is_unreachable(served_glinet: ServedGlinet) -> None:
    served_glinet.state.down = True
    client = GlinetRpcClient(_settings(served_glinet))
    with pytest.raises(GlinetUnreachableError), client.session():
        pass


def test_connection_refused_is_unreachable(served_glinet: ServedGlinet) -> None:
    client = GlinetRpcClient(_settings(served_glinet, port=1))
    with pytest.raises(GlinetUnreachableError):
        client.probe_tls()
    with pytest.raises(GlinetUnreachableError), client.session():
        pass
