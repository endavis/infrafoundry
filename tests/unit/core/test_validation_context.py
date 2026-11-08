"""Tests for ValidationContext, run_validators and the SpecializedValidator protocol."""

from dataclasses import FrozenInstanceError, dataclass, replace
from typing import override

import pytest

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationContext, ValidationReport, run_validators


@dataclass(frozen=True, kw_only=True)
class _ExtraContext(ValidationContext):
    """Context with a required extra field."""

    names: frozenset[str]


class _Recorder(SpecializedValidator[ValidationContext]):
    """Validator that records the contexts it receives."""

    def __init__(self, calls: list[tuple[str, ValidationContext]], label: str) -> None:
        self.report = ValidationReport()
        self._calls = calls
        self._label = label

    @override
    def validate(self, context: ValidationContext, /) -> None:
        self._calls.append((self._label, context))


class _NoValidate:
    """Has a report but no validate method."""

    report = ValidationReport()


def test_context_defaults_resources_to_empty() -> None:
    """A bare context carries no resources, and each instance has its own list."""
    first, second = ValidationContext(), ValidationContext()
    assert first.resources == []
    assert first.resources is not second.resources


def test_context_is_frozen() -> None:
    """Contexts cannot be mutated after creation."""
    context = ValidationContext()
    with pytest.raises(FrozenInstanceError):
        context.resources = []  # type: ignore[misc]


def test_replace_keeps_other_fields() -> None:
    """dataclasses.replace changes one field and keeps the rest."""
    context = _ExtraContext(names=frozenset({"a"}))
    changed = replace(context, resources=[])
    assert changed.names == frozenset({"a"})


def test_run_validators_calls_each_in_order_with_same_context() -> None:
    """Each validator runs once, in order, with the identical context object."""
    calls: list[tuple[str, ValidationContext]] = []
    context = ValidationContext()
    run_validators([_Recorder(calls, "one"), _Recorder(calls, "two")], context)
    assert [label for label, _ in calls] == ["one", "two"]
    assert all(received is context for _, received in calls)


def test_run_validators_with_no_validators_is_a_noop() -> None:
    """An empty validator sequence does nothing."""
    run_validators([], ValidationContext())


def test_protocol_recognises_validators() -> None:
    """A class with report and validate satisfies the protocol; others do not."""
    assert isinstance(_Recorder([], "x"), SpecializedValidator)
    assert not isinstance(object(), SpecializedValidator)
    assert not isinstance(_NoValidate(), SpecializedValidator)
