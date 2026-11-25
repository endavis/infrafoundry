"""Certificate pinning helpers shared by the HTTPS device clients."""

from __future__ import annotations

import pytest

from infrafoundry.core.tls_pin import PinnedHTTPSConnection, normalize_fingerprint

from ..providers.qnap.qnap_fake import ServedQnap
from ..providers.qnap.qnap_fake import served_qnap as served_qnap

pytestmark = pytest.mark.unit

HEX = "ab" * 32


class _PinMismatchError(Exception):
    pass


def _connection(served: ServedQnap, fingerprint: str | None) -> PinnedHTTPSConnection:
    return PinnedHTTPSConnection(
        "127.0.0.1",
        served.port,
        fingerprint=fingerprint,
        timeout=5,
        on_mismatch=lambda: _PinMismatchError("mismatch"),
    )


def test_normalize_accepts_colons_and_any_case() -> None:
    colons = ":".join(HEX[i : i + 2].upper() for i in range(0, 64, 2))
    assert normalize_fingerprint(colons) == HEX
    assert normalize_fingerprint(f"  {HEX.upper()} ") == HEX


@pytest.mark.parametrize("value", ["ab" * 31, "zz" * 32, "", None, 12, b"ab" * 32])
def test_normalize_rejects_bad_values(value: object) -> None:
    assert normalize_fingerprint(value) is None


def test_matching_pin_connects(served_qnap: ServedQnap) -> None:
    connection = _connection(served_qnap, served_qnap.fingerprint)
    connection.connect()
    connection.close()


def test_mismatch_raises_the_factory_error_and_sends_nothing(served_qnap: ServedQnap) -> None:
    connection = _connection(served_qnap, served_qnap.other_fingerprint)
    with pytest.raises(_PinMismatchError):
        connection.request("GET", "/api/live")
    assert served_qnap.state.requests == []


def test_no_pin_connects(served_qnap: ServedQnap) -> None:
    connection = _connection(served_qnap, None)
    connection.connect()
    connection.close()
