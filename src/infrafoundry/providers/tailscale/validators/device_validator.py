"""Device reference validation for ``device_subnet_routes`` and ``device_tags``."""

from __future__ import annotations

import ipaddress
from typing import Any, override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationReport

from ._common import check_tags, fail
from .context import TailscaleConfigContext

_DEVICE_TYPES = ("device_subnet_routes", "device_tags")


def device_key(config: dict[str, Any]) -> tuple[str, str] | None:
    """Return a hashable identity for the device a resource points at, or None."""
    if isinstance(config.get("device_id"), str) and config["device_id"]:
        return ("device_id", config["device_id"])
    device = config.get("device")
    if isinstance(device, dict):
        for field in ("hostname", "name"):
            if isinstance(device.get(field), str) and device[field]:
                return (field, device[field])
    return None


class DeviceReferenceValidator(SpecializedValidator[TailscaleConfigContext]):
    """Checks device references, routes, tags and per-device uniqueness."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    @override
    def validate(self, context: TailscaleConfigContext) -> None:
        """Check each device-bound resource.

        Args:
            context: Context whose resources are checked.
        """
        owners: dict[tuple[str, tuple[str, str]], str] = {}
        for resource in context.resources:
            if resource.type not in _DEVICE_TYPES:
                continue
            config = resource.config
            name = resource.name
            check = f"tailscale_device_{name}"
            has_device = "device" in config
            has_id = "device_id" in config
            ok = True
            if has_device == has_id:
                fail(
                    self.report,
                    check,
                    f"{resource.type} '{name}' needs exactly one of 'device' or 'device_id'",
                )
                ok = False
            elif has_id:
                if not isinstance(config["device_id"], str) or not config["device_id"]:
                    fail(self.report, check, f"'{name}': device_id must be a non-empty string")
                    ok = False
            else:
                ok = self._check_device(name, config["device"])
            if resource.type == "device_tags" and not isinstance(
                config.get("keep_tags_on_destroy", False), bool
            ):
                fail(
                    self.report,
                    f"tailscale_keep_tags_{name}",
                    f"'{name}': keep_tags_on_destroy must be a boolean",
                )
                ok = False
            if resource.type == "device_subnet_routes":
                ok = self._check_routes(name, config.get("routes")) and ok
            else:
                ok = check_tags(self.report, name, config.get("tags"), context.acl_policy) and ok
            key = device_key(config)
            if ok and key is not None:
                slot = (resource.type, key)
                if slot in owners:
                    fail(
                        self.report,
                        f"tailscale_device_duplicate_{name}",
                        f"{resource.type} '{name}' and '{owners[slot]}' manage the same device; "
                        "each resource owns the device's full set, so use one",
                    )
                else:
                    owners[slot] = name

    def _check_device(self, name: str, device: Any) -> bool:
        check = f"tailscale_device_{name}"
        if not isinstance(device, dict):
            fail(self.report, check, f"'{name}': device must be a mapping")
            return False
        selectors = [f for f in ("hostname", "name") if f in device]
        if (
            len(selectors) != 1
            or not isinstance(device[selectors[0]], str)
            or not device[selectors[0]]
        ):
            fail(
                self.report,
                check,
                f"'{name}': device needs exactly one non-empty 'hostname' or 'name'",
            )
            return False
        if "wait_for" in device and not isinstance(device["wait_for"], str):
            fail(self.report, check, f"'{name}': device.wait_for must be a duration string")
            return False
        extra = sorted(set(device) - {"hostname", "name", "wait_for"})
        if extra:
            fail(self.report, check, f"'{name}': unknown device keys {extra}")
            return False
        return True

    def _check_routes(self, name: str, routes: Any) -> bool:
        check = f"tailscale_routes_{name}"
        if not isinstance(routes, list) or not routes:
            fail(self.report, check, f"'{name}': routes must be a non-empty list of CIDRs")
            return False
        for route in routes:
            try:
                ipaddress.ip_network(route, strict=True)
            except (ValueError, TypeError):
                fail(
                    self.report,
                    check,
                    f"'{name}': route {route!r} is not a valid CIDR with no host bits set",
                )
                return False
        return True
