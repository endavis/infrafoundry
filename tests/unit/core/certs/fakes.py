"""Fakes for the certificate tests: a real test CA, ACME, DNS, resolvers, SSH and sops.

Every external piece of ``core/certs`` is injected, so nothing here touches a network.
Sentinel strings stand in for tokens; key material is checked for by its PEM armour.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from infrafoundry.core.certs.acme_client import AcmeOrder, DnsChallenge
from infrafoundry.core.certs.models import AcmeError, AcmeSettings, DnsError
from infrafoundry.core.provider import ResourceConfig

TOKEN = "cf-token-SENTINEL-0123456789"  # a fake
ZONE = "zone-id-SENTINEL-abcdef"
NOW = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
KEY_ARMOUR = "PRIVATE " + "KEY"


def settings(**over: Any) -> AcmeSettings:
    """Settings for tests; the Cloudflare values are sentinels."""
    values: dict[str, Any] = {
        "directory": "https://acme.example.test/directory",
        "directory_id": "staging",
        "agree_tos": True,
        "email": "admin@example.com",
        "renew_before_days": 30,
        "api_token": TOKEN,
        "zone_id": ZONE,
        "propagation_timeout": 30,
        "propagation_interval": 1,
        "doh_urls": ("https://doh-a.example.test/q", "https://doh-b.example.test/q"),
    }
    values.update(over)
    return AcmeSettings(**values)


class TestCa:
    """A throwaway CA that signs the certificates ``FakeAcme`` returns."""

    __test__ = False

    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
        self.cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(self.key.public_key())
            .serial_number(1)
            .not_valid_before(NOW - dt.timedelta(days=1))
            .not_valid_after(NOW + dt.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(self.key, hashes.SHA256())
        )

    def sign(
        self, key_pem: str, names: Sequence[str], *, days: int = 90, start: dt.datetime = NOW
    ) -> str:
        """Return a full chain PEM (leaf then CA) for the key and names."""
        leaf_key = serialization.load_pem_private_key(key_pem.encode(), password=None)
        public: Any = leaf_key.public_key()
        builder = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])]))
            .issuer_name(self.cert.subject)
            .public_key(public)
            .serial_number(x509.random_serial_number())
            .not_valid_before(start)
            .not_valid_after(start + dt.timedelta(days=days))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False
            )
        )
        leaf = builder.sign(self.key, hashes.SHA256())
        pem = leaf.public_bytes(serialization.Encoding.PEM)
        return (pem + self.cert.public_bytes(serialization.Encoding.PEM)).decode()


class FakeAcme:
    """An ``AcmeClient`` that issues real certificates from :class:`TestCa`."""

    def __init__(self, ca: TestCa | None = None, *, days: int = 90) -> None:
        self.ca = ca or TestCa()
        self.days = days
        self.calls: list[str] = []
        self.accounts: list[tuple[str, str | None, str | None]] = []
        self.orders: list[list[str]] = []
        self.answered: list[str] = []
        self.fail_on: str | None = None
        self.account_uri = "https://acme.example.test/acct/1"

    def _maybe_fail(self, step: str) -> None:
        if self.fail_on == step:
            raise AcmeError(f"{step} refused by the test CA")

    def ensure_account(self, key_pem: str, uri: str | None, email: str | None) -> str:
        self.calls.append("account")
        self.accounts.append((key_pem, uri, email))
        self._maybe_fail("account")
        return uri or self.account_uri

    def new_order(self, names: Sequence[str], key_pem: str) -> AcmeOrder:
        self.calls.append("new_order")
        self._maybe_fail("new_order")
        self.orders.append(list(names))
        challenges = tuple(
            DnsChallenge(
                identifier=n.removeprefix("*."),
                record_name=f"_acme-challenge.{n.removeprefix('*.')}",
                record_value=f"validation-{i}-{n.removeprefix('*.')}",
            )
            for i, n in enumerate(names)
        )
        return AcmeOrder(challenges, (list(names), key_pem))

    def answer(self, order: AcmeOrder, challenge: DnsChallenge) -> None:
        self.calls.append("answer")
        self._maybe_fail("answer")
        self.answered.append(challenge.record_value)

    def finalize(self, order: AcmeOrder, timeout: float) -> str:
        self.calls.append("finalize")
        self._maybe_fail("finalize")
        names, key_pem = order.handle
        return self.ca.sign(key_pem, names, days=self.days)


class FakeCloudflare:
    """A ``DnsProvider`` holding records in memory."""

    def __init__(self) -> None:
        self.records: dict[str, tuple[str, str, str]] = {}
        self.added: list[str] = []
        self.deleted: list[str] = []
        self.purged = 0
        self.fail_add_after: int | None = None
        self.fail_delete = False
        self._n = 0

    def add_txt(self, name: str, value: str, comment: str) -> str:
        if self.fail_add_after is not None and len(self.added) >= self.fail_add_after:
            raise DnsError("Cloudflare POST failed (HTTP 500)")
        self._n += 1
        record_id = f"rec-{self._n}"
        self.records[record_id] = (name, value, comment)
        self.added.append(record_id)
        return record_id

    def delete(self, record_id: str) -> None:
        if self.fail_delete:
            raise DnsError("Cloudflare DELETE failed (HTTP 500)")
        self.records.pop(record_id, None)
        self.deleted.append(record_id)

    def purge_stale(self) -> int:
        stale = [i for i, (_, _, c) in self.records.items() if c.startswith("infrafoundry-acme")]
        for record_id in stale:
            del self.records[record_id]
        self.purged += len(stale)
        return len(stale)

    def resolver(self, *, visible: bool = True) -> Any:
        """A resolver that sees this host's records, or none when ``visible`` is False."""

        def resolve(name: str) -> set[str]:
            if not visible:
                return set()
            return {v for n, v, _ in self.records.values() if n == name}

        return resolve


class FakeRun:
    """``subprocess.run`` stand-in: records calls, answers from a queue or a function."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.responses: list[tuple[int, str]] = []
        self.raises: BaseException | None = None

    def __call__(self, argv: list[str], **kwargs: Any) -> Any:
        self.calls.append((argv, kwargs))
        if self.raises is not None:
            raise self.raises
        code, err = self.responses.pop(0) if self.responses else (self.returncode, self.stderr)

        class _Result:
            returncode = code
            stdout = self.stdout
            stderr = err

        return _Result()


class FakeSopsRun(FakeRun):
    """A ``sops set`` stand-in that edits a JSON file the way sops would, for the store tests."""

    def __call__(self, argv: list[str], **kwargs: Any) -> Any:
        result = super().__call__(argv, **kwargs)
        if argv[:3] == ["sops", "set", "--value-stdin"] and self.returncode == 0:
            path = Path(argv[3])
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
            keys = [k for k in argv[4].replace("[", "").split("]") if k]
            node = data
            for key in keys[:-1]:
                node = node.setdefault(key.strip('"'), {})
            node[keys[-1].strip('"')] = json.loads(kwargs["input"])
            path.write_text(json.dumps(data), encoding="utf-8")
        return result


class MemoryWriter:
    """A ``SecretsWriter`` stand-in keeping values in a dict."""

    def __init__(self) -> None:
        self.values: dict[tuple[str, ...], dict[str, Any]] = {}
        self.paths: list[Path] = []
        self.created: list[tuple[Path, str]] = []
        self.history: list[tuple[tuple[str, ...], dict[str, Any]]] = []
        self.fail = False

    def ensure_file(self, path: Path, cwd: Path, initial: str) -> None:
        self.created.append((path, initial))

    def write_value(self, path: Path, keys: Sequence[str], value: dict[str, Any]) -> None:
        if self.fail:
            from infrafoundry.core.certs.models import CertificateStoreError

            raise CertificateStoreError("sops failed to write secrets.yaml (exit 1)")
        self.paths.append(path)
        self.values[tuple(keys)] = dict(value)
        self.history.append((tuple(keys), dict(value)))


def certificate_resource(
    name: str = "proxy-cert",
    *,
    names: Sequence[str] = ("*.example.com", "example.com"),
    package: str | None = "proxy",
    stored: dict[str, Any] | None = None,
    **config: Any,
) -> ResourceConfig:
    """A valid ``certificate`` resource targeting the host ``proxy-01``."""
    body: dict[str, Any] = {
        "names": list(names),
        "target": {
            "provider": "host",
            "resource": "proxy-01",
            "fullchain_path": "/etc/ssl/infrafoundry/proxy.fullchain.pem",
            "key_path": "/etc/ssl/infrafoundry/proxy.key",
            "reload": ["systemctl", "reload", "caddy"],
            "verify": {"port": 443, "server_name": "proxy.example.com"},
        },
    }
    body.update(config)
    return ResourceConfig(
        name=name,
        type="certificate",
        provider="acme",
        config=body,
        package_name=package,
        package_path=package,
        package_secrets={"acme_certificates": {name: stored}} if stored else {},
    )


def host_resource(name: str = "proxy-01", **config: Any) -> ResourceConfig:
    """A valid ``host`` resource."""
    body = {"address": "192.0.2.10", "ssh_user": "deploy", "ssh_port": 2222}
    body.update(config)
    return ResourceConfig(name=name, type="host", provider="host", config=body)


def have_tool(name: str) -> bool:
    """Whether an executable is on PATH."""
    return shutil.which(name) is not None
