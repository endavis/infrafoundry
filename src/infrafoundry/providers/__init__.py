"""InfraFoundry Providers Package."""

from infrafoundry.providers.aws import AWSProvider
from infrafoundry.providers.esxi import EsxiProvider
from infrafoundry.providers.host import HostProvider
from infrafoundry.providers.kubernetes import KubernetesProvider
from infrafoundry.providers.oci import OCIProvider
from infrafoundry.providers.opnsense import OPNsenseProvider
from infrafoundry.providers.proxmox import ProxmoxProvider
from infrafoundry.providers.tailscale import TailscaleProvider

__all__ = [
    "AWSProvider",
    "EsxiProvider",
    "HostProvider",
    "KubernetesProvider",
    "OCIProvider",
    "OPNsenseProvider",
    "ProxmoxProvider",
    "TailscaleProvider",
]
