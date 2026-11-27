"""``LibAcmeClient`` against a mocked ``acme`` library (no network)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from acme import challenges, errors

from infrafoundry.core.certs.acme_client import LibAcmeClient
from infrafoundry.core.certs.keys import generate_key
from infrafoundry.core.certs.models import AcmeError

pytestmark = pytest.mark.unit

URL = "https://ca.example.test/dir"
ACCOUNT = "https://ca.example.test/acct/9"


@pytest.fixture
def lib() -> Iterator[Any]:
    """Patch ``ClientNetwork`` and ``ClientV2``; yield the ``ClientV2`` instance mock."""
    with patch("acme.client.ClientNetwork"), patch("acme.client.ClientV2") as client_cls:
        client_cls.get_directory.return_value = MagicMock()
        instance = client_cls.return_value
        instance.new_account.return_value = SimpleNamespace(uri=ACCOUNT)
        instance.query_registration.return_value = SimpleNamespace(uri=ACCOUNT)
        yield instance


def _order(*domains: str, dns: bool = True) -> Any:
    offered = [SimpleNamespace(chall=challenges.HTTP01(token=b"x" * 32))]
    if dns:
        offered.append(SimpleNamespace(chall=challenges.DNS01(token=b"y" * 32)))
    authorizations = [
        SimpleNamespace(
            body=SimpleNamespace(identifier=SimpleNamespace(value=d), challenges=offered)
        )
        for d in domains
    ]
    return SimpleNamespace(authorizations=authorizations, fullchain_pem="CHAIN")


def _ready(lib: Any, *domains: str) -> tuple[LibAcmeClient, Any]:
    client = LibAcmeClient(URL)
    client.ensure_account(generate_key("ec-p256"), None, None)
    lib.new_order.return_value = _order(*domains)
    return client, client.new_order(list(domains), generate_key("ec-p256"))


def test_a_new_account_is_registered_with_the_terms_agreed(lib: Any) -> None:
    uri = LibAcmeClient(URL).ensure_account(generate_key("ec-p256"), None, "admin@example.com")
    assert uri == ACCOUNT
    registration = lib.new_account.call_args.args[0]
    assert registration.terms_of_service_agreed is True
    assert registration.emails == ("admin@example.com",)


def test_an_existing_account_is_looked_up_by_uri(lib: Any) -> None:
    uri = LibAcmeClient(URL).ensure_account(generate_key("ec-p256"), ACCOUNT, None)
    assert uri == ACCOUNT
    lib.new_account.assert_not_called()
    assert lib.query_registration.call_args.args[0].uri == ACCOUNT


def test_a_conflict_falls_back_to_the_existing_account(lib: Any) -> None:
    lib.new_account.side_effect = errors.ConflictError("https://ca.example.test/acct/3")
    LibAcmeClient(URL).ensure_account(generate_key("ec-p256"), None, None)
    assert lib.query_registration.call_args.args[0].uri == "https://ca.example.test/acct/3"


def test_an_account_failure_is_an_acme_error_without_the_key(lib: Any) -> None:
    key = generate_key("ec-p256")
    lib.new_account.side_effect = errors.Error("rejected")
    with pytest.raises(AcmeError) as caught:
        LibAcmeClient(URL).ensure_account(key, None, None)
    assert "rejected" in str(caught.value)
    assert "PRIVATE" not in str(caught.value)
    assert key not in str(caught.value)


def test_new_order_collects_the_dns01_challenges(lib: Any) -> None:
    client = LibAcmeClient(URL)
    client.ensure_account(generate_key("ec-p256"), None, None)
    lib.new_order.return_value = _order("example.com")
    order = client.new_order(["*.example.com", "example.com"], generate_key("ec-p256"))
    assert len(order.challenges) == 1
    challenge = order.challenges[0]
    assert challenge.record_name == "_acme-challenge.example.com"
    assert challenge.identifier == "example.com"
    assert challenge.record_value
    csr = lib.new_order.call_args.args[0]
    assert csr.startswith(b"-----BEGIN CERTIFICATE REQUEST")
    assert b"PRIVATE" not in csr


def test_new_order_needs_an_account_first() -> None:
    with pytest.raises(AcmeError, match="account"):
        LibAcmeClient(URL).new_order(["a.example.com"], "k")


def test_a_server_without_dns01_is_reported(lib: Any) -> None:
    client = LibAcmeClient(URL)
    client.ensure_account(generate_key("ec-p256"), None, None)
    lib.new_order.return_value = _order("example.com", dns=False)
    with pytest.raises(AcmeError, match="DNS-01"):
        client.new_order(["example.com"], generate_key("ec-p256"))


def test_answer_and_finalize(lib: Any) -> None:
    client, order = _ready(lib, "example.com")
    client.answer(order, order.challenges[0])
    assert lib.answer_challenge.called
    lib.poll_and_finalize.return_value = SimpleNamespace(fullchain_pem="CHAIN")
    assert client.finalize(order, 60) == "CHAIN"


def test_finalize_passes_a_naive_local_deadline(lib: Any) -> None:
    """acme compares the deadline with naive ``datetime.now()``; an aware one raises."""
    client, order = _ready(lib, "example.com")

    def poll_and_finalize(_order: Any, deadline: datetime) -> Any:
        assert datetime.now() < deadline  # what acme does; TypeError if deadline is aware
        assert deadline < datetime.now() + timedelta(seconds=120)
        return SimpleNamespace(fullchain_pem="CHAIN")

    lib.poll_and_finalize.side_effect = poll_and_finalize
    assert client.finalize(order, 60) == "CHAIN"


def test_finalize_failure_is_an_acme_error(lib: Any) -> None:
    client, order = _ready(lib, "example.com")
    lib.poll_and_finalize.side_effect = errors.TimeoutError()
    with pytest.raises(AcmeError, match="finalization"):
        client.finalize(order, 1)
