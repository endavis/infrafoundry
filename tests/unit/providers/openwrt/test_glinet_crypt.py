"""Pure-Python crypt against published vectors and the openssl CLI (#1655)."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from infrafoundry.providers.openwrt.glinet.crypt import UnsupportedCryptError, crypt

pytestmark = pytest.mark.unit

# Drepper, "Unix crypt using SHA-256 and SHA-512", test vectors.
DREPPER = [
    (
        "$5$saltstring",
        "Hello world!",
        "$5$saltstring$5B8vYYiY.CVt1RlTTf8KbXBH3hsxY/GNooZaBBGWEc5",
    ),
    (
        "$5$rounds=10000$saltstringsaltstring",
        "Hello world!",
        "$5$rounds=10000$saltstringsaltst$3xv.VbSHBb41AL9AvLeujZkZRBAwqFMz2.opqey6IcA",
    ),
    (
        "$5$rounds=77777$short",
        "we have a short salt string but not a short password",
        "$5$rounds=77777$short$JiO1O3ZpDAxGJeaDIuqCoEFysAe1mZNJRs3pw0KQRd/",
    ),
    (
        "$6$saltstring",
        "Hello world!",
        "$6$saltstring$svn8UoSVapNtMuq1ukKS4tPQd8iKwSMHWjl/O817G3uBnIFNjnQJu"
        "esI68u4OTLiBFdcbYEdFCoEOfaS35inz1",
    ),
    (
        "$6$rounds=10000$saltstringsaltstring",
        "Hello world!",
        "$6$rounds=10000$saltstringsaltst$OW1/O6BYHV6BcXZu8QVeXbDWra3Oeqh0sbHbbMCVNSnCM/"
        "UrjmM0Dp8vOuZeHBy/YTBmSK6H9qs/y3RnOaw5v.",
    ),
]


@pytest.mark.parametrize(("setting", "password", "expected"), DREPPER)
def test_drepper_vectors(setting: str, password: str, expected: str) -> None:
    assert crypt(password, setting) == expected


def test_md5_crypt_vector() -> None:
    assert crypt("password", "$1$5pZSV9va") == "$1$5pZSV9va$azfrPr6af3Fc7dLblQXVa0"


def test_trailing_hash_in_setting_is_ignored() -> None:
    assert crypt("Hello world!", "$5$saltstring$ignored") == DREPPER[0][2]


def test_salt_is_truncated() -> None:
    assert crypt("x", "$6$" + "a" * 40) == crypt("x", "$6$" + "a" * 16)
    assert crypt("x", "$1$" + "a" * 20) == crypt("x", "$1$" + "a" * 8)


def test_rounds_are_clamped() -> None:
    assert crypt("x", "$5$rounds=1$salt").startswith("$5$rounds=1000$salt$")
    assert crypt("x", "$5$rounds=1000$salt") == crypt("x", "$5$rounds=1$salt")


@pytest.mark.parametrize("setting", ["$2b$12$abcdefghijklmnopqrstuv", "garbage", "", "$7$salt"])
def test_unsupported_setting_raises_without_leaking(setting: str) -> None:
    with pytest.raises(UnsupportedCryptError) as exc:
        crypt("hunter2-secret", setting)
    assert "hunter2-secret" not in str(exc.value)


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl CLI not available")
@pytest.mark.parametrize("flag", ["-1", "-5", "-6"])
@pytest.mark.parametrize(
    ("password", "salt"),
    [("s3cret-pass", "abcdefgh"), ("a", "Zz09./-x"), ("long" * 20, "salty")],
)
def test_matches_openssl(flag: str, password: str, salt: str) -> None:
    ident = {"-1": "$1$", "-5": "$5$", "-6": "$6$"}[flag]
    expected = subprocess.run(
        ["openssl", "passwd", flag, "-salt", salt, password],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert crypt(password, ident + salt) == expected
