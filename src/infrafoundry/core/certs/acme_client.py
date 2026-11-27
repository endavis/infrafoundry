"""The ACME seam: the :class:`AcmeClient` protocol and its ``acme``-library implementation.

This is the only module that imports ``acme`` or ``josepy``, and it does so lazily. Tests
replace the whole client with a fake that issues real certificates from a test CA.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from infrafoundry.core.certs.models import AcmeError

USER_AGENT = "infrafoundry-acme"
HTTP_TIMEOUT = 45


@dataclass(frozen=True)
class DnsChallenge:
    """One DNS-01 challenge: the TXT record to publish.

    ``handle`` is the client's own object for answering the challenge.
    """

    identifier: str
    record_name: str
    record_value: str
    handle: Any = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class AcmeOrder:
    """An order with its DNS-01 challenges. ``handle`` is the client's own order object."""

    challenges: tuple[DnsChallenge, ...]
    handle: Any = field(default=None, repr=False, compare=False)


class AcmeClient(Protocol):
    """What the issuer needs from an ACME client."""

    def ensure_account(self, key_pem: str, uri: str | None, email: str | None) -> str:
        """Register the account (or look it up) and return its URI."""
        ...

    def new_order(self, names: Sequence[str], key_pem: str) -> AcmeOrder:
        """Open an order for ``names``, with a CSR signed by the certificate key."""
        ...

    def answer(self, order: AcmeOrder, challenge: DnsChallenge) -> None:
        """Tell the server the challenge's record is published."""
        ...

    def finalize(self, order: AcmeOrder, timeout: float) -> str:
        """Wait for validation, finalize and return the full chain PEM."""
        ...


class LibAcmeClient:
    """:class:`AcmeClient` on the ``acme`` library, for one directory."""

    def __init__(
        self,
        directory_url: str,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            directory_url: The ACME directory URL.
            now: Clock; replaced in tests.
        """
        self._directory_url = directory_url
        self._now = now or (lambda: datetime.now(UTC))
        self._client: Any = None
        self._account_key: Any = None

    def ensure_account(self, key_pem: str, uri: str | None, email: str | None) -> str:
        """Register the account, or look up the existing one, and return its URI."""
        import josepy
        from acme import client, errors, messages

        try:
            key = josepy.JWK.load(key_pem.encode("ascii"))
            alg = josepy.ES256 if isinstance(key, josepy.JWKEC) else josepy.RS256
            net = client.ClientNetwork(key, alg=alg, user_agent=USER_AGENT, timeout=HTTP_TIMEOUT)
            directory = client.ClientV2.get_directory(self._directory_url, net)
            acme = client.ClientV2(directory, net)
            self._account_key = key
            self._client = acme
            if uri:
                regr = messages.RegistrationResource(uri=uri, body=messages.Registration())
                return str(acme.query_registration(regr).uri)
            registration = messages.NewRegistration.from_data(
                email=email, terms_of_service_agreed=True
            )
            try:
                return str(acme.new_account(registration).uri)
            except errors.ConflictError as exc:
                regr = messages.RegistrationResource(uri=exc.location, body=messages.Registration())
                return str(acme.query_registration(regr).uri)
        except (errors.Error, ValueError, OSError) as exc:
            raise AcmeError(f"ACME account setup failed: {_describe(exc)}") from None

    def new_order(self, names: Sequence[str], key_pem: str) -> AcmeOrder:
        """Open an order and collect its DNS-01 challenges."""
        from acme import challenges, crypto_util, errors

        if self._client is None:
            raise AcmeError("the ACME account is not set up")
        try:
            csr = crypto_util.make_csr(key_pem.encode("ascii"), list(names))
            order = self._client.new_order(csr)
            found: list[DnsChallenge] = []
            for authz in order.authorizations:
                domain = str(authz.body.identifier.value)
                for challb in authz.body.challenges:
                    if isinstance(challb.chall, challenges.DNS01):
                        _, validation = challb.chall.response_and_validation(self._account_key)
                        found.append(
                            DnsChallenge(
                                identifier=domain,
                                record_name=challb.chall.validation_domain_name(domain),
                                record_value=validation,
                                handle=challb,
                            )
                        )
                        break
                else:
                    raise AcmeError(f"the server offers no DNS-01 challenge for '{domain}'")
        except (errors.Error, ValueError, OSError) as exc:
            raise AcmeError(f"ACME order failed: {_describe(exc)}") from None
        return AcmeOrder(tuple(found), order)

    def answer(self, order: AcmeOrder, challenge: DnsChallenge) -> None:
        """Answer one challenge."""
        from acme import errors

        challb = challenge.handle
        try:
            response, _ = challb.chall.response_and_validation(self._account_key)
            self._client.answer_challenge(challb, response)
        except (errors.Error, ValueError, OSError) as exc:
            raise AcmeError(f"ACME challenge answer failed: {_describe(exc)}") from None

    def finalize(self, order: AcmeOrder, timeout: float) -> str:
        """Poll the order, finalize it and return the full chain."""
        from acme import errors

        try:
            # acme compares the deadline with a naive local ``datetime.now()``; an aware
            # deadline raises TypeError, so convert it to naive local time.
            deadline = (self._now() + timedelta(seconds=timeout)).astimezone().replace(tzinfo=None)
            done = self._client.poll_and_finalize(order.handle, deadline)
        except (errors.Error, ValueError, OSError) as exc:
            raise AcmeError(f"ACME finalization failed: {_describe(exc)}") from None
        if not done.fullchain_pem:
            raise AcmeError("the ACME server returned no certificate")
        return str(done.fullchain_pem)


def _describe(exc: BaseException) -> str:
    """Return a bounded, key-free description of a library error."""
    text = " ".join(str(exc).split())
    return f"{exc.__class__.__name__}: {text[:300]}" if text else exc.__class__.__name__
