window.BENCHMARK_DATA = {
  "lastUpdate": 1773838412222,
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
          "id": "033e5fedd77e0becf5f109b1ccd99dc0969c7560",
          "message": "fix: correct Kea DHCPv6 API integration (merges PR #293, addresses #292)\n\nfix: correct Kea DHCPv6 API integration — wrapper keys, field names, and auto-enable service\n\n- Add ensure_dhcp6_enabled() to auto-enable DHCPv6 service and select\n  interfaces in general settings before creating subnets\n- Fix general settings path (dhcpv6.general.enabled, not dhcpv6.enabled)\n- Fix subnet wrapper key (subnet6, not subnet)\n- Fix pools format (newline-separated string, not list of dicts)\n- Fix DNS field nesting (under option_data, not top-level)\n- Fix reservation field names (subnet not subnet_id, ip_address not ip_addresses)\n- Search for UUID after subnet creation (add response doesn't include it)\n- Add validation error checking on create responses\n\nAddresses #292\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-04T16:07:10Z",
          "tree_id": "2bad525684d2cf84815c89da13de16195a268c37",
          "url": "https://github.com/endavis/infrafoundry/commit/033e5fedd77e0becf5f109b1ccd99dc0969c7560"
        },
        "date": 1772640457928,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8980.397843864255,
            "unit": "iter/sec",
            "range": "stddev: 0.000020133523945523156",
            "extra": "mean: 111.35364127361434 usec\nrounds: 2796"
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
          "id": "a56c53d6f1bf72f66a732c67f3ba30d8b8e665db",
          "message": "feat: add Proxmox storage resource type for NFS, CIFS, and directory backends (merges PR #295, addresses #294)\n\nAddresses #294\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-04T17:08:58Z",
          "tree_id": "b53bb54aea4578c0878c9dd55dbad6b1a78991a5",
          "url": "https://github.com/endavis/infrafoundry/commit/a56c53d6f1bf72f66a732c67f3ba30d8b8e665db"
        },
        "date": 1772644169643,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9229.66070757115,
            "unit": "iter/sec",
            "range": "stddev: 0.000014400808942408301",
            "extra": "mean: 108.3463446472841 usec\nrounds: 2681"
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
          "id": "59c263a07572444ddec555683202ad8505eb7a8f",
          "message": "fix: parse imported disk path for NFS storage compatibility (merges PR #297, addresses #296)\n\nfix: parse imported disk path from qm config for NFS storage compatibility\n\nThe template disk attachment hardcoded the path as storage:vm-VMID-disk-0\nwhich only works for LVM storage. NFS storage uses storage:VMID/vm-VMID-disk-0.raw.\nNow parses the unused0 entry from qm config after importdisk, which works for\nall storage backends.\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-05T11:53:07Z",
          "tree_id": "3f755496b7d70fe74a20803966fb818988bd1594",
          "url": "https://github.com/endavis/infrafoundry/commit/59c263a07572444ddec555683202ad8505eb7a8f"
        },
        "date": 1772711619995,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7061.306267077574,
            "unit": "iter/sec",
            "range": "stddev: 0.000008173000378984719",
            "extra": "mean: 141.6168570201197 usec\nrounds: 3497"
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
          "id": "81043db925adfdc7782da534272c9d63bc6d91e1",
          "message": "fix: correct DHCPv6 reservation lookup field from subnet_id to subnet (merges PR #299, addresses #298)\n\nThe OPNsense Kea DHCPv6 API returns the subnet UUID in a field called\n\"subnet\", not \"subnet_id\". The wrong field name caused the existing\nreservation lookup to always miss, making every apply attempt to create\nduplicates instead of updating in place.\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-05T13:09:33Z",
          "tree_id": "09f030f6f5f43cf2a57284e8806c31dfc40b82f5",
          "url": "https://github.com/endavis/infrafoundry/commit/81043db925adfdc7782da534272c9d63bc6d91e1"
        },
        "date": 1772716212116,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6758.356984185519,
            "unit": "iter/sec",
            "range": "stddev: 0.00002103098559196757",
            "extra": "mean: 147.9649569177818 usec\nrounds: 2414"
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
          "id": "bbe6ef6bc49bc8aa3924a4479f9df384ce556edf",
          "message": "fix: correct Proxmox container hostname and provider config rendering (merges PR #301, addresses #300)\n\n- Fix container hostname from nested block to flat attribute\n- Update provider.tf.j2 to use Terraform variables for API credentials\n- Update test to match corrected hostname rendering\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-05T13:17:42Z",
          "tree_id": "a68dc24e87719fb2a32e14b18bd47ad2a0128930",
          "url": "https://github.com/endavis/infrafoundry/commit/bbe6ef6bc49bc8aa3924a4479f9df384ce556edf"
        },
        "date": 1772716695157,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6291.338318464815,
            "unit": "iter/sec",
            "range": "stddev: 0.000031124594371373404",
            "extra": "mean: 158.94869253256365 usec\nrounds: 2049"
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
          "id": "265d5cff4f2f5b3d35046ec156c06431960cf4da",
          "message": "fix: pass through all cloud-init directives in snippet processor (merges PR #303, addresses #302)\n\n* fix: pass through all cloud-init directives in snippet processor\n\nInstead of extracting a hardcoded list of cloud-init fields (hostname,\nusers, packages, runcmd, network), store the full merged cloud-init\nas a YAML string and output it directly in the template. This preserves\nall directives including mounts, write_files, bootcmd, swap, etc.\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n\n* fix: remove domain-like string from test to avoid CodeQL false positive\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-05T15:03:02Z",
          "tree_id": "13d02f2550b4cdccb6c12a11345306a9dd1cc5dc",
          "url": "https://github.com/endavis/infrafoundry/commit/265d5cff4f2f5b3d35046ec156c06431960cf4da"
        },
        "date": 1772723043725,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6972.1953863528715,
            "unit": "iter/sec",
            "range": "stddev: 0.000012949917132856148",
            "extra": "mean: 143.42684686624884 usec\nrounds: 1835"
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
          "id": "17b89a6e57643b6561e378fa854b9edfafe38e01",
          "message": "fix: use terraform -target for resource filter instead of regenerating config (merges PR #305, addresses #304)\n\n* fix: use terraform -target for resource filter instead of regenerating config\n\nThe -r resource filter previously regenerated .tf files with only the\nfiltered resources, causing terraform to see missing resources as deleted\nand destroy them. Now all resources are always generated, and the filter\nis applied via terraform's -target flag.\n\n- orchestrator_workflows: generate all resources, pass filter to runner\n- terraform_runner: add _resolve_terraform_targets() and -target support\n- deployment_executor: pass resource_filter through to runners\n- test_deployment_executor: update mock signatures for new kwargs\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n\n* chore: trigger CI re-run\n\n---------\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-05T18:05:35Z",
          "tree_id": "a3458b33dae2065f87d96b38dd93828bcbac4344",
          "url": "https://github.com/endavis/infrafoundry/commit/17b89a6e57643b6561e378fa854b9edfafe38e01"
        },
        "date": 1772734095853,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6759.482672638948,
            "unit": "iter/sec",
            "range": "stddev: 0.00002015098184681069",
            "extra": "mean: 147.94031561731828 usec\nrounds: 2446"
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
          "id": "9eaf536c131941cedda3ba91eede21262ab064c7",
          "message": "fix: pass resource filter as -target to terraform destroy (merges PR #307, addresses #306)\n\nThe destroy path was missed in PR #305 which fixed plan and apply.\nWithout this, `foundry infra destroy -r <name>` destroyed ALL resources\ninstead of only the targeted ones.\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-06T10:35:01Z",
          "tree_id": "c008c9c036e1be8b7b2b71b4aa5d599c7c6bf263",
          "url": "https://github.com/endavis/infrafoundry/commit/9eaf536c131941cedda3ba91eede21262ab064c7"
        },
        "date": 1772793331355,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7066.566156964532,
            "unit": "iter/sec",
            "range": "stddev: 0.000007970859749700178",
            "extra": "mean: 141.51144668962579 usec\nrounds: 2326"
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
          "id": "cdbac1eb56457f88b36c33324972592da384db89",
          "message": "feat: add boot_order support for Proxmox VMs (merges PR #309, addresses #308)\n\nAdds a boot_order config option that maps to the terraform provider's\nboot_order list attribute. This is needed for ISO-based installs (e.g.,\nESXi) where disk must boot before CD after installation to prevent\ninfinite reinstall loops.\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-06T12:55:04Z",
          "tree_id": "ae858f5cdef453e1320940da60dacde6d488b78d",
          "url": "https://github.com/endavis/infrafoundry/commit/cdbac1eb56457f88b36c33324972592da384db89"
        },
        "date": 1772801749360,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6907.787009003514,
            "unit": "iter/sec",
            "range": "stddev: 0.00001257302231792096",
            "extra": "mean: 144.76416234267413 usec\nrounds: 2544"
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
          "id": "c27aee948057f013239eb595d35cedf964395bbc",
          "message": "feat: add OVF deployment support with network mapping (merges PR #311, addresses #310)\n\nfeat: add OVF deployment resource type to ESXi provider\n\nAdd ovf_deployment resource type that uses ovftool directly with --net:\nflags for per-network OVF-to-portgroup mapping. This enables deploying\nOVF appliances (e.g., ONTAP Simulator) that define multiple logical\nnetworks requiring different target port groups.\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-06T16:36:17Z",
          "tree_id": "09e59c536de607482e491b9a424a1f0fe91769b0",
          "url": "https://github.com/endavis/infrafoundry/commit/c27aee948057f013239eb595d35cedf964395bbc"
        },
        "date": 1772815008898,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6839.0457487412195,
            "unit": "iter/sec",
            "range": "stddev: 0.000014667268797314524",
            "extra": "mean: 146.21922951517877 usec\nrounds: 2331"
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
          "id": "16756161b4c0dc4cafa376b67f18b659c3ba8b58",
          "message": "fix: URL-encode ESXi password in OVF deployment vi:// URL (merges PR #313, addresses #312)\n\nfix: URL-encode ESXi password and use self references in OVF deployment\n\nThe ovf_deployment template had two issues:\n1. Passwords with URL-special characters (e.g., #, @, ?) broke the\n   vi:// URL passed to ovftool. Now URL-encoded via python3 urllib.\n2. Destroy provisioner referenced var.* which Terraform forbids in\n   destroy-time provisioners. Now stores connection details in\n   triggers_replace and uses self.triggers_replace.* throughout.\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-06T17:04:17Z",
          "tree_id": "e0fb25fafbc064072289628451875d3808e4090f",
          "url": "https://github.com/endavis/infrafoundry/commit/16756161b4c0dc4cafa376b67f18b659c3ba8b58"
        },
        "date": 1772816686048,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6842.586743726931,
            "unit": "iter/sec",
            "range": "stddev: 0.000019306886155300812",
            "extra": "mean: 146.14356199675052 usec\nrounds: 2484"
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
          "id": "f7e708f9cbbb48e2e96fa734ae130b817107430b",
          "message": "feat: add mac_map support to ovf_deployment for deterministic MAC addresses (merges PR #315, addresses #314)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-07T09:13:17Z",
          "tree_id": "37c53bfc024046b803bd412ccc4bd87ee0eb375d",
          "url": "https://github.com/endavis/infrafoundry/commit/f7e708f9cbbb48e2e96fa734ae130b817107430b"
        },
        "date": 1772874824628,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6605.016253728227,
            "unit": "iter/sec",
            "range": "stddev: 0.000027365805467078235",
            "extra": "mean: 151.40008163273575 usec\nrounds: 2450"
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
          "id": "0351cb88281e67a054865d552724542f24cc00dd",
          "message": "fix: change mac_map keys from network names to ethernet adapter names (merges PR #316, addresses #314)\n\nOVFs can have multiple NICs on the same network (e.g., ONTAP has\nethernet0 and ethernet1 both on \"hostonly\"). Using network names as\nmac_map keys couldn't distinguish between them. Now keys are ethernet\nadapter names (ethernet0, ethernet1, etc.) which map directly to VMX\nentries, simplifying the SSH script and supporting all NICs.\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-07T09:47:28Z",
          "tree_id": "1115f4ff6f219d7bafff8082c6b61bf4c02f54d8",
          "url": "https://github.com/endavis/infrafoundry/commit/0351cb88281e67a054865d552724542f24cc00dd"
        },
        "date": 1772876876129,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7022.714658843161,
            "unit": "iter/sec",
            "range": "stddev: 0.000008868752417531363",
            "extra": "mean: 142.39507776964533 usec\nrounds: 2726"
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
          "id": "91495383faa47f488e1db75d345564ec01da13f0",
          "message": "feat: add Unbound DNS host override support to OPNsense provider (merges PR #318, addresses #317)\n\n* feat: add Unbound DNS host override support to OPNsense provider\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n\n* fix: avoid CodeQL false positive for URL substring check in test\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-07T11:38:16Z",
          "tree_id": "21e101aaddfc55f75a7e2a9866e4c1f8dc714c8e",
          "url": "https://github.com/endavis/infrafoundry/commit/91495383faa47f488e1db75d345564ec01da13f0"
        },
        "date": 1772883521624,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9612.239946393955,
            "unit": "iter/sec",
            "range": "stddev: 0.000005515654405864584",
            "extra": "mean: 104.03402386715818 usec\nrounds: 2891"
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
          "id": "4004341fd28859790c5f062d427133e7f4ce12ef",
          "message": "fix: resource filter fails for prefixed terraform names (merges PR #319, addresses #304)\n\nfix: resource filter fails for prefixed terraform names and runs unfiltered on no match\n\n- Add suffix matching in _resolve_terraform_targets so prefixed resources\n  (e.g., ovf_ontap_node_01) match filter names (e.g., ontap-node-01)\n- Skip terraform execution when no targets match instead of running\n  unfiltered against all resources\n- Add tests for exact match, prefix/suffix match, no match, and skip behavior\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-08T10:41:58Z",
          "tree_id": "824047a9cd3d8439c146902f03f2fccfa17ed92d",
          "url": "https://github.com/endavis/infrafoundry/commit/4004341fd28859790c5f062d427133e7f4ce12ef"
        },
        "date": 1772966547252,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6968.359114364535,
            "unit": "iter/sec",
            "range": "stddev: 0.000008021726086519898",
            "extra": "mean: 143.5058072622299 usec\nrounds: 2506"
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
          "id": "47b078bcddd0f14cc53ea513bce66295ef7793cb",
          "message": "feat: add OVA-based VM creation support to Proxmox provider (merges PR #323, addresses #322)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-08T12:10:11Z",
          "tree_id": "93bb48b4a4d3de6aa56ad4cbbfcfe95459c2bbbe",
          "url": "https://github.com/endavis/infrafoundry/commit/47b078bcddd0f14cc53ea513bce66295ef7793cb"
        },
        "date": 1772971844731,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6362.711765703945,
            "unit": "iter/sec",
            "range": "stddev: 0.0000293952472826778",
            "extra": "mean: 157.16569236880463 usec\nrounds: 2529"
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
          "id": "fa803a6e71689e20c6ba60cd2cb943b8ebcb946a",
          "message": "feat: add example config and Ansible roles for Proxmox ONTAP Simulator cluster (merges PR #324, addresses #283)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-08T15:15:29Z",
          "tree_id": "8129e4f182bd4f8a4f2b9955874214a11507476b",
          "url": "https://github.com/endavis/infrafoundry/commit/fa803a6e71689e20c6ba60cd2cb943b8ebcb946a"
        },
        "date": 1772982957568,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7033.456116353524,
            "unit": "iter/sec",
            "range": "stddev: 0.000009225457585909492",
            "extra": "mean: 142.17761274928483 usec\nrounds: 2306"
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
          "id": "bea8c4d7b2051ac223dff0aad55080c865578f46",
          "message": "fix: use self references in OVA VM destroy provisioner (merges PR #326, addresses #325)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-08T15:51:16Z",
          "tree_id": "a452763771bbdbfb7c008e565f73920a4f543ca1",
          "url": "https://github.com/endavis/infrafoundry/commit/bea8c4d7b2051ac223dff0aad55080c865578f46"
        },
        "date": 1772985100636,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8729.074976578215,
            "unit": "iter/sec",
            "range": "stddev: 0.000024409311632981335",
            "extra": "mean: 114.55967587438441 usec\nrounds: 2715"
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
          "id": "542af1873f57e92f4ee2083774f64b8c3f78c0ec",
          "message": "fix: escape shell variables in OVA VM disk import loop for Terraform (merges PR #328, addresses #327)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-08T15:56:26Z",
          "tree_id": "cce9f930d9afe2e7f7af1bd4953c28d862e8552e",
          "url": "https://github.com/endavis/infrafoundry/commit/542af1873f57e92f4ee2083774f64b8c3f78c0ec"
        },
        "date": 1772985413703,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6513.984100720704,
            "unit": "iter/sec",
            "range": "stddev: 0.00002451619108721127",
            "extra": "mean: 153.5158797654051 usec\nrounds: 2229"
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
          "id": "baa87c938340d7eb13f2f3c6cdb689d07466d1d3",
          "message": "fix: always grep for unused0 in OVA disk import loop (merges PR #331, addresses #330)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-08T17:11:04Z",
          "tree_id": "7c587349759747f2b9b0c57e1e848159f84d7341",
          "url": "https://github.com/endavis/infrafoundry/commit/baa87c938340d7eb13f2f3c6cdb689d07466d1d3"
        },
        "date": 1772989894834,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6973.594934336527,
            "unit": "iter/sec",
            "range": "stddev: 0.000009929914312959382",
            "extra": "mean: 143.39806217826168 usec\nrounds: 2525"
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
          "id": "e73ef52ac35dfce4af73bf801b2a934f1139ca08",
          "message": "fix: use per-VM target_node as SSH target for OVA VMs (merges PR #333, addresses #332)\n\nfix: use per-VM target_node as SSH target instead of global ssh_hostname\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-08T18:00:38Z",
          "tree_id": "275811b50408b9d2d6794144a3f92b6b82543979",
          "url": "https://github.com/endavis/infrafoundry/commit/e73ef52ac35dfce4af73bf801b2a934f1139ca08"
        },
        "date": 1772992867778,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6923.583395798379,
            "unit": "iter/sec",
            "range": "stddev: 0.000009955849689672389",
            "extra": "mean: 144.433878070546 usec\nrounds: 2239"
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
          "id": "f80a7dd220a951c65ea003a86c143ffd7bdb131d",
          "message": "feat: emit runner lifecycle events in deployment executor (merges PR #335, addresses #334)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-10T16:19:51Z",
          "tree_id": "735229e00db38ae1512c74a09a8f137cc71fb785",
          "url": "https://github.com/endavis/infrafoundry/commit/f80a7dd220a951c65ea003a86c143ffd7bdb131d"
        },
        "date": 1773159643210,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7032.703596678645,
            "unit": "iter/sec",
            "range": "stddev: 0.000008183851706549252",
            "extra": "mean: 142.1928261660669 usec\nrounds: 2744"
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
          "id": "4f956fe16c4298ae32be984dd7099c2d3b339eb2",
          "message": "feat: wire events config to UnifiedEventBus (merges PR #337, addresses #336)\n\nfeat: wire events config in settings.yaml to UnifiedEventBus\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-10T17:29:50Z",
          "tree_id": "34ccfaf55a2da33e0f6ec4d9d4b152202042a4fe",
          "url": "https://github.com/endavis/infrafoundry/commit/4f956fe16c4298ae32be984dd7099c2d3b339eb2"
        },
        "date": 1773163821421,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6997.442438820977,
            "unit": "iter/sec",
            "range": "stddev: 0.000007798303163798977",
            "extra": "mean: 142.90935706053386 usec\nrounds: 2599"
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
          "id": "e7d6fbb3a92d388087423249eb3150e261d4d91d",
          "message": "fix: show event handler output and resolve scripts from config repo (merges PR #339, addresses #338)\n\n- Pass config_base_dir to EventManager in CLI so ScriptHandler resolves\n  scripts relative to the config repo, not the framework CWD\n- Add _print_handler_result() to UnifiedEventBus that prints handler\n  results (success/failure with stdout/stderr) to the Rich console\n- Add console parameter to UnifiedEventBus.__init__()\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-10T19:15:51Z",
          "tree_id": "84932fcaa5c8a1aee55440c2edd2165adc941583",
          "url": "https://github.com/endavis/infrafoundry/commit/e7d6fbb3a92d388087423249eb3150e261d4d91d"
        },
        "date": 1773170181732,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6917.279365575925,
            "unit": "iter/sec",
            "range": "stddev: 0.00001036360000748939",
            "extra": "mean: 144.5655072103252 usec\nrounds: 2011"
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
          "id": "38452d20efdd651e2874045da6b82b158295b766",
          "message": "feat: add INFRAFOUNDRY_PHASE env var to runner events (merges PR #341, addresses #340)\n\nAdd phase field (plan/apply/destroy) to RunnerEventData so event handler\nscripts can distinguish which workflow phase triggered the event. Inject\nas INFRAFOUNDRY_PHASE in ScriptHandler environment variables.\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-10T19:55:17Z",
          "tree_id": "b166555a36a2f8eba22ce5f85057ba190bb90f7a",
          "url": "https://github.com/endavis/infrafoundry/commit/38452d20efdd651e2874045da6b82b158295b766"
        },
        "date": 1773172546797,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6851.00780316521,
            "unit": "iter/sec",
            "range": "stddev: 0.00001670401155690002",
            "extra": "mean: 145.96392658288806 usec\nrounds: 2479"
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
          "id": "7b2a1141c6c7fe81032826c8a5fbb270f3b05eb7",
          "message": "feat: stream event handler output in real-time (merges PR #343, addresses #342)\n\nReplace subprocess.run with subprocess.Popen and threaded stream\nreaders in ScriptHandler so stdout/stderr are printed to the Rich\nconsole line-by-line as the script runs, instead of being buffered\nuntil completion.\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-11T11:31:23Z",
          "tree_id": "95aec8195735f7d9c300aabaf9bb5e6cbb0affb7",
          "url": "https://github.com/endavis/infrafoundry/commit/7b2a1141c6c7fe81032826c8a5fbb270f3b05eb7"
        },
        "date": 1773228712838,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7059.086507131006,
            "unit": "iter/sec",
            "range": "stddev: 0.000008436563937999455",
            "extra": "mean: 141.6613890465589 usec\nrounds: 3524"
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
          "id": "f4d08017cef9da381bc05f82049fdd558d62574d",
          "message": "feat: add infrastructure packages with infrafoundry.yml manifest (merges PR #345, addresses #344)\n\n* feat: add infrastructure packages with infrafoundry.yml manifest\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n\n* fix: suppress bandit B701 false positive for YAML Jinja2 rendering\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-11T14:48:31Z",
          "tree_id": "62235c0657ebed9008d29678c487f05cc03d7c40",
          "url": "https://github.com/endavis/infrafoundry/commit/f4d08017cef9da381bc05f82049fdd558d62574d"
        },
        "date": 1773240540619,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7029.625441996142,
            "unit": "iter/sec",
            "range": "stddev: 0.000008364801347473809",
            "extra": "mean: 142.255090011743 usec\nrounds: 2533"
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
          "id": "f0b14089f1de4bec9616c056ee29889847ee49a5",
          "message": "fix: always clear event handlers before loading to prevent duplicates (merges PR #351, addresses #350)\n\n_load_event_config() returned early without calling clear_handlers() when\nenv_config.events was empty. When package events moved from settings.yaml\nto infrafoundry.yml manifests, settings.yaml had no events, so handlers\nwere never cleared between plan and apply phases. Package events\naccumulated, causing event handlers to fire multiple times.\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-11T17:54:39Z",
          "tree_id": "b7716193b8a95d543f0cf4f8fc1573294c0fbd51",
          "url": "https://github.com/endavis/infrafoundry/commit/f0b14089f1de4bec9616c056ee29889847ee49a5"
        },
        "date": 1773251710953,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6942.85297219135,
            "unit": "iter/sec",
            "range": "stddev: 0.000009258486272362607",
            "extra": "mean: 144.03300833322606 usec\nrounds: 2280"
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
          "id": "d4bb97be75c763fa661d8ebcc4beb1acd0ac7589",
          "message": "fix: clear stale package events buffer before reloading (merges PR #353, addresses #352)\n\nget_all_resources_all_providers() is called by both _load_resources()\n(which drains the event buffer) and build_dependency_graph() (which\ndoes not). When build_dependency_graph() runs first during the plan\nphase, stale events accumulate in _pending_package_events and persist\ninto the apply phase, causing event handlers to fire twice.\n\nClear _pending_package_events at the start of\nget_all_resources_all_providers() so each call starts fresh.\n\nAddresses #352",
          "timestamp": "2026-03-12T12:42:25Z",
          "tree_id": "f2b9a651d66375e0ff2816d52efbd27efd107040",
          "url": "https://github.com/endavis/infrafoundry/commit/d4bb97be75c763fa661d8ebcc4beb1acd0ac7589"
        },
        "date": 1773319375208,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6994.7886460443515,
            "unit": "iter/sec",
            "range": "stddev: 0.000007453946525544841",
            "extra": "mean: 142.9635762569486 usec\nrounds: 2367"
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
          "id": "a5206c76a3f918b9cf4d04f62d96f6e6f44025f4",
          "message": "feat: support resource-centric format in package loader (merges PR #355, addresses #354)\n\nAdd cross-provider resource support to PackageLoader. Resource files\ncan now use a `resources:` key where each item declares its own\nprovider and type, enabling packages to manage resources across\nmultiple providers (e.g., OPNsense DHCP reservations in a Proxmox\npackage).\n\nAddresses #354\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-12T15:00:56Z",
          "tree_id": "c7533b260ffc258cebf6cf9b32f476047304e8bb",
          "url": "https://github.com/endavis/infrafoundry/commit/a5206c76a3f918b9cf4d04f62d96f6e6f44025f4"
        },
        "date": 1773327687803,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6997.60405836922,
            "unit": "iter/sec",
            "range": "stddev: 0.00001164866674486126",
            "extra": "mean: 142.9060563671058 usec\nrounds: 2395"
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
          "id": "c9809f1a8a488f4493eea7b15ae1d687e75d8ccc",
          "message": "chore: migrate ONTAP lab example to infrastructure package (merges PR #356, addresses #346)\n\nMove the ONTAP Simulator lab from scattered files into a self-contained\ninfrastructure package at envs/dev/proxmox/ontap-cluster/. All variables\nare centralized in infrafoundry.yml — the only file users need to edit.\nUses expect-script approach for serial console automation, with dynamic\ninventory generation at runtime.\n\nAddresses #346\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-12T15:10:18Z",
          "tree_id": "142bac1b245b8a5192d163432926d6f1eaf303e8",
          "url": "https://github.com/endavis/infrafoundry/commit/c9809f1a8a488f4493eea7b15ae1d687e75d8ccc"
        },
        "date": 1773328248667,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6736.095893214641,
            "unit": "iter/sec",
            "range": "stddev: 0.000019787870983002042",
            "extra": "mean: 148.45394362739302 usec\nrounds: 2040"
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
          "id": "e1d8e00ccb16ae8e280702c47f01ffea1b0252d1",
          "message": "fix: resolve destroy command double-prompting for confirmation (merges PR #358, addresses #349)\n\nMove confirmation from orchestrator callback to CLI level, matching\nthe apply command pattern. After user confirms, auto_approve is set\nto True so Terraform does not prompt again.\n\nAddresses #349\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-12T15:24:08Z",
          "tree_id": "fe63da54605aeca9f5ca5a923bd08ecf040c80f4",
          "url": "https://github.com/endavis/infrafoundry/commit/e1d8e00ccb16ae8e280702c47f01ffea1b0252d1"
        },
        "date": 1773329079172,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7007.593833841131,
            "unit": "iter/sec",
            "range": "stddev: 0.000009099844203029177",
            "extra": "mean: 142.70233459747504 usec\nrounds: 2373"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "88e3b34b219c18cede3d85119dcad543cbbe2aaa",
          "message": "chore(deps): bump mkdocs-material from 9.7.1 to 9.7.2 (merges PR #277)\n\nBumps [mkdocs-material](https://github.com/squidfunk/mkdocs-material) from 9.7.1 to 9.7.2.\n- [Release notes](https://github.com/squidfunk/mkdocs-material/releases)\n- [Changelog](https://github.com/squidfunk/mkdocs-material/blob/master/CHANGELOG)\n- [Commits](https://github.com/squidfunk/mkdocs-material/compare/9.7.1...9.7.2)\n\n---\nupdated-dependencies:\n- dependency-name: mkdocs-material\n  dependency-version: 9.7.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-12T15:27:44Z",
          "tree_id": "b42ade2703675ce31ba673eba436d84b5554cea4",
          "url": "https://github.com/endavis/infrafoundry/commit/88e3b34b219c18cede3d85119dcad543cbbe2aaa"
        },
        "date": 1773329295861,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6923.730703304259,
            "unit": "iter/sec",
            "range": "stddev: 0.000008959752278579272",
            "extra": "mean: 144.43080513266688 usec\nrounds: 2299"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "36351513fdc889d52cac9fc646518eaa4239b9f0",
          "message": "chore(deps): bump types-boto3 from 1.42.39 to 1.42.54 (merges PR #276)\n\nBumps [types-boto3](https://github.com/youtype/mypy_boto3_builder) from 1.42.39 to 1.42.54.\n- [Release notes](https://github.com/youtype/mypy_boto3_builder/releases)\n- [Commits](https://github.com/youtype/mypy_boto3_builder/commits)\n\n---\nupdated-dependencies:\n- dependency-name: types-boto3\n  dependency-version: 1.42.54\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-12T15:33:21Z",
          "tree_id": "189f9b7b0bf1609fb4ed0b9fdec92b5d5a9c3f6f",
          "url": "https://github.com/endavis/infrafoundry/commit/36351513fdc889d52cac9fc646518eaa4239b9f0"
        },
        "date": 1773329638368,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6944.539994408692,
            "unit": "iter/sec",
            "range": "stddev: 0.000009109523579414205",
            "extra": "mean: 143.9980187032024 usec\nrounds: 2406"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2a25107b34151a3b554b4a32309cf27fd5e0285c",
          "message": "chore(deps): bump commitizen from 4.13.0 to 4.13.8 (merges PR #275)\n\nBumps [commitizen](https://github.com/commitizen-tools/commitizen) from 4.13.0 to 4.13.8.\n- [Release notes](https://github.com/commitizen-tools/commitizen/releases)\n- [Changelog](https://github.com/commitizen-tools/commitizen/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/commitizen-tools/commitizen/compare/v4.13.0...v4.13.8)\n\n---\nupdated-dependencies:\n- dependency-name: commitizen\n  dependency-version: 4.13.8\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-12T15:41:27Z",
          "tree_id": "eb2d72c2bbd043b097856f4fd725bfba8e9597d0",
          "url": "https://github.com/endavis/infrafoundry/commit/2a25107b34151a3b554b4a32309cf27fd5e0285c"
        },
        "date": 1773330119082,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 5945.448475284521,
            "unit": "iter/sec",
            "range": "stddev: 0.00003750822532688722",
            "extra": "mean: 168.19589037850415 usec\nrounds: 2536"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "914b0768a4f02a62d8c0ad309076ac5dcddf3dff",
          "message": "chore(deps): bump boto3 from 1.42.39 to 1.42.54 (merges PR #274)\n\nBumps [boto3](https://github.com/boto/boto3) from 1.42.39 to 1.42.54.\n- [Release notes](https://github.com/boto/boto3/releases)\n- [Commits](https://github.com/boto/boto3/compare/1.42.39...1.42.54)\n\n---\nupdated-dependencies:\n- dependency-name: boto3\n  dependency-version: 1.42.54\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-12T15:45:42Z",
          "tree_id": "4943b741ddfecf3d0edc162256e1ab133e221704",
          "url": "https://github.com/endavis/infrafoundry/commit/914b0768a4f02a62d8c0ad309076ac5dcddf3dff"
        },
        "date": 1773330382224,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7072.581659287173,
            "unit": "iter/sec",
            "range": "stddev: 0.000008635682245495203",
            "extra": "mean: 141.39108576949076 usec\nrounds: 3626"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "dda2f03e303a1621c26833a3970cdeea496ca344",
          "message": "chore(deps): bump pyproject-fmt from 2.12.1 to 2.16.1 (merges PR #273)\n\nBumps [pyproject-fmt](https://github.com/tox-dev/toml-fmt) from 2.12.1 to 2.16.1.\n- [Release notes](https://github.com/tox-dev/toml-fmt/releases)\n- [Commits](https://github.com/tox-dev/toml-fmt/compare/pyproject-fmt/2.12.1...pyproject-fmt/2.16.1)\n\n---\nupdated-dependencies:\n- dependency-name: pyproject-fmt\n  dependency-version: 2.16.1\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-12T15:50:39Z",
          "tree_id": "334d929710d574d6158766857c31ff22f612a9ac",
          "url": "https://github.com/endavis/infrafoundry/commit/dda2f03e303a1621c26833a3970cdeea496ca344"
        },
        "date": 1773330671711,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6898.647258470349,
            "unit": "iter/sec",
            "range": "stddev: 0.000007662165717918045",
            "extra": "mean: 144.95595477391203 usec\nrounds: 2388"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1ab71f8057738b2233af8359b4ec75b01d31a369",
          "message": "chore(deps): bump azure-identity from 1.25.1 to 1.25.2 (merges PR #270)\n\nBumps [azure-identity](https://github.com/Azure/azure-sdk-for-python) from 1.25.1 to 1.25.2.\n- [Release notes](https://github.com/Azure/azure-sdk-for-python/releases)\n- [Commits](https://github.com/Azure/azure-sdk-for-python/compare/azure-identity_1.25.1...azure-identity_1.25.2)\n\n---\nupdated-dependencies:\n- dependency-name: azure-identity\n  dependency-version: 1.25.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-12T15:54:52Z",
          "tree_id": "464725a278c450186a4e43ac782a994dc579f7d6",
          "url": "https://github.com/endavis/infrafoundry/commit/1ab71f8057738b2233af8359b4ec75b01d31a369"
        },
        "date": 1773330929468,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6847.752054564597,
            "unit": "iter/sec",
            "range": "stddev: 0.000016719079280524105",
            "extra": "mean: 146.03332480962376 usec\nrounds: 2229"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f198f5f1ccf8fed1599640ea3e60ae8423ec75c5",
          "message": "chore(deps): bump opnsense-openapi from 0.1.0 to 0.2.0 (merges PR #269)\n\nBumps [opnsense-openapi](https://github.com/endavis/opnsense-openapi) from 0.1.0 to 0.2.0.\n- [Commits](https://github.com/endavis/opnsense-openapi/compare/v0.1.0...v0.2.0)\n\n---\nupdated-dependencies:\n- dependency-name: opnsense-openapi\n  dependency-version: 0.2.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-12T15:59:01Z",
          "tree_id": "b334bcc02d350c66ef29c392ea12dcf22f63c30b",
          "url": "https://github.com/endavis/infrafoundry/commit/f198f5f1ccf8fed1599640ea3e60ae8423ec75c5"
        },
        "date": 1773331174295,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8451.524636598084,
            "unit": "iter/sec",
            "range": "stddev: 0.000025653230571767144",
            "extra": "mean: 118.32184641214288 usec\nrounds: 2676"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "d6e3f9710433dffac345f9a5531fc1e3b2b3051f",
          "message": "chore(deps): bump doit from 0.36.0 to 0.37.0 (merges PR #265)\n\nBumps [doit](https://github.com/pydoit/doit) from 0.36.0 to 0.37.0.\n- [Changelog](https://github.com/pydoit/doit/blob/master/CHANGES)\n- [Commits](https://github.com/pydoit/doit/compare/0.36.0...0.37.0)\n\n---\nupdated-dependencies:\n- dependency-name: doit\n  dependency-version: 0.37.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-12T16:08:12Z",
          "tree_id": "0243220ae3334ecd8f21f632b773280998b18e62",
          "url": "https://github.com/endavis/infrafoundry/commit/d6e3f9710433dffac345f9a5531fc1e3b2b3051f"
        },
        "date": 1773331726626,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6199.509189626749,
            "unit": "iter/sec",
            "range": "stddev: 0.00003424866670103043",
            "extra": "mean: 161.303091811403 usec\nrounds: 1612"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "021f64369a7579b4acf52b24fb750f73ffca38b7",
          "message": "chore(deps): bump pyinfra from 3.6 to 3.6.1 (merges PR #262)\n\nBumps [pyinfra](https://github.com/pyinfra-dev/pyinfra) from 3.6 to 3.6.1.\n- [Release notes](https://github.com/pyinfra-dev/pyinfra/releases)\n- [Changelog](https://github.com/pyinfra-dev/pyinfra/blob/3.x/CHANGELOG.md)\n- [Commits](https://github.com/pyinfra-dev/pyinfra/compare/v3.6...v3.6.1)\n\n---\nupdated-dependencies:\n- dependency-name: pyinfra\n  dependency-version: 3.6.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-12T16:12:17Z",
          "tree_id": "8c6cc67330efe34213a69dae912915809492a8fb",
          "url": "https://github.com/endavis/infrafoundry/commit/021f64369a7579b4acf52b24fb750f73ffca38b7"
        },
        "date": 1773331970260,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6922.846153760466,
            "unit": "iter/sec",
            "range": "stddev: 0.000011176493966238557",
            "extra": "mean: 144.44925942154637 usec\nrounds: 2282"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "10521ac089f9c58eb2e950c89199ed2bb5deaa2d",
          "message": "chore(deps): bump hashicorp/setup-terraform from 3 to 4 (merges PR #278)\n\nBumps [hashicorp/setup-terraform](https://github.com/hashicorp/setup-terraform) from 3 to 4.\n- [Release notes](https://github.com/hashicorp/setup-terraform/releases)\n- [Changelog](https://github.com/hashicorp/setup-terraform/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/hashicorp/setup-terraform/compare/v3...v4)\n\n---\nupdated-dependencies:\n- dependency-name: hashicorp/setup-terraform\n  dependency-version: '4'\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-12T16:19:08Z",
          "tree_id": "8fcc7a36b161707bb2e77963e4b1d314dfff097d",
          "url": "https://github.com/endavis/infrafoundry/commit/10521ac089f9c58eb2e950c89199ed2bb5deaa2d"
        },
        "date": 1773332379172,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6799.82993974558,
            "unit": "iter/sec",
            "range": "stddev: 0.000020694936217681595",
            "extra": "mean: 147.06250139505926 usec\nrounds: 2150"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2cb8707379502aedacb2755573bc1b589d0b5c53",
          "message": "chore(deps): bump actions/download-artifact from 7 to 8 (merges PR #279)\n\nBumps [actions/download-artifact](https://github.com/actions/download-artifact) from 7 to 8.\n- [Release notes](https://github.com/actions/download-artifact/releases)\n- [Commits](https://github.com/actions/download-artifact/compare/v7...v8)\n\n---\nupdated-dependencies:\n- dependency-name: actions/download-artifact\n  dependency-version: '8'\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-12T16:22:42Z",
          "tree_id": "153dc7543a4d7a0f75a1d4a871c9e12ac674c4e1",
          "url": "https://github.com/endavis/infrafoundry/commit/2cb8707379502aedacb2755573bc1b589d0b5c53"
        },
        "date": 1773332593908,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7088.672215911548,
            "unit": "iter/sec",
            "range": "stddev: 0.000007590403699868735",
            "extra": "mean: 141.07014255157063 usec\nrounds: 2336"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "4861fdce3b2d0aa29ac4e8a2cc015053950eb0eb",
          "message": "chore(deps): bump actions/upload-artifact from 6 to 7 (merges PR #280)\n\nBumps [actions/upload-artifact](https://github.com/actions/upload-artifact) from 6 to 7.\n- [Release notes](https://github.com/actions/upload-artifact/releases)\n- [Commits](https://github.com/actions/upload-artifact/compare/v6...v7)\n\n---\nupdated-dependencies:\n- dependency-name: actions/upload-artifact\n  dependency-version: '7'\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-12T16:26:27Z",
          "tree_id": "22b3eae63b692ffa5c0496f04592dd236b828108",
          "url": "https://github.com/endavis/infrafoundry/commit/4861fdce3b2d0aa29ac4e8a2cc015053950eb0eb"
        },
        "date": 1773332817362,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6946.925578122014,
            "unit": "iter/sec",
            "range": "stddev: 0.000007856448385659659",
            "extra": "mean: 143.94856958728693 usec\nrounds: 2249"
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
          "id": "08f9ee24faf6f65fd6d94bedac6dac840a707da8",
          "message": "chore: update all dependencies and migrate to StrEnum (merges PR #361, addresses #360)\n\nUpdate all dependencies via uv lock --upgrade. Notable updates:\nruff 0.14.14 → 0.15.5, ansible 13.3.0 → 13.4.0,\ncryptography 46.0.3 → 46.0.5, sqlalchemy 2.0.46 → 2.0.48.\n\nMigrate 11 (str, Enum) classes to StrEnum per ruff UP042 rule\nand apply ruff 0.15 formatting changes.\n\nAddresses #360\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-13T09:45:13Z",
          "tree_id": "7110d84d0b87fc6041b2a98780bf150b91aa9617",
          "url": "https://github.com/endavis/infrafoundry/commit/08f9ee24faf6f65fd6d94bedac6dac840a707da8"
        },
        "date": 1773395150493,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6534.8436607230815,
            "unit": "iter/sec",
            "range": "stddev: 0.00020696013079272041",
            "extra": "mean: 153.02584911256312 usec\nrounds: 2366"
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
          "id": "ac89864e830d75f99ac7aef1d75f40a690cb7d91",
          "message": "fix: correct resource-centric name injection and clean stale .tf files (merges PR #365, addresses #364)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-13T10:20:15Z",
          "tree_id": "456ebc17eaacd96627dab79e0e634ff4a6b24222",
          "url": "https://github.com/endavis/infrafoundry/commit/ac89864e830d75f99ac7aef1d75f40a690cb7d91"
        },
        "date": 1773397247220,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9645.838857538347,
            "unit": "iter/sec",
            "range": "stddev: 0.000004399189790080742",
            "extra": "mean: 103.67164689035698 usec\nrounds: 2798"
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
          "id": "36c388a6c9f76467cec0ce6ba9a50ed0aa47020c",
          "message": "feat: support resource-scoped event handlers in package manifests (merges PR #368, addresses #363)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-13T18:55:32Z",
          "tree_id": "20b619e85b9872801cae27ff526feb5f911ef314",
          "url": "https://github.com/endavis/infrafoundry/commit/36c388a6c9f76467cec0ce6ba9a50ed0aa47020c"
        },
        "date": 1773428165499,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8558.591692969814,
            "unit": "iter/sec",
            "range": "stddev: 0.000016398406129388543",
            "extra": "mean: 116.84165291135673 usec\nrounds: 2181"
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
          "id": "cd476bdabaad57ca9ff56d2e222fea8c63f5adc1",
          "message": "refactor: replace null_resource template provisioners with native proxmox provider resources (merges PR #369, addresses #366)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-13T19:31:40Z",
          "tree_id": "85a254d772a5fc0e17b8445a41db9ea86158fcfc",
          "url": "https://github.com/endavis/infrafoundry/commit/cd476bdabaad57ca9ff56d2e222fea8c63f5adc1"
        },
        "date": 1773430338750,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6872.315979448821,
            "unit": "iter/sec",
            "range": "stddev: 0.000018039316691679812",
            "extra": "mean: 145.51135352193202 usec\nrounds: 2229"
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
          "id": "38393e3d2c73323c7e906d9083f8d3eeea5e6124",
          "message": "fix: parse ova disk path from import output instead of fragile unused0 lookup (merges PR #371, addresses #370)\n\n* fix: parse ova disk path from import output instead of fragile unused0 lookup\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n\n* test: update ova disk import test for new parsing approach\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-13T21:27:54Z",
          "tree_id": "8ab9d4b4e11095b14b773e21ece09cb4a38d1ac9",
          "url": "https://github.com/endavis/infrafoundry/commit/38393e3d2c73323c7e906d9083f8d3eeea5e6124"
        },
        "date": 1773437312123,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6834.338851237599,
            "unit": "iter/sec",
            "range": "stddev: 0.000029672616249373274",
            "extra": "mean: 146.31993258849238 usec\nrounds: 2685"
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
          "id": "39059ca78695637bf8561e2b8fba51b9550478f7",
          "message": "fix: raise error when -r resource filter matches no resources (merges PR #372, addresses #367)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-14T09:29:46Z",
          "tree_id": "11db1c4105b3f6fe7f5c32d4a205bb45a0e43dbf",
          "url": "https://github.com/endavis/infrafoundry/commit/39059ca78695637bf8561e2b8fba51b9550478f7"
        },
        "date": 1773480617951,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9060.438521881366,
            "unit": "iter/sec",
            "range": "stddev: 0.00001816994198145864",
            "extra": "mean: 110.36993381556037 usec\nrounds: 2765"
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
          "id": "90171fb142fafd9e321d53cd1371f6ce94da5830",
          "message": "feat: add package model foundation with env-root discovery (merges PR #373, addresses #357)\n\nfeat: add env-root package discovery and loose resource deprecation\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-14T10:39:12Z",
          "tree_id": "1fc586fa33c01a0722d1285b8b3ef48a90baef6c",
          "url": "https://github.com/endavis/infrafoundry/commit/90171fb142fafd9e321d53cd1371f6ce94da5830"
        },
        "date": 1773484782291,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6784.577457158054,
            "unit": "iter/sec",
            "range": "stddev: 0.000020715212299079996",
            "extra": "mean: 147.39311420860145 usec\nrounds: 2224"
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
          "id": "1b23bd9d355234d1c2e727b0b86178635f9c796c",
          "message": "feat: add per-package terraform state isolation (merges PR #374, addresses #357)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-14T11:21:52Z",
          "tree_id": "7beb1375f13f3bfb3510717fa1d394b2eb8156f8",
          "url": "https://github.com/endavis/infrafoundry/commit/1b23bd9d355234d1c2e727b0b86178635f9c796c"
        },
        "date": 1773487342690,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7070.782848335498,
            "unit": "iter/sec",
            "range": "stddev: 0.000010163228008783077",
            "extra": "mean: 141.42705573759852 usec\nrounds: 2135"
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
          "id": "89edb1f729edeb5c4da57e0eb6b8a4326e4081da",
          "message": "feat: add --package/-p CLI flag for plan, apply, and destroy (merges PR #375, addresses #357)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-14T11:44:22Z",
          "tree_id": "04174403cdf8fc9a8799628e073aec6af252210d",
          "url": "https://github.com/endavis/infrafoundry/commit/89edb1f729edeb5c4da57e0eb6b8a4326e4081da"
        },
        "date": 1773488692219,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6958.271241048682,
            "unit": "iter/sec",
            "range": "stddev: 0.00001129577926178701",
            "extra": "mean: 143.71385727258456 usec\nrounds: 2207"
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
          "id": "aedc717dde481e17ab9876a957e032cd962a569d",
          "message": "fix: skip non-matching packages and deduplicate resource filter (merges PR #379, addresses #376, #378)\n\nfix: skip non-matching packages during filtered plan/apply/destroy\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-14T13:36:56Z",
          "tree_id": "3ffe8df8bd14ba87da9e89f58a5b0fdc27c46ade",
          "url": "https://github.com/endavis/infrafoundry/commit/aedc717dde481e17ab9876a957e032cd962a569d"
        },
        "date": 1773495448021,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9659.055270959068,
            "unit": "iter/sec",
            "range": "stddev: 0.000004306533155032207",
            "extra": "mean: 103.52979374769723 usec\nrounds: 2783"
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
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "distinct": true,
          "id": "9ba889143488659a01d7310c8df6be8b9806c0ef",
          "message": "fix: namespace provider files in per-package terraform directories\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-14T13:47:17Z",
          "tree_id": "73f6ede762cdc29f136cb9fbaf868d02665c0a1d",
          "url": "https://github.com/endavis/infrafoundry/commit/9ba889143488659a01d7310c8df6be8b9806c0ef"
        },
        "date": 1773496069563,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6882.051123614969,
            "unit": "iter/sec",
            "range": "stddev: 0.00001004679098196904",
            "extra": "mean: 145.30551750314885 usec\nrounds: 2371"
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
          "id": "aedc717dde481e17ab9876a957e032cd962a569d",
          "message": "fix: skip non-matching packages and deduplicate resource filter (merges PR #379, addresses #376, #378)\n\nfix: skip non-matching packages during filtered plan/apply/destroy\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-14T13:36:56Z",
          "tree_id": "3ffe8df8bd14ba87da9e89f58a5b0fdc27c46ade",
          "url": "https://github.com/endavis/infrafoundry/commit/aedc717dde481e17ab9876a957e032cd962a569d"
        },
        "date": 1773496259019,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9409.027510316828,
            "unit": "iter/sec",
            "range": "stddev: 0.000013967928368439583",
            "extra": "mean: 106.28090936109159 usec\nrounds: 2692"
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
          "id": "c6a2b29fa43f5532ae387d1357d476a00a78a66f",
          "message": "fix: namespace provider files in per-package terraform directories (merges PR #381, addresses #380)\n\n* fix: namespace provider files in per-package terraform directories\n\nIn package context, provider.tf, variables.tf, outputs.tf, terraform.tfvars,\nand secrets.auto.tfvars are now namespaced by provider name to prevent\noverwriting when multiple providers share a package directory. Stale file\ncleanup is skipped in package context to preserve other providers' files.\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n\n* fix: block all git push to protected branches, not just force push\n\nAlso fixes false positive where git stash push was matched as git push.\n\nCo-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-14T14:52:55Z",
          "tree_id": "ff9b5b6876f5647d8690ac07d0f6a06d99452ff6",
          "url": "https://github.com/endavis/infrafoundry/commit/c6a2b29fa43f5532ae387d1357d476a00a78a66f"
        },
        "date": 1773500012940,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7089.465062945435,
            "unit": "iter/sec",
            "range": "stddev: 0.000008841772001876331",
            "extra": "mean: 141.05436603767302 usec\nrounds: 2385"
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
          "id": "e90690948f588650edde9f4cb0a31aadbacdfa60",
          "message": "fix: merge required_providers into shared file for multi-provider packages (merges PR #382, addresses #380)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-14T15:14:58Z",
          "tree_id": "f9ddf413ece9321e4c2b5620ebfad402ec7f52c6",
          "url": "https://github.com/endavis/infrafoundry/commit/e90690948f588650edde9f4cb0a31aadbacdfa60"
        },
        "date": 1773501334844,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7085.416537725656,
            "unit": "iter/sec",
            "range": "stddev: 0.000007972967865165166",
            "extra": "mean: 141.1349628741784 usec\nrounds: 2505"
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
          "id": "effb8326b5669a47625b0760d3c7a0164b92c98c",
          "message": "fix: auto-load tfvars and upgrade lock file for multi-provider packages (merges PR #383, addresses #380)\n\n- Rename terraform_{name}.tfvars to {name}.auto.tfvars so terraform\n  auto-loads them (only terraform.tfvars and *.auto.tfvars are auto-loaded)\n- Detect missing providers in lock file and run terraform init -upgrade\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-14T16:45:33Z",
          "tree_id": "65b001c3011c5259e56c7befaeed73f0c52c242c",
          "url": "https://github.com/endavis/infrafoundry/commit/effb8326b5669a47625b0760d3c7a0164b92c98c"
        },
        "date": 1773506765641,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6981.977911174229,
            "unit": "iter/sec",
            "range": "stddev: 0.00001313567637130104",
            "extra": "mean: 143.2258899587123 usec\nrounds: 2181"
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
          "id": "06d317e2e8284c15b12409a48935d042b7bff954",
          "message": "fix: decrypt SOPS-encrypted settings.yaml before generating tfvars (merges PR #385, addresses #384)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-14T17:26:45Z",
          "tree_id": "11f950e4c39d4d7f98720f25136b0ab8817bf25e",
          "url": "https://github.com/endavis/infrafoundry/commit/06d317e2e8284c15b12409a48935d042b7bff954"
        },
        "date": 1773509236049,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7030.789865064862,
            "unit": "iter/sec",
            "range": "stddev: 0.000008740904729365387",
            "extra": "mean: 142.23153005452178 usec\nrounds: 2379"
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
          "id": "39059ca78695637bf8561e2b8fba51b9550478f7",
          "message": "fix: raise error when -r resource filter matches no resources (merges PR #372, addresses #367)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-14T09:29:46Z",
          "tree_id": "11db1c4105b3f6fe7f5c32d4a205bb45a0e43dbf",
          "url": "https://github.com/endavis/infrafoundry/commit/39059ca78695637bf8561e2b8fba51b9550478f7"
        },
        "date": 1773512127603,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9694.164305031401,
            "unit": "iter/sec",
            "range": "stddev: 0.00000385175076106273",
            "extra": "mean: 103.15484331960276 usec\nrounds: 2687"
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
          "id": "aae42fe44a904359a62d6d541ffc012144b1a931",
          "message": "feat: packages as primary resource model with shared provider state (merges PR #386, addresses #357)\n\nfeat: packages as primary resource model (without per-package state isolation)\n\nAdds env-root package discovery, provider field on manifest, --package CLI\nflag, loose resource deprecation, SOPS settings decryption, and push-to-main\nhook protection. Uses shared per-provider terraform state with -target\nfiltering instead of per-package state isolation.\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-14T18:25:41Z",
          "tree_id": "18cf8258516c08488eac6e8b1aee353d4cf55203",
          "url": "https://github.com/endavis/infrafoundry/commit/aae42fe44a904359a62d6d541ffc012144b1a931"
        },
        "date": 1773512771665,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9605.633422000765,
            "unit": "iter/sec",
            "range": "stddev: 0.00000428582939511193",
            "extra": "mean: 104.10557597478139 usec\nrounds: 2797"
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
          "id": "978ed9608cdc08c1d3f91c878e4359b4e63d0d37",
          "message": "fix: replace runner-level event blocking with outcome-based resource lifecycle events (merges PR #392, addresses #390, #388)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-15T18:21:16Z",
          "tree_id": "524d2ea7e87ad6d83f0a4f55e77efcb0a257b1d2",
          "url": "https://github.com/endavis/infrafoundry/commit/978ed9608cdc08c1d3f91c878e4359b4e63d0d37"
        },
        "date": 1773598910859,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7058.007411233383,
            "unit": "iter/sec",
            "range": "stddev: 0.000008743462329382615",
            "extra": "mean: 141.68304759901784 usec\nrounds: 2374"
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
          "id": "9b0ea9c917f98b61673be9c5b4a35eef8b7ece89",
          "message": "fix: make ResourceOutcome JSON-serializable for audit logging (merges PR #393, addresses #390)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-15T18:52:08Z",
          "tree_id": "8bb6b31bd2a3b9d3a3af4ebd62e9f45a14e6c5da",
          "url": "https://github.com/endavis/infrafoundry/commit/9b0ea9c917f98b61673be9c5b4a35eef8b7ece89"
        },
        "date": 1773600759381,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9619.990422144729,
            "unit": "iter/sec",
            "range": "stddev: 0.000004359319010740227",
            "extra": "mean: 103.95020744491084 usec\nrounds: 2767"
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
          "id": "48912a13e8cadb9a787dd937e3aedecfb047bfcd",
          "message": "fix: support on_create/on_destroy/on_update aliases and requires group events (merges PR #395, addresses #390)\n\n- Map lifecycle aliases (on_create → resource_created) in event bus config loader\n- Add requires field support to matches_resources() — all required resources\n  must be present (group event semantics)\n- Per-resource RESOURCE_CREATED events pass only the single resource name as\n  target_resources so group handlers with requires don't match individual events\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-15T21:07:01Z",
          "tree_id": "258b6c7fc02f150685ae0db2affea75269f17ac2",
          "url": "https://github.com/endavis/infrafoundry/commit/48912a13e8cadb9a787dd937e3aedecfb047bfcd"
        },
        "date": 1773608856107,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7024.486911008983,
            "unit": "iter/sec",
            "range": "stddev: 0.000008373511251836008",
            "extra": "mean: 142.3591520161808 usec\nrounds: 2480"
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
          "id": "ec38b4c1d40e3f7c5d44c456160fb4aaa580755b",
          "message": "fix: prevent group event handlers from firing per-resource (merges PR #397, addresses #394)\n\nfix: pass single resource name in per-resource RESOURCE_CREATED emissions\n\nThe old RESOURCE_CREATED emission in apply_single_provider passed the full\nCLI resource_filter as target_resources, causing group handlers with\nrequires: [a, b] to match individual resource events. Now passes only\n[resource.name] so group handlers only match the aggregate emission.\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-16T00:56:40Z",
          "tree_id": "be44e2ee0e71079dd8702bf7936c9d58866ded44",
          "url": "https://github.com/endavis/infrafoundry/commit/ec38b4c1d40e3f7c5d44c456160fb4aaa580755b"
        },
        "date": 1773622631353,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7001.515707449657,
            "unit": "iter/sec",
            "range": "stddev: 0.000011487471386439365",
            "extra": "mean: 142.82621674846686 usec\nrounds: 2436"
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
          "id": "18deb529dab153b184135575b05c7bf0b8df8d72",
          "message": "fix: use suffix matching for terraform_data address-to-name mapping (merges PR #402, addresses #396)\n\nCo-authored-by: Claude Opus 4.6 <noreply@anthropic.com>",
          "timestamp": "2026-03-16T09:58:54Z",
          "tree_id": "096746cb16adbcffbfffa0bba5afe5b40efbd55c",
          "url": "https://github.com/endavis/infrafoundry/commit/18deb529dab153b184135575b05c7bf0b8df8d72"
        },
        "date": 1773655166517,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9639.42817324843,
            "unit": "iter/sec",
            "range": "stddev: 0.000004400096579834577",
            "extra": "mean: 103.74059353180553 usec\nrounds: 2721"
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
          "id": "cd92cbb08a6b60142eaa6b8e6189e0163b82d1f9",
          "message": "fix: proxmox VM template defaults for clones, CPU, and cloud-init (merges PR #404, addresses #403)\n\nfix: proxmox VM template defaults for clones, CPU type, and cloud-init escaping\n\n- Allow disk block on cloned VMs for resize (was skipped entirely)\n- Default disk interface to scsi0 for clones (matches virtio-scsi-pci controller)\n- Change default CPU type from kvm64 to host (modern distros need x86-64-v2)\n- Escape ${...} in cloud-init snippets for terraform heredoc compatibility",
          "timestamp": "2026-03-16T12:48:02Z",
          "tree_id": "f308c8c72c75edd75cc0560bc048510a05286bf5",
          "url": "https://github.com/endavis/infrafoundry/commit/cd92cbb08a6b60142eaa6b8e6189e0163b82d1f9"
        },
        "date": 1773665314543,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7058.088767467708,
            "unit": "iter/sec",
            "range": "stddev: 0.00000920529968223612",
            "extra": "mean: 141.68141446580003 usec\nrounds: 2461"
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
          "id": "4475b5c2adbe7a9a800118521be23920c86f10c5",
          "message": "fix: add type-aware event filtering to prevent duplicate handler firing (merges PR #406, addresses #405)",
          "timestamp": "2026-03-16T16:32:17Z",
          "tree_id": "c840d49f370be7376219750cb506bd8ce31f92f7",
          "url": "https://github.com/endavis/infrafoundry/commit/4475b5c2adbe7a9a800118521be23920c86f10c5"
        },
        "date": 1773678771835,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7029.184770189912,
            "unit": "iter/sec",
            "range": "stddev: 0.00000765392180491346",
            "extra": "mean: 142.26400823049957 usec\nrounds: 2430"
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
          "id": "a0448ca57cc08d48aea47fb27ecc491e508326c2",
          "message": "docs: update ontap-cluster example and add aiqum example package (merges PR #408, addresses #407)\n\n* docs: update ontap-cluster example and add aiqum example package\n\n* fix: remove clear-text password logging from aiqum setup script",
          "timestamp": "2026-03-16T19:55:02Z",
          "tree_id": "97aa7e7513a0c43a446b32ca1d7191db19113ed2",
          "url": "https://github.com/endavis/infrafoundry/commit/a0448ca57cc08d48aea47fb27ecc491e508326c2"
        },
        "date": 1773690941456,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7028.712208267641,
            "unit": "iter/sec",
            "range": "stddev: 0.000009130979724282525",
            "extra": "mean: 142.27357307697605 usec\nrounds: 2080"
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
          "id": "3c7d0b53c18417a8fe40f79b4b337cf6f4ab4e87",
          "message": "feat: add per-package secrets.yaml with SOPS decryption (merges PR #410, addresses #409)\n\nExtract shared load_yaml_with_sops() utility and wire it into\nPackageLoader to automatically detect, decrypt, and merge\nsecrets.yaml variables into package manifests. Update docs.",
          "timestamp": "2026-03-16T20:41:40Z",
          "tree_id": "3ddd8a4e3bc370ae1bdeba8516901ef1ec27103f",
          "url": "https://github.com/endavis/infrafoundry/commit/3c7d0b53c18417a8fe40f79b4b337cf6f4ab4e87"
        },
        "date": 1773693734231,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 5920.509941216206,
            "unit": "iter/sec",
            "range": "stddev: 0.00003660634602256199",
            "extra": "mean: 168.90436971288617 usec\nrounds: 1915"
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
          "id": "57d16730e6be4d61294f91ba4c985b4f50e3883d",
          "message": "feat: pass all variables via environment instead of files on disk (merges PR #414, addresses #413)\n\n- TerraformRunner sets TF_VAR_* env vars from provider settings/credentials\n- Remove secrets.auto.tfvars and terraform.tfvars file generation\n- Add package_variables to ResourceConfig and EventContext\n- ScriptHandler sets INFRAFOUNDRY_PACKAGE_VARS (JSON) and INFRAFOUNDRY_VAR_*\n- PackageLoader returns merged variables (including secrets.yaml) as third element\n- Aggregate events pass package_variables for group handlers",
          "timestamp": "2026-03-17T16:05:35Z",
          "tree_id": "3988988e22115382bdad218044b2c0d6906360c1",
          "url": "https://github.com/endavis/infrafoundry/commit/57d16730e6be4d61294f91ba4c985b4f50e3883d"
        },
        "date": 1773763577165,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6935.089465226601,
            "unit": "iter/sec",
            "range": "stddev: 0.000008476751675500235",
            "extra": "mean: 144.19424652185444 usec\nrounds: 2300"
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
          "id": "95444180e1100a13bc6b359f69e795198f4bd01a",
          "message": "fix: map credential env vars to TF_VAR_ for terraform authentication (merges PR #416, addresses #415)\n\n* fix: map credential env vars to TF_VAR_ for terraform authentication\n\n* fix: add nosec B105 for credential mapping variable names",
          "timestamp": "2026-03-17T16:55:47Z",
          "tree_id": "19afae858718305b61dc344a7a07628d5425b1dd",
          "url": "https://github.com/endavis/infrafoundry/commit/95444180e1100a13bc6b359f69e795198f4bd01a"
        },
        "date": 1773766581427,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8877.523172373329,
            "unit": "iter/sec",
            "range": "stddev: 0.000007704825771090361",
            "extra": "mean: 112.64403151455348 usec\nrounds: 2126"
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
          "id": "482087554ffbaeab551f5cbd1aee5a87080313f9",
          "message": "fix: correct proxmox credential loader key names to match SOPS file (merges PR #417, addresses #415)\n\n* fix: correct proxmox credential loader key names to match SOPS file\n\n* test: update credential loader test to match corrected key names",
          "timestamp": "2026-03-17T18:03:15Z",
          "tree_id": "90bcbe8462298f68fd4c6374ef24eb745e578d66",
          "url": "https://github.com/endavis/infrafoundry/commit/482087554ffbaeab551f5cbd1aee5a87080313f9"
        },
        "date": 1773770626670,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8959.376141858877,
            "unit": "iter/sec",
            "range": "stddev: 0.000006816210213540791",
            "extra": "mean: 111.61491427153338 usec\nrounds: 2018"
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
          "id": "419bb8c395ee4e0adf15e109a9fc8ec9ca67b695",
          "message": "docs: update example scripts to use INFRAFOUNDRY_VAR_* env vars (merges PR #418)",
          "timestamp": "2026-03-17T18:09:32Z",
          "tree_id": "01d5ff98d569ed0875e79f411ae0fbea3d852343",
          "url": "https://github.com/endavis/infrafoundry/commit/419bb8c395ee4e0adf15e109a9fc8ec9ca67b695"
        },
        "date": 1773771009549,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7077.222375398119,
            "unit": "iter/sec",
            "range": "stddev: 0.000007805600478906806",
            "extra": "mean: 141.29837201049463 usec\nrounds: 3387"
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
          "id": "1f7caf638f089b984ae2de16864e147a2edc1999",
          "message": "docs: add README documentation to example packages (merges PR #420)",
          "timestamp": "2026-03-17T18:55:41Z",
          "tree_id": "2503c47029e6a749f0d7b6f88d6e599fa90723fb",
          "url": "https://github.com/endavis/infrafoundry/commit/1f7caf638f089b984ae2de16864e147a2edc1999"
        },
        "date": 1773773785048,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9063.848553135287,
            "unit": "iter/sec",
            "range": "stddev: 0.000006785320159456225",
            "extra": "mean: 110.3284100719102 usec\nrounds: 2085"
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
          "id": "2faf5acf7d7d2af3370f5e63a1f6e4deb856a93d",
          "message": "docs: add rocky9-template example package (merges PR #421, addresses #422)",
          "timestamp": "2026-03-18T12:52:58Z",
          "tree_id": "5e30fa7548d468353768d1ea0af284dd363889b2",
          "url": "https://github.com/endavis/infrafoundry/commit/2faf5acf7d7d2af3370f5e63a1f6e4deb856a93d"
        },
        "date": 1773838411733,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7023.457225429598,
            "unit": "iter/sec",
            "range": "stddev: 0.000008060991809665145",
            "extra": "mean: 142.38002281544954 usec\nrounds: 2323"
          }
        ]
      }
    ]
  }
}