# ADR-0002: State locking via deployment_locks table

## Status

Accepted

## Context

`StateManager` coordinates deployment history, resource tracking, and events for every `infra apply` / `infra destroy`, but it has no mutual-exclusion mechanism across concurrent runs. When two operators (or two CI jobs) kick off an apply against the same environment simultaneously, both runs race on resource creation, state updates, and Terraform backend writes. The outcome is corrupted InfraFoundry state, duplicated resources, and unpredictable infrastructure drift.

Terraform backends provide their own lock for the generated `.tfstate` files, but InfraFoundry's own state DB, event log, and multi-runner workflow sit *outside* that lock - so relying on it is insufficient. See `docs/architecture/state-management.md` for the wider state model.

We need a correctness primitive that:
- Works against both SQLite (default) and PostgreSQL.
- Fails fast by default so operators see contention instead of silent waits.
- Has a stale-lock recovery path for crashed processes.
- Leaves `plan` unlocked (CI plan jobs should never queue behind an apply).
- Offers an audited escape hatch for emergencies.

Addresses #246.

## Decision

Introduce a `deployment_locks` table with a unique index on `environment`. Wrap `Orchestrator.apply()` and `Orchestrator.destroy()` in a context manager (`environment_lock`) that:

1. Inserts a lock row keyed by `environment`. The unique constraint is the atomic primitive - exactly one writer wins.
2. Records `locked_by` (`user@host:pid`), `acquired_at`, and `expires_at` (TTL-based, default 1 hour).
3. On contention, immediately raises `LockAcquisitionError` (default `--lock-timeout 0`). Operators can opt into blocking waits with `--lock-timeout <seconds>`.
4. Recovers automatically from expired locks: the next acquirer updates the row in place rather than refusing.
5. Always releases in `finally`, even on exception.
6. Emits `LOCK_ACQUIRED` / `LOCK_RELEASED` / `LOCK_TIMEOUT` events through the existing `EventManager`.

Management surface:
- `foundry infra unlock --env <name>` refuses active locks, releases expired ones.
- `foundry infra unlock --env <name> --force` force-releases (with confirm prompt unless `--yes`).
- `foundry infra unlock --list` shows all current locks.
- `INFRAFOUNDRY_SKIP_LOCK=1` environment variable bypasses locking entirely, with a loud warning. Used only in emergencies when the state DB is inaccessible.

`plan` is intentionally **not** locked - it only reads state and generates files, so running it in parallel with an active apply on the same env is safe and useful.

Schema change is delivered through `Base.metadata.create_all()` - the existing initialization path. No Alembic migration is introduced; the broader Alembic tracking work is scoped to #196.

## Consequences

**Positive**

- Concurrent applies/destroys on the same environment now fail fast with a clear, actionable error message (`foundry infra unlock --env <name>`).
- `plan` stays lock-free, preserving CI preview workflows.
- Works identically on SQLite and PostgreSQL - both honor the unique constraint.
- Stale lock recovery means a crashed apply does not permanently block future runs (at worst, the next operator waits for `lock_ttl` seconds or uses `--force`).
- All lock transitions are observable via the existing event system.

**Negative / trade-offs**

- TTL-based recovery introduces a time window where a truly alive but slow process may have its lock taken over. The default TTL (1 hour) is conservative for realistic apply durations, but operations running longer than the TTL need to supply `--lock-ttl`.
- The lock is advisory from Terraform's perspective - if someone runs `terraform apply` directly against the same generated files while a foundry apply holds the lock, the direct invocation is not blocked. See feedback `feedback_use_infra_not_terraform.md` for the mitigating user contract.
- Requires manual intervention (`unlock --force`) when a process dies holding a lock and TTL has not yet expired.
- `INFRAFOUNDRY_SKIP_LOCK` exists and can be abused; this is an accepted trade-off for emergencies.

**Out of scope (follow-ups)**

- Lock heartbeat / TTL extension during long applies.
- Distributed coordination backends (Redis, etcd).
- Locking `plan`.
- Alembic migrations (tracked separately under #196).

## Implementation

See `docs/architecture/state-management.md` (section "InfraFoundry-level locking") for the user-facing description and the `src/infrafoundry/core/state/lock_repository.py`, `lock_context.py`, and `src/infrafoundry/cli/commands/infra/unlock.py` modules for the code.
