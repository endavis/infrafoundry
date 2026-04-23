# ADR-9015: install_tools framework: archive extraction and custom URLs

## Status

Accepted

## Decision

Extend `tools/doit/install_tools.py` with three orthogonal capabilities while preserving full backward compatibility:

1. **`download_and_extract_archive(url, extract_binaries, dest_dir)`** — new public function for `.tar.gz`/`.tgz`/`.zip` archives with path-traversal protection (tarfile `data_filter` plus basename-only extraction and a defense-in-depth zip-slip check).
2. **`url_template` parameter** on `install_tool()` and `create_install_task()` supporting `{version}`, `{os}`, and `{arch}` placeholders for non-GitHub-release downloads (e.g., `releases.hashicorp.com`).
3. **`prefer_brew` flag** so callers can opt out of the macOS brew fallback when they need consistent cross-platform downloads.

Supporting refactors: a private `_get_arch()` helper that maps `platform.machine()` to amd64/arm64 (passthrough for unknowns), and a private `_build_github_release_url()` so the binary path and the new archive path share URL construction.

## Rationale

Downstream consumers (e.g., InfraFoundry) need to install five tools, but only direnv-style single binaries from GitHub releases work today. age and sops ship as multi-binary tar.gz archives; terraform and opentofu ship from non-GitHub URLs. Without these extensions every downstream consumer reinvents download/extract code with inconsistent (often missing) security handling.

The three capabilities are intentionally orthogonal so simple cases stay simple — existing direnv install code does not change — and complex cases compose naturally (`extract_binaries` and `url_template` can be combined).

## Consequences

**Positive:**
- 100% backward compatible — existing direnv install task and the original 22 tests pass unchanged.
- Downstream consumers install age, sops, terraform, and opentofu without custom download/extract code.
- Centralized, audited safe extraction (tarfile data_filter + basename-only + zip-slip resolve check).
- macOS users can opt into brew (default) or force download for cross-platform consistency.

**Negative:**
- Larger public API surface to maintain.
- The framework is now responsible for safe archive extraction; security regressions here affect every downstream consumer.

**Future work:**
- SHA256 checksum verification.
- GPG signature verification.
- Local archive caching between runs.
- Windows binary download support.

## Related Issues

- Issue #326: install_tools framework: archive extraction and custom URLs

## Related Documentation

- [install_tools Framework](../../development/install-tools-framework.md)
