window.BENCHMARK_DATA = {
  "lastUpdate": 1772633763356,
  "repoUrl": "https://github.com/endavis/infrafoundry",
  "entries": {
    "Benchmark": [
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "b18f10c8aed272667f4e1e2753454c81637beb70",
          "message": "chore: sync with pyproject-template (merges PR #285, addresses #284)\n\n* chore: sync with pyproject-template (5486031)\n\nSynchronize with latest pyproject-template upstream changes:\n\n- pyproject.toml: add hypothesis, mutmut, pytest-benchmark, pytest-xdist,\n  cyclonedx-bom deps; update bandit, vulture, pyright, mutmut config\n- CI: add benchmark and mutation testing workflows, SBOM generation in\n  release workflow, GitHub auto-generated release notes config\n- Doit tasks: add benchmark, mutation testing (mutate), and SBOM tasks;\n  enhance pre-commit install with post-merge/post-checkout hooks\n- AI tooling: add Gemini CLI settings/commands, Codex CLI config, Claude\n  Code commands/statusline/LSP setup, GEMINI.md collaboration guide\n- AGENTS.md: add pre-action checks table, prohibited reasoning examples,\n  tool hierarchy, dependabot workflow, PR checklist, file operations table\n- Switch all PR/merge references from \"Closes\" to \"Addresses\" throughout\n- Add .editorconfig, shell completions, VS Code tasks, .envrc.local.example\n- Update .pre-commit-config.yaml with explicit stages and sync hooks\n- Update manage.py and configure.py to latest template versions\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n\n* fix: resolve CI failures in benchmark and pip-audit steps\n\n- benchmark.yml: create tmp/ dir before writing benchmark JSON output\n- benchmark.yml: add placeholder benchmark test (tests/benchmarks/)\n- ci.yml: restore pip upgrade before pip-audit, add continue-on-error\n  for transitive dependency CVEs that can't be fixed in this repo\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n\n* fix: address remaining gaps from pyproject-template sync audit\n\n- pyproject.toml: add pip>=26.0 to security deps (resolves CVE-2026-1703)\n- ci.yml: add HYPOTHESIS_PROFILE env var, simplify pip-audit step\n- tools/doit/install.py: add assume-unchanged for _version.py\n- tools/doit/github.py: fix KeyError on 'closes' key (now 'addresses')\n- tests/conftest.py: add Hypothesis CI/default profile registration\n- tests/test_properties.py: add property-based tests for validation framework\n- tests/benchmarks/conftest.py: add benchmark marker documentation\n- AGENTS.md: add missing prohibited example, fix auto-close wording\n- .github/CONTRIBUTING.md: change \"Fixed in PR\" to \"Addressed in PR\"\n- docs: add doit-tasks-reference.md, property-based testing, mutation\n  testing, benchmark tracking, SBOM generation, release notes sections\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-03T11:37:06Z",
          "tree_id": "387bbd2191b9b4ea9c91a1ea4cc57c49120d5fe1",
          "url": "https://github.com/endavis/infrafoundry/commit/b18f10c8aed272667f4e1e2753454c81637beb70"
        },
        "date": 1772537859679,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7017.155306305891,
            "unit": "iter/sec",
            "range": "stddev: 0.00000892940579448594",
            "extra": "mean: 142.5078904982138 usec\nrounds: 2347"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "e20acaf17f14c5c93859d08a06ddf8d1dc26138a",
          "message": "feat: add multi-NIC, CPU type, machine type, BIOS, and ISO boot support to Proxmox provider (merges PR #286, addresses #281)",
          "timestamp": "2026-03-03T15:23:27Z",
          "tree_id": "cd4c994fb26aa74290a02759b0fb30cb264bfd61",
          "url": "https://github.com/endavis/infrafoundry/commit/e20acaf17f14c5c93859d08a06ddf8d1dc26138a"
        },
        "date": 1772551441267,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6997.656278890577,
            "unit": "iter/sec",
            "range": "stddev: 0.000009056500914681771",
            "extra": "mean: 142.90498992021685 usec\nrounds: 2381"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "3940ccc668016b6f4f6a5418270e01cfbbb6c6cd",
          "message": "feat: add ESXi provider for managing resources inside ESXi hosts (merges PR #287, addresses #282)\n\n* feat: add ESXi provider for managing resources inside ESXi hosts\n\n* fix: resolve bandit B404 and CodeQL URL sanitization warnings in ESXi provider\n\n* fix: avoid writing ESXi passwords to tfvars file\n\nPasswords must be provided via TF_VAR_esxi_password_<alias> environment\nvariables instead of being written as clear text to terraform.tfvars.",
          "timestamp": "2026-03-03T17:09:31Z",
          "tree_id": "05a782c60cd6d700d1742e09efa914cf056b5ec4",
          "url": "https://github.com/endavis/infrafoundry/commit/3940ccc668016b6f4f6a5418270e01cfbbb6c6cd"
        },
        "date": 1772557803262,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8917.0906109389,
            "unit": "iter/sec",
            "range": "stddev: 0.000021986604502191345",
            "extra": "mean: 112.14420079720462 usec\nrounds: 2007"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "034446163a09bab4ccf1af7b9bc3e1e359b3d3c0",
          "message": "fix: catch SecretNotFoundError in --allow-missing-secrets (merges PR #289, addresses #288)\n\nfix: catch SecretNotFoundError in _export_secrets for --allow-missing-secrets\n\nThe _export_secrets method only caught FileNotFoundError, but the SOPS\nprovider raises SecretNotFoundError which inherits from InfraFoundryError,\nnot FileNotFoundError. This caused --allow-missing-secrets to have no\neffect when encrypted secrets files were missing.\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-04T09:13:49Z",
          "tree_id": "76bc7f12a3a7c7a54b7a6b47f80118efdc33cd7a",
          "url": "https://github.com/endavis/infrafoundry/commit/034446163a09bab4ccf1af7b9bc3e1e359b3d3c0"
        },
        "date": 1772615667207,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6955.443270313314,
            "unit": "iter/sec",
            "range": "stddev: 0.000009513382098962517",
            "extra": "mean: 143.77228900250293 usec\nrounds: 2346"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6298d04354739d75408037898b29effc85aba402",
          "message": "feat: add LXC container support to Proxmox provider (merges PR #291, addresses #290)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-04T14:15:32Z",
          "tree_id": "85a9bf61228502b5e0e7562274f1c8b8fdd9d82e",
          "url": "https://github.com/endavis/infrafoundry/commit/6298d04354739d75408037898b29effc85aba402"
        },
        "date": 1772633762853,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6686.28642524553,
            "unit": "iter/sec",
            "range": "stddev: 0.000026976163299129543",
            "extra": "mean: 149.55985077520495 usec\nrounds: 2580"
          }
        ]
      }
    ]
  }
}