"""Pin the Proxmox tfvars mapping to the literal it replaced (#1209)."""

from infrafoundry.providers.proxmox import ProxmoxProvider


def test_tfvars_mapping_matches_the_original_literal() -> None:
    assert ProxmoxProvider._PROXMOX_TFVARS_MAPPING == {
        "api_url": "proxmox_api_url",
        "api_token": "proxmox_api_token",
        "api_token_id": "proxmox_api_token_id",
        "api_token_secret": "proxmox_api_token_secret",
        "node": "proxmox_node",
        "storage": "proxmox_storage",
    }
