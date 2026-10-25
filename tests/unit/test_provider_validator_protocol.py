"""Every provider validator satisfies ``ProviderValidator`` (#1074).

The protocol declared ``env_config: EnvironmentData`` while every validator
stores an ``EnvironmentConfig``, so none was assignable to it under mypy. The
runtime ``isinstance`` check only compares attribute names and could not catch
that. ``_as_protocol`` returns each validator as ``ProviderValidator``, so
``doit type_check`` fails here if an implementation drifts from the protocol
again; the test itself covers the runtime side.
"""

from __future__ import annotations

import pytest

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.validation import ProviderValidator, ValidationReport
from infrafoundry.providers.esxi.validator import EsxiValidator
from infrafoundry.providers.kubernetes.validator import KubernetesValidator
from infrafoundry.providers.oci.validator import OCIValidator
from infrafoundry.providers.opnsense.validator import OPNsenseValidator
from infrafoundry.providers.proxmox.validator import ProxmoxValidator

ValidatorClass = (
    type[EsxiValidator]
    | type[KubernetesValidator]
    | type[OCIValidator]
    | type[OPNsenseValidator]
    | type[ProxmoxValidator]
)


def _as_protocol(cls: ValidatorClass, env: EnvironmentConfig) -> ProviderValidator:
    """Build a validator typed as the protocol; mypy rejects this if one drifts."""
    return cls(env, ValidationReport())


@pytest.mark.parametrize(
    "cls",
    [EsxiValidator, KubernetesValidator, OCIValidator, OPNsenseValidator, ProxmoxValidator],
)
def test_validator_satisfies_protocol(cls: ValidatorClass) -> None:
    env = EnvironmentConfig(name="dev")

    validator = _as_protocol(cls, env)

    assert isinstance(validator, ProviderValidator)
    assert validator.env_config is env
