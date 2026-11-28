"""``CertificateService``: status and issue for the ``certificate`` resources of one environment.

Per certificate the order is: issue, write the encrypted entry, install, verify, write
``installed_sha256``, record the state row. A certificate that is stored but not installed
(``installed_sha256`` differs from ``sha256``) gets an install-only retry. One failure never
stops the run: it is reported and the next certificate is processed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from infrafoundry.core.certs.install import (
    CertificateTarget,
    resolve_target,
    verify_served,
)
from infrafoundry.core.certs.issuer import CertificateIssuer
from infrafoundry.core.certs.keys import describe
from infrafoundry.core.certs.models import (
    CERTIFICATE_TYPE,
    CERTS_VARIABLE,
    DEFAULT_RENEW_BEFORE_DAYS,
    AccountRecord,
    CertificateError,
    CertificateInstallError,
    CertificateSpec,
    IssuedCertificate,
)
from infrafoundry.core.certs.schema import parse_spec
from infrafoundry.core.certs.store import SecretsWriter
from infrafoundry.core.events.types import EventType
from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.protocols import InstallsCertificate
from infrafoundry.core.provider import ResourceConfig

logger = logging.getLogger(__name__)

SECRETS_FILENAME = "secrets.yaml"

Action = Literal["issued", "installed", "skipped", "failed"]
StateRecorder = Callable[[ResourceConfig, dict[str, Any]], None]
Verifier = Callable[[CertificateTarget, str], None]
Emitter = Callable[[EventType, dict[str, Any]], None]


@dataclass(frozen=True)
class CertStatus:
    """The state of one declared certificate."""

    name: str
    package: str
    names: tuple[str, ...]
    state: str
    not_after: datetime | None = None
    days_left: int | None = None
    installed: bool = False


@dataclass(frozen=True)
class CertOutcome:
    """What a run did for one certificate."""

    name: str
    action: Action
    message: str


@dataclass(frozen=True)
class CertPlan:
    """What a run would do for one certificate (``renew --dry-run``, plan notes)."""

    name: str
    action: Literal["issue", "install", "error"]
    reason: str


def certificate_resources(resources: Sequence[ResourceConfig]) -> list[ResourceConfig]:
    """Return the ``certificate`` resources of the ``acme`` provider."""
    return [r for r in resources if r.provider == "acme" and r.type == CERTIFICATE_TYPE]


def _stored_entry(resource: ResourceConfig) -> dict[str, Any] | None:
    certs = (resource.package_secrets or {}).get(CERTS_VARIABLE)
    entry = certs.get(resource.name) if isinstance(certs, dict) else None
    return entry if isinstance(entry, dict) else None


class CertificateService:
    """Status and issue, with every external piece injected."""

    def __init__(
        self,
        *,
        env: str,
        envs_dir: Path,
        writer: SecretsWriter,
        providers: Mapping[str, Any],
        default_renew_days: int = DEFAULT_RENEW_BEFORE_DAYS,
        verify: Verifier | None = None,
        record_state: StateRecorder | None = None,
        now: Callable[[], datetime] | None = None,
        emit: Emitter | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            env: Environment name.
            envs_dir: The config repo's ``envs`` directory.
            writer: Writes encrypted ``secrets.yaml`` entries.
            providers: Provider objects by name; those with ``install_certificate`` are
                install targets.
            default_renew_days: Renewal window when a certificate does not set its own.
            verify: ``(target, expected_sha256)`` check after an install; ``verify_served``
                by default.
            record_state: Records an ``ACTIVE`` state row (no key material in its config).
            now: Wall clock; replaced in tests.
            emit: Publishes ``CERTIFICATE_*`` events; payloads carry no key or token.
        """
        self._env = env
        self._envs_dir = envs_dir
        self._writer = writer
        self._providers = providers
        self._default_renew = default_renew_days
        self._verify: Verifier = verify or (lambda target, sha: verify_served(target, sha))
        self._record_state = record_state
        self._now = now or (lambda: datetime.now(UTC))
        self._emitter = emit

    # -- status -------------------------------------------------------------------------

    def status(self, resources: Sequence[ResourceConfig]) -> list[CertStatus]:
        """Report the state of each declared certificate. Reads only; no network."""
        return certificate_statuses(resources, self._default_renew, self._now())

    def plan(
        self,
        resources: Sequence[ResourceConfig],
        *,
        directory: str,
        only: Sequence[str] = (),
    ) -> list[CertPlan]:
        """List what ``renew`` would do: certificates that are missing, due or not installed.

        Reads only: no lock, no CA, no DNS, no target. Certificates that need nothing are
        left out.

        Raises:
            CertificateError: If a name in ``only`` is not declared.
        """
        chosen = self._choose(resources, only)
        plans: list[CertPlan] = []
        for resource in chosen:
            try:
                spec = parse_spec(resource)
            except InfraFoundryError as exc:
                plans.append(CertPlan(resource.name, "error", str(exc)))
                continue
            entry = _stored_entry(resource)
            reason = self._issue_reason(spec, entry, directory)
            if reason:
                plans.append(CertPlan(resource.name, "issue", reason))
            elif entry is not None and entry.get("installed_sha256") != entry.get("sha256"):
                plans.append(CertPlan(resource.name, "install", "stored but not installed"))
        return plans

    def renew(
        self,
        resources: Sequence[ResourceConfig],
        issuer: CertificateIssuer,
        account: AccountRecord | None,
        *,
        directory: str,
        directory_id: str,
        only: Sequence[str] = (),
    ) -> list[CertOutcome]:
        """Process what is due, never issued or not installed; the unattended entry point.

        The selection is that of ``issue`` without ``force``: a current, installed
        certificate is never ordered again.
        """
        return self.issue(
            resources,
            issuer,
            account,
            directory=directory,
            directory_id=directory_id,
            only=only,
            force=False,
        )

    # -- issue --------------------------------------------------------------------------

    def issue(
        self,
        resources: Sequence[ResourceConfig],
        issuer: CertificateIssuer,
        account: AccountRecord | None,
        *,
        directory: str,
        directory_id: str,
        only: Sequence[str] = (),
        force: bool = False,
    ) -> list[CertOutcome]:
        """Issue and install the certificates that need it, one at a time.

        Args:
            resources: Every resource of the environment.
            issuer: The issuer.
            account: The stored ACME account, or ``None`` before the first run.
            directory: The ACME directory URL; a certificate from another one is replaced.
            directory_id: Name of the account's slot under ``acme.accounts``.
            only: Certificate names to process; all when empty.
            force: Issue again even when the stored certificate is current.

        Returns:
            One outcome per processed certificate.

        Raises:
            CertificateError: If a name in ``only`` is not declared.
        """
        chosen = self._choose(resources, only)
        outcomes: list[CertOutcome] = []
        current_account = account
        for resource in chosen:
            try:
                spec = parse_spec(resource)
                entry = _stored_entry(resource)
                needs_issue = force or self._needs_issue(spec, entry, directory)
                if needs_issue:
                    current_account = self._ensure_account(issuer, current_account, directory_id)
                outcomes.append(
                    self._process(resource, spec, entry, needs_issue, issuer, resources)
                )
            except (InfraFoundryError, OSError) as exc:
                logger.warning("certificate '%s' failed: %s", resource.name, exc)
                outcomes.append(CertOutcome(resource.name, "failed", str(exc)))
                self._emit(
                    EventType.CERTIFICATE_FAILED,
                    {"certificate": resource.name, "error": str(exc)},
                )
        return outcomes

    @staticmethod
    def _choose(resources: Sequence[ResourceConfig], only: Sequence[str]) -> list[ResourceConfig]:
        declared = certificate_resources(resources)
        unknown = sorted(set(only) - {r.name for r in declared})
        if unknown:
            raise CertificateError(f"no certificate named: {', '.join(unknown)}")
        return [r for r in declared if not only or r.name in only]

    def _emit(self, event: EventType, data: dict[str, Any]) -> None:
        """Publish an event. A failing subscriber never fails a certificate run."""
        if self._emitter is None:
            return
        try:
            self._emitter(event, data)
        except Exception as exc:
            logger.warning("event %s handler failed: %s", event.value, exc.__class__.__name__)

    def _needs_issue(
        self, spec: CertificateSpec, entry: dict[str, Any] | None, directory: str
    ) -> bool:
        return self._issue_reason(spec, entry, directory) is not None

    def _issue_reason(
        self, spec: CertificateSpec, entry: dict[str, Any] | None, directory: str
    ) -> str | None:
        """Why the certificate must be ordered again, or ``None`` when the stored one is fine."""
        if entry is None:
            return "never issued"
        try:
            info = describe(str(entry.get("cert_pem", "")))
        except CertificateError:
            return "the stored certificate is unreadable"
        days = (info.not_after - self._now()).days
        window = spec.renew_before_days or self._default_renew
        if days < 0:
            return "expired"
        if days <= window:
            return f"due: {days} days left, renewing within {window}"
        if set(info.names) != set(spec.names):
            return "the declared names changed"
        if entry.get("key_type") != spec.key_type:
            return "the declared key type changed"
        if entry.get("directory") != directory:
            return "the ACME directory changed"
        if not entry.get("key_pem"):
            return "the stored private key is missing"
        return None

    def _ensure_account(
        self, issuer: CertificateIssuer, account: AccountRecord | None, directory_id: str
    ) -> AccountRecord:
        record = issuer.ensure_account(account)
        if record != account:
            path = self._envs_dir / self._env / SECRETS_FILENAME
            self._writer.ensure_file(path, self._envs_dir.parent, "acme: {}\n")
            self._writer.write_value(
                path,
                ("acme", "accounts", directory_id),
                {"key_pem": record.key_pem, "uri": record.uri},
            )
        return record

    def _secrets_path(self, resource: ResourceConfig) -> Path:
        return self._envs_dir / self._env / str(resource.package_path) / SECRETS_FILENAME

    def _write_entry(self, resource: ResourceConfig, entry: dict[str, Any]) -> None:
        path = self._secrets_path(resource)
        self._writer.ensure_file(path, self._envs_dir.parent, "variables: {}\n")
        self._writer.write_value(path, ("variables", CERTS_VARIABLE, resource.name), entry)

    def _process(
        self,
        resource: ResourceConfig,
        spec: CertificateSpec,
        entry: dict[str, Any] | None,
        needs_issue: bool,
        issuer: CertificateIssuer,
        resources: Sequence[ResourceConfig],
    ) -> CertOutcome:
        target = replace(resolve_target(spec.target, spec.names, resources), env=self._env)
        action: Action = "skipped"
        if needs_issue:
            issued = issuer.issue(spec)
            entry = _entry_from(issued)
            self._write_entry(resource, entry)
            action = "issued"
            self._emit(EventType.CERTIFICATE_ISSUED, _event_data(resource, entry))
        assert entry is not None  # set above or present
        sha = str(entry.get("sha256", ""))
        if entry.get("installed_sha256") != sha:
            try:
                self._install(target, entry)
            except CertificateInstallError as exc:
                prefix = "issued and stored, but " if needs_issue else ""
                raise CertificateInstallError(
                    f"{prefix}the install failed: {exc}; run 'foundry certs issue' again to retry"
                ) from None
            entry = {**entry, "installed_sha256": sha}
            self._write_entry(resource, entry)
            action = action if action == "issued" else "installed"
            self._emit(EventType.CERTIFICATE_INSTALLED, _event_data(resource, entry))
        if action == "skipped":
            return CertOutcome(resource.name, "skipped", "up to date and installed")
        self._record(resource, spec, entry)
        verb = "issued and installed" if action == "issued" else "installed"
        return CertOutcome(resource.name, action, f"{verb}; valid until {entry['not_after']}")

    def _install(self, target: CertificateTarget, entry: dict[str, Any]) -> None:
        provider = self._providers.get(target.provider)
        if not isinstance(provider, InstallsCertificate):
            raise CertificateInstallError(
                f"provider '{target.provider}' cannot install certificates"
            )
        provider.install_certificate(
            target,
            str(entry["cert_pem"]),
            str(entry.get("chain_pem", "")),
            str(entry["key_pem"]),
        )
        self._verify(target, str(entry["sha256"]))

    def _record(
        self, resource: ResourceConfig, spec: CertificateSpec, entry: dict[str, Any]
    ) -> None:
        if self._record_state is None:
            return
        target: dict[str, Any] = {
            "provider": spec.target.get("provider"),
            "resource": spec.target.get("resource"),
        }
        if spec.target.get("kind"):
            target["kind"] = spec.target["kind"]
        if spec.target.get("svm"):
            target["svm"] = spec.target["svm"]
        self._record_state(
            resource,
            {
                "names": list(spec.names),
                "not_after": entry["not_after"],
                "sha256": entry["sha256"],
                "target": target,
            },
        )


def _event_data(resource: ResourceConfig, entry: dict[str, Any]) -> dict[str, Any]:
    """Event payload: public facts only, never ``key_pem`` or a token."""
    return {
        "certificate": resource.name,
        "names": list(entry.get("names") or ()),
        "not_after": entry.get("not_after"),
        "sha256": entry.get("sha256"),
    }


def certificate_statuses(
    resources: Sequence[ResourceConfig], default_renew_days: int, now: datetime
) -> list[CertStatus]:
    """Report the state of each declared certificate from the encrypted store. No network."""
    result: list[CertStatus] = []
    for resource in certificate_resources(resources):
        names = tuple(resource.config.get("names") or ())
        package = resource.package_path or "-"
        entry = _stored_entry(resource)
        if entry is None:
            result.append(CertStatus(resource.name, package, names, "not issued"))
            continue
        try:
            info = describe(str(entry.get("cert_pem", "")))
        except CertificateError:
            result.append(CertStatus(resource.name, package, names, "invalid"))
            continue
        days = (info.not_after - now).days
        window = int(resource.config.get("renew_before_days") or default_renew_days)
        installed = entry.get("installed_sha256") == info.sha256
        if days < 0:
            state = "expired"
        elif days <= window:
            state = "due"
        elif not installed:
            state = "not installed"
        else:
            state = "valid"
        result.append(
            CertStatus(resource.name, package, names, state, info.not_after, days, installed)
        )
    return result


def _entry_from(issued: IssuedCertificate) -> dict[str, Any]:
    """Build the encrypted store entry for a freshly issued certificate."""
    info = issued.info
    return {
        "cert_pem": issued.cert_pem,
        "chain_pem": issued.chain_pem,
        "key_pem": issued.key_pem,
        "not_after": info.not_after.isoformat(),
        "not_before": info.not_before.isoformat(),
        "serial": info.serial,
        "sha256": info.sha256,
        "names": list(info.names),
        "key_type": issued.key_type,
        "directory": issued.directory,
        "issued_at": issued.issued_at.isoformat(),
        "installed_sha256": "",
    }
