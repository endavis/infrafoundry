"""Order one certificate: DNS-01 records, propagation, validation, finalization, cleanup."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from infrafoundry.core.certs.acme_client import AcmeClient
from infrafoundry.core.certs.dns_cloudflare import DnsProvider
from infrafoundry.core.certs.keys import describe, generate_key, split_fullchain
from infrafoundry.core.certs.models import (
    RECORD_COMMENT,
    AccountRecord,
    AcmeSettings,
    CertificateSpec,
    DnsError,
    IssuedCertificate,
)
from infrafoundry.core.certs.propagation import Resolver, wait_for_txt

logger = logging.getLogger(__name__)

ACCOUNT_KEY_TYPE = "ec-p256"
FINALIZE_TIMEOUT = 180


class CertificateIssuer:
    """Issues certificates; every external piece is injected."""

    def __init__(
        self,
        acme: AcmeClient,
        dns: DnsProvider,
        resolvers: Sequence[Resolver],
        settings: AcmeSettings,
        *,
        extra_resolvers: Sequence[Resolver] = (),
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        """Initialize the issuer.

        Args:
            acme: ACME client.
            dns: DNS host holding the zone.
            resolvers: Resolvers that must see the TXT records before the CA is asked.
            settings: The ACME settings.
            extra_resolvers: Resolvers polled only after every primary resolver sees every
                value, each stage with the full propagation timeout.
            sleep: Sleep function for the propagation poll.
            monotonic: Clock for the propagation poll.
            now: Wall clock; replaced in tests.
        """
        self._acme = acme
        self._dns = dns
        self._resolvers = resolvers
        self._extra_resolvers = extra_resolvers
        self._settings = settings
        self._sleep = sleep
        self._monotonic = monotonic
        self._now = now or (lambda: datetime.now(UTC))

    def ensure_account(self, record: AccountRecord | None) -> AccountRecord:
        """Return the account record, generating a key and registering when needed.

        Args:
            record: The stored account, or ``None`` for a first run.

        Returns:
            The stored record when nothing changed, else a new one to persist.
        """
        key_pem = record.key_pem if record else generate_key(ACCOUNT_KEY_TYPE)
        uri = self._acme.ensure_account(
            key_pem, record.uri if record else None, self._settings.email
        )
        if record is not None and record.uri == uri:
            return record
        return AccountRecord(key_pem=key_pem, uri=uri)

    def issue(self, spec: CertificateSpec) -> IssuedCertificate:
        """Order, validate and download one certificate.

        Every TXT record created is deleted again, whatever happens.

        Raises:
            AcmeError: If the CA refuses.
            DnsError: If a record cannot be created or seen in time.
        """
        self._dns.purge_stale()
        key_pem = generate_key(spec.key_type)
        order = self._acme.new_order(spec.names, key_pem)
        comment = f"{RECORD_COMMENT} {spec.name}"
        created: list[str] = []
        try:
            values: dict[str, set[str]] = {}
            for challenge in order.challenges:
                record_id = self._dns.add_txt(
                    challenge.record_name, challenge.record_value, comment
                )
                created.append(record_id)
                values.setdefault(challenge.record_name, set()).add(challenge.record_value)
            for name, expected in values.items():
                for stage in (self._resolvers, self._extra_resolvers):
                    if not stage:
                        continue
                    wait_for_txt(
                        name,
                        expected,
                        stage,
                        timeout=self._settings.propagation_timeout,
                        interval=self._settings.propagation_interval,
                        sleep=self._sleep,
                        monotonic=self._monotonic,
                    )
            for challenge in order.challenges:
                self._acme.answer(order, challenge)
            fullchain = self._acme.finalize(order, FINALIZE_TIMEOUT)
        finally:
            self._cleanup(created)
        cert_pem, chain_pem = split_fullchain(fullchain)
        return IssuedCertificate(
            cert_pem=cert_pem,
            chain_pem=chain_pem,
            key_pem=key_pem,
            info=describe(cert_pem),
            key_type=spec.key_type,
            directory=self._settings.directory,
            issued_at=self._now(),
        )

    def _cleanup(self, record_ids: list[str]) -> None:
        for record_id in record_ids:
            try:
                self._dns.delete(record_id)
            except DnsError as exc:
                # Left for the next order's purge of stale records; never masks the real error.
                logger.warning("could not delete a DNS-01 record: %s", exc)
