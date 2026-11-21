"""Load and validate the ``collectors:`` section and resolve device credentials."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from infrafoundry.core.config.models import CollectorDeviceConfig, EnvironmentConfig
from infrafoundry.secrets.environment import build_secret_resolver

from .base import CollectorConfigError

HTTP_TYPES = frozenset({"huawei-ont-web", "routeros-rest"})
SSH_TYPES = frozenset({"openwrt-ssh"})
KNOWN_TYPES = HTTP_TYPES | SSH_TYPES


class ConfigSource(Protocol):
    """What loading needs from a ``ConfigManager`` (tests substitute a fake)."""

    base_dir: Path

    def load_environment(self, env_name: str) -> EnvironmentConfig:
        """Load an environment."""
        ...


@dataclass(frozen=True)
class Collection:
    """The resolved plan for one ``infra collect`` run."""

    env_config: EnvironmentConfig
    output_dir: Path
    config_root: Path
    devices: list[CollectorDeviceConfig]


def load_collection(
    config_manager: ConfigSource,
    env_name: str,
    devices: tuple[str, ...] = (),
    known_types: frozenset[str] = KNOWN_TYPES,
) -> Collection:
    """Load the environment's collectors and pick the devices to run.

    Args:
        config_manager: Config manager of the config repo.
        env_name: Environment name.
        devices: Device names to restrict to; empty means all.
        known_types: Accepted collector types.

    Raises:
        CollectorConfigError: On a missing section, unknown device or type, or a bad output dir.
    """
    env_config = config_manager.load_environment(env_name)
    section = env_config.collectors if env_config else None
    if env_config is None or section is None or not section.devices:
        raise CollectorConfigError(f"No collectors configured for environment '{env_name}'")
    by_name = {d.name: d for d in section.devices}
    unknown = [n for n in devices if n not in by_name]
    if unknown:
        raise CollectorConfigError(f"Unknown device(s): {', '.join(unknown)}")
    selected = [by_name[n] for n in devices] if devices else list(section.devices)
    for device in selected:
        if device.type not in known_types:
            raise CollectorConfigError(
                f"device '{device.name}' has unknown collector type '{device.type}'"
            )
    config_root = config_manager.base_dir.parent.resolve()
    output_dir = _resolve_output_dir(
        config_root, config_manager.base_dir.resolve(), section.output_dir, env_name
    )
    return Collection(env_config, output_dir, config_root, selected)


def _resolve_output_dir(
    config_root: Path, envs_dir: Path, configured: str | None, env_name: str
) -> Path:
    relative = configured or f"device-configs/{env_name}"
    resolved = (config_root / relative).resolve()
    if not resolved.is_relative_to(config_root) or resolved == config_root:
        raise CollectorConfigError("collectors.output_dir must be inside the config repo")
    if resolved == envs_dir or resolved.is_relative_to(envs_dir):
        raise CollectorConfigError(
            "collectors.output_dir must not be under the envs directory (it would be "
            "discovered as a provider)"
        )
    return resolved


def resolve_device(
    env_config: EnvironmentConfig, device: CollectorDeviceConfig
) -> CollectorDeviceConfig:
    """Resolve ``secret://`` references of one device and check its required fields.

    Args:
        env_config: The environment (its decrypted ``secrets`` back ``secret://env_secrets``).
        device: The device entry.

    Raises:
        CollectorConfigError: If a reference or required field is bad. Never carries values.
    """
    resolver = build_secret_resolver(env_config)
    try:
        resolved = resolver.resolve_config(device.model_dump())
    except Exception as exc:
        raise CollectorConfigError(
            f"device '{device.name}': could not resolve secret references ({type(exc).__name__})"
        ) from exc
    finally:
        resolver.close()
    result = CollectorDeviceConfig.model_validate(resolved)
    if result.type in HTTP_TYPES:
        if urlparse(result.address).scheme not in ("http", "https"):
            raise CollectorConfigError(f"device '{result.name}': address must be an http(s) URL")
        missing = [k for k in ("username", "password") if not getattr(result, k)]
        if missing:
            raise CollectorConfigError(f"device '{result.name}' is missing: {', '.join(missing)}")
    elif result.type in SSH_TYPES and not result.username:
        raise CollectorConfigError(f"device '{result.name}' is missing: username")
    return result
