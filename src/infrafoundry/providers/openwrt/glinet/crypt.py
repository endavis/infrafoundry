"""Pure-Python ``crypt(3)`` for the MD5, SHA-256 and SHA-512 schemes (ADR-0036).

The GL.iNet login challenge names one of these algorithms and a salt; the client must
reproduce the device's ``crypt`` output. The standard library's ``crypt`` module is
gone in Python 3.13 and no declared dependency provides these schemes, so they are
implemented here from the published algorithms (Drepper, "Unix crypt using SHA-256 and
SHA-512"; the FreeBSD/PHK MD5-crypt).
"""

from __future__ import annotations

import hashlib
import re

from infrafoundry.core.exceptions import InfraFoundryError

_ALPHABET = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
MIN_ROUNDS = 1000
MAX_ROUNDS = 999_999_999
DEFAULT_ROUNDS = 5000
MD5_SALT_MAX = 8
SHA_SALT_MAX = 16

_MD5_ORDER = ((0, 6, 12), (1, 7, 13), (2, 8, 14), (3, 9, 15), (4, 10, 5))
_SHA256_ORDER = (
    (0, 10, 20),
    (21, 1, 11),
    (12, 22, 2),
    (3, 13, 23),
    (24, 4, 14),
    (15, 25, 5),
    (6, 16, 26),
    (27, 7, 17),
    (18, 28, 8),
    (9, 19, 29),
)
_SHA512_ORDER = (
    (0, 21, 42),
    (22, 43, 1),
    (44, 2, 23),
    (3, 24, 45),
    (25, 46, 4),
    (47, 5, 26),
    (6, 27, 48),
    (28, 49, 7),
    (50, 8, 29),
    (9, 30, 51),
    (31, 52, 10),
    (53, 11, 32),
    (12, 33, 54),
    (34, 55, 13),
    (56, 14, 35),
    (15, 36, 57),
    (37, 58, 16),
    (59, 17, 38),
    (18, 39, 60),
    (40, 61, 19),
    (62, 20, 41),
)
_SETTING = re.compile(r"^\$(?P<id>[156])\$(?:rounds=(?P<rounds>\d+)\$)?(?P<salt>[^$]*)")


class UnsupportedCryptError(InfraFoundryError):
    """The crypt setting names an algorithm this module does not implement."""


def _to64(value: int, count: int) -> str:
    out = []
    for _ in range(count):
        out.append(_ALPHABET[value & 0x3F])
        value >>= 6
    return "".join(out)


def _encode(digest: bytes, order: tuple[tuple[int, int, int], ...]) -> str:
    return "".join(_to64((digest[a] << 16) | (digest[b] << 8) | digest[c], 4) for a, b, c in order)


def _md5_crypt(password: bytes, salt: bytes) -> str:
    salt = salt[:MD5_SALT_MAX]
    alt = hashlib.md5(password + salt + password, usedforsecurity=False).digest()
    ctx = hashlib.md5(password + b"$1$" + salt, usedforsecurity=False)
    remaining = len(password)
    while remaining > 0:
        ctx.update(alt[: min(16, remaining)])
        remaining -= 16
    bit = len(password)
    while bit:
        ctx.update(b"\x00" if bit & 1 else password[:1])
        bit >>= 1
    final = ctx.digest()
    for i in range(1000):
        step = hashlib.md5(usedforsecurity=False)
        step.update(password if i & 1 else final)
        if i % 3:
            step.update(salt)
        if i % 7:
            step.update(password)
        step.update(final if i & 1 else password)
        final = step.digest()
    return "$1$" + salt.decode() + "$" + _encode(final, _MD5_ORDER) + _to64(final[11], 2)


def _sha_crypt(password: bytes, salt: bytes, rounds: int, explicit: bool, wide: bool) -> str:
    hasher = hashlib.sha512 if wide else hashlib.sha256
    size = 64 if wide else 32
    salt = salt[:SHA_SALT_MAX]
    digest_b = hasher(password + salt + password).digest()
    ctx = hasher(password + salt)
    count = len(password)
    while count > size:
        ctx.update(digest_b)
        count -= size
    ctx.update(digest_b[:count])
    bit = len(password)
    while bit > 0:
        ctx.update(digest_b if bit & 1 else password)
        bit >>= 1
    digest_a = ctx.digest()
    dp = hasher(password * len(password)).digest()
    p_bytes = (dp * (len(password) // size + 1))[: len(password)]
    ds = hasher(salt * (16 + digest_a[0])).digest()
    s_bytes = (ds * (len(salt) // size + 1))[: len(salt)]
    for i in range(rounds):
        step = hasher()
        step.update(p_bytes if i & 1 else digest_a)
        if i % 3:
            step.update(s_bytes)
        if i % 7:
            step.update(p_bytes)
        step.update(digest_a if i & 1 else p_bytes)
        digest_a = step.digest()
    if wide:
        body = _encode(digest_a, _SHA512_ORDER) + _to64(digest_a[63], 2)
    else:
        body = _encode(digest_a, _SHA256_ORDER) + _to64((digest_a[31] << 8) | digest_a[30], 3)
    prefix = "$6$" if wide else "$5$"
    if explicit:
        prefix += f"rounds={rounds}$"
    return prefix + salt.decode() + "$" + body


def crypt(password: str, setting: str) -> str:
    """Return ``crypt(3)`` of ``password`` for an MD5, SHA-256 or SHA-512 ``setting``.

    Args:
        password: The clear-text password.
        setting: ``$1$<salt>``, ``$5$[rounds=N$]<salt>`` or ``$6$[rounds=N$]<salt>``; any
            trailing ``$hash`` is ignored. Salts are truncated (8 characters for MD5, 16
            for SHA) and ``rounds`` is clamped to 1000-999999999.

    Returns:
        The full crypt string (``$id$[rounds=N$]salt$hash``).

    Raises:
        UnsupportedCryptError: If the setting is not one of the three schemes. The
            message never contains the password.
    """
    match = _SETTING.match(setting)
    if match is None:
        raise UnsupportedCryptError("unsupported crypt algorithm in the login challenge")
    scheme = match.group("id")
    salt = match.group("salt").encode()
    secret = password.encode()
    if scheme == "1":
        return _md5_crypt(secret, salt)
    explicit = match.group("rounds") is not None
    rounds = int(match.group("rounds")) if explicit else DEFAULT_ROUNDS
    rounds = max(MIN_ROUNDS, min(MAX_ROUNDS, rounds))
    return _sha_crypt(secret, salt, rounds, explicit, wide=scheme == "6")
