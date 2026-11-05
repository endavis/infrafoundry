"""System firmware service for OPNsense direct-API operations (#806).

Manages the OPNsense ``<system><firmware>`` block via the
``firmware/info`` (read) + ``firmware/install/<name>`` (write) endpoints.
This is the **keystone** surface for #806 — without ``firmware.plugins``
automating the install of contrib plugins, the modern controllers for
follow-up issues (#790 AcmeClient, #808 OpenVPN-legacy) don't exist on
the cutover target and ``infra apply`` for those issues silently
no-ops with 404s.

Identity is the singleton ``settings`` — there is exactly one firmware
configuration per box.

**Apply semantics (per #806 user decision, 2026-05-10):**

- ``apply`` is **install-missing only**: any plugin in YAML but not on
  the box is installed; any plugin on the box but not in YAML is
  **logged at warning level only — never auto-removed**.
- ``destroy`` is a no-op (don't auto-uninstall).

This intentionally violates the usual "live state == YAML state" symmetry
for safety: an operator who forgot to declare ``os-tailscale`` in YAML
should not lose Tailscale on the next apply.

Endpoint surface (26.1; #1149):

- ``GET core/firmware/info`` — plugin/package list (verified live, 26.1.6_2).
- ``GET core/firmware/get`` — settings under ``{"firmware": {...}}``
  (verified live, 26.1.6_2).
- ``POST core/firmware/set`` — settings write (verified live, 26.1.6_2).
- ``POST core/firmware/install/<plugin_name>`` — install one plugin. The
  request reaches OPNsense on 26.1.6_2 but only queues a background job;
  the response acknowledges the request, not the install. A box that is
  out of date refuses it in the job log (#1238).
- ``GET core/firmware/upgradestatus`` — the job's ``status`` (``"running"``
  while it runs) and ``log``. Apply polls it after queuing an install and
  re-reads ``firmware/info``; if the plugin is still not installed once
  the job is no longer running (or on timeout) it raises ``APIError`` with
  the log tail, so apply cannot report success for an install that did not
  happen (#1238).
- ``POST core/firmware/remove|lock/<plugin_name>`` — not tested; the apply
  path NEVER calls them.

Field schema:

- ``plugins`` — list of plugin names that should be installed.
- ``mirror``, ``flavour``, ``type``, ``subscription``, ``reboot`` —
  settings fields. Only the keys present in YAML are compared or written,
  so an omitted ``mirror`` is never blanked.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import urlsplit

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig

from ..api_client import OPNsenseClient, SystemClient
from ..components._singleton import diff_singleton
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService, raise_on_failed_write

logger = logging.getLogger(__name__)

_INSTALL_TIMEOUT_SECONDS = 300.0
_INSTALL_POLL_INTERVAL_SECONDS = 3.0
_LOG_TAIL_LINES = 20
_URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://\S+")
_URL_TRAILING = ".,;:)]}'\""
_MASK = "***"

_SETTINGS_FIELDS = ("mirror", "flavour", "type", "subscription", "reboot")


class SystemFirmwareService(BaseService):
    """Service for OPNsense system-firmware operations via direct-API.

    Args:
        client: Configured ``OPNsenseClient`` instance.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize the firmware service with a SystemClient wrapper."""
        super().__init__(client)
        self.system_client = SystemClient(client)

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

    def get_firmware_info(self) -> dict[str, Any]:
        """Fetch firmware/plugin info from OPNsense.

        Returns:
            Raw API response from ``core/firmware/info``.
        """
        return self.system_client.get_firmware_info()

    def get_firmware_settings(self) -> dict[str, Any]:
        """Fetch firmware settings from OPNsense.

        Returns:
            Raw API response from ``core/firmware/get``.
        """
        return self.system_client.get_firmware_settings()

    def set_firmware_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Write firmware settings.

        Args:
            payload: ``{"firmware": {<field>: <value>}}``.

        Returns:
            API response.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        response = self.system_client.set_firmware_settings(payload)
        raise_on_failed_write(response, "set firmware settings")
        return response

    def get_upgrade_status(self) -> dict[str, Any]:
        """Fetch the status of the running or last firmware background job.

        Returns:
            Raw API response from ``core/firmware/upgradestatus``.
        """
        return self.system_client.get_upgrade_status()

    def install_plugin(self, name: str) -> dict[str, Any]:
        """Install a single plugin and wait until it is installed.

        The install endpoint only queues a background job, so this waits
        via :meth:`wait_for_plugin_install` and raises if the plugin is not
        installed afterwards.

        Args:
            name: Plugin name (e.g., ``os-acme-client``).

        Returns:
            API response of the install request.

        Raises:
            APIError: If the request is rejected or the plugin is not
                installed once the job ends or the wait times out.
        """
        response = self.system_client.install_plugin(name)
        raise_on_failed_write(response, f"install firmware plugin {name}")
        self.wait_for_plugin_install(name)
        return response

    def wait_for_plugin_install(
        self,
        name: str,
        *,
        timeout: float = _INSTALL_TIMEOUT_SECONDS,
        interval: float = _INSTALL_POLL_INTERVAL_SECONDS,
    ) -> None:
        """Wait until ``name`` shows as installed in ``firmware/info``.

        Each round re-reads ``firmware/info``; if the plugin is not installed
        it reads ``firmware/upgradestatus``. A ``running`` status keeps the
        wait going. Two consecutive non-running observations (one ``interval``
        apart) with the plugin still missing are a failure; the second
        guards against a stale "done" status left by an earlier job.

        Args:
            name: Plugin name to wait for.
            timeout: Seconds to wait before giving up.
            interval: Seconds between polls.

        Raises:
            APIError: On timeout, or when the job ended without installing
                the plugin. The message carries the tail of the job log.
        """
        deadline = time.monotonic() + timeout
        idle_polls = 0
        while True:
            if name in self.extract_installed_plugins(self.get_firmware_info()):
                return
            status = self.get_upgrade_status()
            running = isinstance(status, dict) and status.get("status") == "running"
            if running:
                idle_polls = 0
            else:
                idle_polls += 1
                if idle_polls >= 2:
                    raise _install_error(
                        name,
                        "the install job ended but the plugin is not installed",
                        status,
                        self._subscription_or_none(),
                    )
            if time.monotonic() >= deadline:
                raise _install_error(
                    name,
                    f"timed out after {timeout:g}s waiting for the install job",
                    status,
                    self._subscription_or_none(),
                )
            time.sleep(interval)

    def _subscription_or_none(self) -> str | None:
        """Read the configured subscription for log masking; ``None`` on any failure."""
        try:
            fields = self.extract_firmware_settings_fields(self.get_firmware_settings())
        except Exception:  # best effort on an error path; URL masking still applies
            logger.debug("could not read firmware settings to mask the install log")
            return None
        return _str(fields.get("subscription")) or None

    # ------------------------------------------------------------------
    # Field extract / build
    # ------------------------------------------------------------------

    def extract_installed_plugins(self, api_response: dict[str, Any]) -> list[str]:
        """Return the sorted list of plugin names currently installed.

        ``firmware/info`` returns ``plugin: [{name, installed, ...}, ...]``;
        a plugin is installed iff its ``installed`` field equals ``"1"``
        (string sentinel) or ``1`` (int) or any truthy value.

        Args:
            api_response: Raw response from :meth:`get_firmware_info`.

        Returns:
            Sorted list of installed plugin names. Empty list if the
            response shape is unexpected.
        """
        plugin_rows = api_response.get("plugin", [])
        if not isinstance(plugin_rows, list):
            return []
        installed: list[str] = []
        for row in plugin_rows:
            if not isinstance(row, dict):
                continue
            name = _str(row.get("name"))
            if not name:
                continue
            if _is_truthy(row.get("installed")):
                installed.append(name)
        return sorted(installed)

    def build_desired_plugin_list(self, resource: ResourceConfig) -> list[str]:
        """Build the desired plugin list from a YAML singleton.

        Args:
            resource: ``system.firmware`` ``ResourceConfig``.

        Returns:
            Sorted, de-duplicated list of plugin names from
            ``config["plugins"]``. Empty list when no ``plugins`` key.
        """
        config = resource.config
        raw = config.get("plugins", [])
        if isinstance(raw, str):
            names = [s.strip() for s in raw.split(",") if s.strip()]
        elif isinstance(raw, list):
            names = [_str(v) for v in raw if _str(v)]
        else:
            names = []
        return sorted(set(names))

    def extract_firmware_settings_fields(self, api_response: dict[str, Any]) -> dict[str, Any]:
        """Extract firmware settings from a ``core/firmware/get`` response.

        Args:
            api_response: Raw response from :meth:`get_firmware_settings`.

        Returns:
            ``{field: str}`` for every settings field; ``{}`` when the
            ``firmware`` envelope is missing or not a dict. ``plugins`` and
            ``aux`` are ignored.
        """
        envelope = api_response.get("firmware")
        if not isinstance(envelope, dict):
            return {}
        return {field: _str(envelope.get(field)) for field in _SETTINGS_FIELDS}

    def build_desired_firmware_settings_fields(self, resource: ResourceConfig) -> dict[str, Any]:
        """Build the desired settings map: only keys present in YAML.

        Args:
            resource: ``system.firmware`` ``ResourceConfig``.

        Returns:
            ``{field: str}`` for each settings field set in the YAML.
        """
        config = resource.config
        return {field: _str(config[field]) for field in _SETTINGS_FIELDS if field in config}

    def settings_drift(
        self, live: dict[str, Any], desired: dict[str, Any]
    ) -> dict[str, str] | None:
        """Compare only the keys named in YAML.

        Args:
            live: Output of :meth:`extract_firmware_settings_fields`.
            desired: Output of :meth:`build_desired_firmware_settings_fields`.

        Returns:
            The desired keys/values on any difference, else ``None``.
        """
        if not desired:
            return None
        scoped = {key: live.get(key, "") for key in desired}
        return diff_singleton(scoped, desired)

    # ------------------------------------------------------------------
    # Plugin reconciliation
    # ------------------------------------------------------------------

    def desired_vs_installed_plugins(
        self,
        desired: list[str],
        installed: list[str],
    ) -> tuple[list[str], list[str]]:
        """Return ``(install_missing, extras_to_warn)`` plugin name lists.

        - ``install_missing``: in ``desired`` but not in ``installed`` —
          the apply path will install each.
        - ``extras_to_warn``: in ``installed`` but not in ``desired`` —
          **never removed**; the manager logs each at WARNING level so
          the operator can react out-of-band.

        Args:
            desired: Plugin names from YAML.
            installed: Plugin names from the live ``firmware/info`` response.

        Returns:
            Tuple of (sorted install-missing list, sorted extras list).
        """
        desired_set = set(desired)
        installed_set = set(installed)
        return sorted(desired_set - installed_set), sorted(installed_set - desired_set)

    # ------------------------------------------------------------------
    # migrate()
    # ------------------------------------------------------------------

    def export_to_yaml(self) -> str:
        """Export current firmware settings as nested YAML for ``infra migrate``.

        Returns:
            YAML string under the ``opnsense.system.firmware`` namespace.
        """
        info = self.get_firmware_info()
        installed = self.extract_installed_plugins(info)
        settings = self.extract_firmware_settings_fields(self.get_firmware_settings())
        clean: dict[str, Any] = {}
        if installed:
            clean["plugins"] = installed
        for key, value in settings.items():
            if key == "subscription":
                continue
            if isinstance(value, str) and value:
                clean[key] = value
        return emit_nested_singleton_yaml("system.firmware", clean)


def _mask_url(match: re.Match[str]) -> str:
    """Reduce one URL to ``scheme://host``, adding ``/***`` if anything was dropped."""
    raw = match.group(0)
    core = raw.rstrip(_URL_TRAILING)
    trailing = raw[len(core) :]
    try:
        parts = urlsplit(core)
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return f"{_MASK}{trailing}"
    if not host:
        return f"{_MASK}{trailing}"
    if ":" in host:
        host = f"[{host}]"
    dropped = bool(
        parts.path.strip("/") or parts.query or parts.fragment or parts.username or parts.password
    )
    suffix = f"/{_MASK}" if dropped else ""
    return f"{parts.scheme}://{host}{port}{suffix}{trailing}"


def _sanitize_log(text: str, subscription: str | None = None) -> str:
    """Mask the subscription value and strip URLs down to ``scheme://host``.

    OPNsense Business embeds the subscription key as a path segment of the
    mirror URL, which the firmware log can echo.
    """
    if subscription:
        text = text.replace(subscription, _MASK)
    return _URL_RE.sub(_mask_url, text)


def _install_error(
    name: str, reason: str, status: Any, subscription: str | None = None
) -> APIError:
    """Build the ``APIError`` for a plugin install that did not complete."""
    log = status.get("log") if isinstance(status, dict) else None
    tail = ""
    if isinstance(log, str):
        tail = _sanitize_log("\n".join(log.strip().splitlines()[-_LOG_TAIL_LINES:]), subscription)
    detail = f"; firmware log tail:\n{tail}" if tail else "; no firmware log available"
    return APIError(
        f"OPNsense did not install firmware plugin {name}: {reason}{detail}",
        response=tail or None,
        provider="opnsense",
    )


def _is_truthy(value: Any) -> bool:
    """OPNsense returns ``"1"`` / ``"0"`` / int / bool — accept any truthy form."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip() not in ("", "0", "false", "False", "no", "No", "off")
    return bool(value)


def _str(value: Any) -> str:
    """Return a stripped string for any scalar."""
    if value is None:
        return ""
    return str(value).strip()
