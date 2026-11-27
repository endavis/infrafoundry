"""A small stdlib DNS client for TXT lookups: wire format and socket transports.

Queries go out with recursion off, so an authoritative nameserver answers from its own data and
no resolver cache is involved. UDP is tried first; a truncated answer is retried over TCP.
"""

from __future__ import annotations

import socket
import struct
from collections.abc import Callable
from dataclasses import dataclass

TXT_TYPE = 16
CLASS_IN = 1
DNS_PORT = 53
FLAG_QR = 0x8000
FLAG_AA = 0x0400
FLAG_TC = 0x0200
OPCODE_MASK = 0x7800
RCODE_MASK = 0x000F
HEADER_LEN = 12
MAX_LABEL = 63
MAX_NAME = 255
MAX_POINTER_JUMPS = 32
UDP_BUFFER = 4096

Exchange = Callable[[str, bytes, float], bytes]
"""``(address, query packet, timeout) -> response packet``; may raise ``OSError``."""


@dataclass(frozen=True)
class TxtResponse:
    """The parts of a TXT answer the propagation check needs."""

    rcode: int
    authoritative: bool
    truncated: bool
    values: frozenset[str]


def encode_txt_query(name: str, qid: int) -> bytes:
    """Build a TXT query packet with recursion off.

    Raises:
        ValueError: If the name has an empty or over-long label, is too long, or is not ASCII.
    """
    try:
        raw = name.rstrip(".").encode("ascii")
    except UnicodeEncodeError:
        raise ValueError("DNS name must be ASCII") from None
    labels = raw.split(b".")
    if any(not label or len(label) > MAX_LABEL for label in labels):
        raise ValueError("DNS name has an empty or over-long label")
    wire = b"".join(bytes([len(label)]) + label for label in labels) + b"\x00"
    if len(wire) > MAX_NAME:
        raise ValueError("DNS name is too long")
    header = struct.pack("!HHHHHH", qid, 0, 1, 0, 0, 0)
    return header + wire + struct.pack("!HH", TXT_TYPE, CLASS_IN)


def _read_name(packet: bytes, offset: int) -> tuple[str, int]:
    """Read a (possibly compressed) name; return it lowercased and the offset after it."""
    labels: list[str] = []
    end = -1
    jumps = 0
    pos = offset
    while True:
        if pos >= len(packet):
            raise ValueError("name runs past the packet")
        length = packet[pos]
        if length & 0xC0 == 0xC0:
            if pos + 1 >= len(packet):
                raise ValueError("pointer runs past the packet")
            target = ((length & 0x3F) << 8) | packet[pos + 1]
            if target >= pos:
                raise ValueError("compression pointer does not point backwards")
            jumps += 1
            if jumps > MAX_POINTER_JUMPS:
                raise ValueError("too many compression jumps")
            if end < 0:
                end = pos + 2
            pos = target
            continue
        if length & 0xC0:
            raise ValueError("unsupported label type")
        pos += 1
        if length == 0:
            return ".".join(labels).lower(), (end if end >= 0 else pos)
        if pos + length > len(packet):
            raise ValueError("label runs past the packet")
        labels.append(packet[pos : pos + length].decode("ascii", "replace"))
        pos += length


def _txt_value(rdata: bytes) -> str:
    parts: list[bytes] = []
    pos = 0
    while pos < len(rdata):
        length = rdata[pos]
        pos += 1
        if pos + length > len(rdata):
            raise ValueError("character-string runs past the record")
        parts.append(rdata[pos : pos + length])
        pos += length
    return b"".join(parts).decode("utf-8", "replace")


def parse_txt_response(packet: bytes, qid: int, name: str) -> TxtResponse:
    """Parse a response to :func:`encode_txt_query`.

    Raises:
        ValueError: If the packet is malformed or does not answer this query.
    """
    if len(packet) < HEADER_LEN:
        raise ValueError("response is shorter than a DNS header")
    rid, flags, qdcount, ancount, _ns, _ar = struct.unpack("!HHHHHH", packet[:HEADER_LEN])
    if rid != qid:
        raise ValueError("response id does not match the query")
    if not flags & FLAG_QR or flags & OPCODE_MASK:
        raise ValueError("not a standard query response")
    if qdcount != 1:
        raise ValueError("response does not echo exactly one question")
    qname, pos = _read_name(packet, HEADER_LEN)
    if pos + 4 > len(packet):
        raise ValueError("question runs past the packet")
    qtype, qclass = struct.unpack("!HH", packet[pos : pos + 4])
    pos += 4
    owner = name.rstrip(".").lower()
    if qname != owner or qtype != TXT_TYPE or qclass != CLASS_IN:
        raise ValueError("response question does not match the query")
    values: set[str] = set()
    for _ in range(ancount):
        rname, pos = _read_name(packet, pos)
        if pos + 10 > len(packet):
            raise ValueError("record runs past the packet")
        rtype, rclass, _ttl, rdlength = struct.unpack("!HHIH", packet[pos : pos + 10])
        pos += 10
        if pos + rdlength > len(packet):
            raise ValueError("rdlength runs past the packet")
        if rtype == TXT_TYPE and rclass == CLASS_IN and rname == owner:
            values.add(_txt_value(packet[pos : pos + rdlength]))
        pos += rdlength
    return TxtResponse(
        rcode=flags & RCODE_MASK,
        authoritative=bool(flags & FLAG_AA),
        truncated=bool(flags & FLAG_TC),
        values=frozenset(values),
    )


def _family(address: str) -> socket.AddressFamily:
    return socket.AF_INET6 if ":" in address else socket.AF_INET


def udp_exchange(address: str, query: bytes, timeout: float) -> bytes:
    """Send ``query`` over UDP to ``address`` port 53 and return the first response."""
    with socket.socket(_family(address), socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(query, (address, DNS_PORT))
        data, _peer = sock.recvfrom(UDP_BUFFER)
        return data


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("connection closed before the full DNS message arrived")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def tcp_exchange_on(sock: socket.socket, query: bytes) -> bytes:
    """Run one length-prefixed DNS exchange on a connected socket."""
    sock.sendall(struct.pack("!H", len(query)) + query)
    (length,) = struct.unpack("!H", _recv_exact(sock, 2))
    return _recv_exact(sock, length)


def tcp_exchange(address: str, query: bytes, timeout: float) -> bytes:
    """Send ``query`` over TCP to ``address`` port 53 and return the response."""
    with socket.socket(_family(address), socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect((address, DNS_PORT))
        return tcp_exchange_on(sock, query)


def query_txt(
    address: str,
    name: str,
    qid: int,
    timeout: float,
    *,
    udp: Exchange = udp_exchange,
    tcp: Exchange = tcp_exchange,
) -> TxtResponse:
    """Ask one nameserver address for the TXT records of ``name``; retry over TCP on TC.

    Raises:
        OSError: On a socket failure or timeout.
        ValueError: If the answer is malformed, or still truncated over TCP.
    """
    query = encode_txt_query(name, qid)
    response = parse_txt_response(udp(address, query, timeout), qid, name)
    if not response.truncated:
        return response
    response = parse_txt_response(tcp(address, query, timeout), qid, name)
    if response.truncated:
        raise ValueError("TCP answer is truncated")
    return response
