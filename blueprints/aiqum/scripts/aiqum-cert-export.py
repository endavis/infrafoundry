#!/usr/bin/env python3
"""Export the HTTPS certificate AIQUM serves, for ontap-cluster to trust (#1648).

Stdlib only. The same file runs in two places:

* On the AIQUM VM (Python 3.9, piped over the pinned SSH channel as
  ``python3 - served-cert 127.0.0.1 443``): prints the PEM of the certificate
  served on that address.
* On the host running ``aiqum-post-terraform.sh`` (``export``): takes that PEM,
  fetches the certificate served at ``<host>:443`` over the network, and writes
  the PEM to ``--out`` only when the two match.

The certificate is fetched without verification on purpose: it is self-signed
and the point is to learn it. The pinned SSH channel supplies the trust, and the
match between both copies shows the network path reaches the same AIQUM.

Usage:
    aiqum-cert-export.py served-cert HOST PORT
    aiqum-cert-export.py export --pem-file F --host H [--port 443] --out PATH
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import os
import socket
import ssl
import sys
import tempfile
from pathlib import Path


class ExportError(Exception):
    """A certificate could not be fetched, compared or written."""


def fetch_der(host: str, port: int, timeout: float = 30) -> bytes:
    """Return the DER certificate served at ``host:port`` without verifying it.

    Args:
        host: Address to connect to.
        port: TCP port.
        timeout: Connect and handshake timeout in seconds.

    Returns:
        The DER-encoded leaf certificate.

    Raises:
        ExportError: If the handshake fails or no certificate is presented.
    """
    ctx = client_context()
    try:
        with (
            socket.create_connection((host, port), timeout=timeout) as sock,
            ctx.wrap_socket(sock, server_hostname=host) as tls,
        ):
            der = tls.getpeercert(binary_form=True)
    except (OSError, ssl.SSLError) as exc:
        raise ExportError(f"cannot fetch the certificate from {host}:{port}: {exc}") from None
    if not der:
        raise ExportError(f"{host}:{port} presented no certificate")
    return der


def client_context() -> ssl.SSLContext:
    """Return the TLS client context used to read the served certificate.

    Certificate verification is off on purpose: the certificate is self-signed and is
    what is being learned; it is trusted only after the two copies are compared.
    Protocols older than TLS 1.2 are refused.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def parse_pem(text: str) -> bytes:
    """Return the DER bytes of the single CERTIFICATE block in ``text``.

    Raises:
        ExportError: If ``text`` does not hold exactly one certificate.
    """
    begin = "-----BEGIN CERTIFICATE-----"
    count = text.count(begin)
    if count != 1:
        raise ExportError(f"expected exactly one PEM certificate, found {count}")
    try:
        return ssl.PEM_cert_to_DER_cert(text.strip())
    except ValueError as exc:
        raise ExportError(f"invalid PEM certificate: {exc}") from None


def fingerprint(der: bytes) -> str:
    """Return the SHA-256 of ``der`` as uppercase hex separated by colons."""
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def resolve_out(path: str) -> Path:
    """Expand ``~`` and require an absolute output path.

    Raises:
        ExportError: If ``path`` is empty or not absolute.
    """
    if not path.strip():
        raise ExportError("output path is empty")
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        raise ExportError(f"output path must be absolute (got {path!r})")
    return resolved


def write_atomic(path: Path, text: str) -> None:
    """Write ``text`` plus a newline to ``path`` atomically with mode 0644."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="ascii") as fh:
            fh.write(text.rstrip("\n") + "\n")
            fh.flush()
            os.fchmod(fh.fileno(), 0o644)
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def export(pem_text: str, host: str, port: int, out: Path) -> Path:
    """Write the served certificate to ``out`` when both copies match.

    Args:
        pem_text: PEM of the certificate the VM serves on itself.
        host: Address whose network-served certificate must match.
        port: TCP port.
        out: Destination file.

    Returns:
        ``out``.

    Raises:
        ExportError: If the copies differ or either cannot be read.
    """
    vm_der = parse_pem(pem_text)
    net_der = fetch_der(host, port)
    if vm_der != net_der:
        raise ExportError(
            f"the certificate served at {host}:{port} differs from the one AIQUM serves on "
            f"the VM (VM {fingerprint(vm_der)}, network {fingerprint(net_der)}); "
            "refusing to export"
        )
    write_atomic(out, ssl.DER_cert_to_PEM_cert(vm_der))
    return out


def main(argv: list[str] | None = None) -> int:
    """Run the CLI; return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    sub = parser.add_subparsers(dest="command", required=True)
    served = sub.add_parser("served-cert", help="print the PEM served at HOST PORT")
    served.add_argument("host")
    served.add_argument("port", type=int)
    exp = sub.add_parser("export", help="write the PEM when the VM and network copies match")
    exp.add_argument("--pem-file", required=True)
    exp.add_argument("--host", required=True)
    exp.add_argument("--port", type=int, default=443)
    exp.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "served-cert":
            sys.stdout.write(ssl.DER_cert_to_PEM_cert(fetch_der(args.host, args.port)))
            return 0
        out = resolve_out(args.out)
        pem_text = Path(args.pem_file).read_text(encoding="ascii")
        export(pem_text, args.host, args.port, out)
        print(f"  Exported AIQUM HTTPS certificate to {out}")
        print(f"  SHA-256: {fingerprint(parse_pem(pem_text))}")
        return 0
    except (ExportError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
