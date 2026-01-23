# ADR-0001: Linux-only CI testing

## Status

Accepted

## Context

The pyproject-template CI uses a multi-OS matrix (Ubuntu, Windows, macOS) for testing. When synchronizing infrafoundry's CI workflows with the template (issue #149), we evaluated whether multi-OS testing provides value for this project.

InfraFoundry is an infrastructure automation tool that wraps Terraform, Ansible, SOPS/age, and PyInfra - all Linux/macOS tools. These system tools are not available on Windows and have limited CI support on macOS (GitHub API rate limits during installation).

The old CI (tests.yml) ran exclusively on Ubuntu with doit install_deps to install system tools.

## Decision

Run CI tests on Ubuntu (Linux) only, with dynamic Python version bookend strategy from the template. Do not include Windows or macOS in the test matrix.

## Consequences

Positive: All tests run with full system tool support. Simpler CI configuration. Faster execution (no 6x matrix explosion). Matches the actual user base (infrastructure engineers on Linux/macOS).

Negative: Won't catch platform-specific Python bugs on Windows/macOS. Diverges from pyproject-template's multi-OS approach.

Mitigations: Code quality checks (ruff, mypy) are platform-independent. InfraFoundry's target audience does not include Windows users. If macOS-specific issues arise, a targeted matrix can be added later.
