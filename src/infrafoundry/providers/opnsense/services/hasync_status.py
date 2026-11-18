"""HA config sync after apply for OPNsense direct-API operations (#1390).

After a direct-API apply succeeds on the primary node, the provider's
``post_apply_hook`` calls :func:`run_ha_sync_after_apply`. It reads
``synchronizetoip`` from ``core/hasync/get``. When a backup is set, it calls
``core/hasync_status/version`` as a preflight and then
``core/hasync_status/restartAll``, the action behind the GUI's "Synchronize and
reconfigure all".

Settings (provider settings in ``settings.yaml``):

- ``ha_sync_after_apply``: ``true`` (default) syncs only when the apply changed
  something; ``"always"`` syncs even when nothing changed (the recovery path after a
  failed sync); ``false`` turns the sync off. With ``true`` and a no-op apply, a node
  with ``ha_backup`` set still syncs when the backup lacks one of its CARP VIPs
  (a rebuilt backup, #1474).
- ``ha_sync_timeout``: seconds per request, a positive int, default ``300``.

What the evidence says (probed on a single test node; wording generic):

- ``version`` reports an unreachable backup only after about 60 s, so the default
  30 s client timeout would hide the endpoint's message. All three calls use one
  client built with ``ha_sync_timeout``.
- With no target set, ``version`` answers ``{"response": false}``.
- ``restartAll`` runs ``exec_sync`` and ``reload_templates`` and then restarts each
  service on the backup. ``exec_sync`` always echoes ``{"status": "done"}``, so
  OPNsense does not report errors that occur while pushing the config.

Not verified: a successful sync to a real backup node.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider_instances import qualified_provider_id

from .. import endpoints
from ..firewalls import firewall_settings, ha_backup_name
from .base import BaseService
from .carp_status import CarpStatusService, carp_vip_keys, missing_carp_vips
from .hasync_settings import HasyncSettingsService
from .openvpn_instances import flatten_option

logger = logging.getLogger(__name__)

#: Default seconds per request for the sync calls.
DEFAULT_TIMEOUT = 300

_MODE_KEY = "ha_sync_after_apply"
_TIMEOUT_KEY = "ha_sync_timeout"


@dataclass(frozen=True)
class HaSyncOptions:
    """Resolved ``ha_sync_after_apply`` / ``ha_sync_timeout`` settings."""

    mode: Literal["changed", "always", "off"]
    timeout: int


def resolve_ha_sync_options(provider_settings: dict[str, Any] | None) -> HaSyncOptions:
    """Validate and resolve the HA sync settings.

    Args:
        provider_settings: The opnsense provider settings, or ``None``.

    Returns:
        The resolved options; defaults are ``changed`` and 300 seconds.

    Raises:
        InvalidConfigurationError: If a value has the wrong type or range.
    """
    settings = provider_settings or {}
    mode: Literal["changed", "always", "off"] = "changed"
    if _MODE_KEY in settings:
        raw = settings[_MODE_KEY]
        if raw is True:
            mode = "changed"
        elif raw is False:
            mode = "off"
        elif raw == "always":
            mode = "always"
        else:
            raise InvalidConfigurationError(
                f"{_MODE_KEY} must be true, false or 'always', got {raw!r}"
            )
    timeout = DEFAULT_TIMEOUT
    if _TIMEOUT_KEY in settings:
        raw_timeout = settings[_TIMEOUT_KEY]
        if isinstance(raw_timeout, bool) or not isinstance(raw_timeout, int) or raw_timeout <= 0:
            raise InvalidConfigurationError(
                f"{_TIMEOUT_KEY} must be an integer greater than 0, got {raw_timeout!r}"
            )
        timeout = raw_timeout
    return HaSyncOptions(mode=mode, timeout=timeout)


class HasyncStatusService(BaseService):
    """Service for the OPNsense HA status actions that sync config to the backup."""

    def __init__(self, client: Any, timeout: int = DEFAULT_TIMEOUT) -> None:
        """Initialize the service.

        Args:
            client: API client, built with ``timeout``.
            timeout: Seconds the client waits; only used in error messages.
        """
        super().__init__(client)
        self.timeout = timeout

    def _post(self, backup: str, ep: endpoints.Endpoint) -> Any:
        """POST an endpoint, turning transport failures into :class:`APIError`."""
        try:
            return self.client.request(ep.method, ep.path())
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise APIError(
                f"HA sync to backup {backup} failed at {ep.path()}: "
                f"{type(exc).__name__} (ha_sync_timeout is {self.timeout}s)",
                response=type(exc).__name__,
                provider="opnsense",
            ) from exc

    def version(self, backup: str) -> dict[str, Any]:
        """Run the ``core/hasync_status/version`` preflight against the backup.

        Args:
            backup: The ``synchronizetoip`` address, for messages.

        Returns:
            The reply.

        Raises:
            APIError: On a non-dict reply, an error status or a transport failure.
        """
        ep = endpoints.HASYNC_STATUS_VERSION
        response = self._post(backup, ep)
        if not isinstance(response, dict):
            raise APIError(
                f"HA sync to backup {backup} failed at {ep.path()}: unexpected reply",
                response="",
                provider="opnsense",
            )
        if response.get("status") == "error":
            raise APIError(
                f"HA sync to backup {backup} failed at {ep.path()}: "
                f"{response.get('message') or sorted(response)}",
                response=str(sorted(response)),
                provider="opnsense",
            )
        if not response.get("response") and response.get("status") != "ok":
            logger.warning(
                "HA sync preflight %s for backup %s returned no version; continuing",
                ep.path(),
                backup,
            )
        return response

    def restart_all(self, backup: str) -> int | None:
        """Run ``core/hasync_status/restartAll`` ("Synchronize and reconfigure all").

        ``exec_sync`` always echoes ``{"status": "done"}``, so errors while pushing the
        config to the backup are not reported by OPNsense.

        Args:
            backup: The ``synchronizetoip`` address, for messages.

        Returns:
            The number of services restarted, or ``None`` when the reply omits it.

        Raises:
            APIError: If the reply is not ``status == "ok"`` or on a transport failure.
        """
        ep = endpoints.HASYNC_STATUS_RESTART_ALL
        response = self._post(backup, ep)
        if not isinstance(response, dict) or response.get("status") != "ok":
            detail = (
                response.get("message") or sorted(response) if isinstance(response, dict) else ""
            )
            raise APIError(
                f"HA sync to backup {backup} failed at {ep.path()}: {detail}",
                response=str(sorted(response)) if isinstance(response, dict) else "",
                provider="opnsense",
            )
        count = response.get("count")
        return count if isinstance(count, int) and not isinstance(count, bool) else None


def run_ha_sync_after_apply(
    env_name: str, provider_name: str, config_dir: Path, changed: bool
) -> str:
    """Sync the config to the HA backup after a successful apply or destroy.

    Args:
        env_name: Active environment name.
        provider_name: Provider name (``opnsense``).
        config_dir: Configuration directory.
        changed: Whether the apply or destroy created, updated or deleted anything.

    Returns:
        A status line for the runner to print.

    Raises:
        APIError: If the preflight or the sync fails.
        InvalidConfigurationError: If the HA sync settings are invalid.
    """
    from infrafoundry.core.config import ConfigManager

    env_config = ConfigManager(config_dir).load_environment(env_name)
    settings = firewall_settings(env_config, provider_name)
    options = resolve_ha_sync_options(settings)
    if options.mode == "off":
        return "HA sync after apply disabled (ha_sync_after_apply: false)"
    check_backup: str | None = None
    if options.mode == "changed" and not changed:
        check_backup = ha_backup_name(env_config, provider_name)
        if check_backup is None:
            return "HA sync skipped: nothing changed"

    client = BaseService.client_from_environment(
        env_name, provider_name, config_dir, timeout=options.timeout
    )
    settings_service = HasyncSettingsService(client)
    live = settings_service.live_hasync(settings_service.get_settings())
    backup = flatten_option(live.get("synchronizetoip")).strip()
    if not backup:
        return "HA sync skipped: no synchronize_to_ip on this node"

    missing_note = ""
    if check_backup is not None:
        primary_status = CarpStatusService(client).vip_status()
        primary_keys = carp_vip_keys(primary_status)
        if not primary_keys:
            return (
                "HA sync skipped: nothing changed, no CARP VIPs on this node to compare "
                f"with backup {check_backup}"
            )
        try:
            backup_client = BaseService.client_from_environment(
                env_name,
                qualified_provider_id("opnsense", check_backup),
                config_dir,
                timeout=options.timeout,
            )
            backup_status = CarpStatusService(backup_client).vip_status()
        except (APIError, httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "HA sync check could not read CARP state of ha_backup firewall %r: %s",
                check_backup,
                exc,
            )
            return (
                "HA sync skipped: nothing changed, could not read CARP state of "
                f"ha_backup firewall '{check_backup}': {exc}"
            )
        missing = missing_carp_vips(primary_status, backup_status)
        if not missing:
            return (
                f"HA sync skipped: nothing changed, backup {check_backup} has all "
                f"{len(primary_keys)} CARP VIP(s)"
            )
        missing_note = (
            f" backup {check_backup} missing {len(missing)} of {len(primary_keys)} CARP VIP(s),"
        )

    service = HasyncStatusService(client, options.timeout)
    service.version(backup)
    count = service.restart_all(backup)
    suffix = "" if count is None else f" {count} service(s)"
    return f"HA sync to backup {backup}:{missing_note} synchronized and reconfigured{suffix}"
