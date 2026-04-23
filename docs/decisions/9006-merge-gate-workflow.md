# ADR-9006: Merge-gate workflow requiring ready-to-merge label

## Status

Accepted

## Decision

Implement a merge-gate GitHub Actions workflow that requires the `ready-to-merge` label on PRs before allowing merge, enforced via branch protection rules.

The `ready-to-merge` label is a **pure merge gate** - it signals approval but does not trigger additional CI runs. The default CI matrix provides sufficient coverage for most PRs.

## Rationale

PRs could be merged while CI was still running or without explicit human approval. The merge-gate provides a lightweight mechanism requiring explicit "ready" signal after review, preventing premature merges and AI agents from merging without human review.

## Related Issues

- Issue #149: Add merge-gate workflow to require ready-to-merge label
- Issue #154: Fix merge-gate to wait for CI completion before allowing merge
- Issue #168: Add Python 3.14 to CI testing matrix (changed ready-to-merge to pure gate)
- Issue #428: Use GitHub App token for label application so Merge Gate re-runs on auto-applied labels

## Related Documentation

- [CI/CD Testing Guide](../../development/ci-cd-testing.md)
