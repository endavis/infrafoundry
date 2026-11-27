"""Key generation and certificate parsing, on ``cryptography``."""

from __future__ import annotations

import hashlib
import re

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from infrafoundry.core.certs.models import CertificateError, CertInfo

_CERT_RE = re.compile(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", re.DOTALL)


def generate_key(key_type: str) -> str:
    """Generate a private key and return it as an unencrypted PKCS#8 PEM.

    Args:
        key_type: ``ec-p256`` or ``rsa-2048``.

    Raises:
        CertificateError: If ``key_type`` is unknown.
    """
    key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey
    if key_type == "ec-p256":
        key = ec.generate_private_key(ec.SECP256R1())
    elif key_type == "rsa-2048":
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    else:
        raise CertificateError(f"unknown key type '{key_type}'")
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")


def split_fullchain(fullchain_pem: str) -> tuple[str, str]:
    """Split a full chain into the leaf certificate and the rest.

    Returns:
        ``(leaf PEM, chain PEM)``; the chain is empty when only the leaf is present.

    Raises:
        CertificateError: If the text holds no certificate.
    """
    certs = _CERT_RE.findall(fullchain_pem)
    if not certs:
        raise CertificateError("the ACME server returned no certificate")
    return certs[0] + "\n", "\n".join(certs[1:]) + ("\n" if len(certs) > 1 else "")


def describe(cert_pem: str) -> CertInfo:
    """Read validity, serial, SHA-256 fingerprint and names from a certificate PEM.

    Raises:
        CertificateError: If the text is not a certificate.
    """
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise CertificateError("the stored certificate is not a valid PEM certificate") from exc
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        names = tuple(san.value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        names = ()
    return CertInfo(
        not_before=cert.not_valid_before_utc,
        not_after=cert.not_valid_after_utc,
        serial=format(cert.serial_number, "x"),
        sha256=hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest(),
        names=names,
    )


def der_sha256(der: bytes) -> str:
    """Return the SHA-256 hex digest of a DER certificate."""
    return hashlib.sha256(der).hexdigest()
