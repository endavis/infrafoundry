"""Every provider sub-validator satisfies the ``validate(context)`` contract (#1307)."""

import importlib
import inspect
import pkgutil
import typing
from collections.abc import Iterator

import pytest

import infrafoundry.providers as providers_pkg
from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationContext


def _validator_modules() -> Iterator[tuple[str, str]]:
    """Yield ``(provider, module name)`` for each module under ``providers/*/validators``."""
    for provider in pkgutil.iter_modules(providers_pkg.__path__):
        if not provider.ispkg:
            continue
        try:
            package = importlib.import_module(f"infrafoundry.providers.{provider.name}.validators")
        except ModuleNotFoundError:
            continue
        for module in pkgutil.iter_modules(package.__path__):
            yield provider.name, f"{package.__name__}.{module.name}"


def _discover() -> list[tuple[str, type]]:
    """Return ``(provider, class)`` for each ``*Validator`` class or class defining ``validate``."""
    found: dict[type, str] = {}
    for provider, module_name in _validator_modules():
        module = importlib.import_module(module_name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ != module_name:
                continue
            if cls.__name__.endswith("Validator") or "validate" in vars(cls):
                found[cls] = provider
    return sorted(((p, c) for c, p in found.items()), key=lambda item: (item[0], item[1].__name__))


DISCOVERED = _discover()
IDS = [f"{provider}.{cls.__name__}" for provider, cls in DISCOVERED]
CLASSES = [cls for _, cls in DISCOVERED]


def test_discovery_covers_every_provider_with_validators() -> None:
    """Discovery finds validators in each provider that ships a validators package."""
    providers = {provider for provider, _ in DISCOVERED}
    assert {"esxi", "kubernetes", "oci", "opnsense", "proxmox"} <= providers


@pytest.mark.parametrize("cls", CLASSES, ids=IDS)
def test_validator_class_defines_validate(cls: type) -> None:
    """A class named ``*Validator`` defines ``validate`` itself."""
    assert "validate" in vars(cls), f"{cls.__name__} does not define validate()"


@pytest.mark.parametrize("cls", CLASSES, ids=IDS)
def test_validator_subclasses_specialized_validator(cls: type) -> None:
    """Every validator names the contract in its bases."""
    assert SpecializedValidator in cls.__mro__, f"{cls.__name__} must subclass SpecializedValidator"


@pytest.mark.parametrize("cls", CLASSES, ids=IDS)
def test_validate_signature_is_self_and_context(cls: type) -> None:
    """``validate`` takes ``(self, context)``, a ValidationContext subclass, and returns None."""
    signature = inspect.signature(cls.validate)  # type: ignore[attr-defined]
    assert list(signature.parameters) == ["self", "context"]
    hints = typing.get_type_hints(cls.validate)  # type: ignore[attr-defined]
    context_type = hints["context"]
    assert inspect.isclass(context_type)
    assert issubclass(context_type, ValidationContext)
    assert hints["return"] is type(None)
