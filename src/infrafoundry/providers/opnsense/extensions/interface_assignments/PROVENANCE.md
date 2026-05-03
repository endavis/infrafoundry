# AssignSettingsController.php — Provenance & Maintenance

## Upstream lineage

Forked from szymczag's gist `df152a82e86aff67b984ed3786b027ba`
(<https://gist.github.com/szymczag/df152a82e86aff67b984ed3786b027ba>),
under BSD-2-Clause. The base gist provides `addItem` (auto-numbered
OPT name) and `delItem` only. This file is a maintained fork with
explicit additions enumerated below.

## License

BSD-2-Clause (inherited from the upstream gist). The fork copyright
is dual: original by Maciej Szymczak (2025); fork modifications by
the InfraFoundry contributors (2026).

## Modifications relative to upstream gist

| Addition                            | Surface                              | Rationale                                                                            |
| :---------------------------------- | :----------------------------------- | :----------------------------------------------------------------------------------- |
| `setItemAction($identifier)`        | In-place update by logical name      | Production CRUD requires update-without-delete-and-recreate.                         |
| `getItemAction($identifier)`        | Single-item fetch                    | Verification + introspection in `inspect`/`migrate` flows.                           |
| `searchItemAction()`                | Controller-side list                 | Confirms the extended controller is installed and reachable.                         |
| Explicit `name` field on `addItem`  | Bind a specific `optN` on creation   | Cutover continuity — keeps logical names stable between the legacy and the new box.  |
| IPv6 support across add/set         | `ipv6Type`, `ipv6Address`, `ipv6Subnet`, `ipv6Track` | Production write path needs dual-stack (no upstream IPv6).            |
| Removed legacy `sessionClose()` x2  | Two call sites                       | Modern OPNsense rejects the call (Paradoxis comment 2026-02-25 on the gist).         |

LoC delta vs. upstream: ~225 net-new (additions + minor refactor for shared
validation helpers).

## Maintenance ownership

InfraFoundry now owns this code. Upstream gist updates are not
auto-merged. PR-back of the IPv6/setItem extensions to the original
gist is tracked as a follow-up. If upstream issues a security fix,
the responsibility for forward-porting is the InfraFoundry
maintainer's, per ADR-0014's risk register.

## Deployment path on OPNsense

`/usr/local/opnsense/mvc/app/controllers/OPNsense/Interfaces/Api/AssignSettingsController.php`

The MVC autoloader discovers the file at this path; the URL routing
maps `AssignSettingsController` to `assign_settings`, so REST calls
go through `/api/interfaces/assign_settings/<action>`.

## Authn / authz inheritance

Extends `OPNsense\Base\ApiControllerBase`, which inherits OPNsense's
standard authentication + CSRF protection. API key + secret HMAC are
honored via the existing dispatcher; no auth code lives in this
file.

## Security review summary (Gate (3) for #720)

Performed against this fork. See PR description for the rendered
write-up.

- **Input validation:** All payload fields read via
  `$this->request->getPost()` or `$this->getModel()->Item->fromArray()`.
  Each `<field>Type` value is checked against a closed set of constants
  before any state is touched. `name` (when supplied via the explicit-name
  extension) is validated against `^opt\d+$` and uniqueness within the
  current `<interfaces>` block.
- **Authn / authz:** Inherits `ApiControllerBase`. OPNsense's API
  key + CSRF surface applies unmodified; no privilege-bypass code
  is added in the fork.
- **File-system access:** `Config::save()` (XML config persistence)
  only. No direct I/O, no `exec`, no `shell_exec`, no `system`, no
  `popen`, no `passthru`. The reconfigure side effect goes through
  `Backend::configdRun('interface reconfigure all')` which is the
  documented OPNsense IPC path; the command is a constant string,
  not built from user input.
- **Privilege escalation surface:** None added. The configd call
  inherits the existing OPNsense privilege model; the action runs
  under the same uid/gid as every other GUI-driven interface
  reconfigure.
- **Injection surface:** No SQL (OPNsense uses XML config). The
  XPath expressions used to write into `<interfaces>` are
  parameterized by static keys; user input only flows into
  attribute *values*, never into XPath structure.

Findings list: none introduced by this fork beyond the upstream
gist's own surface. The fork's net-new LoC reuses existing
OPNsense base-class validation helpers.

## Issue references

- Spike + extension: PR [#716](https://github.com/endavis/infrafoundry/pull/716) (issue #715)
- ADR-0014 amendment recording the mechanism: PR [#718](https://github.com/endavis/infrafoundry/pull/718) (issue #717)
- Production conversion (this lift): #720

## Re-running the security review

If upstream changes (or a future fork merges new sources in), a
reviewer should:

1. Diff `AssignSettingsController.php` against the previous tagged
   version inside this directory.
2. Re-walk the bullets in the security review summary above.
3. Update this file's "Modifications relative to upstream gist"
   table.
4. Bump the security review date in the PR that lands the change.
