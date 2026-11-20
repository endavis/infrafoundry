"""Tests for cross-provider Terraform output references (#1536)."""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError, OutputReferenceError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.terraform_outputs import (
    PLACEHOLDER,
    OutputRef,
    is_output_ref,
    output_ref_dependencies,
    output_refs,
    parse_output_ref,
    resolve_output_refs,
)

REF = "outputs.tailscale.oauth_client_x_secret"
VAR = "TF_VAR_outputs_tailscale_oauth_client_x_secret"
SENTINEL = "sentinel-output-value-1536"  # pragma: allowlist secret


def _proc(outputs: dict[str, Any], code: int = 0) -> subprocess.CompletedProcess[str]:
    payload = {k: {"value": v, "sensitive": True} for k, v in outputs.items()}
    return subprocess.CompletedProcess([], code, stdout=json.dumps(payload), stderr="")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "tailscale" / ".terraform").mkdir(parents=True)
    return tmp_path


class TestParse:
    def test_accepts(self) -> None:
        assert parse_output_ref(REF) == OutputRef("tailscale", "oauth_client_x_secret")
        assert str(parse_output_ref(REF)) == REF

    @pytest.mark.parametrize(
        "ref",
        [
            "outputs.tailscale",
            "outputs.tailscale.a.b",
            "outputs.Tailscale.a",
            "outputs.tail-scale.a",
            "outputs.opnsense@fw-b.a",
            "outputs.tailscale.a-b",
            "outputs..a",
            "secrets.tailscale.a",
        ],
    )
    def test_rejects(self, ref: str) -> None:
        with pytest.raises(InvalidConfigurationError):
            parse_output_ref(ref)

    def test_is_output_ref_and_filter(self) -> None:
        assert is_output_ref(REF)
        assert not is_output_ref("tailscale.oauth_client_secret")
        assert output_refs(["a.b", REF]) == [REF]


class TestResolve:
    def test_resolves_once_per_producer(self, root: Path) -> None:
        refs = [REF, "outputs.tailscale.oauth_client_x_id"]
        with patch(
            "infrafoundry.core.terraform_outputs.subprocess.run",
            return_value=_proc({"oauth_client_x_secret": SENTINEL, "oauth_client_x_id": "id1"}),
        ) as run:
            env = resolve_output_refs(refs, tool_path="terraform", terraform_root=root, strict=True)
        assert env == {VAR: SENTINEL, f"{VAR[:-6]}id": "id1"}
        assert run.call_count == 1
        assert run.call_args.args[0] == ["terraform", "output", "-json"]
        assert run.call_args.kwargs["cwd"] == root / "tailscale"

    def test_strict_missing_directory(self, tmp_path: Path) -> None:
        with pytest.raises(OutputReferenceError, match="-P tailscale") as exc:
            resolve_output_refs([REF], tool_path="t", terraform_root=tmp_path, strict=True)
        assert "tailscale" in str(exc.value)

    def test_strict_nonzero_exit(self, root: Path) -> None:
        with (
            patch("infrafoundry.core.terraform_outputs.subprocess.run", return_value=_proc({}, 1)),
            pytest.raises(OutputReferenceError, match="exit 1"),
        ):
            resolve_output_refs([REF], tool_path="t", terraform_root=root, strict=True)

    def test_strict_missing_output(self, root: Path) -> None:
        with (
            patch("infrafoundry.core.terraform_outputs.subprocess.run", return_value=_proc({})),
            pytest.raises(OutputReferenceError, match="no output 'oauth_client_x_secret'"),
        ):
            resolve_output_refs([REF], tool_path="t", terraform_root=root, strict=True)

    def test_strict_non_string_value_never_leaks_it(self, root: Path) -> None:
        proc = _proc({"oauth_client_x_secret": {"k": SENTINEL}})
        with (
            patch("infrafoundry.core.terraform_outputs.subprocess.run", return_value=proc),
            pytest.raises(OutputReferenceError, match="dict") as exc,
        ):
            resolve_output_refs([REF], tool_path="t", terraform_root=root, strict=True)
        assert SENTINEL not in str(exc.value)

    def test_strict_unreadable_json(self, root: Path) -> None:
        proc = subprocess.CompletedProcess([], 0, stdout="not json", stderr="")
        with (
            patch("infrafoundry.core.terraform_outputs.subprocess.run", return_value=proc),
            pytest.raises(OutputReferenceError, match="not readable"),
        ):
            resolve_output_refs([REF], tool_path="t", terraform_root=root, strict=True)

    def test_lenient_placeholder_and_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            env = resolve_output_refs([REF], tool_path="t", terraform_root=tmp_path, strict=False)
        assert env == {VAR: PLACEHOLDER}
        assert REF in caplog.text
        assert "tailscale" in caplog.text

    def test_lenient_missing_output_placeholder(self, root: Path) -> None:
        with patch("infrafoundry.core.terraform_outputs.subprocess.run", return_value=_proc({})):
            env = resolve_output_refs([REF], tool_path="t", terraform_root=root, strict=False)
        assert env == {VAR: PLACEHOLDER}

    def test_value_never_logged(self, root: Path, caplog: pytest.LogCaptureFixture) -> None:
        proc = _proc({"oauth_client_x_secret": SENTINEL})
        with (
            caplog.at_level(logging.DEBUG),
            patch("infrafoundry.core.terraform_outputs.subprocess.run", return_value=proc),
        ):
            resolve_output_refs([REF], tool_path="t", terraform_root=root, strict=True)
        assert SENTINEL not in caplog.text

    def test_malformed_ref_raises(self, root: Path) -> None:
        with pytest.raises(InvalidConfigurationError):
            resolve_output_refs(["outputs.x"], tool_path="t", terraform_root=root, strict=True)


class TestDependencies:
    def _provider(self, refs: list[str]) -> MagicMock:
        provider = MagicMock()
        provider.get_terraform_output_refs.return_value = refs
        return provider

    def test_maps_consumer_to_producers_excluding_self(self) -> None:
        providers = {
            "kubernetes": self._provider([REF, "outputs.kubernetes.own", "outputs.bad"]),
            "tailscale": self._provider([]),
        }
        resources = {
            "kubernetes": [
                ResourceConfig(name="a", type="secrets", provider="kubernetes", config={})
            ],
            "tailscale": [ResourceConfig(name="b", type="acl", provider="tailscale", config={})],
        }
        assert output_ref_dependencies(providers, resources) == {"kubernetes": {"tailscale"}}

    def test_provider_without_resources_is_skipped(self) -> None:
        providers = {"kubernetes": self._provider([REF])}
        assert output_ref_dependencies(providers, {"kubernetes": []}) == {}

    def test_none_resources_uses_last_generation(self) -> None:
        providers = {"kubernetes": self._provider([REF])}
        assert output_ref_dependencies(providers, None) == {"kubernetes": {"tailscale"}}

    def test_provider_without_the_hook_has_no_dependencies(self) -> None:
        # A protocol-only provider plugin may not inherit ProviderBase's default hook.
        providers = {"plugin": object()}
        assert output_ref_dependencies(providers, None) == {}
