"""The QNAP web API client against a local fake switch."""

from __future__ import annotations

import base64
import logging

import pytest

from infrafoundry.providers.qnap.client import (
    QnapApiDriftError,
    QnapApiError,
    QnapAuthError,
    QnapClient,
    QnapTimeoutError,
    QnapTlsPinError,
    QnapUnreachableError,
    ez_encode,
)

from .conftest import settings_for
from .qnap_fake import PASSWORD, PASSWORD_B64, RENEWED_TOKEN, TOKEN, ServedQnap

pytestmark = pytest.mark.unit


def test_ez_encode_ascii_equals_base64() -> None:
    assert ez_encode("Passw0rd-example") == base64.b64encode(b"Passw0rd-example").decode()


def test_ez_encode_masks_bmp_characters_to_8_bits() -> None:
    # U+0141 is masked to 0x41 ("A"), as the web UI's code-unit masking does.
    assert ez_encode("Ł") == base64.b64encode(b"A").decode()


def test_ez_encode_masks_each_surrogate_of_a_non_bmp_character() -> None:
    # U+1F600 is the surrogates D83D DE00, masked to 0x3D and 0x00.
    assert ez_encode("\U0001f600") == base64.b64encode(bytes([0x3D, 0x00])).decode()


def test_login_sends_base64_password_and_bearer_afterwards(served_qnap: ServedQnap) -> None:
    client = QnapClient(settings_for(served_qnap))
    client.login()
    assert client.get("firmware/info")["version"] == "2.5.0"
    requests = served_qnap.state.requests
    assert requests[0][3]["password"] == PASSWORD_B64
    assert requests[0][2] is None
    assert requests[1][2] == f"Bearer {TOKEN}"


def test_session_logs_out_on_success_and_on_error(served_qnap: ServedQnap) -> None:
    client = QnapClient(settings_for(served_qnap))
    with client.session():
        pass
    with pytest.raises(RuntimeError), client.session():
        raise RuntimeError("boom")
    assert served_qnap.state.logouts == 2


def test_wrong_password_logs_in_exactly_once_and_leaks_nothing(
    served_qnap: ServedQnap, caplog: pytest.LogCaptureFixture
) -> None:
    client = QnapClient(settings_for(served_qnap, password="wrong-pw-example"))
    with caplog.at_level(logging.DEBUG), pytest.raises(QnapAuthError) as caught:
        client.login()
    assert served_qnap.state.logins == 1
    secrets = ["wrong-pw-example", ez_encode("wrong-pw-example"), TOKEN]
    haystack = str(caught.value) + repr(client) + caplog.text
    assert not any(secret in haystack for secret in secrets)
    assert "not retrying" in str(caught.value)


def test_non_200_error_code_names_the_endpoint(served_qnap: ServedQnap) -> None:
    served_qnap.state.envelopes["firmware/info"] = {
        "error_code": 500,
        "error_message": "x",
        "result": None,
    }
    client = QnapClient(settings_for(served_qnap))
    client.login()
    with pytest.raises(QnapApiError, match="firmware/info") as caught:
        client.get("firmware/info")
    assert caught.value.error_code == 500


def test_http_401_raises_auth_error(served_qnap: ServedQnap) -> None:
    client = QnapClient(settings_for(served_qnap))
    with pytest.raises(QnapAuthError):
        client.get("firmware/info")  # no login: the fake answers 401


@pytest.mark.parametrize(
    "body",
    [b"<html>no</html>", b"[1]", b'{"error_code": 200}', b'{"error_code": "x", "result": 1}'],
)
def test_malformed_replies_are_api_drift(served_qnap: ServedQnap, body: bytes) -> None:
    client = QnapClient(settings_for(served_qnap))
    client.login()
    served_qnap.state.raw["firmware/info"] = body
    with pytest.raises(QnapApiDriftError, match="firmware/info"):
        client.get("firmware/info")


def test_per_call_timeout_raises_timeout_error(served_qnap: ServedQnap) -> None:
    client = QnapClient(settings_for(served_qnap))
    client.login()
    served_qnap.state.delays["firmware/update/check"] = 1.5
    with pytest.raises(QnapTimeoutError):
        client.get("firmware/update/check", timeout=0.3)


def test_refused_port_raises_unreachable(served_qnap: ServedQnap) -> None:
    client = QnapClient(settings_for(served_qnap))
    served_qnap.stop()
    with pytest.raises(QnapUnreachableError):
        client.login()


def test_pin_mismatch_raises_and_sends_nothing(served_qnap: ServedQnap) -> None:
    client = QnapClient(settings_for(served_qnap, fingerprint=served_qnap.other_fingerprint))
    with pytest.raises(QnapTlsPinError):
        client.login()
    assert served_qnap.state.requests == []


def test_renew_replaces_the_token(served_qnap: ServedQnap) -> None:
    client = QnapClient(settings_for(served_qnap))
    client.login()
    client.renew()
    client.get("firmware/info")
    assert served_qnap.state.requests[-1][2] == f"Bearer {RENEWED_TOKEN}"


def test_live_is_true_when_up_and_false_when_stopped(served_qnap: ServedQnap) -> None:
    client = QnapClient(settings_for(served_qnap))
    assert client.live() is True
    served_qnap.stop()
    assert client.live() is False


def test_about_sends_no_authorization_header(served_qnap: ServedQnap) -> None:
    client = QnapClient(settings_for(served_qnap))
    client.login()
    about = client.about()
    assert about["Product"] == "QSW-M"
    assert served_qnap.state.requests[-1][2] is None


def test_verify_ssl_false_connects_and_warns(
    served_qnap: ServedQnap, caplog: pytest.LogCaptureFixture
) -> None:
    client = QnapClient(settings_for(served_qnap, fingerprint=None, verify_ssl=False))
    with caplog.at_level(logging.WARNING):
        client.probe_tls()
        assert client.live() is True
    assert "certificate is not checked" in caplog.text


def test_password_constant_matches_the_literal() -> None:
    assert ez_encode(PASSWORD) == PASSWORD_B64


def test_repr_shows_host_and_port_only(served_qnap: ServedQnap) -> None:
    text = repr(QnapClient(settings_for(served_qnap)))
    assert "127.0.0.1" in text and PASSWORD not in text


def test_get_raw_returns_exact_bytes_with_bearer(served_qnap: ServedQnap) -> None:
    payload = b"\x1f\x8b\x00binary-example"
    served_qnap.state.raw["system/config"] = payload
    client = QnapClient(settings_for(served_qnap))
    with client.session():
        assert client.get_raw("system/config") == payload
    request = next(r for r in served_qnap.state.requests if r[1].endswith("system/config"))
    assert request[2] == f"Bearer {TOKEN}"


@pytest.mark.parametrize("body", [b"<!DOCTYPE html><html></html>", b"<html>x</html>", b""])
def test_get_raw_rejects_html_and_empty(served_qnap: ServedQnap, body: bytes) -> None:
    served_qnap.state.raw["system/config"] = body
    client = QnapClient(settings_for(served_qnap))
    with client.session(), pytest.raises(QnapApiDriftError):
        client.get_raw("system/config")


def test_get_raw_envelope_error_code_and_success(served_qnap: ServedQnap) -> None:
    served_qnap.state.envelopes["a"] = {"error_code": 500, "error_message": "x", "result": None}
    served_qnap.state.envelopes["b"] = {"error_code": 200, "error_message": "OK", "result": 1}
    served_qnap.state.envelopes["c"] = {"error_code": 401, "error_message": "x", "result": None}
    client = QnapClient(settings_for(served_qnap))
    with client.session():
        with pytest.raises(QnapApiError) as caught:
            client.get_raw("a")
        assert caught.value.error_code == 500
        with pytest.raises(QnapApiDriftError, match="not a download"):
            client.get_raw("b")
        with pytest.raises(QnapAuthError):
            client.get_raw("c")


def test_get_raw_without_login_is_an_auth_error(served_qnap: ServedQnap) -> None:
    client = QnapClient(settings_for(served_qnap))
    with pytest.raises(QnapAuthError):
        client.get_raw("firmware/info")


def test_get_raw_errors_leak_nothing(
    served_qnap: ServedQnap, caplog: pytest.LogCaptureFixture
) -> None:
    served_qnap.state.raw["system/config"] = b"<html>x</html>"
    client = QnapClient(settings_for(served_qnap))
    with (
        caplog.at_level(logging.DEBUG),
        pytest.raises(QnapApiDriftError) as caught,
        client.session(),
    ):
        client.get_raw("system/config")
    secrets = [PASSWORD, ez_encode(PASSWORD), TOKEN]
    haystack = str(caught.value) + repr(client) + caplog.text
    assert not any(secret in haystack for secret in secrets)
