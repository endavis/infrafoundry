"""``VerifiesDestroy`` and ``HasSnippetStrictness`` match what ``hasattr`` matched (#1121).

The orchestrator used ``hasattr`` guards before calling ``verify_destroyed`` and
before setting ``fail_on_missing_snippets``. ``isinstance`` against a
runtime-checkable protocol checks the same attribute, and lets type checkers
narrow the object.
"""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.protocols import HasSnippetStrictness, VerifiesDestroy
from infrafoundry.core.runners.ansible_runner import AnsibleRunner
from infrafoundry.core.runners.terraform_runner import TerraformRunner


class _Strict:
    def __init__(self) -> None:
        self.fail_on_missing_snippets = False


class _Verifier:
    def verify_destroyed(self, provider: Any, expected_destroyed_names: list[str]) -> list[str]:
        return []


@pytest.mark.parametrize(
    ("obj", "expected"),
    [(_Strict(), True), (_Verifier(), False), (object(), False)],
    ids=["has-attribute", "other-attribute", "bare-object"],
)
def test_snippet_strictness_matches_hasattr(obj: object, expected: bool) -> None:
    assert isinstance(obj, HasSnippetStrictness) is expected
    assert hasattr(obj, "fail_on_missing_snippets") is expected


@pytest.mark.parametrize(
    ("obj", "expected"),
    [(_Verifier(), True), (_Strict(), False), (object(), False)],
    ids=["has-method", "other-attribute", "bare-object"],
)
def test_verifies_destroy_matches_hasattr(obj: object, expected: bool) -> None:
    assert isinstance(obj, VerifiesDestroy) is expected
    assert hasattr(obj, "verify_destroyed") is expected


def test_terraform_runner_verifies_destroy_and_ansible_does_not() -> None:
    """The destroy workflow's defense-in-depth check still runs for terraform only."""
    assert isinstance(TerraformRunner(), VerifiesDestroy)
    assert not isinstance(AnsibleRunner(), VerifiesDestroy)
