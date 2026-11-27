"""Shared pieces of the ``certs`` commands, including the seam tests replace."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import click

from infrafoundry.core.certs.acme_client import AcmeClient, LibAcmeClient
from infrafoundry.core.certs.dns_cloudflare import CloudflareDns, HttpSession
from infrafoundry.core.certs.install import CertificateTarget
from infrafoundry.core.certs.issuer import CertificateIssuer
from infrafoundry.core.certs.models import (
    PROVIDER_NAME,
    AccountRecord,
    AcmeSettings,
    CertificateSchemaError,
)
from infrafoundry.core.certs.propagation import (
    NameserverQuery,
    authoritative_resolver,
    doh_resolver,
    query_nameserver,
)
from infrafoundry.core.certs.schema import raw_settings_problems, settings_from_mapping
from infrafoundry.core.certs.service import CertificateService
from infrafoundry.core.certs.store import SecretsWriter
from infrafoundry.core.events.types import EventType
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.state.models import DeploymentStatus, ResourceState
from infrafoundry.secrets.environment import resolved_provider_settings

if TYPE_CHECKING:
    from infrafoundry.core.config.models import EnvironmentConfig
    from infrafoundry.core.orchestrator import Orchestrator


def _requests_session() -> HttpSession:
    import requests

    return cast(HttpSession, requests.Session())


@dataclass(frozen=True)
class CertsDeps:
    """The seams tests replace: ACME, HTTP, the secrets writer, verification and clocks."""

    acme_client: Callable[[AcmeSettings], AcmeClient] = lambda s: LibAcmeClient(s.directory)
    session: Callable[[], HttpSession] = _requests_session
    writer: Callable[[], SecretsWriter] = SecretsWriter
    verify: Callable[[CertificateTarget, str], None] | None = None
    nameserver_query: NameserverQuery = query_nameserver
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic
    now: Callable[[], datetime] = lambda: datetime.now(UTC)


DEPS = CertsDeps()


def load_environment(orchestrator: Orchestrator, env: str) -> EnvironmentConfig:
    """Load the environment configuration (with its decrypted secrets)."""
    return orchestrator.config_manager.load_environment(env)


def load_settings(env_config: EnvironmentConfig) -> AcmeSettings:
    """Check and resolve ``provider_settings.acme``.

    Raises:
        click.UsageError: If the settings are missing or invalid. Names keys, never values.
    """
    raw = env_config.provider_settings.get(PROVIDER_NAME)
    problems = raw_settings_problems(raw)
    if problems:
        raise click.UsageError("; ".join(problems))
    resolved = resolved_provider_settings(env_config, PROVIDER_NAME) or {}
    try:
        return settings_from_mapping(resolved)
    except CertificateSchemaError as exc:
        raise click.UsageError(str(exc)) from None


def stored_account(env_config: EnvironmentConfig, settings: AcmeSettings) -> AccountRecord | None:
    """Return the account stored for the settings' directory, if any."""
    acme: Any = (env_config.secrets or {}).get("acme")
    accounts = acme.get("accounts") if isinstance(acme, dict) else None
    entry = accounts.get(settings.directory_id) if isinstance(accounts, dict) else None
    if not isinstance(entry, dict) or not entry.get("key_pem"):
        return None
    return AccountRecord(key_pem=str(entry["key_pem"]), uri=entry.get("uri"))


def build_issuer(settings: AcmeSettings, deps: CertsDeps) -> CertificateIssuer:
    """Build the issuer from the settings and the seams."""
    session = deps.session()
    dns = CloudflareDns(settings.api_token, settings.zone_id, session)
    return CertificateIssuer(
        deps.acme_client(settings),
        dns,
        [authoritative_resolver(dns.name_servers, deps.nameserver_query)],
        settings,
        extra_resolvers=[doh_resolver(url, session) for url in settings.doh_urls],
        sleep=deps.sleep,
        monotonic=deps.monotonic,
        now=deps.now,
    )


def build_service(
    orchestrator: Orchestrator,
    env: str,
    deps: CertsDeps,
    default_renew_days: int,
    *,
    record: bool,
    command: str = "certs issue",
) -> CertificateService:
    """Build the service for an environment."""
    providers = dict(orchestrator.providers)
    for provider in providers.values():
        # API-based installs (a Proxmox node) read the environment's credentials
        set_environment = getattr(provider, "set_environment", None)
        if callable(set_environment):
            set_environment(env)
    return CertificateService(
        env=env,
        envs_dir=orchestrator.config_manager.base_dir,
        writer=deps.writer(),
        providers=providers,
        default_renew_days=default_renew_days,
        verify=deps.verify,
        record_state=_state_recorder(orchestrator, env, command) if record else None,
        now=deps.now,
        emit=_event_emitter(orchestrator, env),
    )


def _event_emitter(
    orchestrator: Orchestrator, env: str
) -> Callable[[EventType, dict[str, Any]], None]:
    def emit(event: EventType, data: dict[str, Any]) -> None:
        orchestrator.event_manager.emit_event(event, env, data)

    return emit


def _state_recorder(
    orchestrator: Orchestrator, env: str, command: str
) -> Callable[[ResourceConfig, dict[str, Any]], None]:
    def record(resource: ResourceConfig, config: dict[str, Any]) -> None:
        manager = orchestrator.state_manager
        deployment = manager.create_deployment(env, command)
        manager.track_resource(
            deployment,
            env,
            PROVIDER_NAME,
            resource.type,
            resource.name,
            ResourceState.ACTIVE,
            config,
        )
        manager.update_deployment_status(deployment, DeploymentStatus.COMPLETED)

    return record
