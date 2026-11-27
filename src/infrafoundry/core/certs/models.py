"""Constants, value objects and exceptions shared by the certificate modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from infrafoundry.core.exceptions import InfraFoundryError

PROVIDER_NAME = "acme"
CERTIFICATE_TYPE = "certificate"

#: Reserved key under a package's secrets ``variables:`` holding issued certificates.
CERTS_VARIABLE = "acme_certificates"

LETSENCRYPT_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"
LETSENCRYPT_PRODUCTION = "https://acme-v02.api.letsencrypt.org/directory"
DIRECTORIES = {"staging": LETSENCRYPT_STAGING, "production": LETSENCRYPT_PRODUCTION}
DEFAULT_DIRECTORY = "staging"

KEY_TYPES = ("ec-p256", "rsa-2048")
DEFAULT_KEY_TYPE = "ec-p256"
DEFAULT_RENEW_BEFORE_DAYS = 30
MAX_NAMES = 100

DEFAULT_PROPAGATION_TIMEOUT = 180
DEFAULT_PROPAGATION_INTERVAL = 5
DEFAULT_DOH_URLS = (
    "https://cloudflare-dns.com/dns-query",
    "https://dns.google/resolve",
)

#: Comment carried by every TXT record InfraFoundry creates, followed by the certificate name.
RECORD_COMMENT = "infrafoundry-acme"


class CertificateError(InfraFoundryError):
    """Base class for certificate errors. Messages never carry a key or a token."""


class CertificateSchemaError(CertificateError):
    """A certificate declaration or the ACME settings are invalid."""


class AcmeError(CertificateError):
    """The ACME server refused or failed an order."""


class DnsError(CertificateError):
    """A DNS-01 record could not be created, seen or removed."""


class CertificateStoreError(CertificateError):
    """The encrypted certificate store could not be read or written."""


class CertificateInstallError(CertificateError):
    """A certificate could not be installed on, or was not served by, its target."""


@dataclass(frozen=True)
class AcmeSettings:
    """``provider_settings.acme`` with its secrets resolved. Secrets are hidden from ``repr``."""

    directory: str
    directory_id: str
    agree_tos: bool
    email: str | None
    renew_before_days: int
    api_token: str = field(repr=False)
    zone_id: str = field(repr=False)
    propagation_timeout: int = DEFAULT_PROPAGATION_TIMEOUT
    propagation_interval: int = DEFAULT_PROPAGATION_INTERVAL
    doh_urls: tuple[str, ...] = DEFAULT_DOH_URLS


@dataclass(frozen=True)
class CertificateSpec:
    """One declared certificate (a ``certificate`` resource)."""

    name: str
    names: tuple[str, ...]
    key_type: str
    renew_before_days: int | None
    target: dict[str, Any]


@dataclass(frozen=True)
class CertInfo:
    """What is read back from a certificate PEM."""

    not_before: datetime
    not_after: datetime
    serial: str
    sha256: str
    names: tuple[str, ...]


@dataclass(frozen=True)
class IssuedCertificate:
    """A freshly issued certificate. ``key_pem`` is hidden from ``repr``."""

    cert_pem: str
    chain_pem: str
    key_pem: str = field(repr=False)
    info: CertInfo
    key_type: str
    directory: str
    issued_at: datetime


@dataclass(frozen=True)
class AccountRecord:
    """The ACME account of one environment and directory. The key is hidden from ``repr``."""

    key_pem: str = field(repr=False)
    uri: str | None = None
