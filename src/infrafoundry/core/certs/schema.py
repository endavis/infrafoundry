"""Offline checks and parsing for ``certificate`` resources and ``provider_settings.acme``."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any

from infrafoundry.core.certs.install import target_problems
from infrafoundry.core.certs.models import (
    DEFAULT_DIRECTORY,
    DEFAULT_DOH_URLS,
    DEFAULT_KEY_TYPE,
    DEFAULT_PROPAGATION_INTERVAL,
    DEFAULT_PROPAGATION_TIMEOUT,
    DEFAULT_RENEW_BEFORE_DAYS,
    DIRECTORIES,
    KEY_TYPES,
    MAX_NAMES,
    AcmeSettings,
    CertificateSchemaError,
    CertificateSpec,
)
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel
from infrafoundry.secrets.resolver import is_secret_uri

_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_NAME_RE = re.compile(rf"^(?:\*\.)?{_LABEL}(?:\.{_LABEL})+$")
_RESOURCE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CERT_KEYS = frozenset({"names", "key_type", "renew_before_days", "target"})
_SETTINGS_KEYS = frozenset(
    {"directory", "agree_tos", "email", "renew_before_days", "cloudflare", "propagation", "doh"}
)
MIN_RENEW_DAYS = 1
MAX_RENEW_DAYS = 60


@dataclass(frozen=True)
class CertificateFinding:
    """One schema finding for a certificate resource."""

    resource: str
    level: ValidationLevel
    message: str


def _is_name(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 253 or not _NAME_RE.fullmatch(value):
        return False
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return True
    return False


def _renew_problem(value: Any, where: str) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return f"{where} must be an integer number of days"
    if not MIN_RENEW_DAYS <= value <= MAX_RENEW_DAYS:
        return f"{where} must be within {MIN_RENEW_DAYS}-{MAX_RENEW_DAYS} days"
    return None


def certificate_problems(resource: ResourceConfig) -> list[str]:
    """Return what is wrong with one ``certificate`` resource (empty when valid). No network."""
    config = resource.config or {}
    where = f"certificate '{resource.name}'"
    problems: list[str] = []
    if not _RESOURCE_NAME_RE.fullmatch(resource.name):
        problems.append(f"{where}: the name may only hold letters, digits, '_' and '-'")
    unknown = sorted(set(config) - _CERT_KEYS - {"name"})
    if unknown:
        problems.append(f"{where} has unknown keys: {', '.join(map(str, unknown))}")
    names = config.get("names")
    if not isinstance(names, list) or not 1 <= len(names) <= MAX_NAMES:
        problems.append(f"{where}.names must be a list of 1-{MAX_NAMES} names")
        names = []
    else:
        bad = [n for n in names if not _is_name(n)]
        if bad:
            problems.append(
                f"{where}.names holds {len(bad)} invalid name(s): a name must be a DNS name "
                "with at most one leading '*.' label, not an IP address"
            )
        if len(set(names)) != len(names):
            problems.append(f"{where}.names holds duplicates")
    key_type = config.get("key_type", DEFAULT_KEY_TYPE)
    if key_type not in KEY_TYPES:
        problems.append(f"{where}.key_type must be one of: {', '.join(KEY_TYPES)}")
    if "renew_before_days" in config:
        problem = _renew_problem(config["renew_before_days"], f"{where}.renew_before_days")
        if problem:
            problems.append(problem)
    problems.extend(
        target_problems(
            config.get("target"), [n for n in names if isinstance(n, str)], f"{where}.target"
        )
    )
    if not resource.package_path:
        problems.append(
            f"{where} must be declared inside a package: its keys are stored in that "
            "package's secrets.yaml"
        )
    return problems


def check_certificates(resources: list[ResourceConfig]) -> list[CertificateFinding]:
    """Check every ``certificate`` resource and report duplicate names."""
    findings: list[CertificateFinding] = []
    seen: dict[str, int] = {}
    for resource in resources:
        if resource.type != "certificate":
            continue
        seen[resource.name] = seen.get(resource.name, 0) + 1
        findings.extend(
            CertificateFinding(resource.name, ValidationLevel.ERROR, problem)
            for problem in certificate_problems(resource)
        )
    findings.extend(
        CertificateFinding(
            name, ValidationLevel.ERROR, f"certificate '{name}' is declared {count} times"
        )
        for name, count in seen.items()
        if count > 1
    )
    return findings


def parse_spec(resource: ResourceConfig) -> CertificateSpec:
    """Build a spec from a valid ``certificate`` resource.

    Raises:
        CertificateSchemaError: If the resource is invalid.
    """
    problems = certificate_problems(resource)
    if problems:
        raise CertificateSchemaError("; ".join(problems))
    config = resource.config
    return CertificateSpec(
        name=resource.name,
        names=tuple(config["names"]),
        key_type=config.get("key_type", DEFAULT_KEY_TYPE),
        renew_before_days=config.get("renew_before_days"),
        target=dict(config["target"]),
    )


def directory_url(raw: Any) -> str | None:
    """Return the directory URL for ``staging``, ``production`` or an https URL, else None."""
    if isinstance(raw, str) and raw in DIRECTORIES:
        return DIRECTORIES[raw]
    if isinstance(raw, str) and re.fullmatch(r"https://[^\s]+", raw):
        return raw
    return None


def directory_id(raw: str) -> str:
    """Return a short stable id for a directory setting, used as the account key's name."""
    import hashlib

    if raw in DIRECTORIES:
        return raw
    return "custom-" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def raw_settings_problems(
    raw: dict[str, Any] | None, *, require_secret_refs: bool = True
) -> list[str]:
    """Return what is wrong with the raw ``provider_settings.acme`` mapping. Names keys only."""
    where = "provider_settings.acme"
    if not raw:
        return [f"{where} is missing"]
    problems: list[str] = []
    unknown = sorted(set(raw) - _SETTINGS_KEYS)
    if unknown:
        problems.append(f"{where} has unknown keys: {', '.join(map(str, unknown))}")
    if directory_url(raw.get("directory", DEFAULT_DIRECTORY)) is None:
        problems.append(f"{where}.directory must be staging, production or an https:// URL")
    if raw.get("agree_tos") is not True:
        problems.append(f"{where}.agree_tos must be true (you accept the CA's terms of service)")
    email = raw.get("email")
    if email is not None and not (isinstance(email, str) and _EMAIL_RE.fullmatch(email)):
        problems.append(f"{where}.email must be an email address")
    if "renew_before_days" in raw:
        problem = _renew_problem(raw["renew_before_days"], f"{where}.renew_before_days")
        if problem:
            problems.append(problem)
    cloudflare = raw.get("cloudflare")
    if not isinstance(cloudflare, dict):
        problems.append(f"{where}.cloudflare is required: api_token and zone_id")
    else:
        for key in ("api_token", "zone_id"):
            value = cloudflare.get(key)
            if not value:
                problems.append(f"{where}.cloudflare.{key} is required")
            elif require_secret_refs and not (isinstance(value, str) and is_secret_uri(value)):
                problems.append(f"{where}.cloudflare.{key} must be a secret:// reference")
    propagation = raw.get("propagation", {})
    if not isinstance(propagation, dict):
        problems.append(f"{where}.propagation must be a mapping")
    else:
        for key, low, high in (("timeout", 10, 900), ("interval", 1, 60)):
            value = propagation.get(key)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high
            ):
                problems.append(f"{where}.propagation.{key} must be an integer within {low}-{high}")
    doh = raw.get("doh")
    if doh is not None and not (
        isinstance(doh, list)
        and doh
        and all(isinstance(u, str) and u.startswith("https://") for u in doh)
    ):
        problems.append(f"{where}.doh must be a list of https:// URLs")
    return problems


def settings_from_mapping(resolved: dict[str, Any]) -> AcmeSettings:
    """Build settings from an already secret-resolved ``provider_settings.acme`` mapping.

    Raises:
        CertificateSchemaError: On a missing key or an invalid value. Names keys, never values.
    """
    problems = raw_settings_problems(resolved, require_secret_refs=False)
    if problems:
        raise CertificateSchemaError("; ".join(problems))
    raw_directory = str(resolved.get("directory", DEFAULT_DIRECTORY))
    url = directory_url(raw_directory)
    assert url is not None  # checked by raw_settings_problems
    cloudflare = resolved["cloudflare"]
    propagation = resolved.get("propagation") or {}
    return AcmeSettings(
        directory=url,
        directory_id=directory_id(raw_directory),
        agree_tos=True,
        email=resolved.get("email"),
        renew_before_days=int(resolved.get("renew_before_days", DEFAULT_RENEW_BEFORE_DAYS)),
        api_token=str(cloudflare["api_token"]),
        zone_id=str(cloudflare["zone_id"]),
        propagation_timeout=int(propagation.get("timeout", DEFAULT_PROPAGATION_TIMEOUT)),
        propagation_interval=int(propagation.get("interval", DEFAULT_PROPAGATION_INTERVAL)),
        doh_urls=tuple(resolved.get("doh") or DEFAULT_DOH_URLS),
    )
