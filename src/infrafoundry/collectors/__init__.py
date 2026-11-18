"""Read-only collectors that back up the configuration of unmanaged network devices.

Collectors are not providers or runners: they plan nothing, keep no state and generate no
Terraform. Their artifacts land in the config repo, SOPS-encrypted when they carry secrets.
"""

from __future__ import annotations

from .base import (
    Artifact,
    Collector,
    CollectorAuthError,
    CollectorConfigError,
    CollectorEncryptionError,
    CollectorError,
    CollectorFactory,
)
from .huawei_ont_web import HuaweiOntWebCollector
from .openwrt_ssh import OpenWrtSshCollector
from .routeros_rest import RouterOSRestCollector

COLLECTORS: dict[str, CollectorFactory] = {
    "huawei-ont-web": HuaweiOntWebCollector,
    "routeros-rest": RouterOSRestCollector,
    "openwrt-ssh": OpenWrtSshCollector,
}

__all__ = [
    "COLLECTORS",
    "Artifact",
    "Collector",
    "CollectorAuthError",
    "CollectorConfigError",
    "CollectorEncryptionError",
    "CollectorError",
    "CollectorFactory",
]
