"""Key generation and certificate parsing."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from infrafoundry.core.certs.keys import describe, generate_key, split_fullchain
from infrafoundry.core.certs.models import CertificateError

from .fakes import NOW, TestCa

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("key_type", "kind"), [("ec-p256", ec.EllipticCurvePrivateKey), ("rsa-2048", rsa.RSAPrivateKey)]
)
def test_generate_key_makes_the_requested_type(key_type: str, kind: type) -> None:
    pem = generate_key(key_type)
    assert isinstance(serialization.load_pem_private_key(pem.encode(), password=None), kind)


def test_generate_key_rejects_an_unknown_type() -> None:
    with pytest.raises(CertificateError):
        generate_key("dsa")


def test_split_and_describe_round_trip() -> None:
    ca = TestCa()
    chain = ca.sign(generate_key("ec-p256"), ["*.example.com", "example.com"], days=60)
    leaf, rest = split_fullchain(chain)
    assert leaf.count("BEGIN CERTIFICATE") == 1
    assert rest.count("BEGIN CERTIFICATE") == 1
    info = describe(leaf)
    assert info.names == ("*.example.com", "example.com")
    assert (info.not_after - NOW).days == 60
    assert len(info.sha256) == 64


def test_split_a_leaf_only_chain_has_an_empty_remainder() -> None:
    leaf, rest = split_fullchain(
        split_fullchain(TestCa().sign(generate_key("ec-p256"), ["a.example.com"]))[0]
    )
    assert leaf
    assert rest == ""


def test_split_rejects_text_without_a_certificate() -> None:
    with pytest.raises(CertificateError):
        split_fullchain("nothing here")


def test_describe_rejects_garbage_without_echoing_it() -> None:
    with pytest.raises(CertificateError) as caught:
        describe("SENTINEL-GARBAGE")
    assert "SENTINEL" not in str(caught.value)
