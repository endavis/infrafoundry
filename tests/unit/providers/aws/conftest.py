"""Shared fixtures and builders for the AWS provider tests (placeholder IDs only)."""

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.aws import AWSProvider

VPC = "vpc-0123456789abcdef0"
SUBNET = "subnet-0123456789abcdef0"
SG = "sg-0123456789abcdef0"
INSTANCE = "i-0123456789abcdef0"
VOLUME = "vol-0123456789abcdef0"
AMI = "ami-0123456789abcdef0"
RULE = "sgr-0123456789abcdef0"
ZONE = "us-east-1a"


def make_env(
    settings: dict[str, Any] | None = None, secrets: dict[str, Any] | None = None
) -> EnvironmentConfig:
    """Build an EnvironmentConfig with ``provider_settings.aws``."""
    return EnvironmentConfig(
        name="test",
        provider_settings={"aws": settings} if settings is not None else {},
        secrets=secrets,
    )


def res(name: str, rtype: str, **config: Any) -> ResourceConfig:
    """Build an aws ResourceConfig; ``import_id`` becomes the field."""
    import_id = config.pop("import_id", None)
    return ResourceConfig(name=name, type=rtype, provider="aws", config=config, import_id=import_id)


def sg(name: str = "web", **extra: Any) -> ResourceConfig:
    """A valid security group."""
    return res(name, "security_group", vpc_id=VPC, **extra)


def rule(name: str = "ssh", **extra: Any) -> dict[str, Any]:
    """A valid IPv4 TCP ingress rule."""
    base: dict[str, Any] = {
        "name": name,
        "ip_protocol": "tcp",
        "from_port": 22,
        "to_port": 22,
        "cidr_ipv4": "192.0.2.0/24",
    }
    base.update(extra)
    return base


def instance(name: str = "app", **extra: Any) -> ResourceConfig:
    """A valid instance with a literal AMI."""
    config: dict[str, Any] = {"ami": AMI, "instance_type": "t3.micro", "subnet_id": SUBNET}
    config.update(extra)
    return res(name, "instance", **config)


def volume(name: str = "data", **extra: Any) -> ResourceConfig:
    """A valid volume attached to the instance ``app``."""
    config: dict[str, Any] = {"availability_zone": ZONE, "size": 20, "instance": "app"}
    config.update(extra)
    return res(name, "ebs_volume", **config)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the host's AWS_* and override-gate variables out of every test."""
    for var in (
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "AWS_PROFILE",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "INFRAFOUNDRY_ALLOW_ENV_OVERRIDE",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def provider(tmp_path: Path) -> AWSProvider:
    """An AWSProvider writing under tmp_path for environment 'test'."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    p = AWSProvider(config_dir, tmp_path / "output")
    p.set_environment("test")
    return p
