"""Pin OPNsense literals that were restructured to drop bandit suppressions (#1209)."""

from infrafoundry.providers.opnsense import OPNsenseProvider
from infrafoundry.providers.opnsense.validator import _API_SECRET_ENV


def test_tfvars_mapping_matches_the_original_literal() -> None:
    assert OPNsenseProvider._OPNSENSE_TFVARS_MAPPING == {
        "api_url": "opnsense_api_url",
        "api_key": "opnsense_api_key",
        "api_secret": "opnsense_api_secret",
    }


def test_api_secret_env_name_is_unchanged() -> None:
    assert _API_SECRET_ENV == "OPNSENSE_API_SECRET"
