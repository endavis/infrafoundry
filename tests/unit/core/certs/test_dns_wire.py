"""The stdlib DNS client: encoder, parser, transports and the TCP retry."""

from __future__ import annotations

import socket
import struct

import pytest

from infrafoundry.core.certs.dns_wire import (
    FLAG_AA,
    FLAG_QR,
    FLAG_TC,
    TXT_TYPE,
    encode_txt_query,
    parse_txt_response,
    query_txt,
    tcp_exchange_on,
)

pytestmark = pytest.mark.unit

NAME = "_acme-challenge.example.com"
QID = 0x1234


def wire_name(name: str) -> bytes:
    return b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"


def txt_rr(owner: bytes, *strings: str, rtype: int = TXT_TYPE) -> bytes:
    rdata = b"".join(bytes([len(s)]) + s.encode() for s in strings)
    return owner + struct.pack("!HHIH", rtype, 1, 60, len(rdata)) + rdata


def response(
    *records: bytes,
    qid: int = QID,
    flags: int = FLAG_QR | FLAG_AA,
    name: str = NAME,
    rcode: int = 0,
    count: int | None = None,
) -> bytes:
    header = struct.pack(
        "!HHHHHH", qid, flags | rcode, 1, len(records) if count is None else count, 0, 0
    )
    return header + wire_name(name) + struct.pack("!HH", TXT_TYPE, 1) + b"".join(records)


POINTER = b"\xc0\x0c"


def test_encoder_matches_a_hand_built_packet() -> None:
    expected = (
        struct.pack("!HHHHHH", QID, 0, 1, 0, 0, 0) + wire_name(NAME) + struct.pack("!HH", 16, 1)
    )
    assert encode_txt_query(NAME, QID) == expected


@pytest.mark.parametrize("name", ["a..example.com", "", "x" * 64 + ".com", "é.example.com"])
def test_encoder_rejects_bad_names(name: str) -> None:
    with pytest.raises(ValueError):
        encode_txt_query(name, 1)


def test_encoder_rejects_a_name_over_255_bytes() -> None:
    with pytest.raises(ValueError):
        encode_txt_query(".".join(["a" * 60] * 5), 1)


def test_compressed_owner_gives_the_value() -> None:
    parsed = parse_txt_response(response(txt_rr(POINTER, "token")), QID, NAME)
    assert parsed.values == {"token"}
    assert parsed.authoritative
    assert not parsed.truncated
    assert parsed.rcode == 0


def test_character_strings_are_concatenated() -> None:
    parsed = parse_txt_response(response(txt_rr(POINTER, "ab", "cd")), QID, NAME)
    assert parsed.values == {"abcd"}


def test_two_records_give_two_values() -> None:
    packet = response(txt_rr(POINTER, "one"), txt_rr(POINTER, "two"))
    assert parse_txt_response(packet, QID, NAME).values == {"one", "two"}


def test_other_types_and_other_owners_are_ignored() -> None:
    packet = response(
        txt_rr(POINTER, "cname", rtype=5),
        txt_rr(wire_name("other.example.com"), "elsewhere"),
        txt_rr(POINTER, "mine"),
    )
    assert parse_txt_response(packet, QID, NAME).values == {"mine"}


def test_nxdomain_reports_rcode_and_no_values() -> None:
    soa = POINTER[:0] + wire_name("example.com") + struct.pack("!HHIH", 6, 1, 60, 0)
    parsed = parse_txt_response(response(soa, rcode=3), QID, NAME)
    assert parsed.rcode == 3
    assert parsed.values == frozenset()


def test_aa_and_tc_bits_are_reported() -> None:
    parsed = parse_txt_response(response(flags=FLAG_QR | FLAG_TC), QID, NAME)
    assert parsed.truncated
    assert not parsed.authoritative


@pytest.mark.parametrize(
    "packet",
    [
        response(qid=QID + 1),
        response(flags=FLAG_AA),
        response(name="other.example.com"),
        b"\x00" * 5,
        response(txt_rr(POINTER, "x")[:-3]),
        response(txt_rr(b"\xc0\x30", "x")),
        response(b"\xc0\x0e", count=1),
    ],
)
def test_malformed_or_mismatched_packets_raise(packet: bytes) -> None:
    with pytest.raises(ValueError):
        parse_txt_response(packet, QID, NAME)


def test_a_looping_pointer_raises() -> None:
    # A pointer at offset 12 pointing at itself is not backwards.
    packet = struct.pack("!HHHHHH", QID, FLAG_QR, 1, 0, 0, 0) + b"\xc0\x0c" + b"\x00" * 4
    with pytest.raises(ValueError):
        parse_txt_response(packet, QID, NAME)


def test_truncated_udp_answer_is_retried_over_tcp() -> None:
    calls: list[str] = []

    def udp(address: str, query: bytes, timeout: float) -> bytes:
        calls.append("udp")
        return response(flags=FLAG_QR | FLAG_AA | FLAG_TC)

    def tcp(address: str, query: bytes, timeout: float) -> bytes:
        calls.append("tcp")
        return response(txt_rr(POINTER, "big"))

    result = query_txt("192.0.2.1", NAME, QID, 1.0, udp=udp, tcp=tcp)
    assert calls == ["udp", "tcp"]
    assert result.values == {"big"}


def test_a_truncated_tcp_answer_raises() -> None:
    def truncated(address: str, query: bytes, timeout: float) -> bytes:
        return response(flags=FLAG_QR | FLAG_AA | FLAG_TC)

    with pytest.raises(ValueError):
        query_txt("192.0.2.1", NAME, QID, 1.0, udp=truncated, tcp=truncated)


def test_tcp_exchange_writes_a_length_prefix_and_reads_the_reply() -> None:
    left, right = socket.socketpair()
    with left, right:
        reply = b"hello-reply"
        right.sendall(struct.pack("!H", len(reply)) + reply)
        assert tcp_exchange_on(left, b"question") == reply
        sent = right.recv(100)
    assert sent == struct.pack("!H", 8) + b"question"


def test_a_short_tcp_read_raises_connection_error() -> None:
    left, right = socket.socketpair()
    with left, right:
        right.sendall(struct.pack("!H", 50) + b"short")
        right.shutdown(socket.SHUT_WR)
        with pytest.raises(ConnectionError):
            tcp_exchange_on(left, b"q")
