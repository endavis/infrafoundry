"""A strict host-key failure in a terraform error summary gets the fix hint (#1588)."""

import json

from infrafoundry.core.runners.terraform_runner import TerraformRunner


def test_diagnostic_detail_gets_the_hint() -> None:
    line = json.dumps(
        {
            "@level": "error",
            "type": "diagnostic",
            "diagnostic": {
                "summary": "local-exec provisioner error",
                "detail": "Host key for 192.0.2.10 has changed and you have requested "
                "strict checking.\nHost key verification failed.",
            },
        }
    )

    summary = TerraformRunner._extract_error_summary([line], "")

    assert "ssh-keygen -R 192.0.2.10" in summary


def test_stderr_fallback_gets_the_hint() -> None:
    stderr = "Host key verification failed."

    summary = TerraformRunner._extract_error_summary([], stderr)

    assert summary.startswith(stderr)
    assert "ssh-keyscan" in summary


def test_other_errors_are_unchanged() -> None:
    assert TerraformRunner._extract_error_summary([], "boom") == "boom"
