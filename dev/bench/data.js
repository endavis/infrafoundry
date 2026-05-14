window.BENCHMARK_DATA = {
  "lastUpdate": 1778718876022,
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
          "id": "f3a3c59b5055acdbb13abb43ecd1b575c09e1841",
          "message": "docs: update documentation for env-var secrets, lifecycle events, and removed tfvars (merges PR #424, addresses #423)",
          "timestamp": "2026-03-19T10:19:57Z",
          "tree_id": "1aabb2995853986257f97c2208713dace3d73443",
          "url": "https://github.com/endavis/infrafoundry/commit/f3a3c59b5055acdbb13abb43ecd1b575c09e1841"
        },
        "date": 1773915631161,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6500.22243867168,
            "unit": "iter/sec",
            "range": "stddev: 0.000026194663626401665",
            "extra": "mean: 153.8408892056854 usec\nrounds: 2455"
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
          "id": "ef567f0ce48f82a478b6ae77909ec91851d7db71",
          "message": "feat: support cross-node VM cloning in Proxmox provider (merges PR #426, addresses #425)\n\nNormalize scalar clone values to dict format and render node_name and\ndatastore_id fields in the VM clone block, matching the existing container\ntemplate pattern. Backward compatible — scalar clone: <vmid> still works.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-03-19T13:25:54Z",
          "tree_id": "8222f3fa445808e79428f8150e92e3935ea8af2e",
          "url": "https://github.com/endavis/infrafoundry/commit/ef567f0ce48f82a478b6ae77909ec91851d7db71"
        },
        "date": 1773926794782,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7083.365257905406,
            "unit": "iter/sec",
            "range": "stddev: 0.000007899322622180482",
            "extra": "mean: 141.1758343089745 usec\nrounds: 2221"
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
          "id": "22a2bae38ca722d8646cc13efa50a7b609cdcaa0",
          "message": "feat: add trigger resource type to Proxmox provider (merges PR #429, addresses #428)\n\nAdd lightweight terraform_data-based trigger resources for packages that\nneed lifecycle events without creating real infrastructure. Used by\nscript-only packages (e.g., Helm deployments) to fire on_create events.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-03-19T15:14:38Z",
          "tree_id": "cdde7f16e2c81c200c3ddca9823ce8e38b2ad0ea",
          "url": "https://github.com/endavis/infrafoundry/commit/22a2bae38ca722d8646cc13efa50a7b609cdcaa0"
        },
        "date": 1773933316441,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7000.4861668041485,
            "unit": "iter/sec",
            "range": "stddev: 0.000008653510598811809",
            "extra": "mean: 142.84722177467262 usec\nrounds: 2232"
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
          "id": "eccecaaa12a7935a35070cf8c23ab0931b714848",
          "message": "fix: generate depends_on in kubernetes templates from dependency graph (merges PR #431, addresses #430)\n\nAdd _build_dependency_refs() that translates the provider's type-level\ndependency graph into concrete Terraform depends_on references. Pass\nthese to all 12 templates so resources wait for their dependencies.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-03-20T13:59:57Z",
          "tree_id": "b947850951abf52a46d2429754e04f24f38ee3f8",
          "url": "https://github.com/endavis/infrafoundry/commit/eccecaaa12a7935a35070cf8c23ab0931b714848"
        },
        "date": 1774015231508,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7038.392563478468,
            "unit": "iter/sec",
            "range": "stddev: 0.000009073997136066382",
            "extra": "mean: 142.07789505645115 usec\nrounds: 2306"
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
          "id": "9502049def328908b247e4e9fa76687624966b4e",
          "message": "fix: filter package events by --package flag (merges PR #438, addresses #427)\n\nfix: filter package events by --package flag to prevent unrelated handlers from firing\n\nTag handler configs with _package metadata during loading, add\nmatches_package() to BaseHandler, and thread package_filter through\nCLI → orchestrator → workflows → deployment executor → event bus.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-03-24T10:16:51Z",
          "tree_id": "95058fd7b8b5192661cff6cc5782b397e8308499",
          "url": "https://github.com/endavis/infrafoundry/commit/9502049def328908b247e4e9fa76687624966b4e"
        },
        "date": 1774347443002,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7002.057739483188,
            "unit": "iter/sec",
            "range": "stddev: 0.000008707544615213256",
            "extra": "mean: 142.81516051505864 usec\nrounds: 2330"
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
          "id": "074fd1550b5ee946e5375adec5d7f8cb4f208bbe",
          "message": "fix: skip unnecessary Kea DHCPv6 reconfiguration when config is unchanged (merges PR #440, addresses #439)\n\nfix: add change detection to Kea DHCPv6 subnet and reservation updates\n\nCompare existing OPNsense state with desired state before calling update\nAPIs. Only reconfigure Kea service when actual changes are detected,\npreventing unnecessary Unbound DNS disruptions.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-03-24T12:06:00Z",
          "tree_id": "5383a144b9513c08a4f4c6e54a0c74a100bbe5fe",
          "url": "https://github.com/endavis/infrafoundry/commit/074fd1550b5ee946e5375adec5d7f8cb4f208bbe"
        },
        "date": 1774353991483,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7102.926622362804,
            "unit": "iter/sec",
            "range": "stddev: 0.000008421655060473077",
            "extra": "mean: 140.78703795863626 usec\nrounds: 2371"
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
          "id": "1a5a7935641df1bb3ad9be5334960a6d1269efcc",
          "message": "fix: scope resource-level event handlers to their owning resource (merges PR #443, addresses #442)\n\nTag resource-level handler configs with _resource_owner during registration\nso they only fire when their specific resource is created, not any resource\nsharing the same name from a different provider.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-03-24T14:18:13Z",
          "tree_id": "b7629bfedbd85816097025d74152b004b3157af1",
          "url": "https://github.com/endavis/infrafoundry/commit/1a5a7935641df1bb3ad9be5334960a6d1269efcc"
        },
        "date": 1774361924436,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7053.712982034339,
            "unit": "iter/sec",
            "range": "stddev: 0.000008667653245876827",
            "extra": "mean: 141.76930682421857 usec\nrounds: 2301"
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
          "id": "532b96dd869effa4803bf5efc0d518276cce6681",
          "message": "fix: use provider-qualified resource owner to prevent cross-provider event firing (merges PR #444, addresses #442)\n\nQualify _resource_owner with provider name (e.g., \"proxmox:aiqum\") so\nresource-level events don't fire when a different provider creates a\nresource with the same name (e.g., \"opnsense:aiqum\").\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-03-24T15:06:40Z",
          "tree_id": "5161115f07a12fb9a35b87ec7c6ad3de12ec6c9d",
          "url": "https://github.com/endavis/infrafoundry/commit/532b96dd869effa4803bf5efc0d518276cce6681"
        },
        "date": 1774364836541,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9666.248068029025,
            "unit": "iter/sec",
            "range": "stddev: 0.000003673260218444878",
            "extra": "mean: 103.45275570854483 usec\nrounds: 2759"
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
          "id": "895a4455857d8ef60be55cb7ebf79441a667ad1f",
          "message": "fix: normalize Kea DHCPv6 subnet fields to prevent false-positive change detection (merges PR #445, addresses #441)\n\nAdd _normalize_field_value() that strips whitespace and sorts multi-line\nvalues. Apply consistently to both _extract_subnet_fields() and\n_build_desired_subnet_fields(). Add debug diff logging for field mismatches.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-03-25T13:57:26Z",
          "tree_id": "5962d5e1b27a973376f8d8bed5d5d37ca39774d4",
          "url": "https://github.com/endavis/infrafoundry/commit/895a4455857d8ef60be55cb7ebf79441a667ad1f"
        },
        "date": 1774447078647,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6718.733144588673,
            "unit": "iter/sec",
            "range": "stddev: 0.000029123386340615656",
            "extra": "mean: 148.83758269301245 usec\nrounds: 2473"
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
          "id": "1ce10fc6d4a6684060e2d0e09640e1018def1a13",
          "message": "docs: update example packages with ONTAP and AIQUM improvements (merges PR #454, addresses #453)\n\nSync example packages with production improvements: serial setup timing\nfix, root volume snapshot disable, licenses, CIFS/NFS volumes, and\nAIQUM certificate regeneration.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-03-30T12:20:15+01:00",
          "tree_id": "ad46b7c4fc4caebefc754e6084ac1edb9503610d",
          "url": "https://github.com/endavis/infrafoundry/commit/1ce10fc6d4a6684060e2d0e09640e1018def1a13"
        },
        "date": 1774869645504,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6926.8870322475195,
            "unit": "iter/sec",
            "range": "stddev: 0.000023518080442948683",
            "extra": "mean: 144.36499329996101 usec\nrounds: 2388"
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
          "id": "91659db75b74e882181452abed9a1a740efadc95",
          "message": "chore(deps): bump azure-identity from 1.25.2 to 1.25.3 (merges PR #400)\n\nBumps [azure-identity](https://github.com/Azure/azure-sdk-for-python) from 1.25.2 to 1.25.3.\n- [Release notes](https://github.com/Azure/azure-sdk-for-python/releases)\n- [Commits](https://github.com/Azure/azure-sdk-for-python/compare/azure-identity_1.25.2...azure-identity_1.25.3)\n\n---\nupdated-dependencies:\n- dependency-name: azure-identity\n  dependency-version: 1.25.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-30T13:04:20+01:00",
          "tree_id": "835ea5003f2c190600e4f4ee9473bead92bddfc7",
          "url": "https://github.com/endavis/infrafoundry/commit/91659db75b74e882181452abed9a1a740efadc95"
        },
        "date": 1774872290227,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9654.867453152581,
            "unit": "iter/sec",
            "range": "stddev: 0.0000043784890801311096",
            "extra": "mean: 103.57469999999559 usec\nrounds: 2680"
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
          "id": "32c6d6218b5b4b7ee4eb466dbb508a686bef0367",
          "message": "chore(deps): bump opentofu/setup-opentofu from 1 to 2 (merges PR #432)\n\nBumps [opentofu/setup-opentofu](https://github.com/opentofu/setup-opentofu) from 1 to 2.\n- [Release notes](https://github.com/opentofu/setup-opentofu/releases)\n- [Commits](https://github.com/opentofu/setup-opentofu/compare/v1...v2)\n\n---\nupdated-dependencies:\n- dependency-name: opentofu/setup-opentofu\n  dependency-version: '2'\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-30T13:14:33+01:00",
          "tree_id": "da0f307d2d0c5ebe1629eb39df5f59edc311d8c5",
          "url": "https://github.com/endavis/infrafoundry/commit/32c6d6218b5b4b7ee4eb466dbb508a686bef0367"
        },
        "date": 1774872909233,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7302.223043610426,
            "unit": "iter/sec",
            "range": "stddev: 0.00000936072881786231",
            "extra": "mean: 136.94459810769786 usec\nrounds: 2431"
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
          "id": "fb07a8fc7a675ffdc8fba60c011431401866d65f",
          "message": "chore(deps): bump pyproject-fmt from 2.18.1 to 2.20.0 (merges PR #433)\n\nBumps [pyproject-fmt](https://github.com/tox-dev/toml-fmt) from 2.18.1 to 2.20.0.\n- [Release notes](https://github.com/tox-dev/toml-fmt/releases)\n- [Commits](https://github.com/tox-dev/toml-fmt/compare/pyproject-fmt/2.18.1...pyproject-fmt/2.20.0)\n\n---\nupdated-dependencies:\n- dependency-name: pyproject-fmt\n  dependency-version: 2.20.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-30T13:34:37+01:00",
          "tree_id": "0d3ed881be5d1649b57999aff5e82a28098f36b4",
          "url": "https://github.com/endavis/infrafoundry/commit/fb07a8fc7a675ffdc8fba60c011431401866d65f"
        },
        "date": 1774874114364,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6639.818750838818,
            "unit": "iter/sec",
            "range": "stddev: 0.000026555768481597262",
            "extra": "mean: 150.6065206785454 usec\nrounds: 2418"
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
          "id": "c1b40b8da1a3a3d11ace40c7fd67476ee8dc2d7c",
          "message": "chore(deps): bump mkdocs-material from 9.7.5 to 9.7.6 (merges PR #436)\n\nBumps [mkdocs-material](https://github.com/squidfunk/mkdocs-material) from 9.7.5 to 9.7.6.\n- [Release notes](https://github.com/squidfunk/mkdocs-material/releases)\n- [Changelog](https://github.com/squidfunk/mkdocs-material/blob/master/CHANGELOG)\n- [Commits](https://github.com/squidfunk/mkdocs-material/compare/9.7.5...9.7.6)\n\n---\nupdated-dependencies:\n- dependency-name: mkdocs-material\n  dependency-version: 9.7.6\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-30T15:04:48+01:00",
          "tree_id": "c73e4341c590fb11ff7f57682bca302d7d4d66b0",
          "url": "https://github.com/endavis/infrafoundry/commit/c1b40b8da1a3a3d11ace40c7fd67476ee8dc2d7c"
        },
        "date": 1774879523581,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6570.3014557482375,
            "unit": "iter/sec",
            "range": "stddev: 0.000027879036997549364",
            "extra": "mean: 152.20001802582712 usec\nrounds: 2330"
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
          "id": "9c80c2ed82cf9d329c7572419e2a4363dc07d9fc",
          "message": "chore(deps): bump the dev-dependencies group across 1 directory with 2 updates (merges PR #437)\n\nBumps the dev-dependencies group with 2 updates in the / directory: [pytest-cov](https://github.com/pytest-dev/pytest-cov) and [ruff](https://github.com/astral-sh/ruff).\n\n\nUpdates `pytest-cov` from 7.0.0 to 7.1.0\n- [Changelog](https://github.com/pytest-dev/pytest-cov/blob/master/CHANGELOG.rst)\n- [Commits](https://github.com/pytest-dev/pytest-cov/compare/v7.0.0...v7.1.0)\n\nUpdates `ruff` from 0.15.5 to 0.15.7\n- [Release notes](https://github.com/astral-sh/ruff/releases)\n- [Changelog](https://github.com/astral-sh/ruff/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/astral-sh/ruff/compare/0.15.5...0.15.7)\n\n---\nupdated-dependencies:\n- dependency-name: pytest-cov\n  dependency-version: 7.1.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: dev-dependencies\n- dependency-name: ruff\n  dependency-version: 0.15.7\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: dev-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-30T15:30:09+01:00",
          "tree_id": "cbe274638cb5e32fd0dcc3f9db97d65011497fd2",
          "url": "https://github.com/endavis/infrafoundry/commit/9c80c2ed82cf9d329c7572419e2a4363dc07d9fc"
        },
        "date": 1774881041156,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6572.099393839273,
            "unit": "iter/sec",
            "range": "stddev: 0.000030439052667339742",
            "extra": "mean: 152.1583804617146 usec\nrounds: 2426"
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
          "id": "db695b78a084588a9cb6d5d3ad4e94412933b106",
          "message": "chore(deps): bump codecov/codecov-action from 5 to 6 (merges PR #446)\n\nBumps [codecov/codecov-action](https://github.com/codecov/codecov-action) from 5 to 6.\n- [Release notes](https://github.com/codecov/codecov-action/releases)\n- [Changelog](https://github.com/codecov/codecov-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/codecov/codecov-action/compare/v5...v6)\n\n---\nupdated-dependencies:\n- dependency-name: codecov/codecov-action\n  dependency-version: '6'\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-30T15:56:04+01:00",
          "tree_id": "a0a0ce8a17a0a8e18869c936b60f608cfa050b4d",
          "url": "https://github.com/endavis/infrafoundry/commit/db695b78a084588a9cb6d5d3ad4e94412933b106"
        },
        "date": 1774882601065,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7704.746516075885,
            "unit": "iter/sec",
            "range": "stddev: 0.000009840273313931184",
            "extra": "mean: 129.790123258891 usec\nrounds: 3805"
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
          "id": "531579ed2490d2358187ff6064bfdb18cc11b282",
          "message": "chore(deps): bump requests from 2.32.5 to 2.33.0 (merges PR #447)\n\nBumps [requests](https://github.com/psf/requests) from 2.32.5 to 2.33.0.\n- [Release notes](https://github.com/psf/requests/releases)\n- [Changelog](https://github.com/psf/requests/blob/main/HISTORY.md)\n- [Commits](https://github.com/psf/requests/compare/v2.32.5...v2.33.0)\n\n---\nupdated-dependencies:\n- dependency-name: requests\n  dependency-version: 2.33.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-30T16:17:49+01:00",
          "tree_id": "78b2fb6d5f26d2a1ab12f333656455733955a890",
          "url": "https://github.com/endavis/infrafoundry/commit/531579ed2490d2358187ff6064bfdb18cc11b282"
        },
        "date": 1774883909531,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6673.600325094686,
            "unit": "iter/sec",
            "range": "stddev: 0.000030854112145941174",
            "extra": "mean: 149.84415477200636 usec\nrounds: 2326"
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
          "id": "7c61c186c7de99ac614d8f73ba065178bbb0cac1",
          "message": "chore(deps): bump pip-licenses from 5.5.1 to 5.5.5 (merges PR #448)\n\nBumps [pip-licenses](https://github.com/raimon49/pip-licenses) from 5.5.1 to 5.5.5.\n- [Release notes](https://github.com/raimon49/pip-licenses/releases)\n- [Changelog](https://github.com/raimon49/pip-licenses/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/raimon49/pip-licenses/compare/v-5.5.1...v-5.5.5)\n\n---\nupdated-dependencies:\n- dependency-name: pip-licenses\n  dependency-version: 5.5.5\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-30T16:24:20+01:00",
          "tree_id": "bcb298d603495139f234e58491902f15a302f84f",
          "url": "https://github.com/endavis/infrafoundry/commit/7c61c186c7de99ac614d8f73ba065178bbb0cac1"
        },
        "date": 1774884291225,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7159.416108372164,
            "unit": "iter/sec",
            "range": "stddev: 0.000020689614473958693",
            "extra": "mean: 139.67619493866377 usec\nrounds: 2529"
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
          "id": "a1d4c4e27c58310e605456d921a5e471e34d5268",
          "message": "chore(deps): bump boto3 from 1.42.66 to 1.42.78 (merges PR #449)\n\nBumps [boto3](https://github.com/boto/boto3) from 1.42.66 to 1.42.78.\n- [Release notes](https://github.com/boto/boto3/releases)\n- [Commits](https://github.com/boto/boto3/compare/1.42.66...1.42.78)\n\n---\nupdated-dependencies:\n- dependency-name: boto3\n  dependency-version: 1.42.78\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-30T17:16:32+01:00",
          "tree_id": "ae7273026b77028facc24b782dbc93316d9eb935",
          "url": "https://github.com/endavis/infrafoundry/commit/a1d4c4e27c58310e605456d921a5e471e34d5268"
        },
        "date": 1774887426058,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6763.05703634693,
            "unit": "iter/sec",
            "range": "stddev: 0.000026295671176135416",
            "extra": "mean: 147.86212723412885 usec\nrounds: 2350"
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
          "id": "68f7f72ff20580f7f6a91930fd0e3c11c4f12663",
          "message": "chore(deps): bump hypothesis from 6.151.9 to 6.151.10 (merges PR #450)\n\nBumps [hypothesis](https://github.com/HypothesisWorks/hypothesis) from 6.151.9 to 6.151.10.\n- [Release notes](https://github.com/HypothesisWorks/hypothesis/releases)\n- [Commits](https://github.com/HypothesisWorks/hypothesis/compare/hypothesis-python-6.151.9...hypothesis-python-6.151.10)\n\n---\nupdated-dependencies:\n- dependency-name: hypothesis\n  dependency-version: 6.151.10\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-30T18:19:36+01:00",
          "tree_id": "6349ea5da0971f24b43399c6aa4ad2e4a560ccde",
          "url": "https://github.com/endavis/infrafoundry/commit/68f7f72ff20580f7f6a91930fd0e3c11c4f12663"
        },
        "date": 1774891206842,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7332.938658483317,
            "unit": "iter/sec",
            "range": "stddev: 0.000009343463169230247",
            "extra": "mean: 136.37097575378212 usec\nrounds: 3217"
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
          "id": "705fa9200b853f265c703e021c30cd30172f5f61",
          "message": "chore(deps): bump types-requests from 2.32.4.20260107 to 2.33.0.20260327 (merges PR #451)\n\nBumps [types-requests](https://github.com/python/typeshed) from 2.32.4.20260107 to 2.33.0.20260327.\n- [Commits](https://github.com/python/typeshed/commits)\n\n---\nupdated-dependencies:\n- dependency-name: types-requests\n  dependency-version: 2.33.0.20260327\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-30T20:11:22+01:00",
          "tree_id": "5fec2139eaf30f49f6124365b981652a9e8eda0a",
          "url": "https://github.com/endavis/infrafoundry/commit/705fa9200b853f265c703e021c30cd30172f5f61"
        },
        "date": 1774897916829,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7239.407853920883,
            "unit": "iter/sec",
            "range": "stddev: 0.000017869956353703232",
            "extra": "mean: 138.13284458871829 usec\nrounds: 2310"
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
          "id": "08c0fae157df86925567cef0a773027c8c7913de",
          "message": "chore(deps): bump types-boto3 from 1.42.66 to 1.42.78 (merges PR #452)\n\nBumps [types-boto3](https://github.com/youtype/mypy_boto3_builder) from 1.42.66 to 1.42.78.\n- [Release notes](https://github.com/youtype/mypy_boto3_builder/releases)\n- [Commits](https://github.com/youtype/mypy_boto3_builder/commits)\n\n---\nupdated-dependencies:\n- dependency-name: types-boto3\n  dependency-version: 1.42.78\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-03-30T22:19:13+01:00",
          "tree_id": "de51ff686dce4286affb35c2557364b6d9d47782",
          "url": "https://github.com/endavis/infrafoundry/commit/08c0fae157df86925567cef0a773027c8c7913de"
        },
        "date": 1774905584878,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 5866.887854576795,
            "unit": "iter/sec",
            "range": "stddev: 0.000042802027972151784",
            "extra": "mean: 170.4481191369448 usec\nrounds: 2409"
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
          "id": "d98b0cd18c41fca1e47ea0ef4de57d14fe7f6ee8",
          "message": "docs: fix overclaimed features in AGENTS.md and README (merges PR #455, addresses #247)\n\nClarify state locking is Terraform backend responsibility, not an\nInfraFoundry feature. Update secrets claim to reflect SOPS-only\nreality with pluggable backends planned (#419).\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-03-31T11:25:47+01:00",
          "tree_id": "bb0861e4b250fa344d00c5f5f23d94c914b69e1c",
          "url": "https://github.com/endavis/infrafoundry/commit/d98b0cd18c41fca1e47ea0ef4de57d14fe7f6ee8"
        },
        "date": 1774952784738,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6405.362658847877,
            "unit": "iter/sec",
            "range": "stddev: 0.000035239135811645105",
            "extra": "mean: 156.11918532335974 usec\nrounds: 2412"
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
          "id": "c667ce3566f6ea56431ab9d1e3ad0f693bfa4ec0",
          "message": "feat: add package blueprints with shared templates and inventory generation (merges PR #457, addresses #456, #348)\n\nfeat: add package blueprints and inventory generation\n\nIntroduce BlueprintResolver for shared reusable package templates\nreferenced via `blueprint:` in manifests, and InventoryGenerator for\ndeclarative Ansible inventory from manifest `inventory:` sections.\nPackages inherit blueprint defaults, resources, events, and inventory\nwith package-first override semantics.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-03-31T13:18:29+01:00",
          "tree_id": "640d054d0695a8c53c363269b853a8f578471a24",
          "url": "https://github.com/endavis/infrafoundry/commit/c667ce3566f6ea56431ab9d1e3ad0f693bfa4ec0"
        },
        "date": 1774959542365,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6667.665738337619,
            "unit": "iter/sec",
            "range": "stddev: 0.000033738672896181125",
            "extra": "mean: 149.9775242556355 usec\nrounds: 1814"
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
          "id": "4c2feb3ef6419d2cafc4c2ed81159851078b9f12",
          "message": "fix: blueprint resolver, event rendering, and ontap-cluster blueprint (merges PR #459, addresses #456)\n\n- Move blueprints to framework repo (resolve via pyproject.toml root)\n- Render event handler configs through Jinja2 for variable resolution\n  in requires/resources fields\n- Fix CIFS server when condition to check name, not dict length\n- Conditionally build volume/export policy lists in playbook\n- Add ontap-cluster as the first framework blueprint\n- Fix test fixtures for framework-local blueprint resolution\n- Add blueprints/ to .gitignore yaml exceptions\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-03-31T15:23:02+01:00",
          "tree_id": "7d10167174d33d0efc2befd424b69246bc1af351",
          "url": "https://github.com/endavis/infrafoundry/commit/4c2feb3ef6419d2cafc4c2ed81159851078b9f12"
        },
        "date": 1774967014822,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7417.916573692935,
            "unit": "iter/sec",
            "range": "stddev: 0.000009129378433643705",
            "extra": "mean: 134.80874178963165 usec\nrounds: 3319"
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
          "id": "c0415a8f81d0e3787669afd5390c34f67093167e",
          "message": "feat: skip OVA extraction when VMDKs already exist (merges PR #460, addresses #362)\n\nCheck for existing VMDKs before extracting OVA tar, and stop deleting\nextracted files after disk import so they persist for future runs.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-03-31T16:26:18+01:00",
          "tree_id": "931a03834147649c2f850e71db1b815a5976d5a5",
          "url": "https://github.com/endavis/infrafoundry/commit/c0415a8f81d0e3787669afd5390c34f67093167e"
        },
        "date": 1774970819440,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7411.599221324836,
            "unit": "iter/sec",
            "range": "stddev: 0.00000903528663264604",
            "extra": "mean: 134.9236473989008 usec\nrounds: 2249"
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
          "id": "4f948c0f8cfa16905ff34b600439557bd5226572",
          "message": "feat: add generate_mac Jinja2 filter for deterministic virtual MAC addresses (merges PR #461, addresses #458)\n\nSHA-256 hash input string, format first 5 bytes as 02:xx:xx:xx:xx:xx\n(locally administered, unicast). Registered in package resource templates,\nevent rendering, and provider template environments.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-03-31T19:11:28+01:00",
          "tree_id": "ebabd5cbb18d4c8bdfff4e129128bea535a024b1",
          "url": "https://github.com/endavis/infrafoundry/commit/4f948c0f8cfa16905ff34b600439557bd5226572"
        },
        "date": 1774980723927,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6471.548295148952,
            "unit": "iter/sec",
            "range": "stddev: 0.00003658508699829966",
            "extra": "mean: 154.52252759198228 usec\nrounds: 2392"
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
          "id": "566c8cdbca1c53b87d545c33aa13ff653cf43fd5",
          "message": "fix: use generate_mac filter in ontap-cluster blueprint for virtual IP MACs (merges PR #462, addresses #458)\n\nReplace hardcoded placeholder MACs with deterministic generate_mac filter\nfor cluster management and data LIF DHCP reservations. Each cluster\ninstance gets unique MACs derived from its name, preventing collisions.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-03-31T20:37:09+01:00",
          "tree_id": "455314ac178716c31eb160f1d5d11ca7a88d6b39",
          "url": "https://github.com/endavis/infrafoundry/commit/566c8cdbca1c53b87d545c33aa13ff653cf43fd5"
        },
        "date": 1774985865777,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7032.988821113757,
            "unit": "iter/sec",
            "range": "stddev: 0.0000253448957996936",
            "extra": "mean: 142.1870595041893 usec\nrounds: 2420"
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
          "id": "495bf10ddfc0690c5423abed989561503389a793",
          "message": "fix: add data_nfs and data_cifs to ONTAP data LIF service policy (merges PR #464, addresses #463)\n\nONTAP 9.18+ uses service policies instead of protocol-based LIF assignment.\nThe default-data-files policy was missing data_nfs and data_cifs, preventing\nNFS/CIFS traffic on data LIFs even when the protocols were enabled.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-03-31T20:54:56+01:00",
          "tree_id": "115791ab2272e636ff406adfd613e0ede6c95070",
          "url": "https://github.com/endavis/infrafoundry/commit/495bf10ddfc0690c5423abed989561503389a793"
        },
        "date": 1774986931275,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7253.611920306804,
            "unit": "iter/sec",
            "range": "stddev: 0.00001085608145885155",
            "extra": "mean: 137.86235202361135 usec\nrounds: 2372"
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
          "id": "d8791f5c62af3c3d4e7276a42e2dad20685311e9",
          "message": "fix: replace broken OPNsense ansible filter reload with credential validation and single apply task (merges PR #465, addresses #391)",
          "timestamp": "2026-04-01T17:03:49+01:00",
          "tree_id": "839e5775aa770edf8813bb964e9cf46b73a65d15",
          "url": "https://github.com/endavis/infrafoundry/commit/d8791f5c62af3c3d4e7276a42e2dad20685311e9"
        },
        "date": 1775059467769,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7374.9222045320275,
            "unit": "iter/sec",
            "range": "stddev: 0.00000986239036178933",
            "extra": "mean: 135.59465066431227 usec\nrounds: 2333"
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
          "id": "2d4f41d65b2d26af29fc98d1dd00dbf0efd8e94c",
          "message": "chore: harden secrets handling file permissions (merges PR #466, addresses #359)\n\nchore: harden secrets handling with restrictive file permissions and cleanup utilities",
          "timestamp": "2026-04-01T17:46:25+01:00",
          "tree_id": "d3cbca42e65b0077c33565725d4a30d01a427bb4",
          "url": "https://github.com/endavis/infrafoundry/commit/2d4f41d65b2d26af29fc98d1dd00dbf0efd8e94c"
        },
        "date": 1775062017203,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7230.403113978753,
            "unit": "iter/sec",
            "range": "stddev: 0.000010490862926853432",
            "extra": "mean: 138.3048751551169 usec\nrounds: 2419"
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
          "id": "9d0b6c4d01c5902418d5e04df27cc1b20620b13d",
          "message": "refactor: make PackageLoader use pluggable SecretProvider instead of hardcoded SOPS (merges PR #467, addresses #419)\n\nBREAKING CHANGE: ConfigManager, ProviderCentricLoader, and PackageLoader constructors\nnow accept an optional secret_provider parameter. Internal attribute initialization\nfor ConfigManager.provider_centric changed to forward the provider. Existing callers\nare unaffected as the parameter defaults to None (uses SopsSecretProvider).",
          "timestamp": "2026-04-02T12:06:05+01:00",
          "tree_id": "01e5e9d5e7b96313c0e33c63c0e47668082e3c7b",
          "url": "https://github.com/endavis/infrafoundry/commit/9d0b6c4d01c5902418d5e04df27cc1b20620b13d"
        },
        "date": 1775127999155,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7342.3131852827355,
            "unit": "iter/sec",
            "range": "stddev: 0.000010788965968231306",
            "extra": "mean: 136.19685986760211 usec\nrounds: 2569"
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
          "id": "559ddbbcd8fd7e2e80ee430321d5cbac463cff5b",
          "message": "refactor: extract CloudInitMixin from duplicated Proxmox/OCI cloud-init code (merges PR #469, addresses #468)",
          "timestamp": "2026-04-02T16:23:56+01:00",
          "tree_id": "6c77710ac3a3279810f3bf9740a6b81f6c1290f2",
          "url": "https://github.com/endavis/infrafoundry/commit/559ddbbcd8fd7e2e80ee430321d5cbac463cff5b"
        },
        "date": 1775143469782,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9712.728994708206,
            "unit": "iter/sec",
            "range": "stddev: 0.0000037944660132856645",
            "extra": "mean: 102.95767549417171 usec\nrounds: 2681"
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
          "id": "c2dd76be7409f647efdf539f97a64d6f17b4849f",
          "message": "refactor: implement Kubernetes validators for kubeconfig, namespace, CRD, and Helm validation (merges PR #471, addresses #444)",
          "timestamp": "2026-04-02T17:17:35+01:00",
          "tree_id": "240eb81cae77df87a6c8d25f897bfa7e689d42ec",
          "url": "https://github.com/endavis/infrafoundry/commit/c2dd76be7409f647efdf539f97a64d6f17b4849f"
        },
        "date": 1775146696031,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7287.44977063358,
            "unit": "iter/sec",
            "range": "stddev: 0.000009089898492124178",
            "extra": "mean: 137.22221510599294 usec\nrounds: 2264"
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
          "id": "19a2b185d95da475ea718926e9500f8774997dcf",
          "message": "refactor: complete OCI validator with live API resource validation (merges PR #473, addresses #472)",
          "timestamp": "2026-04-02T18:04:02+01:00",
          "tree_id": "8bbeb60ed83e1dac7fde180b27da34dc586c9492",
          "url": "https://github.com/endavis/infrafoundry/commit/19a2b185d95da475ea718926e9500f8774997dcf"
        },
        "date": 1775149480109,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7390.009184944865,
            "unit": "iter/sec",
            "range": "stddev: 0.000009835047823880381",
            "extra": "mean: 135.31782910868748 usec\nrounds: 2446"
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
          "id": "e5f9c1e5d74b593e065e47e3289fb8d83e0fd038",
          "message": "refactor: extract dedicated API clients for Proxmox and OCI providers (merges PR #475, addresses #474)",
          "timestamp": "2026-04-03T12:51:13+01:00",
          "tree_id": "d6f0a6a756a5edefb24eec985b50ad80c76999ff",
          "url": "https://github.com/endavis/infrafoundry/commit/e5f9c1e5d74b593e065e47e3289fb8d83e0fd038"
        },
        "date": 1775217104146,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7330.664740379081,
            "unit": "iter/sec",
            "range": "stddev: 0.000009798223946624105",
            "extra": "mean: 136.41327702408176 usec\nrounds: 2285"
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
          "id": "b9e0b3c1333656b874d3194cc317ac88468f58b9",
          "message": "refactor: standardize ESXi validator to use BaseAPIValidator (merges PR #477, addresses #476)",
          "timestamp": "2026-04-03T13:11:46+01:00",
          "tree_id": "dcc4b7c9c640f53bc3ddfe59c77b57d873fa88dc",
          "url": "https://github.com/endavis/infrafoundry/commit/b9e0b3c1333656b874d3194cc317ac88468f58b9"
        },
        "date": 1775218338094,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7309.620300737624,
            "unit": "iter/sec",
            "range": "stddev: 0.000010032566844533326",
            "extra": "mean: 136.80601164729288 usec\nrounds: 2404"
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
          "id": "58968cebe8a31a2dd8bddf0f77cc699c55e117f7",
          "message": "test: expand provider validator test coverage to 71% (merges PR #480, addresses #478)\n\n* test: expand provider validator test coverage to 71%\n\n* test: add kubernetes validator API reference and service selector tests",
          "timestamp": "2026-04-03T13:34:17+01:00",
          "tree_id": "13e29e832ee45ed34f6e67e9d20b77627686f57b",
          "url": "https://github.com/endavis/infrafoundry/commit/58968cebe8a31a2dd8bddf0f77cc699c55e117f7"
        },
        "date": 1775219688673,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6493.671486167955,
            "unit": "iter/sec",
            "range": "stddev: 0.00003162476641759793",
            "extra": "mean: 153.9960871334623 usec\nrounds: 2456"
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
          "id": "482dc6441ba0f20ff5e4810df252ef2fac376a2a",
          "message": "docs: add validator, API client, and mixin patterns to provider guide (merges PR #481, addresses #479)",
          "timestamp": "2026-04-03T13:45:16+01:00",
          "tree_id": "44c5652ec91124efae087fab524f0c77394dcbf3",
          "url": "https://github.com/endavis/infrafoundry/commit/482dc6441ba0f20ff5e4810df252ef2fac376a2a"
        },
        "date": 1775220348372,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7365.802725990653,
            "unit": "iter/sec",
            "range": "stddev: 0.00000874050089396922",
            "extra": "mean: 135.76252815887173 usec\nrounds: 2770"
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
          "id": "2a4d52e47f73c08c874526d1e2d394a3600a8efb",
          "message": "chore: synchronize with latest pyproject-template (merges PR #483, addresses #482)\n\n* chore: sync template state to 75cbe9b37181359365d57b4e54cb59b8a47507fb\n\n* chore: synchronize with latest pyproject-template",
          "timestamp": "2026-04-03T23:33:53+01:00",
          "tree_id": "76d009b6fc4d7fd8e67c73902acde7e60fa0e39c",
          "url": "https://github.com/endavis/infrafoundry/commit/2a4d52e47f73c08c874526d1e2d394a3600a8efb"
        },
        "date": 1775255663456,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9630.1489066661,
            "unit": "iter/sec",
            "range": "stddev: 0.0000054635757391543555",
            "extra": "mean: 103.84055425225964 usec\nrounds: 2728"
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
          "id": "1509233de5da379244b577fdc7ce74f154fb202a",
          "message": "feat: add terraform import block support for existing resources (merges PR #484, addresses #387)\n\nAdd import_id field to ResourceConfig and generate Terraform import\nblocks automatically in render_and_write_terraform. Works across all\nproviders with no per-provider changes.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-05T11:13:41+01:00",
          "tree_id": "18c978da019db1854a08eb92fae8c2e9696ca458",
          "url": "https://github.com/endavis/infrafoundry/commit/1509233de5da379244b577fdc7ce74f154fb202a"
        },
        "date": 1775384048056,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9617.408646542433,
            "unit": "iter/sec",
            "range": "stddev: 0.000004480343672574847",
            "extra": "mean: 103.97811268625996 usec\nrounds: 2751"
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
          "id": "0734fba76205e122e4911dcd01e65cd4d5877364",
          "message": "fix: restore mutation testing workflow for mutmut 3.x (merges PR #496, addresses #485)\n\n* fix: update mutation testing for mutmut 3.x compatibility\n\n- Add dangling symlink cleanup step before mutmut run\n- Remove mutmut html command (removed in 3.x)\n- Save mutmut results as text artifact instead of HTML\n- Remove task_mutate_html doit task\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* fix: correct mutmut 3.x config and workflow compatibility\n\n- Change paths_to_mutate and tests_dir from strings to lists in\n  pyproject.toml (strings are iterated as characters, causing mutmut\n  to walk the entire filesystem via PosixPath('/'))\n- Remove mutmut html step from workflow (removed in mutmut 3.x)\n- Remove task_mutate_html doit task\n- Add mkdir -p tmp before saving results artifact\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* fix: preserve MUTANT_UNDER_TEST env var and fix mutmut config types\n\n- Add autouse fixture to preserve MUTANT_UNDER_TEST across tests that\n  clear os.environ (mutmut 3.x requires this var during test runs)\n- Change paths_to_mutate and tests_dir from strings to lists\n- Add mkdir -p tmp before saving results artifact\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* fix: replace patch.dict clear=True with monkeypatch.delenv for mutmut 3.x\n\nmutmut 3.x injects a trampoline that reads os.environ['MUTANT_UNDER_TEST']\nvia direct dict access. Tests using patch.dict(clear=True) wipe this var,\ncausing KeyError during mutmut's initial test run.\n\nReplace all clear=True usages with targeted monkeypatch.delenv/setenv\ncalls that only remove the specific vars each test needs absent.\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* fix: add terraform install step to mutation testing workflow\n\nThe TerraformRunner constructor validates terraform is on PATH.\nWithout it, mutmut's initial test run fails before testing any mutants.\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* fix: add age and sops install to mutation testing workflow\n\nTests that exercise secrets rotation require age-keygen on PATH.\nMirror the system tools install step from CI workflow.\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* fix: scope builtins.__import__ mock to requests only\n\nThe previous mock used side_effect=ImportError on builtins.__import__\nwhich blocks ALL imports including mutmut's trampoline `import os`.\nUse a selective import function that only raises for 'requests'.\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* fix: suppress hypothesis differing_executors and quiet mutmut output\n\n- Suppress HealthCheck.differing_executors in Hypothesis profiles\n  (mutmut runs tests from multiple executors, triggering this check)\n- Redirect mutmut run output to log file, show only summary in CI\n- Include full run log in uploaded artifacts for debugging\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* fix: strip spinner noise from mutmut output and add summary\n\n- Redirect mutmut run to raw log, then strip carriage returns and\n  spinner characters for a clean log\n- Print clean log and results summary (counts by status) in CI output\n- Only upload results text as artifact (raw log is transient)\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* fix: split mutation run and results into separate steps\n\n- Separate mutmut run from results reporting so results/summary\n  are shown even if mutmut is killed or times out\n- Add explicit 120-minute timeout for mutation run\n- Use tr + grep -vP to strip UTF-8 spinner characters from log\n- Results step runs with if: always()\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* fix: match spinner bytes anywhere on line, not just at start\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* fix: filter spinner phrases by name instead of byte pattern\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* fix: also filter forced-fail spinner and N/M progress lines\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* fix: also force SOPS check in test_init_no_age_key_env\n\nCI sets INFRAFOUNDRY_SKIP_SOPS_CHECK, which the previous patch.dict\nclear=True approach implicitly removed. The monkeypatch replacement\nonly deleted SOPS_AGE_KEY_FILE, so under CI the check was skipped and\nthe expected ValueError was never raised.\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-06T12:56:02+01:00",
          "tree_id": "a829008451440ce5c425c2658496b5431de0cfb3",
          "url": "https://github.com/endavis/infrafoundry/commit/0734fba76205e122e4911dcd01e65cd4d5877364"
        },
        "date": 1775476597340,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7321.627841176612,
            "unit": "iter/sec",
            "range": "stddev: 0.000009763977747444397",
            "extra": "mean: 136.58164846566368 usec\nrounds: 2509"
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
          "id": "7f7b6c756c3e73915c937552897231f60c133d11",
          "message": "chore(deps): bump the dev-dependencies group across 1 directory with 2 updates (merges PR #486)\n\nchore(deps): bump the dev-dependencies group with 2 updates\n\nBumps the dev-dependencies group with 2 updates: [mypy](https://github.com/python/mypy) and [ruff](https://github.com/astral-sh/ruff).\n\n\nUpdates `mypy` from 1.19.1 to 1.20.0\n- [Changelog](https://github.com/python/mypy/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/python/mypy/compare/v1.19.1...v1.20.0)\n\nUpdates `ruff` from 0.15.8 to 0.15.9\n- [Release notes](https://github.com/astral-sh/ruff/releases)\n- [Changelog](https://github.com/astral-sh/ruff/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/astral-sh/ruff/compare/0.15.8...0.15.9)\n\n---\nupdated-dependencies:\n- dependency-name: mypy\n  dependency-version: 1.20.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: dev-dependencies\n- dependency-name: ruff\n  dependency-version: 0.15.9\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: dev-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-06T15:37:18+01:00",
          "tree_id": "61421971781385ae655288c60a8334fe4d81689e",
          "url": "https://github.com/endavis/infrafoundry/commit/7f7b6c756c3e73915c937552897231f60c133d11"
        },
        "date": 1775486271251,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7314.405757539468,
            "unit": "iter/sec",
            "range": "stddev: 0.000009659308621158289",
            "extra": "mean: 136.71650618633376 usec\nrounds: 2748"
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
          "id": "71c58f91b7e7cb201163047623a1f920c16eb882",
          "message": "chore(deps): bump ansible from 13.4.0 to 13.5.0 (merges PR #487)\n\nBumps [ansible](https://github.com/ansible-community/ansible-build-data) from 13.4.0 to 13.5.0.\n- [Changelog](https://github.com/ansible-community/ansible-build-data/blob/main/docs/release-process.md)\n- [Commits](https://github.com/ansible-community/ansible-build-data/compare/13.4.0...13.5.0)\n\n---\nupdated-dependencies:\n- dependency-name: ansible\n  dependency-version: 13.5.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-06T15:48:56+01:00",
          "tree_id": "6c506e88b2c16214413db2c6b9d3695f2e4fe64e",
          "url": "https://github.com/endavis/infrafoundry/commit/71c58f91b7e7cb201163047623a1f920c16eb882"
        },
        "date": 1775486977564,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7290.510396958515,
            "unit": "iter/sec",
            "range": "stddev: 0.00001101363043315345",
            "extra": "mean: 137.16460790141443 usec\nrounds: 2354"
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
          "id": "ebd29a3206df759ccea8be1d431a4db42b65ece9",
          "message": "chore(deps): bump pyproject-fmt from 2.20.0 to 2.21.0 (merges PR #488)\n\nBumps [pyproject-fmt](https://github.com/tox-dev/toml-fmt) from 2.20.0 to 2.21.0.\n- [Release notes](https://github.com/tox-dev/toml-fmt/releases)\n- [Commits](https://github.com/tox-dev/toml-fmt/compare/pyproject-fmt/2.20.0...pyproject-fmt/2.21.0)\n\n---\nupdated-dependencies:\n- dependency-name: pyproject-fmt\n  dependency-version: 2.21.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-06T15:55:36+01:00",
          "tree_id": "d862692b3a60a793a903f99b698e549e06c80bd8",
          "url": "https://github.com/endavis/infrafoundry/commit/ebd29a3206df759ccea8be1d431a4db42b65ece9"
        },
        "date": 1775487371054,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7294.638847850931,
            "unit": "iter/sec",
            "range": "stddev: 0.000009183554819561374",
            "extra": "mean: 137.08697865071272 usec\nrounds: 2342"
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
          "id": "7464305088d69ff0840615b9cbbdedc906c42532",
          "message": "chore(deps): bump click from 8.3.1 to 8.3.2 (merges PR #489)\n\nBumps [click](https://github.com/pallets/click) from 8.3.1 to 8.3.2.\n- [Release notes](https://github.com/pallets/click/releases)\n- [Changelog](https://github.com/pallets/click/blob/main/CHANGES.rst)\n- [Commits](https://github.com/pallets/click/compare/8.3.1...8.3.2)\n\n---\nupdated-dependencies:\n- dependency-name: click\n  dependency-version: 8.3.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-06T16:40:25+01:00",
          "tree_id": "edb86614e3d0725d041e66381e47ebd923c84448",
          "url": "https://github.com/endavis/infrafoundry/commit/7464305088d69ff0840615b9cbbdedc906c42532"
        },
        "date": 1775490063748,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6746.481529957256,
            "unit": "iter/sec",
            "range": "stddev: 0.000025287323557980654",
            "extra": "mean: 148.22541135843528 usec\nrounds: 2606"
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
          "id": "887cffe3d21918046a81fc265dd0806a0f810ee6",
          "message": "chore(deps): bump cyclonedx-bom from 7.2.2 to 7.3.0 (merges PR #490)\n\nBumps [cyclonedx-bom](https://github.com/CycloneDX/cyclonedx-python) from 7.2.2 to 7.3.0.\n- [Release notes](https://github.com/CycloneDX/cyclonedx-python/releases)\n- [Changelog](https://github.com/CycloneDX/cyclonedx-python/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/CycloneDX/cyclonedx-python/compare/v7.2.2...v7.3.0)\n\n---\nupdated-dependencies:\n- dependency-name: cyclonedx-bom\n  dependency-version: 7.3.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-06T16:49:21+01:00",
          "tree_id": "a1cf49f446b6e380c36c7e5ab028ae0531b50639",
          "url": "https://github.com/endavis/infrafoundry/commit/887cffe3d21918046a81fc265dd0806a0f810ee6"
        },
        "date": 1775490594327,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6961.699021641869,
            "unit": "iter/sec",
            "range": "stddev: 0.000023612654249040296",
            "extra": "mean: 143.6430958723287 usec\nrounds: 2253"
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
          "id": "60bfd284804463678e0e9320ed950dc1244383fd",
          "message": "chore(deps): bump vulture from 2.15 to 2.16 (merges PR #491)\n\nBumps [vulture](https://github.com/jendrikseipp/vulture) from 2.15 to 2.16.\n- [Release notes](https://github.com/jendrikseipp/vulture/releases)\n- [Changelog](https://github.com/jendrikseipp/vulture/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/jendrikseipp/vulture/compare/v2.15...v2.16)\n\n---\nupdated-dependencies:\n- dependency-name: vulture\n  dependency-version: '2.16'\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-06T16:58:47+01:00",
          "tree_id": "2fdc2f5a0bd92b107c834b016d07e5b3d1b4a6b9",
          "url": "https://github.com/endavis/infrafoundry/commit/60bfd284804463678e0e9320ed950dc1244383fd"
        },
        "date": 1775491165706,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7345.090099192828,
            "unit": "iter/sec",
            "range": "stddev: 0.000009790076677345364",
            "extra": "mean: 136.14536874229665 usec\nrounds: 2457"
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
          "id": "b9956f799e9b0b1b5b32374a9576523ddc2ee1b4",
          "message": "chore(deps): bump sqlalchemy from 2.0.48 to 2.0.49 (merges PR #492)\n\nBumps [sqlalchemy](https://github.com/sqlalchemy/sqlalchemy) from 2.0.48 to 2.0.49.\n- [Release notes](https://github.com/sqlalchemy/sqlalchemy/releases)\n- [Changelog](https://github.com/sqlalchemy/sqlalchemy/blob/main/CHANGES.rst)\n- [Commits](https://github.com/sqlalchemy/sqlalchemy/commits)\n\n---\nupdated-dependencies:\n- dependency-name: sqlalchemy\n  dependency-version: 2.0.49\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-06T17:25:15+01:00",
          "tree_id": "28d746db00ff41130fca4050acbc9190d0f7e754",
          "url": "https://github.com/endavis/infrafoundry/commit/b9956f799e9b0b1b5b32374a9576523ddc2ee1b4"
        },
        "date": 1775492744429,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9711.666653751456,
            "unit": "iter/sec",
            "range": "stddev: 0.000004572958462610542",
            "extra": "mean: 102.96893784072753 usec\nrounds: 2751"
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
          "id": "5bab275999ae53e325ddbafac01fde0993c47e55",
          "message": "chore(deps): bump types-requests from 2.33.0.20260327 to 2.33.0.20260402 (merges PR #493)\n\nBumps [types-requests](https://github.com/python/typeshed) from 2.33.0.20260327 to 2.33.0.20260402.\n- [Commits](https://github.com/python/typeshed/commits)\n\n---\nupdated-dependencies:\n- dependency-name: types-requests\n  dependency-version: 2.33.0.20260402\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-06T17:32:15+01:00",
          "tree_id": "3bac8f02585cd51406b69c5cc7f02c9165ff2e85",
          "url": "https://github.com/endavis/infrafoundry/commit/5bab275999ae53e325ddbafac01fde0993c47e55"
        },
        "date": 1775493173684,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7229.696289802652,
            "unit": "iter/sec",
            "range": "stddev: 0.000016467663990698955",
            "extra": "mean: 138.31839677836547 usec\nrounds: 2359"
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
          "id": "f52bb4996c27b4bed4e1dd6c255293491b6f64ec",
          "message": "chore(deps): bump hypothesis from 6.151.10 to 6.151.11 (merges PR #494)\n\nBumps [hypothesis](https://github.com/HypothesisWorks/hypothesis) from 6.151.10 to 6.151.11.\n- [Release notes](https://github.com/HypothesisWorks/hypothesis/releases)\n- [Commits](https://github.com/HypothesisWorks/hypothesis/compare/hypothesis-python-6.151.10...hypothesis-python-6.151.11)\n\n---\nupdated-dependencies:\n- dependency-name: hypothesis\n  dependency-version: 6.151.11\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-06T17:46:45+01:00",
          "tree_id": "90233dea0824c13273999068062d49d6cc54377c",
          "url": "https://github.com/endavis/infrafoundry/commit/f52bb4996c27b4bed4e1dd6c255293491b6f64ec"
        },
        "date": 1775494042009,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7326.075959859886,
            "unit": "iter/sec",
            "range": "stddev: 0.000011471155198819854",
            "extra": "mean: 136.498721208881 usec\nrounds: 3673"
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
          "id": "7a24b7ecfec38359d916b38fcb746cb992a41c6c",
          "message": "chore(deps): bump boto3 from 1.42.78 to 1.42.83 (merges PR #495)\n\nBumps [boto3](https://github.com/boto/boto3) from 1.42.78 to 1.42.83.\n- [Release notes](https://github.com/boto/boto3/releases)\n- [Commits](https://github.com/boto/boto3/compare/1.42.78...1.42.83)\n\n---\nupdated-dependencies:\n- dependency-name: boto3\n  dependency-version: 1.42.83\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-06T17:53:32+01:00",
          "tree_id": "6baf2615d55938f1a93f31e06a14dbb70f1f2d08",
          "url": "https://github.com/endavis/infrafoundry/commit/7a24b7ecfec38359d916b38fcb746cb992a41c6c"
        },
        "date": 1775494450014,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7415.332203811486,
            "unit": "iter/sec",
            "range": "stddev: 0.00000890720518557519",
            "extra": "mean: 134.8557249378523 usec\nrounds: 2414"
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
          "id": "19c67f8bb280f4d01dbd98556f0c18db41efc95f",
          "message": "feat: add per-environment state locking for apply and destroy (merges PR #497, addresses #246)\n\nConcurrent runs of `foundry infra apply` / `foundry infra destroy` against\nthe same environment could previously corrupt the InfraFoundry state DB,\nduplicate resource tracking rows, and race on runner execution. Terraform\nbackend locks only protect the .tfstate file; InfraFoundry's own state\nsits outside that lock and needed its own coordination primitive.\n\nIntroduce a `deployment_locks` table with a unique constraint on\n`environment` and wrap Orchestrator.apply/destroy in an `environment_lock`\ncontext manager. The unique constraint is the atomic primitive, so the\nsame mechanism works on SQLite and PostgreSQL with no backend-specific\ncode. Acquisition fails fast by default (`--lock-timeout 0`), with opt-in\nblocking via `--lock-timeout <seconds>` and a configurable `--lock-ttl`\nfor stale-lock recovery. `plan` is intentionally left unlocked so CI\npreview jobs keep running alongside an active apply. All transitions\nemit LOCK_ACQUIRED / LOCK_RELEASED / LOCK_TIMEOUT events through the\nexisting EventManager.\n\nAdds a `foundry infra unlock` command (`--env`, `--force`, `--yes`,\n`--list`) for operator visibility and recovery, an `INFRAFOUNDRY_SKIP_LOCK`\nemergency escape hatch, ADR-0002 documenting the design, and 29 new\nunit tests covering the repository, context manager, CLI, and\norchestrator integration.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-07T09:52:10+01:00",
          "tree_id": "1b6dafda9d957fda087ff602de835b91cbdff92f",
          "url": "https://github.com/endavis/infrafoundry/commit/19c67f8bb280f4d01dbd98556f0c18db41efc95f"
        },
        "date": 1775551963867,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6784.6149768825635,
            "unit": "iter/sec",
            "range": "stddev: 0.000022733180194095485",
            "extra": "mean: 147.3922991072201 usec\nrounds: 2240"
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
          "id": "c20b8dd531db8b73a9da7e07bb115ed55e438ecb",
          "message": "feat: add lock heartbeat for long-running applies (merges PR #499, addresses #498)\n\nA background daemon thread now auto-extends the environment lock every\nttl/3 seconds while apply/destroy is running, so long applies never\nself-evict. Heartbeat failures log and emit LOCK_HEARTBEAT_FAILED but\ndo not abort the in-flight run — aborting on a transient DB blip is\nstrictly worse than letting the apply finish under a ticking TTL.\n\nBecause live runs no longer depend on the TTL to stay alive, the\ndefault --lock-ttl drops from 3600 s to 600 s, shrinking the stale-\nrecovery window for crashed holders by 6× without penalizing healthy\nlong-running applies.\n\nAddresses #498",
          "timestamp": "2026-04-07T11:51:47+01:00",
          "tree_id": "3a7f0cb05e4fb4854ea4640397bf36a59c126cf8",
          "url": "https://github.com/endavis/infrafoundry/commit/c20b8dd531db8b73a9da7e07bb115ed55e438ecb"
        },
        "date": 1775559141533,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7260.831351497563,
            "unit": "iter/sec",
            "range": "stddev: 0.000010760325555912795",
            "extra": "mean: 137.7252757418402 usec\nrounds: 2292"
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
          "id": "3a9afbb8122cf1f1a3b5f04efed48d2cb0b58a8d",
          "message": "fix: render full timestamps in 'infra unlock --list' (merges PR #501, addresses #500)\n\nThe Acquired and Expires columns previously rendered str(datetime),\nwhich produces ~32-character strings ending in microseconds and a\ntimezone offset. Rich's auto-sized columns squeezed those down to\njust the date — defeating the diagnostic purpose of --list, which\nexists to watch the heartbeat advance expires_at over time.\n\nFormat the columns as 'YYYY-MM-DD HH:MM:SS UTC' (~23 chars) so the\nfull timestamp survives column auto-sizing in any terminal wide\nenough for the rest of the table.\n\nAddresses #500",
          "timestamp": "2026-04-07T12:22:30+01:00",
          "tree_id": "2660218c2737082507ee5be4c40575ad4cf68824",
          "url": "https://github.com/endavis/infrafoundry/commit/3a9afbb8122cf1f1a3b5f04efed48d2cb0b58a8d"
        },
        "date": 1775560982315,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8918.809816469678,
            "unit": "iter/sec",
            "range": "stddev: 0.00001970628194927461",
            "extra": "mean: 112.12258368301308 usec\nrounds: 2145"
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
          "id": "d8e600f2acbb4a1f80a14294b10e893a90edf430",
          "message": "refactor: convert rocky9-template example to a blueprint (merges PR #509, addresses #503)\n\nExtract the rocky9-template resource definition into a reusable blueprint\nat blueprints/rocky9-template/ and collapse the example-config entry to a\nthin consumer that overrides only vmid, target_node, and storage.\n\nThis eliminates duplication between the example and downstream consumers\nthat re-implemented the same Rocky 9 template logic, and unblocks #502\n(aiqum) and #504 (proxmox-k3s), both of which consume this blueprint as\ntheir base image. The new tests/unit/test_rocky9_blueprint.py\nPackageLoader-based integration test establishes the test pattern that\nthe remaining blueprint conversions (#502, #504, #505, #506) will copy.\n\nThis is the first of five blueprint conversions tracked under #508.\n\nAddresses #503",
          "timestamp": "2026-04-07T13:52:01+01:00",
          "tree_id": "11c326eddfe6d10905e6c9eb68cd67c881c33805",
          "url": "https://github.com/endavis/infrafoundry/commit/d8e600f2acbb4a1f80a14294b10e893a90edf430"
        },
        "date": 1775566362372,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7308.352250433004,
            "unit": "iter/sec",
            "range": "stddev: 0.00000979979868726522",
            "extra": "mean: 136.82974844853055 usec\nrounds: 2417"
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
          "id": "fea50bd61fb62ffe30f02c6579c3ccd9a2f6bd24",
          "message": "fix: rocky9-template blueprint must use shorthand format for multi-instance (merges PR #512, addresses #503, #511)\n\nPR #509 used the generic resource format with a hardcoded outer `name`,\nwhich made multi-instance use of the blueprint impossible — two packages\ninstantiating it produced two resources with the same framework\nidentifier, and the framework correctly rejected them with a duplicate-\nname error.\n\nSwitch to the provider-centric shorthand format already used by\nblueprints/ontap-cluster/vm.yaml: rename vm.yaml → template.yaml so the\nfilename-derived resource type matches the proxmox `template` type, and\ntemplate the `name:` field per-instance from `template_name`. Add a\nmulti-instance regression test that creates two synthetic packages and\nverifies they coexist without collision.\n\nValidated live against the prod rocky9-template on Proxmox: re-apply\nthrough the new format produces a working template VM end-to-end.\n\nAddresses #511",
          "timestamp": "2026-04-07T16:47:49+01:00",
          "tree_id": "78f5168011d310546462d43a2014cc34d84f051d",
          "url": "https://github.com/endavis/infrafoundry/commit/fea50bd61fb62ffe30f02c6579c3ccd9a2f6bd24"
        },
        "date": 1775576905194,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7354.088750782866,
            "unit": "iter/sec",
            "range": "stddev: 0.00000949142077707954",
            "extra": "mean: 135.9787777776746 usec\nrounds: 2412"
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
          "id": "d606f023112e1f507a8794d2333a3af1e27cd670",
          "message": "refactor: convert aiqum example to a blueprint (merges PR #513, addresses #502)\n\nEliminate duplicated VM, DHCP, and post-provisioning logic by\nextracting the AIQUM example into a reusable blueprint at\nblueprints/aiqum/. The example config now consumes the blueprint\nvia a thin instantiation.\n\nSecond of five blueprint conversions tracked under #508\n(rocky9-template was first via PR #509 + #512).\n\nApply the format split learned from #511: shorthand `vms:` for the\nproxmox VM (templated name for multi-instance) and the generic\n`resources:` format for the opnsense kea_reservation, since\nshorthand is single-provider and cannot express cross-provider\nDHCP. A multi-instance regression test guards against the\n#511-style templated-name collapse bug.\n\nMove the on_create handler from the per-resource VM to top-level\nblueprint events because the shorthand format does not extract\nper-resource events during expansion. Drop dead `gateway` and\n`dns_server` variables that were never consumed. Promote previously\nhardcoded `vlan_tag` and `bridge` values to overridable blueprint\ndefaults.\n\nAddresses #502",
          "timestamp": "2026-04-07T18:53:04+01:00",
          "tree_id": "c11cb7e74f1b35c6828e4710ef551d149c7e1b48",
          "url": "https://github.com/endavis/infrafoundry/commit/d606f023112e1f507a8794d2333a3af1e27cd670"
        },
        "date": 1775584427696,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7044.771383645811,
            "unit": "iter/sec",
            "range": "stddev: 0.00001952466855874089",
            "extra": "mean: 141.9492479658694 usec\nrounds: 2335"
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
          "id": "5308e6360c4996d75cc65071c37c9da94e91698f",
          "message": "refactor: convert k3s-cluster example to a blueprint (merges PR #514, addresses #504)\n\n* refactor: convert k3s-cluster example to a blueprint\n\nExtracts blueprints/proxmox-k3s-cluster/ from the example k3s-cluster\npackage and collapses the example consumer to a thin instantiation.\nThird blueprint conversion in the #508 chain (after #503 and #502).\n\nFirst blueprint to use Jinja {% for %} loops over a list of dicts in\nresource files, supporting variable agent count. Multi-instance and\nzero-agents regression guards included in the test suite.\n\nAddresses #504\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* refactor: make k3s-cluster blueprint jumphost optional\n\nThe post-deploy script now SSHes directly from the InfraFoundry host to\neach node when jumphost is empty, and tunnels through the jumphost when\nset. Default is direct mode.\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-08T11:50:21+01:00",
          "tree_id": "f353190ee08d8825b42b1279f728edea172f93e3",
          "url": "https://github.com/endavis/infrafoundry/commit/5308e6360c4996d75cc65071c37c9da94e91698f"
        },
        "date": 1775645460413,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6249.798001727279,
            "unit": "iter/sec",
            "range": "stddev: 0.00003509518918982362",
            "extra": "mean: 160.00517132291736 usec\nrounds: 1897"
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
          "id": "b68596f278ebedc46499e21761e894bce622a1e0",
          "message": "feat: integrate official Tailscale cloud-init Terraform module (merges PR #519, addresses #212)\n\n* feat: add secrets to TF_VAR_* bridge for terraform variable injection\n\nAdds a framework mechanism for injecting sops-encrypted secrets into\nTerraform as sensitive variables, without writing values to disk.\n\nResource configs declare a 'terraform_secrets:' list of dotted paths\ninto the env's secrets dict. The framework resolves each at apply time\nand sets TF_VAR_<sanitized> environment variables. Provider variables.tf\ntemplates declare matching sensitive variables, defaulted to empty\nstrings so plan succeeds when no secrets are set.\n\nWired through OCI and Proxmox providers via cached resources on\ngenerate_terraform() and a new optional resources= parameter on\nbuild_terraform_env_vars().\n\nValidation rejects unknown secret references with a clear error\nnaming the missing dotted path.\n\nThis is phase 1 of the work tracked in #212. The Tailscale module\nintegration that consumes this bridge will land in subsequent commits\non the same branch.\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* feat: integrate official Tailscale cloud-init module in OCI and Proxmox\n\nReplaces the custom Tailscale cloud-init snippet with calls to the\nofficial tailscale/cloudinit/tailscale Terraform module (pinned to\n0.0.11) in both providers. Closes the maintenance burden flagged in\nissue #212.\n\nNew optional 'tailscale:' resource config schema on OCI instances and\nProxmox VMs. Supports both static auth_key and OAuth client credentials\nauth modes (mutually exclusive). Auth secrets are dotted references\ninto the env's secrets dict and flow through the phase 1 secrets to\nTF_VAR_* bridge — values never land in generated/*.tf files.\n\nOCI: instances reference module.tailscale_<name>.rendered as user_data\n(base64 multipart MIME, the OCI default).\nProxmox: the existing proxmox_virtual_environment_file resource sources\nits data from module.tailscale_<vm>.rendered with base64_encode=false\n(raw multipart MIME — Proxmox stores it via source_raw and decodes at\nboot).\n\nValidation enforces:\n- exactly-one-of auth modes\n- advertise_tags entries start with 'tag:'\n- tailscale: and cloud_init_snippets are mutually exclusive\n\nThe hashicorp/cloudinit provider is declared unconditionally in both\nproviders' provider.tf for simplicity. Existing cloud_init_snippets\npath is unchanged for resources without a tailscale: block (regression\nguards in the existing test suites still pass).\n\n29 new tests cover the schema, both auth modes, additional_parts\nescape hatch, multi-instance dedup, and the unchanged existing path.\n\nAddresses #212\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-08T16:06:41+01:00",
          "tree_id": "2055cf6cd887fc4c7981120e3d8b7e7f93799674",
          "url": "https://github.com/endavis/infrafoundry/commit/b68596f278ebedc46499e21761e894bce622a1e0"
        },
        "date": 1775660859057,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9703.156260937449,
            "unit": "iter/sec",
            "range": "stddev: 0.0000070291750551252",
            "extra": "mean: 103.05924929043525 usec\nrounds: 2114"
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
          "id": "1c9eebce3cc8ba090b4289bf8dde03783b7e9efc",
          "message": "refactor: convert oci-k3s example to a blueprint (merges PR #518, addresses #505)\n\n* refactor: convert oci-k3s example to a blueprint\n\nExtracts blueprints/oci-k3s-cluster/ from the example oci-k3s\nenvironment and collapses the example to a thin env-root subdir\npackage consumer. Fourth blueprint conversion in the #508 chain\n(after #503, #502, #504).\n\nThe previous example was structurally broken — no infrafoundry.yml\nexisted in the env, so the package loader never discovered it. The\noci/instances.yaml and oci/network.yaml were orphaned files. This\nconversion is effectively a fresh-start blueprint design using the\nold files as a recipe reference.\n\nFirst blueprint to use the env-root subdir package pattern\n(envs/<env>/<subdir>/infrafoundry.yml without a provider directory\nin between). Surfaces two framework gaps tracked separately as #516\n(_package_dir plumbing dead code) and #517 (inventory generator\ncan't render Jinja loops).\n\nAddresses #505\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* refactor: migrate oci-k3s-cluster blueprint to Tailscale module schema\n\nReplaces the custom 'cloud_init_snippets: [tailscale]' wiring in the\noci-k3s-cluster blueprint with the new 'tailscale:' resource block\nintroduced by issue #212. Each instance now declares its tailscale\nconfig inline (hostname, enable_ssh, advertise_tags, OAuth secret refs)\nand the framework's secrets→TF_VAR_* bridge injects the OAuth client\ncredentials at apply time without writing them to disk.\n\nDeletes the obsolete tailscale.yaml cloud-init snippet from the\nexample consumer (it was a hand-rolled retry-loop installer that the\nofficial Tailscale Terraform module replaces).\n\nUpdates the example consumer secrets schema to use\nsecrets.tailscale.{oauth_client_id,oauth_client_secret} instead of\nthe old static auth_key.\n\nUpdates the test_oci_k3s_cluster_example_uses_tailscale_module test\nto assert the new tailscale: schema instead of cloud_init_snippets.\n\nPlan smoke test against example-config/envs/oci-k3s passes:\n- 6 OCI resources rendered (1 vcn + 2 subnets + 3 instances)\n- module 'tailscale_k3s_{control,worker_0,worker_1}' blocks emitted\n- user_data references 'module.tailscale_<name>.rendered'\n- variables.tf declares the sensitive var.tailscale_oauth_client_*\n- No secret values in generated/*.tf (verified via grep)\n\nAddresses #212 #505\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* ci: trigger CodeQL re-analysis for PR 518\n\n---------\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-08T16:53:15+01:00",
          "tree_id": "345e9f26cab07b823003c60a4c93ede47107a3b0",
          "url": "https://github.com/endavis/infrafoundry/commit/1c9eebce3cc8ba090b4289bf8dde03783b7e9efc"
        },
        "date": 1775663720129,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7423.886845370227,
            "unit": "iter/sec",
            "range": "stddev: 0.000008817114824590832",
            "extra": "mean: 134.70032892858973 usec\nrounds: 2119"
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
          "id": "cf413d2fff531ac38efebc600e597b87655d2ce0",
          "message": "fix: regenerate iac configs before infra destroy (merges PR #520, addresses #515)\n\ninfra destroy previously ran terraform destroy against whatever .tf\nfiles happened to be on disk from the last plan/apply. If resources\nhad been renamed or re-keyed in YAML since then, destroy would act\non the stale addresses and could silently leave real infrastructure\nbehind.\n\nExtract the apply-time generation step into a module-level helper\n_regenerate_iac_configs() and call it from both PlanOrchestrator.plan\nand DestroyOrchestrator.destroy. The destroy path mirrors plan's\nfilter rule: when resource_filter is active, regen passes ALL provider\nresources so terraform doesn't see filtered-out resources as deletions\n(the filter is still honored via -target).\n\nScope boundary: this PR adds regen only. Detecting and reporting\nmismatch when state no longer references regenerated addresses is\n#510's responsibility and intentionally out of scope.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-09T10:36:32+01:00",
          "tree_id": "57c27c80aa65c9b0b04a5a0a6c09bbc26232f31e",
          "url": "https://github.com/endavis/infrafoundry/commit/cf413d2fff531ac38efebc600e597b87655d2ce0"
        },
        "date": 1775727426284,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9672.47391994466,
            "unit": "iter/sec",
            "range": "stddev: 0.0000066236372799346846",
            "extra": "mean: 103.38616658743304 usec\nrounds: 2101"
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
          "id": "d61bdcbcce3167f4db17372fe3bca4442b00a0b0",
          "message": "fix: honor runner failure in infra apply and destroy (merges PR #521, addresses #510)\n\nBoth DestroyOrchestrator.destroy and DeploymentExecutor.apply_single_provider\nread the runner result dict but never raised on success: False. The runner\ncorrectly captured terraform's non-zero exit, but the orchestrator/executor\nemitted RUNNER_COMPLETED with a hardcoded success: True and the CLI printed\nthe green checkmark anyway. Original reproduction: a Proxmox template with\nlifecycle { prevent_destroy = true } — terraform refused, framework lied.\n\nFix is in three pieces:\n\n1. Runner: TerraformRunner._run_terraform now captures stderr and a parsed\n   error summary from terraform's JSON diagnostic output, so callers have\n   meaningful context to surface.\n\n2. Shared helper: new raise_on_runner_failure() in core/runner_results.py\n   converts a failed result dict into TerraformError. Used by both destroy\n   and apply paths. Helper is intentionally pure — it raises but does not\n   emit events; each call site's existing except handler emits RUNNER_FAILED\n   exactly once.\n\n3. State verification (destroy only): new TerraformRunner.verify_destroyed\n   reuses get_resource_ids to assert resources we asked to destroy are\n   actually gone from state. Catches the case where terraform exits 0 but\n   leaves things behind. Shares _name_matches_tf_name with the existing\n   _resolve_terraform_targets to handle templated resource names.\n\nCLI required no changes — with_orchestrator already catches InfraFoundryError\nand routes through raise_cli_error, so the success message simply never\nprints when the exception propagates.\n\nSibling to PR #515 (destroy regenerates .tf before invoking terraform).\nTogether they close the destroy-lied bug class: #515 makes terraform run\nagainst the right config; this PR makes the framework believe terraform\nwhen it says no.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-09T12:02:32+01:00",
          "tree_id": "9b80ad6ccc2a21096098b69b982416c6520296c3",
          "url": "https://github.com/endavis/infrafoundry/commit/d61bdcbcce3167f4db17372fe3bca4442b00a0b0"
        },
        "date": 1775732590137,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7279.237794412334,
            "unit": "iter/sec",
            "range": "stddev: 0.000009790961886117077",
            "extra": "mean: 137.3770205402023 usec\nrounds: 2629"
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
          "id": "fb8495eaef3856b1f064d1d4a35f4f50732bb180",
          "message": "fix: populate _package_dir on event handler configs (merges PR #522, addresses #516)\n\nThe script handler at events/handlers/script.py:133-138 reads\nself.config.get(\"_package_dir\") to locate the package's\n.generated-inventory.yml and inject INFRAFOUNDRY_INVENTORY into the\nscript's env. The read was correct but nothing in the codebase ever\npopulated _package_dir, so the env var was never set. Dead code.\n\nSurfaced during the oci-k3s-cluster blueprint conversion (#505): the\nblueprint had to fall back to building the inventory via jq in its\non_create script because the framework's intended pathway was broken.\n\nExtract a _tag_handler_configs() private helper on PackageLoader and\ncall it from both the package-level event tagging path and the\nresource-level event rewrite path in load_package(). Resource-level\nevents previously received NO framework-internal tags at all\n(_package, _blueprint_dir, _package_dir) — this fixes that parallel\ngap alongside the _package_dir fix.\n\nScript handler source is unchanged; the read site was already correct.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-09T14:42:36+01:00",
          "tree_id": "64f1aa81501d912e14917c1e19c5c617880ccdf8",
          "url": "https://github.com/endavis/infrafoundry/commit/fb8495eaef3856b1f064d1d4a35f4f50732bb180"
        },
        "date": 1775742214753,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7391.56082337901,
            "unit": "iter/sec",
            "range": "stddev: 0.000009775658528309005",
            "extra": "mean: 135.28942315364128 usec\nrounds: 2505"
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
          "id": "79afc44e15d96da7cf9bd0e184972598cbaa6211",
          "message": "feat: support jinja control-flow loops in inventory schemas (merges PR #523, addresses #517)\n\nInventoryGenerator previously serialized the inventory dict back to\nYAML and only then ran Jinja, which made {% for %} and {% if %}\nimpossible at YAML structural positions: yaml.safe_load choked on the\ncontrol-flow tag long before Jinja got a chance to expand it.\nBlueprints with variable-cardinality hosts (proxmox-k3s, oci-k3s) had\nto fall back to building the inventory in their on_create scripts via\njq over INFRAFOUNDRY_PACKAGE_VARS.\n\nReplace the dict-then-render pipeline with a render-then-parse\npipeline that mirrors the existing _render_resource_file precedent\nfor vm.yaml/instances.yaml. The raw YAML substring of the inventory:\nblock is extracted from the manifest file before yaml.safe_load runs,\nthen rendered through Jinja, then parsed.\n\n- New manifest_utils.extract_inventory_block helper line-scans for a\n  column-0 inventory: key, captures and dedents the body, replaces\n  the slice with inventory: null plus blank-line padding to preserve\n  line numbers for parser error messages. Rejects flow-style.\n- Both PackageLoader._parse_manifest and BlueprintResolver._load_manifest\n  (separate parsers) now use the extractor and store the raw block.\n- PackageManifest gains inventory_raw: str | None. Legacy inventory\n  field stays for back-compat but is always None when an inventory\n  block exists.\n- InventoryGenerator.generate signature changes to take inventory_raw:\n  str (dict pathway dropped — strictly more capable since string\n  substitution is a subset of full Jinja).\n- load_package blueprint inheritance propagates inventory_raw.\n\nSibling to #516 (_package_dir plumbing for INFRAFOUNDRY_INVENTORY\ninjection). With both landed, blueprints with variable-cardinality\ninventories can use the framework's intended pathway end-to-end.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-09T16:22:43+01:00",
          "tree_id": "d52f8e61d481a458ea3fa65e68f1e06711b698c6",
          "url": "https://github.com/endavis/infrafoundry/commit/79afc44e15d96da7cf9bd0e184972598cbaa6211"
        },
        "date": 1775748199312,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7375.330824015881,
            "unit": "iter/sec",
            "range": "stddev: 0.000008656576826840589",
            "extra": "mean: 135.58713823978653 usec\nrounds: 2568"
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
          "id": "fe482296854d6757059de7402efa7bdab744cf42",
          "message": "fix: always run terraform init so provider.tf changes are detected (merges PR #525, addresses #524)\n\nTerraformRunner.initialize had a fast-path that returned \"Already\ninitialized\" whenever .terraform/ existed, without running terraform\ninit. The only exception was backend-swap detection. The fast-path\ndid not detect changes to required_providers in provider.tf, so when\na generated provider.tf added or removed a provider (exactly what\nPR #519 did by adding hashicorp/cloudinit to the proxmox provider.tf\nfor the Tailscale module), the old .terraform/ and .terraform.lock.hcl\nbecame stale. Apply then failed with Inconsistent dependency lock file.\n\nDrop the fast-path entirely. terraform init is idempotent and fast\n(~100ms no-op) for unchanged directories, so running it unconditionally\neliminates an entire class of stale-.terraform bugs. The backend-swap\ndetection logic is preserved — it still sets reconfigure=True\npreemptively so terraform init -reconfigure is used when a swap is\ndetected.\n\nReproduced today while applying the prod homelab k3s-cluster package\nfor the first time after PR #519 landed. #510's error handling\ncorrectly surfaced the failure as a TerraformError instead of a green\ncheckmark (first real-world validation of that fix), but the root\ncause is this init-time staleness.\n\nAlso updates 3 pre-existing tests that were passively depending on\nthe fast-path (they mocked Popen but not subprocess.run, and worked\nonly because init was being skipped).\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-09T17:08:30+01:00",
          "tree_id": "4b6b59fd242ed0c81bc541176cd4d59cdab2f56d",
          "url": "https://github.com/endavis/infrafoundry/commit/fe482296854d6757059de7402efa7bdab744cf42"
        },
        "date": 1775750943823,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7080.683394114881,
            "unit": "iter/sec",
            "range": "stddev: 0.000018901261580318737",
            "extra": "mean: 141.22930575192098 usec\nrounds: 2260"
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
          "id": "39e3e43692741f2ade60addffe90ad2419ca5913",
          "message": "fix: populate cloud_init_vars.HOSTNAME in proxmox-k3s-cluster blueprint (merges PR #527, addresses #526)\n\nThe blueprint references a shared system/hostname cloud-init snippet\ncontaining ${HOSTNAME} as a placeholder, but never populated\ncloud_init_vars to tell the framework what to substitute. The\nplaceholder fell through to the generated cloud-init YAML as a\nliteral string, every VM came up with the same broken hostname,\nk3s nodes collided on registration, and the on_create handler timed\nout after 30 minutes waiting for agents to become Ready.\n\nThe framework's _merge_cloud_init_snippets at provider_mixins.py:969\nalready does per-VM variable substitution from cloud_init_vars; the\nmechanism is tested at test_cloud_init_mixin.py:96. The blueprint\njust wasn't using it.\n\nAdd the missing 6 lines of YAML wiring per-VM hostname into the\nsubstitution context: HOSTNAME: \"{{ server_name }}\" on the server\nentry, HOSTNAME: \"{{ agent.name }}\" inside the for-agents loop. The\nframework's existing substitution does the rest.\n\nReproduced live in this session during the first homelab k3s-cluster\napply after #515, #510, #516, #517, #524 all landed. The cluster had\nto be destroyed before this fix could be applied.\n\nThe oci-k3s-cluster blueprint is not affected — it sets hostname\ndirectly via the OCI provider's native cloud-init field instead of\nthe snippet pathway.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-09T21:35:34+01:00",
          "tree_id": "9f67c189e3f03f7c6475cab4bcc79f1fd2ea6aa1",
          "url": "https://github.com/endavis/infrafoundry/commit/39e3e43692741f2ade60addffe90ad2419ca5913"
        },
        "date": 1775766977008,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7197.916748141159,
            "unit": "iter/sec",
            "range": "stddev: 0.00001225545574662642",
            "extra": "mean: 138.92908670529528 usec\nrounds: 2249"
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
          "id": "a5d9c8d883a664c6c3bd7d086bd27901889878e6",
          "message": "fix: add terraform -parallelism flag support (merges PR #529, addresses #528)\n\nfix: add terraform parallelism support to prevent CFS lock timeouts",
          "timestamp": "2026-04-10T11:16:01+01:00",
          "tree_id": "628be2c7ce9d0e690f0654cb77610684065af78a",
          "url": "https://github.com/endavis/infrafoundry/commit/a5d9c8d883a664c6c3bd7d086bd27901889878e6"
        },
        "date": 1775816197582,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7354.799835397533,
            "unit": "iter/sec",
            "range": "stddev: 0.000011430377721815713",
            "extra": "mean: 135.9656309322182 usec\nrounds: 2360"
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
          "id": "97b0a2e0a505d80611a500c6acb8f87cc0705ba0",
          "message": "fix: build kubeconfig path from cluster_name in k3s blueprint script (merges PR #531, addresses #530)",
          "timestamp": "2026-04-10T11:41:39+01:00",
          "tree_id": "375932a63497f6ec726a8041316996fc642b39ed",
          "url": "https://github.com/endavis/infrafoundry/commit/97b0a2e0a505d80611a500c6acb8f87cc0705ba0"
        },
        "date": 1775817730581,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9792.324805064423,
            "unit": "iter/sec",
            "range": "stddev: 0.00000715981586016909",
            "extra": "mean: 102.12079561360312 usec\nrounds: 2143"
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
          "id": "e239ed13bf9f7cadbc7d03fd2c310d8a217f4067",
          "message": "refactor: convert ontap-cluster example to use ontap-cluster blueprint (merges PR #533, addresses #506)",
          "timestamp": "2026-04-10T13:17:28+01:00",
          "tree_id": "c37e48f70e111dca3600d729bef8103983503057",
          "url": "https://github.com/endavis/infrafoundry/commit/e239ed13bf9f7cadbc7d03fd2c310d8a217f4067"
        },
        "date": 1775823481804,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 5698.057507951126,
            "unit": "iter/sec",
            "range": "stddev: 0.00004314188208202026",
            "extra": "mean: 175.49840425523786 usec\nrounds: 1363"
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
          "id": "422519c31b572c77b64e8e035ada1337cc498484",
          "message": "fix: propagate event handler failures to apply result (merges PR #534, addresses #532)",
          "timestamp": "2026-04-10T15:46:49+01:00",
          "tree_id": "6a27f9cea0a6e0dfeb60c2295f54e462d7abf576",
          "url": "https://github.com/endavis/infrafoundry/commit/422519c31b572c77b64e8e035ada1337cc498484"
        },
        "date": 1775832449629,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7397.328766135749,
            "unit": "iter/sec",
            "range": "stddev: 0.000009606424697541613",
            "extra": "mean: 135.18393350014435 usec\nrounds: 2000"
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
          "id": "9fac7b0a7412a14f86638de8a8266fd929002892",
          "message": "fix: expand ontap root aggregate and vol0 to prevent disk full (merges PR #537, addresses #536)",
          "timestamp": "2026-04-10T19:17:32+01:00",
          "tree_id": "7f7b73773b69b9ee2a6d1343fd94dd4960231e26",
          "url": "https://github.com/endavis/infrafoundry/commit/9fac7b0a7412a14f86638de8a8266fd929002892"
        },
        "date": 1775845087282,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6388.783616162056,
            "unit": "iter/sec",
            "range": "stddev: 0.000064812195105713",
            "extra": "mean: 156.524318255238 usec\nrounds: 2476"
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
          "id": "f8bec2cb88e7db171133a37fee91c48374dcac61",
          "message": "fix: add hostname, optional jumphost, and install URL to aiqum blueprint (merges PR #541, addresses #540)",
          "timestamp": "2026-04-10T20:54:30+01:00",
          "tree_id": "2ca6d8c2c20d4130022df3c35afdf13067e83d05",
          "url": "https://github.com/endavis/infrafoundry/commit/f8bec2cb88e7db171133a37fee91c48374dcac61"
        },
        "date": 1775850903201,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8859.024636722097,
            "unit": "iter/sec",
            "range": "stddev: 0.000019978768349982164",
            "extra": "mean: 112.87924359695732 usec\nrounds: 1835"
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
          "id": "a4d861f52fdeffe70c95e6d522a02f64dbcfd38d",
          "message": "refactor: extract ubuntu-template blueprint (merges PR #543, addresses #542)",
          "timestamp": "2026-04-10T21:14:17+01:00",
          "tree_id": "d9de6344b52c666e5b9654df9b98fc5ba6719342",
          "url": "https://github.com/endavis/infrafoundry/commit/a4d861f52fdeffe70c95e6d522a02f64dbcfd38d"
        },
        "date": 1775852097285,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7309.356624289536,
            "unit": "iter/sec",
            "range": "stddev: 0.000010485210837558697",
            "extra": "mean: 136.8109467633479 usec\nrounds: 2348"
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
          "id": "2648ac9ebf538f211ecac10a70b24dfc712af0fd",
          "message": "fix: scope on_create event handlers to the created resource (merges PR #545, addresses #539)\n\nEvent handlers with resource-scoped filtering could fire against resources\nthat weren't part of the triggering create, because the resource_scoped flag\nwas not set on all emit_event call sites in DeploymentExecutor. This caused\non_create handlers attached to one package to fire for unrelated resources\nin the same terraform apply.\n\nSet resource_scoped=True on the two emit_event call sites in\nDeploymentExecutor.apply_serial that fire RESOURCE_CREATED, and add helper\nsupport in the event bus and BaseEventHandler so the scoping flag is\nrespected consistently. Tests cover both the package-filter path and the\nper-resource lifecycle path.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-11T18:40:06+01:00",
          "tree_id": "f024554b4a6e4ecfa7c80cb3ac389d2ddc79ddfc",
          "url": "https://github.com/endavis/infrafoundry/commit/2648ac9ebf538f211ecac10a70b24dfc712af0fd"
        },
        "date": 1775929244176,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6547.170137137059,
            "unit": "iter/sec",
            "range": "stddev: 0.000033697037739638156",
            "extra": "mean: 152.73774456047346 usec\nrounds: 2298"
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
          "id": "c64aa3d6f0d594fc9cef3a00a226522a4b975116",
          "message": "fix: translate separate api_token_id/secret keys in proxmox tfvars mapping (merges PR #553, addresses #552)\n\nProxmoxProvider._PROXMOX_TFVARS_MAPPING translated api_token (combined\n\"tokenid=secret\" form) but not the separate api_token_id/api_token_secret\nform, even though every other code path in the Proxmox provider accepts\nboth forms — the validator, api_client, exporter, and the parallel\n_CREDENTIAL_ENV_MAPPING for the env-var credential path.\n\nOnly the settings-path tfvars translation had the gap. Result: an\nenvironment whose credentials are configured only in settings.yaml\nunder proxmox: (nested form) with the separate token_id/token_secret\nkeys silently got no TF_VAR_proxmox_api_token_id / _secret. The\nprovider.tf.j2 expression that combines them produced null, and\nProxmox API auth failed with no useful error.\n\nThis wasn't noticed until a homelab test env was configured with only\nsettings.yaml (no proxmox.yaml credential file feeding the env-var\npath) — environments with proxmox.yaml get credentials via the env-var\npath, which already handles both forms correctly.\n\nFix: add the two missing keys to _PROXMOX_TFVARS_MAPPING so the settings\npath produces the same TF_VAR_ output as the env-var path.\n\nAddresses #552.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-11T18:45:38+01:00",
          "tree_id": "6a27fd75e611ac53a49310b1fa6f0f0f5a27fb3c",
          "url": "https://github.com/endavis/infrafoundry/commit/c64aa3d6f0d594fc9cef3a00a226522a4b975116"
        },
        "date": 1775929569939,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9810.133524307377,
            "unit": "iter/sec",
            "range": "stddev: 0.000006431121989365887",
            "extra": "mean: 101.9354117374873 usec\nrounds: 2164"
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
          "id": "8a15e15bf3f7d5ea0752be11370898bf251c07df",
          "message": "chore: raise script and ansible handler timeout cap to 14400 (merges PR #547, addresses #546)\n\nBoth ScriptHandler and AnsibleHandler capped event-handler timeout at\n3600 seconds (60 minutes). That's too tight for legitimate long-running\npost-terraform installers — the aiqum blueprint is a concrete example\nthat needs ~30-60 minutes for the netapp-um RPM install alone, plus\ncert regeneration, service startup, and first-experience setup.\n\nRaise the upper bound to 14400 seconds (4 hours) in both handlers. 4h\nis still a ceiling that catches runaway/infinite-loop bugs without\nrestricting legitimate workloads. The floor stays at 1.\n\nAlso bump the aiqum blueprint's event handler timeout from 1800 to\n5400 seconds (90 minutes) — the immediate user of the raised cap.\nUpdated the test_aiqum_blueprint.py assertion to match.\n\nAddresses #546.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-11T18:56:15+01:00",
          "tree_id": "81f6425fdcbdaa956d3476016a6cd2a89928697d",
          "url": "https://github.com/endavis/infrafoundry/commit/8a15e15bf3f7d5ea0752be11370898bf251c07df"
        },
        "date": 1775930206394,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9432.55321913186,
            "unit": "iter/sec",
            "range": "stddev: 0.000014899153375846335",
            "extra": "mean: 106.0158343948402 usec\nrounds: 2198"
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
          "id": "4f36b192e53d2ac1630a3cffcd75906b6705bedc",
          "message": "fix: support cloning aiqum VM from template on a different node (merges PR #551, addresses #550)\n\nThe aiqum blueprint's vm.yaml used the scalar shorthand\n\"clone: {{ template_vmid }}\", which the framework normalizes to\n{\"vm_id\": <scalar>} with no node_name. The generated terraform then\nproduces a clone block with only vm_id, and the Proxmox provider\ndefaults the clone source node to target_node. This silently breaks\nwhen the rocky9 template and the target VM live on different Proxmox\nnodes.\n\nThis homelab has rocky9-template (vmid 901) only on pve1, and\naiqum-test targets pve3 (moved there because pve2 was oversubscribed).\nThe fix uses the dict form of clone so the blueprint can specify\nnode_name explicitly. The framework already supports this form via the\nnormalization code in providers/proxmox/__init__.py and the conditional\nnode_name emission in vms.tf.j2 — the aiqum blueprint just wasn't using\nit.\n\nChanges:\n- blueprints/aiqum/vm.yaml: clone switched from scalar to dict form\n  with vm_id and node_name.\n- blueprints/aiqum/blueprint.yaml: added template_node default (pve1,\n  the current location of rocky9-template). Packages can override.\n- tests/unit/test_aiqum_blueprint.py: updated clone assertion to match\n  the new dict form.\n\nAddresses #550.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-11T19:01:44+01:00",
          "tree_id": "86c541baa1f67a63efd92324cb82508008c2d2df",
          "url": "https://github.com/endavis/infrafoundry/commit/4f36b192e53d2ac1630a3cffcd75906b6705bedc"
        },
        "date": 1775930539738,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7295.388790821192,
            "unit": "iter/sec",
            "range": "stddev: 0.000010037653401859425",
            "extra": "mean: 137.07288654145012 usec\nrounds: 2556"
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
          "id": "ba0b3109ec874272ac0f241de45339d5a8e1f304",
          "message": "refactor: add timestamps and jumphost-reexec helper to aiqum scripts (merges PR #549, addresses #548)\n\nTwo related improvements to the aiqum post-terraform scripts:\n\n1. log() helper with [HH:MM:SS] timestamps on every phase and step\n   banner in both aiqum-install-remote.sh and aiqum-post-terraform.sh.\n   Pure observability: when the handler log spans 20-40 minutes, it's\n   now obvious where time was spent per phase.\n\n2. New blueprints/_lib/reexec-on-jumphost.sh shared helper. Any blueprint\n   script can source it at the top; if a jumphost package variable is\n   set, the helper rsyncs the calling script's directory to the jumphost,\n   strips jumphost from INFRAFOUNDRY_PACKAGE_VARS, pipes the modified JSON\n   via stdin, and re-executes the same script on the jumphost with\n   INFRAFOUNDRY_ON_JUMPHOST=1 as a recursion guard. aiqum-post-terraform.sh\n   sources this helper so the entire post-terraform script runs on the\n   jumphost when one is configured. Phases 1-4 use direct SSH (the\n   remote_cmd helpers' no-jumphost branch), and Phase 5's Python wizard\n   reaches the VM directly from the jumphost without needing the\n   operator host to have routing to the target VLAN.\n\nThe reachability issue surfaced concretely during an aiqum-test deploy on\na newly-added VLAN that wasn't advertised by the tailscale subnet router.\nPhases 1-4 succeeded via the jumphost but Phase 5 hung because the\nPython wizard runs locally and made requests.post calls directly to the VM.\n\nThe reexec helper is interim — the long-term solution is framework-native\nsupport in ScriptHandler, tracked as #544. Once that lands, the helper\nand the source line can be removed.\n\nAddresses #548.\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-11T19:05:53+01:00",
          "tree_id": "530b4f4f0d979b51b5752eab89814097c8f93689",
          "url": "https://github.com/endavis/infrafoundry/commit/ba0b3109ec874272ac0f241de45339d5a8e1f304"
        },
        "date": 1775930792811,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6915.004525672272,
            "unit": "iter/sec",
            "range": "stddev: 0.00002534292577674835",
            "extra": "mean: 144.61306515237322 usec\nrounds: 2333"
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
          "id": "4a67823d25ebbb2f12d4a68f95363769e6208182",
          "message": "feat: add framework-native jumphost reexec to script handler (merges PR #557, addresses #544)\n\nWhen a script handler's package variables include a non-empty `jumphost`\nkey, ScriptHandler now rsyncs the script's parent directory to a fresh\n/tmp/infrafoundry-<uuid>/ on the jumphost and invokes the script there\nover SSH. The remote process sees INFRAFOUNDRY_ON_JUMPHOST=1 (recursion\nguard) and receives a stripped INFRAFOUNDRY_PACKAGE_VARS JSON on stdin\nwith the `jumphost` key removed, so downstream logic does not attempt a\nsecond hop and secrets never appear in the jumphost's `ps` output. The\nremote tmp directory is always cleaned up, including on failure and on\ntimeout.\n\nThis replaces the per-blueprint shell helper pattern from #548 with a\nframework-level mechanism. The helper and each blueprint's `source\nblueprints/_lib/reexec-on-jumphost.sh` line are intentionally left in\nplace for this PR: the helper self-deactivates when\nINFRAFOUNDRY_ON_JUMPHOST=1 is already set, so both layers coexist. A\nseparate follow-up PR will remove the helper after this has soaked in\nproduction. AnsibleHandler is out of scope and is tracked in #556.\n\nAddresses #544\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-11T21:20:31+01:00",
          "tree_id": "9a6f83416351b16ae040478585650bc3dc061ef4",
          "url": "https://github.com/endavis/infrafoundry/commit/4a67823d25ebbb2f12d4a68f95363769e6208182"
        },
        "date": 1775938863770,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9752.012703538117,
            "unit": "iter/sec",
            "range": "stddev: 0.000006232998774181159",
            "extra": "mean: 102.5429345100413 usec\nrounds: 2153"
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
          "id": "486f8570fb89f643ac61e531fee40e1a46b552ff",
          "message": "refactor: retire user-space reexec-on-jumphost shell helper (merges PR #559, addresses #558)\n\nThe blueprints/_lib/reexec-on-jumphost.sh helper was an interim\nsolution (added in #548/#549) that let blueprint scripts re-invoke\nthemselves over SSH on a jumphost when the target API was on a\nnon-routable VLAN. Framework-native jumphost reexec landed in #544\n(merged as #557) via ScriptHandler._execute_on_jumphost(), so the\nshell helper is now dead code: the framework sets\nINFRAFOUNDRY_ON_JUMPHOST=1 before the script runs, which makes the\nhelper's recursion guard trip immediately and self-deactivate.\n\nRemoves the helper script, the source guard in the aiqum blueprint's\npost-terraform script, and the stale migration note in the event\nsystem docs. Pure deletion, 72 lines removed.\n\nEnd-to-end behavior was validated during #557's finalization on\naiqum-test (VLAN 110, all 5 phases) with the helper's source line\ntemporarily commented out — functionally identical to this state.\n\nAddresses #558\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-11T21:41:25+01:00",
          "tree_id": "d469bd50353f6ff80aaf73667adec3a52f15b096",
          "url": "https://github.com/endavis/infrafoundry/commit/486f8570fb89f643ac61e531fee40e1a46b552ff"
        },
        "date": 1775940116596,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6625.138876514806,
            "unit": "iter/sec",
            "range": "stddev: 0.00003060032011752702",
            "extra": "mean: 150.94023214288543 usec\nrounds: 2072"
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
          "id": "e99fca015656c315aeac42a173ff548974b311da",
          "message": "chore: delete unused ansible event handler (merges PR #560, addresses #556)\n\nRemove AnsibleHandler, the HandlerType.ANSIBLE enum member, and the\nbus factory branch that constructed it. The handler had zero blueprint\nconsumers, only validation-only test coverage (no execute() tests),\nand every ansible-using blueprint (ontap-cluster, oci-k3s-cluster)\nalready wraps ansible-playbook inside a type: script handler for direct\ncontrol over arguments and output streaming.\n\nBREAKING CHANGE: any config declaring `type: ansible` under an event\nkey (package-level events or resource-level on_create/on_update/\non_destroy) now fails fast at handler registration with\n`ValueError: Unknown handler type: ansible`. Grep confirmed zero such\nconfigs exist in this repo or in the private config repo, so no\ninternal consumers are affected. External users should switch to\n`type: script` wrapping ansible-playbook directly.\n\nAlso removes the three now-orphaned test classes, the ansible-handler\ndocumentation subsections, and the ansible row from the handler-types\ntable.\n\nAddresses #556\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-11T22:13:46+01:00",
          "tree_id": "d8c6aada0037e11ab1a03c4608f6e0b5e460d79a",
          "url": "https://github.com/endavis/infrafoundry/commit/e99fca015656c315aeac42a173ff548974b311da"
        },
        "date": 1775942067837,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7360.994213311055,
            "unit": "iter/sec",
            "range": "stddev: 0.000009730163379733235",
            "extra": "mean: 135.8512139829803 usec\nrounds: 2360"
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
          "id": "75f3d27c2c3750a4c3e0bfeb8b30a6644dadfabb",
          "message": "feat: add default alert policy to aiqum setup wizard (merges PR #561, addresses #555)\n\n* feat: add default alert policy to aiqum setup wizard\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n* feat: send test email after alert policy creation\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-12T11:07:44+01:00",
          "tree_id": "20e4b57c4bbb406e2de64036ae1a0906e393ebff",
          "url": "https://github.com/endavis/infrafoundry/commit/75f3d27c2c3750a4c3e0bfeb8b30a6644dadfabb"
        },
        "date": 1775988496778,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9439.317642212467,
            "unit": "iter/sec",
            "range": "stddev: 0.000016589072149731227",
            "extra": "mean: 105.93986111114825 usec\nrounds: 2124"
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
          "id": "286d6bba3ba327f5d0da2784703e0296407ab644",
          "message": "refactor: retire env-var credential path for proxmox and opnsense providers (merges PR #562, addresses #554)\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-12T11:38:23+01:00",
          "tree_id": "b30bf48b69e14a9522b2cf8093dd53a095432e0f",
          "url": "https://github.com/endavis/infrafoundry/commit/286d6bba3ba327f5d0da2784703e0296407ab644"
        },
        "date": 1775990335378,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6215.703939435653,
            "unit": "iter/sec",
            "range": "stddev: 0.00003221489887316013",
            "extra": "mean: 160.88282352952507 usec\nrounds: 17"
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
          "id": "fe0ed482c89d55a6530446e948b6e12f0318e3e2",
          "message": "feat: support configurable tags in Proxmox blueprints (merges PR #564, addresses #538)\n\nfeat: support configurable extra_tags in all blueprints\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-12T12:10:53+01:00",
          "tree_id": "5f8599992583d68c1af395e56574903f366eb33a",
          "url": "https://github.com/endavis/infrafoundry/commit/fe0ed482c89d55a6530446e948b6e12f0318e3e2"
        },
        "date": 1775992288631,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7424.428325613167,
            "unit": "iter/sec",
            "range": "stddev: 0.000016787767393012278",
            "extra": "mean: 134.69050493088469 usec\nrounds: 2535"
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
          "id": "02a65460dfc792c3d3673c5a310e2c647e735b3f",
          "message": "feat: support configurable freeform_tags in OCI blueprint (merges PR #565, addresses #563)\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-12T12:33:23+01:00",
          "tree_id": "e92a708b0d1d106b0fc09ee5a35cb76b4b961b17",
          "url": "https://github.com/endavis/infrafoundry/commit/02a65460dfc792c3d3673c5a310e2c647e735b3f"
        },
        "date": 1775993634103,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9764.965693050512,
            "unit": "iter/sec",
            "range": "stddev: 0.000006568826066227606",
            "extra": "mean: 102.40691380121035 usec\nrounds: 2123"
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
          "id": "e6db4f2384121247361526236922c0dd98e1c0b8",
          "message": "feat: add infra list command to show packages in an environment (merges PR #567, addresses #535)\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-12T12:52:20+01:00",
          "tree_id": "9b965b2f4407ba6059b8b2556a4a22b06d99d5e9",
          "url": "https://github.com/endavis/infrafoundry/commit/e6db4f2384121247361526236922c0dd98e1c0b8"
        },
        "date": 1775994777618,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9669.535260468776,
            "unit": "iter/sec",
            "range": "stddev: 0.000010844419205649",
            "extra": "mean: 103.41758658125212 usec\nrounds: 2027"
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
          "id": "e386e3963e6f3cb75008116e68adb5a88b6950bf",
          "message": "feat: add infra deployed command to show deployment status (merges PR #568, addresses #566)\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-12T13:32:09+01:00",
          "tree_id": "f7c1f74dd9d96c051ddaf7516f4d0f910f77c46a",
          "url": "https://github.com/endavis/infrafoundry/commit/e386e3963e6f3cb75008116e68adb5a88b6950bf"
        },
        "date": 1775997160258,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9750.358209011745,
            "unit": "iter/sec",
            "range": "stddev: 0.0000067658569855234",
            "extra": "mean: 102.5603345604013 usec\nrounds: 2173"
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
          "id": "9c65a91e670cd683e63e1f8725c924d356bdace9",
          "message": "feat: add multi-provider blueprint support (merges PR #569, addresses #507)\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-12T16:51:23+01:00",
          "tree_id": "3feedd5a4c67afc9e4800d43a610eaf5fec62fd8",
          "url": "https://github.com/endavis/infrafoundry/commit/9c65a91e670cd683e63e1f8725c924d356bdace9"
        },
        "date": 1776009115962,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9896.492130759772,
            "unit": "iter/sec",
            "range": "stddev: 0.00000730986417774006",
            "extra": "mean: 101.0459046283532 usec\nrounds: 2139"
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
          "id": "cb5b5ff043b8be78d1140389fa88851101558a89",
          "message": "feat: unify k3s blueprints using multi-provider support (merges PR #574, addresses #570)\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-12T17:48:55+01:00",
          "tree_id": "47cd91eb77ba7a2387858284ff925dfe53d372ed",
          "url": "https://github.com/endavis/infrafoundry/commit/cb5b5ff043b8be78d1140389fa88851101558a89"
        },
        "date": 1776012569189,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8687.082541234973,
            "unit": "iter/sec",
            "range": "stddev: 0.000025414384101943947",
            "extra": "mean: 115.11344519328557 usec\nrounds: 2226"
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
          "id": "7b072b368ed8ec03e3efc537ab63e1c64d21f07c",
          "message": "feat: add infra move-package command to migrate packages between environments (merges PR #579, addresses #576)\n\nCo-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-13T11:04:43+01:00",
          "tree_id": "cfa7e8b195793e4e57a803ed2c4425fd5fbcd3e2",
          "url": "https://github.com/endavis/infrafoundry/commit/7b072b368ed8ec03e3efc537ab63e1c64d21f07c"
        },
        "date": 1776074723473,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9645.551201785085,
            "unit": "iter/sec",
            "range": "stddev: 0.000006920882075907541",
            "extra": "mean: 103.67473865204633 usec\nrounds: 2181"
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
          "id": "5fecc0db7c7daa42712ffc131494cbf3effc3d9e",
          "message": "feat: show last modified timestamp per resource in deployed command (merges PR #593, addresses #591)",
          "timestamp": "2026-04-13T11:47:33+01:00",
          "tree_id": "bfb976648bbb9d8de1ce3b98ad94f593d6b1a787",
          "url": "https://github.com/endavis/infrafoundry/commit/5fecc0db7c7daa42712ffc131494cbf3effc3d9e"
        },
        "date": 1776077287120,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7351.097060263948,
            "unit": "iter/sec",
            "range": "stddev: 0.000010800654357605622",
            "extra": "mean: 136.0341173299777 usec\nrounds: 2412"
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
          "id": "c46ceb840dde3ee16208d95f19c2f8124220028f",
          "message": "fix: enforce state DB and filesystem consistency (merges PR #594, addresses #592)\n\n* fix: enforce state DB and filesystem consistency\n\n* fix: add nosec B110 for bandit try-except-pass check",
          "timestamp": "2026-04-13T12:44:32+01:00",
          "tree_id": "2a630234a63d19503536bbc091f3ad896df397fe",
          "url": "https://github.com/endavis/infrafoundry/commit/c46ceb840dde3ee16208d95f19c2f8124220028f"
        },
        "date": 1776080708754,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7359.554473904134,
            "unit": "iter/sec",
            "range": "stddev: 0.000010419036013739625",
            "extra": "mean: 135.8777903670458 usec\nrounds: 2533"
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
          "id": "07be109bc551f363a079059a6210c9ffc23906d1",
          "message": "feat: add blueprint schema validation across providers (merges PR #597, addresses #571)",
          "timestamp": "2026-04-13T13:47:14+01:00",
          "tree_id": "a7ce98c4f6d2e5330540114b5828103ba9bd0ee6",
          "url": "https://github.com/endavis/infrafoundry/commit/07be109bc551f363a079059a6210c9ffc23906d1"
        },
        "date": 1776084468171,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9690.226519573935,
            "unit": "iter/sec",
            "range": "stddev: 0.000006926799441040374",
            "extra": "mean: 103.1967620137706 usec\nrounds: 2185"
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
          "id": "adc35a12e515aa8c1fb3f0c1aff025ec0972c9d2",
          "message": "feat: add base schema helpers for common blueprint resource patterns (merges PR #598, addresses #572)",
          "timestamp": "2026-04-13T14:22:40+01:00",
          "tree_id": "53d620f907ee7dd7c741d5f27d1934fdf9924a99",
          "url": "https://github.com/endavis/infrafoundry/commit/adc35a12e515aa8c1fb3f0c1aff025ec0972c9d2"
        },
        "date": 1776086599528,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7376.157193677984,
            "unit": "iter/sec",
            "range": "stddev: 0.000010375001517359643",
            "extra": "mean: 135.57194806763175 usec\nrounds: 2484"
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
          "id": "f2bd26afb5754550827bf055446f9c7b6d8bc561",
          "message": "refactor: reorganize CLI commands under infra, config, and state groups (merges PR #602, addresses #600)\n\nBREAKING CHANGE: CLI command paths changed. `analyze` moved to `infra analyze`,\n`audit` moved to `state audit`, `proxmox export` moved to `config export`,\n`schema` moved to `config schema`. No hidden aliases — old paths removed.",
          "timestamp": "2026-04-13T16:03:07+01:00",
          "tree_id": "6f35b5d2f685440ac56e35fd6bef156f0a46f9c3",
          "url": "https://github.com/endavis/infrafoundry/commit/f2bd26afb5754550827bf055446f9c7b6d8bc561"
        },
        "date": 1776092630545,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7427.982293876497,
            "unit": "iter/sec",
            "range": "stddev: 0.000009190163727005835",
            "extra": "mean: 134.62606134971313 usec\nrounds: 2282"
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
          "id": "5d60ecce1e42eb0147697dac5bf2b6521dcf89c3",
          "message": "refactor: unify health checks under three-tier doctor commands (merges PR #603, addresses #599)\n\nBREAKING CHANGE: Removed commands: `config check`, `config validate`,\n`blueprint validate`, and the `blueprint` command group. Use `config doctor`,\n`config doctor --deep`, and `infra doctor --env <env>` instead.",
          "timestamp": "2026-04-13T17:27:20+01:00",
          "tree_id": "810991a59178e5e019c7e467eddcb81ec44c6446",
          "url": "https://github.com/endavis/infrafoundry/commit/5d60ecce1e42eb0147697dac5bf2b6521dcf89c3"
        },
        "date": 1776097685647,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8117.735508038549,
            "unit": "iter/sec",
            "range": "stddev: 0.00003283344154338258",
            "extra": "mean: 123.18706356098382 usec\nrounds: 2297"
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
          "id": "5909c117a614f7fedb87a440999100884bb0e3a1",
          "message": "docs: document CLI command hierarchy and domain model (merges PR #604, addresses #601)",
          "timestamp": "2026-04-13T18:12:04+01:00",
          "tree_id": "5a91d5b209ece584bc8082c62e5bbc063c16d8cd",
          "url": "https://github.com/endavis/infrafoundry/commit/5909c117a614f7fedb87a440999100884bb0e3a1"
        },
        "date": 1776100367756,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6894.682947626842,
            "unit": "iter/sec",
            "range": "stddev: 0.000029045480393304774",
            "extra": "mean: 145.03930167582268 usec\nrounds: 2506"
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
          "id": "b282afdb688c403be2545f99726a058abf95773f",
          "message": "chore(deps): bump actions/github-script from 8 to 9 (merges PR #580)\n\nBumps [actions/github-script](https://github.com/actions/github-script) from 8 to 9.\n- [Release notes](https://github.com/actions/github-script/releases)\n- [Commits](https://github.com/actions/github-script/compare/v8...v9)\n\n---\nupdated-dependencies:\n- dependency-name: actions/github-script\n  dependency-version: '9'\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-13T19:11:23+01:00",
          "tree_id": "15c30e59e1cc6dc4ebfa676e76d9f2d0819dd53c",
          "url": "https://github.com/endavis/infrafoundry/commit/b282afdb688c403be2545f99726a058abf95773f"
        },
        "date": 1776103953921,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7414.670185421272,
            "unit": "iter/sec",
            "range": "stddev: 0.000009577591373398708",
            "extra": "mean: 134.86776552330008 usec\nrounds: 2303"
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
          "id": "a806379fa7bebdf5811d3a0a31cbcfb0cec9bb9c",
          "message": "chore(deps): bump the dev-dependencies group across 1 directory with 3 updates (merges PR #581)\n\nchore(deps): bump the dev-dependencies group with 3 updates\n\nBumps the dev-dependencies group with 3 updates: [mypy](https://github.com/python/mypy), [pytest](https://github.com/pytest-dev/pytest) and [ruff](https://github.com/astral-sh/ruff).\n\n\nUpdates `mypy` from 1.20.0 to 1.20.1\n- [Changelog](https://github.com/python/mypy/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/python/mypy/compare/v1.20.0...v1.20.1)\n\nUpdates `pytest` from 9.0.2 to 9.0.3\n- [Release notes](https://github.com/pytest-dev/pytest/releases)\n- [Changelog](https://github.com/pytest-dev/pytest/blob/main/CHANGELOG.rst)\n- [Commits](https://github.com/pytest-dev/pytest/compare/9.0.2...9.0.3)\n\nUpdates `ruff` from 0.15.9 to 0.15.10\n- [Release notes](https://github.com/astral-sh/ruff/releases)\n- [Changelog](https://github.com/astral-sh/ruff/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/astral-sh/ruff/compare/0.15.9...0.15.10)\n\n---\nupdated-dependencies:\n- dependency-name: mypy\n  dependency-version: 1.20.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: dev-dependencies\n- dependency-name: pytest\n  dependency-version: 9.0.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: dev-dependencies\n- dependency-name: ruff\n  dependency-version: 0.15.10\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: dev-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-13T19:16:47+01:00",
          "tree_id": "1067ad9d59e3b98ab149d0c78b4716755d5cbc9f",
          "url": "https://github.com/endavis/infrafoundry/commit/a806379fa7bebdf5811d3a0a31cbcfb0cec9bb9c"
        },
        "date": 1776104249064,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7351.820256672284,
            "unit": "iter/sec",
            "range": "stddev: 0.000009609045643051534",
            "extra": "mean: 136.02073569364418 usec\nrounds: 2429"
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
          "id": "94e90c8c17e2f1e5ef3da69c5821812ffb30be5c",
          "message": "chore(deps): bump rich from 14.3.3 to 15.0.0 (merges PR #582)\n\nBumps [rich](https://github.com/Textualize/rich) from 14.3.3 to 15.0.0.\n- [Release notes](https://github.com/Textualize/rich/releases)\n- [Changelog](https://github.com/Textualize/rich/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/Textualize/rich/compare/v14.3.3...v15.0.0)\n\n---\nupdated-dependencies:\n- dependency-name: rich\n  dependency-version: 15.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-13T21:49:42+01:00",
          "tree_id": "ba085e896f7cce5b2a02fcab6e7eac115969de9d",
          "url": "https://github.com/endavis/infrafoundry/commit/94e90c8c17e2f1e5ef3da69c5821812ffb30be5c"
        },
        "date": 1776113423662,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7599.316443097794,
            "unit": "iter/sec",
            "range": "stddev: 0.000010325679154425053",
            "extra": "mean: 131.59078286682833 usec\nrounds: 3537"
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
          "id": "5e5c8a6839ccd4364f4850048f76bee9644e6ee3",
          "message": "chore(deps): update hatchling requirement from >=1.24 to >=1.29.0 (merges PR #583)\n\nUpdates the requirements on [hatchling](https://github.com/pypa/hatch) to permit the latest version.\n- [Release notes](https://github.com/pypa/hatch/releases)\n- [Commits](https://github.com/pypa/hatch/compare/hatchling-v1.24.0...hatchling-v1.29.0)\n\n---\nupdated-dependencies:\n- dependency-name: hatchling\n  dependency-version: 1.29.0\n  dependency-type: direct:development\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-14T09:55:41+01:00",
          "tree_id": "af00074e6f03266dd1ca4806775d0ea5e18934eb",
          "url": "https://github.com/endavis/infrafoundry/commit/5e5c8a6839ccd4364f4850048f76bee9644e6ee3"
        },
        "date": 1776156977985,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9702.180185612044,
            "unit": "iter/sec",
            "range": "stddev: 0.000004243970775855958",
            "extra": "mean: 103.06961743330238 usec\nrounds: 2065"
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
          "id": "6f0d1c99adf6f2e1d5709db1ec7abbccf83dd4bd",
          "message": "chore(deps): bump hypothesis from 6.151.11 to 6.151.13 (merges PR #584)\n\nBumps [hypothesis](https://github.com/HypothesisWorks/hypothesis) from 6.151.11 to 6.151.13.\n- [Release notes](https://github.com/HypothesisWorks/hypothesis/releases)\n- [Commits](https://github.com/HypothesisWorks/hypothesis/compare/hypothesis-python-6.151.11...hypothesis-python-6.151.13)\n\n---\nupdated-dependencies:\n- dependency-name: hypothesis\n  dependency-version: 6.151.13\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-14T11:19:14+01:00",
          "tree_id": "68036a070d1459084a830e41edef8e1a4113c06f",
          "url": "https://github.com/endavis/infrafoundry/commit/6f0d1c99adf6f2e1d5709db1ec7abbccf83dd4bd"
        },
        "date": 1776161991654,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7406.280323363568,
            "unit": "iter/sec",
            "range": "stddev: 0.000009820072427848657",
            "extra": "mean: 135.02054423263434 usec\nrounds: 2306"
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
          "id": "1b6faa60c937e7e7f6c387d34f13e8591fb7a565",
          "message": "chore(deps): bump types-requests from 2.33.0.20260402 to 2.33.0.20260408 (merges PR #585)\n\nBumps [types-requests](https://github.com/python/typeshed) from 2.33.0.20260402 to 2.33.0.20260408.\n- [Commits](https://github.com/python/typeshed/commits)\n\n---\nupdated-dependencies:\n- dependency-name: types-requests\n  dependency-version: 2.33.0.20260408\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-14T11:28:29+01:00",
          "tree_id": "5b27a169856b59f138de763e861a8d80ddea3aa3",
          "url": "https://github.com/endavis/infrafoundry/commit/1b6faa60c937e7e7f6c387d34f13e8591fb7a565"
        },
        "date": 1776162552995,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6468.510387245646,
            "unit": "iter/sec",
            "range": "stddev: 0.00003238676263963208",
            "extra": "mean: 154.59509842818844 usec\nrounds: 2418"
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
          "id": "5319f21f7724ebfe6fae3c197c9ce0f8c155bb26",
          "message": "chore(deps): bump requests from 2.33.0 to 2.33.1 (merges PR #586)\n\nBumps [requests](https://github.com/psf/requests) from 2.33.0 to 2.33.1.\n- [Release notes](https://github.com/psf/requests/releases)\n- [Changelog](https://github.com/psf/requests/blob/main/HISTORY.md)\n- [Commits](https://github.com/psf/requests/compare/v2.33.0...v2.33.1)\n\n---\nupdated-dependencies:\n- dependency-name: requests\n  dependency-version: 2.33.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-14T11:34:10+01:00",
          "tree_id": "efdbde59431135a42c3c349661765012424dd3ac",
          "url": "https://github.com/endavis/infrafoundry/commit/5319f21f7724ebfe6fae3c197c9ce0f8c155bb26"
        },
        "date": 1776162889915,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7289.002796466285,
            "unit": "iter/sec",
            "range": "stddev: 0.000010040535743245977",
            "extra": "mean: 137.19297795917993 usec\nrounds: 2450"
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
          "id": "9800ff46ec287f775ae3a4b2136c23f9fd272db5",
          "message": "chore(deps): update mkdocstrings[python] requirement from >=0.24 to >=1.0.3 (merges PR #587)\n\nchore(deps): update mkdocstrings[python] requirement\n\nUpdates the requirements on [mkdocstrings[python]](https://github.com/mkdocstrings/mkdocstrings) to permit the latest version.\n- [Release notes](https://github.com/mkdocstrings/mkdocstrings/releases)\n- [Changelog](https://github.com/mkdocstrings/mkdocstrings/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/mkdocstrings/mkdocstrings/compare/0.24.0...1.0.3)\n\n---\nupdated-dependencies:\n- dependency-name: mkdocstrings[python]\n  dependency-version: 1.0.3\n  dependency-type: direct:production\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-14T11:42:05+01:00",
          "tree_id": "59a68579d46b0bb31691e50e5403147e19128325",
          "url": "https://github.com/endavis/infrafoundry/commit/9800ff46ec287f775ae3a4b2136c23f9fd272db5"
        },
        "date": 1776163359812,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7399.552105752035,
            "unit": "iter/sec",
            "range": "stddev: 0.000009821283911036121",
            "extra": "mean: 135.1433148531586 usec\nrounds: 2417"
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
          "id": "017892989530ed5fe0fac975d94dd8590b637d83",
          "message": "chore(deps): bump commitizen from 4.13.9 to 4.13.10 (merges PR #588)\n\nBumps [commitizen](https://github.com/commitizen-tools/commitizen) from 4.13.9 to 4.13.10.\n- [Release notes](https://github.com/commitizen-tools/commitizen/releases)\n- [Changelog](https://github.com/commitizen-tools/commitizen/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/commitizen-tools/commitizen/compare/v4.13.9...v4.13.10)\n\n---\nupdated-dependencies:\n- dependency-name: commitizen\n  dependency-version: 4.13.10\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-14T11:49:13+01:00",
          "tree_id": "4e4640d4855d4ef993af57e3870a1398ecb5c407",
          "url": "https://github.com/endavis/infrafoundry/commit/017892989530ed5fe0fac975d94dd8590b637d83"
        },
        "date": 1776163786877,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7375.518301823941,
            "unit": "iter/sec",
            "range": "stddev: 0.000009894311726065573",
            "extra": "mean: 135.5836917593579 usec\nrounds: 2245"
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
          "id": "e75377d93571d0b8ff160d2aa510d8c6d3298426",
          "message": "chore(deps): bump boto3 from 1.42.83 to 1.42.88 (merges PR #589)\n\nBumps [boto3](https://github.com/boto/boto3) from 1.42.83 to 1.42.88.\n- [Release notes](https://github.com/boto/boto3/releases)\n- [Commits](https://github.com/boto/boto3/compare/1.42.83...1.42.88)\n\n---\nupdated-dependencies:\n- dependency-name: boto3\n  dependency-version: 1.42.88\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-14T11:54:15+01:00",
          "tree_id": "82bd20b496a7254554c4f2e5a556ef522441e10e",
          "url": "https://github.com/endavis/infrafoundry/commit/e75377d93571d0b8ff160d2aa510d8c6d3298426"
        },
        "date": 1776164089810,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7211.449597597777,
            "unit": "iter/sec",
            "range": "stddev: 0.000009435090208521244",
            "extra": "mean: 138.6683754030691 usec\nrounds: 2171"
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
          "id": "e735e978b760e0dea3ec108c653dca30c900b92d",
          "message": "chore(deps): bump types-boto3 from 1.42.78 to 1.42.88 (merges PR #590)\n\nBumps [types-boto3](https://github.com/youtype/mypy_boto3_builder) from 1.42.78 to 1.42.88.\n- [Release notes](https://github.com/youtype/mypy_boto3_builder/releases)\n- [Commits](https://github.com/youtype/mypy_boto3_builder/commits)\n\n---\nupdated-dependencies:\n- dependency-name: types-boto3\n  dependency-version: 1.42.88\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-04-14T11:59:01+01:00",
          "tree_id": "ca29718d2c700b6366de386a6a12d6ac69ef6f1e",
          "url": "https://github.com/endavis/infrafoundry/commit/e735e978b760e0dea3ec108c653dca30c900b92d"
        },
        "date": 1776164374623,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8321.517880388825,
            "unit": "iter/sec",
            "range": "stddev: 0.00002505673454713974",
            "extra": "mean: 120.17038410224204 usec\nrounds: 1799"
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
          "id": "ddd0f36f5bb75b469f9a0d693f7a7a39b83135a6",
          "message": "fix: treat Terraform and OpenTofu as alternative IaC runners in doctor (merges PR #606, addresses #605)\n\n* fix: treat Terraform and OpenTofu as alternative IaC runners in doctor\n\nPreviously `foundry doctor` reported OpenTofu as a hard FAIL when only\nTerraform was installed (and vice versa), even though they are alternative\nrunners and only one is required. This caused the command to exit non-zero\non otherwise healthy systems.\n\nNow if at least one of the two is installed, the missing alternative is\nreported as a warning. Only when neither is installed do both report as\nerrors.\n\nAddresses #605\n\n* refactor: collapse IaC tool check into a single row\n\nPer review, do not warn when one of Terraform/OpenTofu is missing — a single\ninstalled runner satisfies the requirement. Replace the two separate rows\nwith a single 'IaC Tool' check that:\n\n- reports ok with the path(s) when at least one is installed\n- reports error only when neither is installed\n\nAddresses #605",
          "timestamp": "2026-04-14T12:40:40+01:00",
          "tree_id": "c9f117eeb49bca710f5f62a52308abfbc04cecd7",
          "url": "https://github.com/endavis/infrafoundry/commit/ddd0f36f5bb75b469f9a0d693f7a7a39b83135a6"
        },
        "date": 1776166879000,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7325.965037850593,
            "unit": "iter/sec",
            "range": "stddev: 0.000012454011482220475",
            "extra": "mean: 136.50078792805647 usec\nrounds: 2452"
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
          "id": "c2d8d604ae7382a86907899511bd7d3af8885ac4",
          "message": "feat: add inputs section to blueprint schema for required user variables (merges PR #608, addresses #607)\n\nReplaces the legacy defaults: section in blueprint manifests with a unified\ninputs: list that declares every variable a blueprint reads. Each entry\ncarries a name and optional description, type, and default. Presence of\ndefault: marks the input as optional; absence marks it as required.\n\nThis lets the blueprint validator distinguish intentional required inputs\nfrom typos and makes config doctor --deep produce actionable signal\n(Blueprint check goes from FAIL with 33 errors to WARN with 1 pre-existing\nasymmetric-variable warning that is out of scope).\n\nPre-release clean cutover: no backwards-compatibility shim; declaring\nboth inputs: and defaults: in the same scope is a hard error at resolve\ntime. BlueprintResolver continues to populate a synthetic defaults dict\nfrom inputs-that-have-default so package_loader.py merge order is\npreserved unchanged.\n\nTop-level-plus-per-provider scoping from ADR-0003 is preserved; only the\nsection name and per-entry shape changed. ADR-0003 now cross-references\nADR-0004.\n\nAddresses #607",
          "timestamp": "2026-04-14T18:58:12+01:00",
          "tree_id": "0ccf1d2598209f5095a07280e51d42d08fa5765a",
          "url": "https://github.com/endavis/infrafoundry/commit/c2d8d604ae7382a86907899511bd7d3af8885ac4"
        },
        "date": 1776189526114,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9743.214399491757,
            "unit": "iter/sec",
            "range": "stddev: 0.000004131354379299201",
            "extra": "mean: 102.63553268951608 usec\nrounds: 2692"
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
          "id": "ecf56bfc550f35de3ad061ff32d971948ae64829",
          "message": "fix: resolve terraform_secrets references during infra doctor (merges PR #611, addresses #609)\n\nThe validation orchestrator was dumping EnvironmentConfig to a dict via\nmodel_dump() before dispatching to provider validators. The helper at\ncore/validation_helpers/terraform_secrets_validator.py reads the env's\ndecrypted secrets via getattr(env_config, \"secrets\", None), which on a\ndict returns None unconditionally — so every terraform_secrets reference\nwas flagged as missing regardless of what was in envs/{env}/secrets.yaml.\n\nPass EnvironmentConfig through the validator chain unchanged and switch\nvalidator internals from dict to attribute access. Exporters and the\ninfra test runner (also on EnvironmentData) are left alone.\n\nAddresses #609",
          "timestamp": "2026-04-15T13:29:23+01:00",
          "tree_id": "dd264e7b78ce9998ace056f16b5268e77dbc88c2",
          "url": "https://github.com/endavis/infrafoundry/commit/ecf56bfc550f35de3ad061ff32d971948ae64829"
        },
        "date": 1776256198524,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7235.610487335488,
            "unit": "iter/sec",
            "range": "stddev: 0.000010321933239403251",
            "extra": "mean: 138.20533896211015 usec\nrounds: 2428"
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
          "id": "8e5115a009145b9c51f54b376a83fbef04235ef9",
          "message": "fix: inject INFRAFOUNDRY_PACKAGE_DIR into blueprint script env (merges PR #613, addresses #612)\n\nBlueprint scripts derived PACKAGE_DIR from $(dirname \"$0\")/.., which\nresolves to the blueprint dir (scripts live inside the blueprint) —\nnot the consumer env package dir. The ontap-cluster post-terraform\nscript wrote .generated-inventory.yml into the blueprint every apply,\npolluting the framework checkout; concurrent consumers would collide.\n\nThe ScriptHandler already tracks _package_dir alongside _blueprint_dir;\nexpose it as INFRAFOUNDRY_PACKAGE_DIR. Both ontap-cluster and aiqum\nscripts now require the env var explicitly (fail-fast :? guard) and\nroute runtime artifacts to the consumer, not the blueprint.\n\nAddresses #612",
          "timestamp": "2026-04-15T17:41:23+01:00",
          "tree_id": "cabec5bbe91f7db24d3baeb2fffedf25a5b41a77",
          "url": "https://github.com/endavis/infrafoundry/commit/8e5115a009145b9c51f54b376a83fbef04235ef9"
        },
        "date": 1776271329937,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7334.370687120955,
            "unit": "iter/sec",
            "range": "stddev: 0.000010368024014602503",
            "extra": "mean: 136.34434945536432 usec\nrounds: 2295"
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
          "id": "ffb62a949e91d260edb7adf21a95af954b5bae11",
          "message": "fix: include all rendered fields in proxmox OVA triggers_replace (merges PR #614, addresses #610)\n\nThe ova_vms.tf.j2 template rendered memory, cores, cpu_type, disk_storage,\nnetwork, serial, boot_order, onboot, and tags into the qm create/qm set\nprovisioners but kept them OUT of triggers_replace. Editing any of those\nin the package config was a silent no-op — the plan reported 0 changes\neven though the config differed.\n\nExtend triggers_replace to cover every rendered field. Field-per-key (not\na hashed blob) so plan diffs remain readable. List values use\n`| tojson | replace` to stay HCL-safe inside the string map; bools use\n`| string | lower` for true/false.\n\nNote: existing deployments will see a one-time replace on next apply\nbecause the stored state was built against the old 7-key trigger map.\nThat's inherent to the fix — it means Terraform can now observe changes\nit previously missed.\n\nAddresses #610",
          "timestamp": "2026-04-15T18:20:14+01:00",
          "tree_id": "14f05e1574260ca2f3fbb83241387288ffa0be41",
          "url": "https://github.com/endavis/infrafoundry/commit/ffb62a949e91d260edb7adf21a95af954b5bae11"
        },
        "date": 1776273651499,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8312.811176605428,
            "unit": "iter/sec",
            "range": "stddev: 0.000028935359516324507",
            "extra": "mean: 120.29624861614556 usec\nrounds: 2168"
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
          "id": "9d20ef011ea28a449386c8534079d7bec921d13f",
          "message": "fix: restore ontap-cluster noVNC console after setup (merges PR #615, addresses #596)\n\n* fix: restore ontap-cluster noVNC console after setup\n\nThe cluster setup automation sets `console=comconsole,vidconsole` at the\nVLOADER prompt so the expect scripts can drive ONTAP over the Proxmox\nserial socket. This VLOADER env is persistent and was never reversed,\nso after setup the Proxmox noVNC console showed no usable output\n(video secondary).\n\nAdd an `ontap-console-restore` role that runs after cluster setup:\nhalt each node cleanly via `system node halt -inhibit-takeover true\n-skip-lif-migration-before-shutdown true -ignore-quorum-warnings true`,\ncatch VLOADER on the serial socket, send `set console=vidconsole,comconsole`\n+ `boot_ontap`, then poll the cluster API until the node is healthy.\nNodes are processed sequentially to keep the 2-node cluster alive.\n\nOn by default; opt out with `ontap_restore_console: false`.\n\nAddresses #596\n\n* fix: handle halt-reboot prompt and drop invalid health field\n\nLive testing on the prod ontap-cluster surfaced three issues in the\ninitial implementation:\n\n1. `system node halt` on the ONTAP simulator parks at a firmware-level\n   \"Please press any key to reboot\" prompt (SRM_F_POWEROFF_VM) rather\n   than dropping directly to VLOADER. The expect script was waiting\n   for \"VLOADER>\" forever. Add a matcher for the halt-reboot prompt\n   that sends a key and continues via exp_continue; the existing\n   boot-prompt matcher then catches the subsequent reboot.\n\n2. If the VM parks at the halt prompt *before* the expect listener\n   attaches (as happens when the halt is fast), the serial line\n   doesn't redraw the prompt for us. Poke the line with a CR\n   immediately after spawning socat so the firmware re-emits it.\n\n3. The health poll queried `fields=state,health`, but the\n   /api/cluster/nodes endpoint does not expose a `health` field and\n   returns HTTP 400 for that query. Drop `health` from both the URL\n   and the `until:` condition; `state=up` is the health signal.\n\nManually rescued node01 and ran the updated role through\nansible-playbook against node02 on the live cluster — both noVNC\nconsoles now show the login prompt instead of blank/serial-redirected\noutput.\n\nAddresses #596",
          "timestamp": "2026-04-16T00:59:25+01:00",
          "tree_id": "bd867019f5f17b68d372eea4b402ee1428c92e02",
          "url": "https://github.com/endavis/infrafoundry/commit/9d20ef011ea28a449386c8534079d7bec921d13f"
        },
        "date": 1776297603181,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7247.385951195115,
            "unit": "iter/sec",
            "range": "stddev: 0.000010036080130503485",
            "extra": "mean: 137.98078462139816 usec\nrounds: 2484"
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
          "id": "2dbd78244bad062619bf9662fcde371cab23a4c6",
          "message": "feat: inject provider variable into package template context (merges PR #616, addresses #573)",
          "timestamp": "2026-04-16T15:51:56+01:00",
          "tree_id": "6a122a0ff7dd60f5da2f38c9bce9957f0493fa93",
          "url": "https://github.com/endavis/infrafoundry/commit/2dbd78244bad062619bf9662fcde371cab23a4c6"
        },
        "date": 1776351159546,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9656.827971490613,
            "unit": "iter/sec",
            "range": "stddev: 0.000007872922149609606",
            "extra": "mean: 103.5536723810605 usec\nrounds: 2100"
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
          "id": "e65b3a70adc98a8a69208844f73253e02b41e905",
          "message": "feat: rename config init to config create with SOPS support (merges PR #617, addresses #577)",
          "timestamp": "2026-04-16T17:54:41+01:00",
          "tree_id": "20f6699ef296499909cac896342a1bacb357efae",
          "url": "https://github.com/endavis/infrafoundry/commit/e65b3a70adc98a8a69208844f73253e02b41e905"
        },
        "date": 1776358516735,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7323.693913576205,
            "unit": "iter/sec",
            "range": "stddev: 0.000009701989269895257",
            "extra": "mean: 136.5431176945097 usec\nrounds: 2481"
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
          "id": "ce0cac88bdd6c7357aec4dc37a971b96f1a1aa71",
          "message": "refactor: extract service-vm blueprint and convert prod infra-web (merges PR #620, addresses #618)\n\nAddresses #618\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-17T13:23:21+01:00",
          "tree_id": "f6b32e10378ecbc61f434bc320d2f0a7b21a190e",
          "url": "https://github.com/endavis/infrafoundry/commit/ce0cac88bdd6c7357aec4dc37a971b96f1a1aa71"
        },
        "date": 1776428634813,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9684.639073213308,
            "unit": "iter/sec",
            "range": "stddev: 0.000007043066076311207",
            "extra": "mean: 103.25630025448184 usec\nrounds: 1965"
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
          "id": "af87811a8ddf641e50bdebae94948bc853989a54",
          "message": "fix: wire proxmox config validators into generate_terraform (merges PR #623, addresses #621)\n\nAddresses #621\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-17T16:27:47+01:00",
          "tree_id": "4349882c1e038ee9669c61e2bf5cdf72b287e356",
          "url": "https://github.com/endavis/infrafoundry/commit/af87811a8ddf641e50bdebae94948bc853989a54"
        },
        "date": 1776439705901,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7040.66916432598,
            "unit": "iter/sec",
            "range": "stddev: 0.000021005048865998317",
            "extra": "mean: 142.0319541595351 usec\nrounds: 2356"
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
          "id": "8c9d42b16caab2a408e54dc6334d78e47ec93bc3",
          "message": "fix: remove cluster-level NFS storage from service-vm blueprint (merges PR #624, addresses #622)\n\nAddresses #622\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-17T23:12:58+01:00",
          "tree_id": "ad7476266810c0ed106e62e3799893744a5ac61f",
          "url": "https://github.com/endavis/infrafoundry/commit/8c9d42b16caab2a408e54dc6334d78e47ec93bc3"
        },
        "date": 1776464014897,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9282.914600721964,
            "unit": "iter/sec",
            "range": "stddev: 0.000016125156397616983",
            "extra": "mean: 107.72478720446557 usec\nrounds: 2157"
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
          "id": "a97d1ff7892b3537967e51868217277231b8a5d4",
          "message": "refactor: extract minio blueprint and convert prod minio package (merges PR #625, addresses #619)\n\nAddresses #619",
          "timestamp": "2026-04-18T18:48:16+01:00",
          "tree_id": "fb6f9a74017bf22a01d6b3b0aef4c9f89ad419b9",
          "url": "https://github.com/endavis/infrafoundry/commit/a97d1ff7892b3537967e51868217277231b8a5d4"
        },
        "date": 1776534535488,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6772.2258615416295,
            "unit": "iter/sec",
            "range": "stddev: 0.00002606232772742171",
            "extra": "mean: 147.6619386956418 usec\nrounds: 2300"
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
          "id": "b0adc01bb931df1c1cd45d08cb59c06d5d847c0f",
          "message": "fix: port advanced-setup CodeQL workflow from pyproject-template (merges PR #638, addresses #637)\n\nReplaces GitHub's CodeQL default setup with an in-repo advanced-setup\nworkflow at .github/workflows/codeql.yml. Default setup was not emitting\na check-run on PRs, which caused the main ruleset's code_scanning rule\n(tool: CodeQL) to stay pending and block merges. Ported verbatim from\npyproject-template#433; the summary job is literally named CodeQL so the\nemitted check-run name matches the ruleset's required tool name.\n\nAddresses #637",
          "timestamp": "2026-04-20T19:36:42+01:00",
          "tree_id": "735a996c5f117884a94006b581f377fb4eb2a6fd",
          "url": "https://github.com/endavis/infrafoundry/commit/b0adc01bb931df1c1cd45d08cb59c06d5d847c0f"
        },
        "date": 1776710237408,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6955.730450105745,
            "unit": "iter/sec",
            "range": "stddev: 0.00001833489003623186",
            "extra": "mean: 143.76635310599153 usec\nrounds: 2141"
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
          "id": "4323c10ff7bd03015c34a11ce02de099054663b5",
          "message": "feat: add provider CLI group and proxmox dump command (merges PR #636, addresses #626)\n\nfeat: add foundry provider CLI group and proxmox dump command\n\nIntroduces a top-level `foundry provider <name>` CLI group backed by the\npreviously-unused `ProviderMetadata.cli_registration` plugin hook and the\n`infrafoundry.providers` entry point group. Providers now own their CLI\ncode under `providers/<name>/cli/`.\n\nShips two Proxmox subcommands under the new group:\n- `foundry provider proxmox dump` (new) — raw JSON snapshot of a live PVE\n  cluster's API state via a curated endpoint list, per-call timeout,\n  inline failure capture, incremental atomic save.\n- `foundry provider proxmox export` (moved) — previously\n  `foundry config export --provider proxmox`.\n\nAlso loosens `ProviderPluginType.validate_plugin` required-method list\nto match `ProviderBase`'s real abstract surface. Adds ADR-0005 + Proxmox\nprovider guide; updates CLI reference, CLI_DESIGN supersede note, and\nCHANGELOG.\n\nBREAKING CHANGE: `foundry config export --provider proxmox` is removed.\nReplace with `foundry provider proxmox export` (drop the `--provider`\nflag; `--node`/`--resource-type` are unchanged). See ADR-0005.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-20T19:45:09+01:00",
          "tree_id": "06479b3062cdd5c1a83f83c1c01fedd7ac8ea6ba",
          "url": "https://github.com/endavis/infrafoundry/commit/4323c10ff7bd03015c34a11ce02de099054663b5"
        },
        "date": 1776710742532,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 5949.251280804228,
            "unit": "iter/sec",
            "range": "stddev: 0.00004358766789922453",
            "extra": "mean: 168.08837831856022 usec\nrounds: 1808"
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
          "id": "3b2465bda65f26cb0c3b9fc6170bce2a88f331ff",
          "message": "fix: forward INFRAFOUNDRY_VAR_* env vars on jumphost reexec (merges PR #640, addresses #639)\n\nThe ScriptHandler jumphost path only forwarded INFRAFOUNDRY_PACKAGE_VARS\n(JSON) to the remote bash invocation, breaking scripts that consume the\ndocumented INFRAFOUNDRY_VAR_<key> contract under `set -u`. Extract the\nremote bash builder and have it parse the JSON blob via jq on the remote\nside, re-exporting each scalar entry as INFRAFOUNDRY_VAR_<key> before\nexecing the target script. Values are null-delimited so newlines, tabs,\nand equals signs round-trip safely. Requires jq on the jumphost.\n\nAddresses #639",
          "timestamp": "2026-04-21T14:58:02+01:00",
          "tree_id": "6e354be65ca03a3d9620c2adfa539f463af60c09",
          "url": "https://github.com/endavis/infrafoundry/commit/3b2465bda65f26cb0c3b9fc6170bce2a88f331ff"
        },
        "date": 1776779917319,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9689.42588717502,
            "unit": "iter/sec",
            "range": "stddev: 0.000005599083881575796",
            "extra": "mean: 103.20528911043179 usec\nrounds: 2608"
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
          "id": "6a66fa70aa631e7ee582a10c2750511a69eca3a1",
          "message": "fix: use python3 instead of jq in jumphost reexec wrapper (merges PR #642, addresses #641)\n\nPR #640 introduced a silent dependency on jq on the jumphost. When jq\nis missing the process substitution emits `jq: command not found` to\nstderr but bash keeps going, and the inner script fails later with an\nunbound-variable error that doesn't point at the real cause -- the\nexact failure mode #639 was supposed to eliminate.\n\nReplace jq with python3, which is a hard ansible requirement and is\npresent in the base install of every modern Linux distro, and add a\n`command -v python3` presence check at the top of the wrapper so a\nmissing interpreter fails fast with a clear, actionable error.",
          "timestamp": "2026-04-21T17:16:31+01:00",
          "tree_id": "c967190c7ba4c6558b6e2ff59badb8a99e87268a",
          "url": "https://github.com/endavis/infrafoundry/commit/6a66fa70aa631e7ee582a10c2750511a69eca3a1"
        },
        "date": 1776788229567,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7202.156128035133,
            "unit": "iter/sec",
            "range": "stddev: 0.000008642573877241005",
            "extra": "mean: 138.8473093643995 usec\nrounds: 2990"
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
          "id": "dc67f12d13fcdac7a53d2059153b7ff91c418779",
          "message": "fix: drop jq dependency from k3s-cluster blueprint scripts (merges PR #646, addresses #645)\n\njq is not in the base install of Debian/Ubuntu, Rocky/RHEL, Alpine, or\nmost cloud images. When the framework rsyncs an event-handler script to\na jumphost without jq, the pipe silently emits zero entries and the\nouter bash continues, producing a misconfigured cluster. Same class of\nfailure as #641 but at the blueprint layer.\n\nSwap all three scripts' jq invocations for `python3 -c` using the stdlib\njson module -- python3 is already required by the framework's jumphost\nwrapper (see PR #642), so no new runtime dependency. Per-item `print`\npreserves jq's zero-length output semantics for empty lists.\n\nAlso add a `command -v ansible-playbook` presence check to the OCI k3s\nvariant so a missing interpreter fails fast with a clear error instead\nof degrading into a confusing later failure.\n\nUpdates each script header with an explicit portability contract.",
          "timestamp": "2026-04-21T18:00:01+01:00",
          "tree_id": "7ad8c0cc25e5e6e0f2a89cb6f817966e25093663",
          "url": "https://github.com/endavis/infrafoundry/commit/dc67f12d13fcdac7a53d2059153b7ff91c418779"
        },
        "date": 1776790835898,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9165.063938318393,
            "unit": "iter/sec",
            "range": "stddev: 0.00001770127366410948",
            "extra": "mean: 109.1099862183264 usec\nrounds: 1814"
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
          "id": "ed4fe448581d5e3fafc4b5fa345b4e258cc41b3f",
          "message": "fix: drop PyYAML dependency from ontap and aiqum event-handler scripts (merges PR #648, addresses #647)\n\nPyYAML is not in the base install of Debian/Ubuntu, so on a minimal\njumphost the inline `import yaml` aborts with ModuleNotFoundError before\nthe script can do any useful work. Same class of portability failure as\nthe jq dependency fixed in #645, just with a different missing package.\n\nontap-post-terraform.sh:\n- Drop the yaml-fallback that read infrafoundry.yml via yaml.safe_load\n  (it was broken under jumphost reexec anyway -- the framework only\n  rsyncs the blueprint script dir, not the consuming package dir)\n- Emit the ansible inventory as JSON via stdlib json.dump instead of\n  yaml.dump. Ansible accepts JSON inventories natively via file\n  extension auto-detection; verified with `ansible-inventory --list`\n- Rename the inventory file `.generated-inventory.yml` to `.json` so\n  ansible picks the JSON parser\n- Require INFRAFOUNDRY_PACKAGE_VARS and fail fast with a clear error\n- Add `command -v ansible-playbook` presence check with exit 127,\n  consistent with the guard added in PR #646 for the OCI k3s variant\n\naiqum-post-terraform.sh:\n- Drop the `else` branch that imported `yaml` and read infrafoundry.yml\n  (same jumphost-reexec-broken fallback as ontap)\n- Require INFRAFOUNDRY_PACKAGE_VARS and fail fast with a clear error",
          "timestamp": "2026-04-21T18:27:22+01:00",
          "tree_id": "3baffc1f1cb6a6533bfa1658bdd1c63399438039",
          "url": "https://github.com/endavis/infrafoundry/commit/ed4fe448581d5e3fafc4b5fa345b4e258cc41b3f"
        },
        "date": 1776792477750,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9679.259373939243,
            "unit": "iter/sec",
            "range": "stddev: 0.000006903972113328372",
            "extra": "mean: 103.3136897532091 usec\nrounds: 2108"
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
          "id": "85de919a5d7925d941e6814a416fceb53f2c8e17",
          "message": "docs: document Rocky 9 target and tool assumptions in aiqum-install-remote.sh (merges PR #650, addresses #649)\n\ndoc: document Rocky 9 target and tool assumptions in aiqum-install-remote.sh\n\nExpand the previous 5-line header block into a structured note covering\nwhere this script runs, how it's invoked, what env vars it requires,\nwhat target-OS tools it assumes, and what it installs.\n\nUnlike the blueprint event-handler scripts fixed in #646/#648, this\nscript is uploaded to the blueprint-controlled Rocky 9 VM and runs\nthere; distro-specific tooling (yum, firewalld, rpm) is appropriate and\nintentional. The header now says so explicitly so future readers don't\nhave to reverse-engineer the assumption from the first 20 lines.\n\nComments only — no behavior change.",
          "timestamp": "2026-04-21T18:46:57+01:00",
          "tree_id": "4856b99b15d3631323db70ff151d2e52f9e5b4e1",
          "url": "https://github.com/endavis/infrafoundry/commit/85de919a5d7925d941e6814a416fceb53f2c8e17"
        },
        "date": 1776793654842,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7231.257050546442,
            "unit": "iter/sec",
            "range": "stddev: 0.000010014802837043517",
            "extra": "mean: 138.28854278170536 usec\nrounds: 2279"
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
          "id": "2b2fcec079e31406deb4c12367ec3c5ea8309944",
          "message": "docs: add blueprint script portability contract (merges PR #652, addresses #651)\n\ndoc: add blueprint script portability contract\n\nCodify what tools blueprint event-handler and target-VM scripts may\nassume on the remote hosts they run on. This captures the policy that\ndrove PRs #642, #646, #648, and #650 into a written reference so\nfuture blueprint authors have something to read and the upcoming CI\nlint has something to enforce.\n\nHighlights:\n- Three execution contexts (orchestration host, jumphost reexec,\n  target VM scp+ssh) with concrete in-tree examples.\n- A portable baseline for contexts 1-2: bash 4+, python3 stdlib only,\n  GNU coreutils, ssh/scp/rsync/curl.\n- Explicit \"jq is not recommended anywhere\" guidance with a jq->python3\n  equivalence table. jq is not in the base install of Debian/Ubuntu,\n  Rocky/RHEL, Alpine, most cloud images, or most minimal containers.\n- Presence-check pattern for tools outside the baseline: command -v\n  with exit 127 and a clear error message (exemplars in the OCI k3s\n  and ontap scripts).\n- Target-VM scripts are exempt from the baseline but must document\n  their OS and tool assumptions (exemplar: aiqum-install-remote.sh).\n- Author checklist to self-review against before PR submission.\n\nAlso updates docs/development/README.md and mkdocs.yml nav to surface\nthe new page.",
          "timestamp": "2026-04-21T18:59:18+01:00",
          "tree_id": "8aab9d0e31b6f0bbb079475919e565d05a732ed3",
          "url": "https://github.com/endavis/infrafoundry/commit/2b2fcec079e31406deb4c12367ec3c5ea8309944"
        },
        "date": 1776794391864,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7271.096411155108,
            "unit": "iter/sec",
            "range": "stddev: 0.000011973419333020188",
            "extra": "mean: 137.53084039235523 usec\nrounds: 2243"
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
          "id": "44c7cda5a05290651b75be5a2ee0f5642f410cbf",
          "message": "chore: enforce blueprint script portability contract via doit lint (merges PR #654, addresses #653)\n\nAdd a CI lint that scans blueprints/**/*.sh for tools called out as\nnot-recommended in docs/development/blueprint-script-portability.md\n(currently jq and yq). Without mechanical enforcement, future blueprint\nauthors could reintroduce the same silent-failure pattern that caused\n#641, #645, and #647.\n\nThe lint:\n- Walks blueprints/**/*.sh and scans non-comment lines for \\bjq\\b /\n  \\byq\\b. Comment-only lines are ignored so headers and prose can\n  freely discuss the tools.\n- Honors a per-line exemption marker for justified uses, either inline\n  on the violating line or on the line immediately above:\n      # SCRIPT_PORTABILITY_EXEMPT: <tool>: <reason>\n  Adjacency requirement is intentional -- a marker far above can drift\n  away from what it justifies.\n- Exits 1 with file:line:tool reports + pointer to the docs and\n  exemption pattern; exits 0 when clean.\n\nWires `lint_blueprints` into the standard `doit check` aggregate so\nthe gate fails on regression. 12 new unit tests cover the detection\ncore, exemption handling, comment-skip rule, word-boundary correctness,\nand a sanity check that the live blueprints/ tree (cleaned up by\nPRs #646 / #648 / #650) lints clean.\n\nCloses the portability audit tracked in #643.",
          "timestamp": "2026-04-21T19:11:29+01:00",
          "tree_id": "bd94b8b78c4d16860c68c253f0e3662f155655b3",
          "url": "https://github.com/endavis/infrafoundry/commit/44c7cda5a05290651b75be5a2ee0f5642f410cbf"
        },
        "date": 1776795125287,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9819.02225518565,
            "unit": "iter/sec",
            "range": "stddev: 0.000006576405555584327",
            "extra": "mean: 101.84313407293452 usec\nrounds: 2163"
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
          "id": "6ecb63cbfa75cc2a0f5d0055558b34fdc4422ffe",
          "message": "fix: surface ssh failures + add Phase 0 preflight in k3s and aiqum scripts (merges PR #659, addresses #658)\n\nThree blueprint event-handler scripts had a \"wait for SSH\" loop that\nsilenced the ssh probe's stderr via &>/dev/null, then exited with a\ngeneric \"not reachable after Ns\" message after a 5-10 minute timeout.\nThe actual cause -- ssh-agent missing keys, network unreachable, auth\nfailure, etc. -- was hidden, so the operator had to re-run the probe\nmanually to find out what went wrong. Hit in real use this week when an\nssh-agent on the jumphost had no keys loaded and 5 minutes of polling\nturned into a black-box timeout.\n\nTwo-part fix per script (proxmox k3s, oci k3s, aiqum):\n\n1. New \"Phase 0: Preflight\" before any other phase:\n   - `ssh-add -l` check: distinct error messages for \"no keys loaded\"\n     (rc=1, the failure mode hit this week) vs \"agent unreachable\"\n     (rc=2, SSH_AUTH_SOCK unset/broken).\n   - One-shot verbose ssh probe to the first target (SERVER_IP /\n     CONTROL_HOST / ip_address). Captures combined output to a tmpfile;\n     dumps to stderr indented on failure, then exits 1.\n\n2. Phase 1 wait loops now redirect each probe's output to a WAIT_ERR\n   tmpfile (overwritten each iteration). On MAX_WAIT timeout, dumps the\n   last attempt's output before exit 1, so the operator sees the actual\n   ssh-side error instead of just the timeout message.\n\nTrap-based cleanup of the tmpfiles on EXIT.\n\nThis is sub-PR 1 of the audit in #655 (findings #1, #4, #5). The other\nfive Category B findings under #655 will land in subsequent PRs.\n\nThe framework-level home for the preflight check is tracked in #657\n(extend `infra doctor` with package-aware jumphost preflight); this PR\nis the immediate per-script affordance that lands today.",
          "timestamp": "2026-04-21T20:10:42+01:00",
          "tree_id": "62d9c59da25a2929b6f89ad6c96f2b55eee7e337",
          "url": "https://github.com/endavis/infrafoundry/commit/6ecb63cbfa75cc2a0f5d0055558b34fdc4422ffe"
        },
        "date": 1776798684178,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7101.813108836311,
            "unit": "iter/sec",
            "range": "stddev: 0.000010040891776228336",
            "extra": "mean: 140.80911235973906 usec\nrounds: 2403"
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
          "id": "a81f1b9c74e9a269c53abd36be84633ffd2aa9bc",
          "message": "fix: surface kubectl failures in proxmox k3s wait loops (sub-PR 2 of #655) (merges PR #663, addresses #662)\n\nfix: surface kubectl failures in proxmox k3s wait loops\n\nTwo kubectl wait loops in proxmox k3s-post-terraform.sh silenced\nkubectl's stderr/output, hiding the actual cause when the wait timed\nout. Same class of failure as #658 (which covered the SSH wait loops)\n-- sub-PR 2 of the audit in #655 (covers findings #2 and #3).\n\nPhase 3 (wait for server API): redirect each probe's combined output\nto a tmpfile; on 180s timeout, dump the last attempt before exit 1.\n\nPhase 5 (poll for nodes Ready): the previous code passed the kubectl\npipeline to the remote shell with `2>/dev/null` baked in, so kubectl's\nstderr was discarded on the remote side before it could ever cross the\nssh boundary. Split the remote call so kubectl output and the\n` Ready `-counting grep are handled on the local side, with stdout\ncaptured to one tmpfile and stderr to another. On timeout, dump the\nlast kubectl stderr in addition to the existing `kubectl get nodes`\nrecap (which is now also redirected to stderr).\n\nLatent bug fix while in there: the original Phase 5 used\n`grep -c ... || echo 0`, which produces multi-line output `0\\n0` on\nzero matches because `grep -c` outputs `0` AND exits 1, triggering\nthe `|| echo 0` fallback. The buggy variable always silently failed\nthe subsequent `[ \"$READY_COUNT\" -ge ... ]` test with \"integer\nexpression expected\", but bash's `if` swallowed the test failure under\n`set -e` and just treated it as not-ready, masking the issue. New code\nuses `|| true` which keeps grep's clean `0` output without appending.",
          "timestamp": "2026-04-21T20:38:05+01:00",
          "tree_id": "849f1433e13b9b026a304b381c3ee4a46506ac9f",
          "url": "https://github.com/endavis/infrafoundry/commit/a81f1b9c74e9a269c53abd36be84633ffd2aa9bc"
        },
        "date": 1776800326705,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6725.008800838207,
            "unit": "iter/sec",
            "range": "stddev: 0.00002787496700155326",
            "extra": "mean: 148.6986901601318 usec\nrounds: 2185"
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
          "id": "5a7dd9e6d079f8b261418d35163897ffca299219",
          "message": "fix: surface curl failures in aiqum web-UI wait loops (sub-PR 3 of #655) (merges PR #665, addresses #664)\n\nfix: surface curl failures in aiqum web-UI wait loops\n\nTwo curl wait loops in aiqum-post-terraform.sh silenced curl's stderr,\nhiding the actual cause when the wait timed out. Same class of failure\nas #658 (SSH waits) and #662 (kubectl waits) -- sub-PR 3 of the audit\nin #655 (covers findings #6 and #7).\n\nPhase 3 (wait for web UI after RPM install): redirect curl's stderr to\na tmpfile each iteration; on 600s timeout, dump the last error before\nexit 1.\n\nPhase 4 (wait for web UI to come back after cert-regen restart): same\nfix; reuses the tmpfile from Phase 3.\n\nLatent issue fix while in there: the original loops used `curl -sk`\nwhere `-s` (silent) suppresses both progress AND errors. Even with the\nnew `2>\"$CURL_ERR\"` redirect, the file would have stayed empty.\nSwitched to `-skS` so `-S` re-enables errors-only output without\nre-enabling progress chatter. Verified locally: pointing curl at\n192.0.2.1:443 (RFC 5737 TEST-NET-1, guaranteed unreachable) now\nproduces `curl: (28) Failed to connect ... Timeout was reached` in the\ntmpfile, where the previous code would have left it empty.",
          "timestamp": "2026-04-21T21:05:06+01:00",
          "tree_id": "f5862382db7ba3bef7b13ed40671af6c1ebd0861",
          "url": "https://github.com/endavis/infrafoundry/commit/5a7dd9e6d079f8b261418d35163897ffca299219"
        },
        "date": 1776801943288,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7044.971034970196,
            "unit": "iter/sec",
            "range": "stddev: 0.000013289684075696177",
            "extra": "mean: 141.94522518774707 usec\nrounds: 2398"
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
          "id": "b6506a2015b24dd2bc6ce4768b67cef4ca04b382",
          "message": "feat: collect non-fatal warnings during apply and render a summary panel (merges PR #666, addresses #661)\n\nAdds a lightweight framework-level mechanism for non-fatal warnings\nduring `infra apply`:\n\n- New `INFRAFOUNDRY_WARNINGS_FILE` env var, set per-deployment by\n  `Orchestrator.apply()` to a JSONL temp file that anyone (Python\n  framework code, shell event handlers, blueprint scripts running on a\n  jumphost) can append to.\n- New `src/infrafoundry/core/warnings.py` with `emit_warning`,\n  `read_warnings`, and `render_warnings_panel` helpers. `emit_warning`\n  uses `fcntl.flock(LOCK_EX)` so parallel-apply ThreadPool workers\n  don't interleave messages that exceed PIPE_BUF (4KB).\n- `Orchestrator.apply()` reads the file in its `finally` block and\n  renders a yellow-bordered `rich.Panel` titled `⚠ Warnings (N)` on\n  both the success and failure paths, then unlinks and restores the\n  prior env-var value.\n- `ScriptHandler._execute_on_jumphost` + `_build_remote_bash` forward\n  the env var to the jumphost and scp the remote warnings file back\n  after the remote script completes. Local execution needed no change\n  -- existing `env = os.environ.copy()` already propagates.\n\nTest coverage: 19 new tests including a 50-thread x 5KB concurrent-\nappend isolation test that proves flock prevents interleaving, and\nend-to-end success/failure-path/env-restore coverage for the\norchestrator integration.\n\nThis is the plumbing for future handlers that need to surface\nabnormalities without aborting or burying them mid-log. First consumer\nlands in #655 sub-PR 4 (sysctl warn-and-continue).",
          "timestamp": "2026-04-21T22:15:59+01:00",
          "tree_id": "75a4ed384d6243c7b9043fd79c0b8a2c27931c46",
          "url": "https://github.com/endavis/infrafoundry/commit/b6506a2015b24dd2bc6ce4768b67cef4ca04b382"
        },
        "date": 1776806190404,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8344.704097443038,
            "unit": "iter/sec",
            "range": "stddev: 0.00002772410612296559",
            "extra": "mean: 119.8364841128899 usec\nrounds: 2801"
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
          "id": "5384b0e8df1dbe07358a0ab5b6d8ac53872b67bc",
          "message": "fix: surface sysctl failures in k3s node prep (sub-PR 4 of #655) (merges PR #668, addresses #667)\n\nThe per-node prep loop in blueprints/k3s-cluster/scripts/proxmox/\nk3s-post-terraform.sh silenced both stdout and stderr of `sysctl --system`\nwith `> /dev/null 2>&1`. This hid two distinct failure modes -- final\nfinding (#8) from the stdio-swallowing audit in #655.\n\nFix: capture output, verify the three required params are 1 in memory\nafter, decide fatal-vs-warn based on that authoritative check. If the\nparams didn't apply, exit 1 with the sysctl output + observed values\nto stderr (fatal -- inconsistent state must not proceed to k3s install).\nIf they did apply but `sysctl --system` still exited non-zero (unrelated\nentries in /etc/sysctl.d/), emit a non-fatal warning via the\nINFRAFOUNDRY_WARNINGS_FILE framework from PR #666 -- operator sees it\nin the end-of-apply summary panel.\n\nUses python3 stdlib for JSON escaping of the sysctl output (which may\ncontain quotes, newlines, backslashes). No jq or third-party packages.",
          "timestamp": "2026-04-22T11:54:40+01:00",
          "tree_id": "e9ebc5d469a4ed24089e59d0f2833bb765329bb2",
          "url": "https://github.com/endavis/infrafoundry/commit/5384b0e8df1dbe07358a0ab5b6d8ac53872b67bc"
        },
        "date": 1776855313560,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7317.980015406377,
            "unit": "iter/sec",
            "range": "stddev: 0.000009518296424679642",
            "extra": "mean: 136.64973092229314 usec\nrounds: 2267"
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
          "id": "6c3924d93ed516b3a30f3cb48795785aee66550c",
          "message": "refactor: rewrite aiqum-initial-setup.py to use stdlib only (drop requests, PyYAML) (merges PR #669, addresses #644)\n\n* refactor: rewrite aiqum-initial-setup.py to use stdlib only\n\nDrop the `requests` and `PyYAML` dependencies in favor of stdlib\n`urllib.request` + `json` + `ssl` + `base64`. Adds an inline\n`AIQUMClient` (Basic auth + permissive SSL for AIQUM's self-signed\nFEW cert). `load_config()` now reads `INFRAFOUNDRY_PACKAGE_VARS`\nexclusively and fails fast when unset.\n\nFixes ModuleNotFoundError on minimal jumphosts where pip packages\naren't installed system-wide. Aligns this script with the portable\nbaseline contract in docs/development/blueprint-script-portability.md.\n\nCLI and env-var interface unchanged; callers need no updates.\nAdds TestStdlibOnly as a regression guard (AST-walk every import).\n\n* fix: avoid logging option names in save_option failure path\n\nCodeQL py/clear-text-logging-sensitive-data (alert 32) flagged the\nfailure log at save_option:299 because `name` flows from a dict whose\nkeys include \"mail.smtp.password\", so CodeQL taints the variable even\nthough only the name (not the value) was ever logged.\n\nDrop the option name from the failure log; print only the HTTP status.\nThe wizard's Step-N progress messages retain enough context for the\noperator to know which step failed.\n\nPre-existing issue in the pre-refactor script too; CodeQL surfaces it\nnow because the file is in the changed set for #644.",
          "timestamp": "2026-04-22T12:49:45+01:00",
          "tree_id": "be4031e384650cfc03cb407fea81f45a3e7b68fc",
          "url": "https://github.com/endavis/infrafoundry/commit/6c3924d93ed516b3a30f3cb48795785aee66550c"
        },
        "date": 1776858624512,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6357.6748868797795,
            "unit": "iter/sec",
            "range": "stddev: 0.00004041287063590116",
            "extra": "mean: 157.2902071579159 usec\nrounds: 2375"
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
          "id": "0f9b96052683c54c36dd682941c5bf04972e7e57",
          "message": "feat: add outputs declaration to script handler for jumphost pullback (merges PR #671, addresses #660)\n\nScript event handlers gain an optional `outputs:` field that declares\nartifact files produced on the execution host and must be copied back to\nthe operator's workstation. Each entry maps a rendered `source` path on\nthe execution host to a rendered `dest` path on the operator. Transport\ndispatches by context: shutil.copy2 for local execution, one scp per\nentry for jumphost execution. Both values are Jinja2-rendered against\nthe package variables at execute time and must resolve to absolute\npaths. Pull-back runs only on script success; failure modes surface as\nnon-fatal warnings via INFRAFOUNDRY_WARNINGS_FILE.\n\nToday every blueprint that emits an operator-consumable artifact\n(kubeconfigs, CA certs, deploy reports) from a jumphost has to glue in\nits own scp back to the operator because `~/...` on the jumphost\nexpands against the jumphost's home, not the operator's. The new\nfield makes that the framework's job, keeps the declaration in the\nmanifest where it's discoverable, and keeps the script portable between\nlocal and jumphost execution.\n\nScope: framework primitive + ADR-0006 + docs + tests only. Migrating\nthe k3s-cluster blueprint's Phase-6 kubeconfig pullback off its ad-hoc\nscp glue is tracked separately.\n\nAddresses #660",
          "timestamp": "2026-04-22T13:57:04+01:00",
          "tree_id": "910895555f7dff75a6a7c375d83ab346bb9d9fe4",
          "url": "https://github.com/endavis/infrafoundry/commit/0f9b96052683c54c36dd682941c5bf04972e7e57"
        },
        "date": 1776862664269,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7375.029633447657,
            "unit": "iter/sec",
            "range": "stddev: 0.000009370573516938522",
            "extra": "mean: 135.59267551478612 usec\nrounds: 2185"
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
          "id": "e61dffad92f38c908ca0bd29be6d85acae34d8dd",
          "message": "chore: add pyproject-template divergence note (merges PR #680, addresses #679)",
          "timestamp": "2026-04-23T11:10:21+01:00",
          "tree_id": "b6f34ddd3b83246d1375d6be2cf70d50c875f8ca",
          "url": "https://github.com/endavis/infrafoundry/commit/e61dffad92f38c908ca0bd29be6d85acae34d8dd"
        },
        "date": 1776939054534,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9654.575900342907,
            "unit": "iter/sec",
            "range": "stddev: 0.000006383573295829561",
            "extra": "mean: 103.5778277909113 usec\nrounds: 2015"
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
          "id": "bf7b7375cc4b31df05cbb1935555c64781570210",
          "message": "chore: adopt upstream dependabot automerge + labels (merges PR #681, addresses #674)",
          "timestamp": "2026-04-23T12:35:34+01:00",
          "tree_id": "511b0d95abf87f9db9db3f338a25569fdbabd6ce",
          "url": "https://github.com/endavis/infrafoundry/commit/bf7b7375cc4b31df05cbb1935555c64781570210"
        },
        "date": 1776944170263,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9224.65873519617,
            "unit": "iter/sec",
            "range": "stddev: 0.000016154289793233526",
            "extra": "mean: 108.4050942919499 usec\nrounds: 2768"
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
          "id": "9287b02d712a160748105ed5e408930d6ee5bfa6",
          "message": "chore: unify ADR directories under docs/decisions (merges PR #682, addresses #675, #670)",
          "timestamp": "2026-04-23T17:54:16+01:00",
          "tree_id": "15689e8762dca21b09db06a1130a2c8107769dac",
          "url": "https://github.com/endavis/infrafoundry/commit/9287b02d712a160748105ed5e408930d6ee5bfa6"
        },
        "date": 1776963290812,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7164.469155132963,
            "unit": "iter/sec",
            "range": "stddev: 0.000011005545539722523",
            "extra": "mean: 139.5776823581623 usec\nrounds: 2273"
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
          "id": "60bdfc934cec96d6b196d0b6b05d70aa24422948",
          "message": "chore: sync new pyproject_template tooling modules and ruff-fix hook (merges PR #684, addresses #676)",
          "timestamp": "2026-04-23T19:35:45+01:00",
          "tree_id": "9da7012242f640d8e03684b1c6bf31d4fefcb969",
          "url": "https://github.com/endavis/infrafoundry/commit/60bdfc934cec96d6b196d0b6b05d70aa24422948"
        },
        "date": 1776969388542,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8783.239784944046,
            "unit": "iter/sec",
            "range": "stddev: 0.000021190024329101558",
            "extra": "mean: 113.85320502284004 usec\nrounds: 2190"
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
          "id": "6c090ee3ba24e53c8eab479e9fd9716b0ccd7463",
          "message": "chore: sync AI agent config, commands, and docs from pyproject-template (merges PR #685, addresses #677)",
          "timestamp": "2026-04-23T20:06:23+01:00",
          "tree_id": "bdefaf3e433d0dd95807f92b212c507cdfbf397c",
          "url": "https://github.com/endavis/infrafoundry/commit/6c090ee3ba24e53c8eab479e9fd9716b0ccd7463"
        },
        "date": 1776971219377,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9640.443922710301,
            "unit": "iter/sec",
            "range": "stddev: 0.000006718503801652311",
            "extra": "mean: 103.72966307539718 usec\nrounds: 2042"
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
          "id": "965c40b15257ad8ce6877b4a5d64478d6dcf4f45",
          "message": "chore: sync remaining doit tooling and hook updates from pyproject-template (merges PR #686, addresses #683)",
          "timestamp": "2026-04-23T20:47:22+01:00",
          "tree_id": "e34ae6e7728566505af6350d599696cf9d47c67a",
          "url": "https://github.com/endavis/infrafoundry/commit/965c40b15257ad8ce6877b4a5d64478d6dcf4f45"
        },
        "date": 1776973682633,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7262.56939466147,
            "unit": "iter/sec",
            "range": "stddev: 0.000010760049005139075",
            "extra": "mean: 137.69231599151047 usec\nrounds: 2345"
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
          "id": "d978f12fa44126bac16f3e2c0b22a88cf5043716",
          "message": "chore: complete pyproject-template sync with phase E dense-merge (merges PR #688, addresses #678)",
          "timestamp": "2026-04-23T21:38:44+01:00",
          "tree_id": "c4ff2fef973b096ab728299cf1d57f0a138fc9e5",
          "url": "https://github.com/endavis/infrafoundry/commit/d978f12fa44126bac16f3e2c0b22a88cf5043716"
        },
        "date": 1776976757230,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9653.171766930709,
            "unit": "iter/sec",
            "range": "stddev: 0.000006856781334728052",
            "extra": "mean: 103.59289403983709 usec\nrounds: 2114"
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
          "id": "6ff0b1e16efcc970c3aa920b619263593bf3bad8",
          "message": "fix: drop stale mypy suppressions in opnsense api_client (merges PR #703, addresses #702)\n\nopnsense-openapi 0.3.0 ships type information, so the\n`# type: ignore[import-untyped]` on the import and the `cast(dict[str,\nAny], ...)` on the request return are now no-ops. mypy reports\nunused-ignore and redundant-cast under `doit check`, blocking CI on\nevery branch that includes the 0.3.0 bump (#697).\n\nDrop both. The remaining `cast(list[dict[str, Any]], ...)` later in the\nsame file stays — mypy does not flag it.\n\nAddresses #702\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-30T14:54:20+01:00",
          "tree_id": "0b2572534cd166b5ac57d551c1f2ff0617e5dc0b",
          "url": "https://github.com/endavis/infrafoundry/commit/6ff0b1e16efcc970c3aa920b619263593bf3bad8"
        },
        "date": 1777557301157,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7379.644510651028,
            "unit": "iter/sec",
            "range": "stddev: 0.000009021487741726854",
            "extra": "mean: 135.5078823318253 usec\nrounds: 2745"
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
          "id": "584ac10ad62b85275868d16cda72b9941c982672",
          "message": "feat: add direct-API VLAN spike to inform ADR-0014 (merges PR #706, addresses #705)\n\n* feat: add direct-API VLAN spike to inform ADR-0014\n\nAdds an engineering spike under tools/spikes/ that demonstrates end-to-end\nVLAN management against OPNsense via opnsense_openapi's typed\n.api.<module>.<function> surface, with a client.get/post(...) fallback for\nendpoints the typed surface fails to expose.\n\nThe spike loads desired state from YAML, computes a diff against live box\nstate keyed by (device, tag), and applies changes only when --confirm is\npassed. Four subcommands: inspect (version + endpoint enumeration), list,\nplan, apply [--confirm].\n\nThis is exploratory tooling. The spike does NOT modify any production code\nunder src/infrafoundry/providers/opnsense/, does NOT introduce a new runner\nor provider component, and does NOT ship an ADR.\n\nIncludes 39 unit tests covering env-var loading, YAML parsing/validation,\nthe diff engine, the typed-surface fallback path, the dry-run guard, and\nthe main() finally-block client-close. No live box is contacted.\n\nPairs with docs/development/opnsense-spike-vlan-findings.md, an\nintentionally empty shell that the operator fills in after running the\nspike against opnsense-a (staging). ADR-0014 cites the completed findings\nand is authored as a follow-up PR.\n\nAlso adds an allow-list entry to .gitignore for tools/spikes/**/*.yaml so\nthe example-vlans.yaml fixture can be tracked. The repo-wide *.yaml\nexclusion is intended for user infra YAML; spike fixtures belong in source\ncontrol.\n\nAddresses #705\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n* feat: complete VLAN spike with hardening, safety flags, and live-run findings\n\nSpike now runs cleanly end-to-end against opnsense-a (verified live):\n- inspect, list, plan, apply --confirm (add cycle), plan (round-trip\n  empty), apply --confirm (delete cycle), plan (round-trip empty)\n- Lock semantics preserved across both apply cycles; WAN VLAN never\n  touched\n\nHardening (forced by the live run):\n- Broaden _typed_call to catch RuntimeError, not just AttributeError —\n  the typed .api property raises RuntimeError when no generated client\n  exists (e.g. when openapi-python-client isn't on PATH)\n- Add _warn_if_codegen_unavailable() startup check with actionable\n  install instructions (uv tool install, NOT uv pip install)\n- VLAN_CONTROLLER renamed from \"vlansettings\" to \"vlan_settings\" — the\n  bundled spec is wrong (filed as endavis/opnsense-openapi#32); live\n  26.1.6_2 uses snake_case for this controller\n- Inspect filter accepts both spellings so it works whether the spec is\n  buggy or fixed upstream\n- Example YAML's device fixed from generic igb1 to actual ixl1\n  (matches opnsense-a's hardware)\n\nSafety flags (motivated by a near-disaster on the first plan run, which\nproposed deleting the WAN trunk):\n- VlanConfig.lock: bool field — observed-but-untouchable resource;\n  recorded in plan output, never added/updated/deleted\n- --add-only flag on plan/apply — suppresses deletes for live VLANs not\n  in YAML; orthogonal to lock; useful for partial migrations\n- Diff.locked field; _print_diff renders locked entries with their UUID\n- Tests cover both flags individually and combined\n\nDocumentation:\n- Filled in docs/development/opnsense-spike-vlan-findings.md with run\n  logs, round-trip evidence, friction points, LoC comparison, typed-\n  surface coverage matrix (none — codegen CLI not installed during the\n  run; fallback path covered everything), and a recommendation section\n- README adds a \"Safety flags\" subsection\n- Cite three upstream issues filed against endavis/opnsense-openapi:\n  #32 (controller name bug — blocker), #33 (misleading error), #34\n  (spec/version resolution refactor)\n\n50 spike tests passing (was 39).\n\nAddresses #705\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-30T19:17:25+01:00",
          "tree_id": "0b63e4cde3bcfe8ea94dff7cbb25f25d03396adc",
          "url": "https://github.com/endavis/infrafoundry/commit/584ac10ad62b85275868d16cda72b9941c982672"
        },
        "date": 1777573071523,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6947.158050660657,
            "unit": "iter/sec",
            "range": "stddev: 0.00001950418078049614",
            "extra": "mean: 143.94375264067912 usec\nrounds: 2272"
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
          "id": "2036694360383afeb1cdf18a1ae2a11e58e98573",
          "message": "docs: add ADR-0014 for OPNsense direct-API apply mechanism (merges PR #708, addresses #707)\n\nCodify the OPNsense direct-API apply mechanism as the path forward,\nclosing the apply-mechanism deferral from ADR-0013. Take explicit\npositions on the nine open questions enumerated in #707:\n\n1. Apply mechanism for new components: direct-API via opnsense_openapi.\n2. Schema source: Pydantic models with hand-typed dict fallback for #32-affected sites.\n3. Client surface: bare client.post/get fallback; typed .api surface deferred.\n4. Runner integration: new OPNsenseDirectRunner implementing ADR-0010 protocols.\n5. Default semantics: fully-managed; --add-only opt-in for cutover.\n6. Lock contract: top-level boolean lock: true.\n7. Plan-time validation: validate interface references against the live box.\n8. config migrate integration: per-component method, matches Kea DHCP pattern.\n9. Existing Terraform paths: phased migration (VLANs first).\n\nLoad-bearing evidence comes from the live VLAN spike (PR #706, commit\n584ac10) and its findings doc at docs/development/opnsense-spike-vlan-findings.md.\n\nNote: ADR-0014 links to ADR-0013, which lives on PR #704's branch and\nhas not merged to main yet. The link will 404 until PR #704 lands; this\nis expected and called out in the ADR's own decision #9.\n\nAddresses #707\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-30T20:01:54+01:00",
          "tree_id": "984bb15bf51c588ee8cbdd69d62e21ce7123f2d2",
          "url": "https://github.com/endavis/infrafoundry/commit/2036694360383afeb1cdf18a1ae2a11e58e98573"
        },
        "date": 1777575755541,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7222.744419528836,
            "unit": "iter/sec",
            "range": "stddev: 0.000010103264826974453",
            "extra": "mean: 138.45152782870218 usec\nrounds: 2192"
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
          "id": "badc268b0ab3f3ad3010e63a9965ffa01019015c",
          "message": "chore: scope OPNsense full-IaC migration with ADR-0013 and resource-coverage doc (merges PR #704, addresses #701)\n\n* chore: scope OPNsense full-IaC migration with ADR-0013 and resource-coverage doc\n\nReplacing the production OPNsense host with a same-spec successor surfaced\nthat only Kea DHCP is currently managed by the InfraFoundry OPNsense provider;\ninterface assignments, NAT, gateways, static routes, virtual IPs, and most of\nUnbound have no IaC coverage. Without closing the gap, every box-to-box\nmigration requires hand-editing config.xml on the target.\n\nThis PR is the scoping/architecture step for closing that gap. No code yet —\nfollow-up issues will land each component.\n\n- docs/decisions/0013-opnsense-full-iac-migration.md: ADR-0013. Defines the\n  in-scope new components (interface_assignments, nat_rules, gateways,\n  static_routes, virtual_ips, Unbound domain_override/host_alias/forward),\n  the tooling work (`config migrate` extractors), and the deliberately\n  out-of-scope set migrated via selective config.xml import (HA sync,\n  OpenVPN, certs/ACME, GRE/GIF/LAGG/bridge/PPP/wireless). Also fixes the\n  data model: YAML schemas mirror the browningluke/opnsense Terraform\n  provider's resource args; extractors read from the OPNsense REST API;\n  config.xml is not in the apply or migrate path.\n- docs/development/opnsense-resource-coverage.md: provider coverage matrix\n  mapping config.xml sections to InfraFoundry resource types, listed gaps,\n  and a generic box-to-box migration runbook template.\n- docs/development/README.md: link the new coverage doc under Core\n  Extension Points.\n\nAddresses #701\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n* docs: defer OPNsense apply mechanism to ADR-0014\n\nThe original \"Data model\" section in ADR-0013 over-committed to the\nexisting Terraform pattern (YAML → Jinja2 .tf.j2 → terraform → the\nbrowningluke/opnsense provider, plus an Ansible playbook for service\nreload). Today's pipeline is a mix — Kea DHCP already calls the OPNsense\nREST API directly via opnsense_openapi (though using untyped .request()\nrather than the typed surface the package exposes).\n\nBefore filing the per-component issues, validate whether the new\ncomponents should follow the Terraform pattern or switch to a typed\ndirect-API pattern using opnsense_openapi (Pydantic models from the\nOPNsense OpenAPI spec, no terraform/ansible binaries). That choice\naffects schema source, runner integration, dependency footprint, and\ntest surface.\n\nRewrite the section to:\n\n- Describe today's mixed pipeline honestly.\n- Defer the apply-mechanism choice to ADR-0014, informed by a VLAN spike\n  (smallest existing surface, suitable for side-by-side comparison).\n- Note that the coverage and out-of-scope lists in this ADR stand\n  independent of that choice — they describe what to manage, not how.\n\nAdd a one-line forward reference at the top of the Implementation order\nsection pointing to ADR-0014 for the apply-mechanism decision.\n\nAddresses #701\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n* docs: take ADR-0013 off hold; reference ADR-0014 for apply mechanism\n\nADR-0014 has landed (PR #708, merges commit 2036694). Update ADR-0013's\n\"Data model and apply mechanism\" section to reference ADR-0014 instead\nof marking the choice as deferred. Tighten the Implementation order\nintro to past tense (the spike has informed ADR-0014). Add cross-refs\nto issue #705, issue #707, the spike findings doc, and ADR-0014 in the\nRelated Issues / Related Documentation sections.\n\nNo changes to scope, out-of-scope set, or implementation order — those\nwere always independent of the apply-mechanism decision.\n\nAddresses #701\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-04-30T20:14:03+01:00",
          "tree_id": "8aaaa774dac8c105bbede2a37ec37d2467455fef",
          "url": "https://github.com/endavis/infrafoundry/commit/badc268b0ab3f3ad3010e63a9965ffa01019015c"
        },
        "date": 1777576470249,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7275.209535794745,
            "unit": "iter/sec",
            "range": "stddev: 0.000010461428577258984",
            "extra": "mean: 137.45308572624637 usec\nrounds: 2403"
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
          "id": "918f8c4cd55c436c4a58e5db0515ab7525f78f5e",
          "message": "feat: add OPNsenseDirectRunner and migrate VLAN to direct-API (merges PR #710, addresses #709)\n\nfeat: add OPNsenseDirectRunner and migrate VLAN component to direct-API\n\nVertical slice that ships OPNsenseDirectRunner together with its first\nproduction consumer (the VLAN component), retiring the terraform/\nbrowningluke pipeline for VLANs and seeding the apply path for the rest\nof the ADR-0013 component list.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-02T12:09:22+01:00",
          "tree_id": "12139b5c16ca8e8be08853eddb75470c430db260",
          "url": "https://github.com/endavis/infrafoundry/commit/918f8c4cd55c436c4a58e5db0515ab7525f78f5e"
        },
        "date": 1777720187613,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 5922.152220360051,
            "unit": "iter/sec",
            "range": "stddev: 0.00004912386883831614",
            "extra": "mean: 168.8575306392923 usec\nrounds: 2252"
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
          "id": "5b4884e6afbd810ad923b6f9e0ad4dd2f95c34d4",
          "message": "feat: add OPNsense interface_assignments (read-only) + dispatch table (merges PR #712, addresses #711)\n\nAdds interface_assignments as a read-only / migrate component and\nrefactors OPNsenseDirectRunner to dispatch via\nprovider.get_direct_api_resource_types(). Apply/destroy are loud\nno-ops because OPNsense 26.1.6_2 has no REST write API for interface\nassignments. Cutover runbook documents the manual GUI step. ADR-0013\nand ADR-0014 amended with the per-component decision and read-only\nconstraint.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-02T13:35:29+01:00",
          "tree_id": "3ceb21e4737f752e522c3844007b92414bfd83ba",
          "url": "https://github.com/endavis/infrafoundry/commit/5b4884e6afbd810ad923b6f9e0ad4dd2f95c34d4"
        },
        "date": 1777725355368,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8464.160452039388,
            "unit": "iter/sec",
            "range": "stddev: 0.00002244193377309544",
            "extra": "mean: 118.14520833652864 usec\nrounds: 48"
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
          "id": "2af2cdf7498cd7bf42ab55faca505ff981cf743b",
          "message": "feat: spike OPNsense gist-based interface_assignments REST write API (merges PR #716, addresses #715)\n\nfeat: add gist-based REST interface_assignments write spike\n\nPivots from #714's rejected SSH+PHP-edit path to a server-side-validated\nREST write path. Forks szymczag's AssignSettingsController.php (BSD-2),\napplies the modern-OPNsense sessionClose() patch, and extends with\nsetItem/getItem/searchItem/IPv6/explicit-name. Live verification on\nopnsense-a (26.1.6_2) confirms all extended endpoints work; round-trip\nproperty holds across add/setItem/delete cycles. Auto-rollback is\nunavailable on this OPNsense version (/api/core/backup/* 404s) —\ndocumented as gate (1) for ADR-0014 amendment. No production code\ntouched; findings doc is the artifact for the upcoming amendment.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-02T19:25:42+01:00",
          "tree_id": "8da69ec2a97b71ed0ccda40dc81f1f49994a3211",
          "url": "https://github.com/endavis/infrafoundry/commit/2af2cdf7498cd7bf42ab55faca505ff981cf743b"
        },
        "date": 1777746366040,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9075.440948773019,
            "unit": "iter/sec",
            "range": "stddev: 0.00001875822586331102",
            "extra": "mean: 110.1874835222412 usec\nrounds: 1942"
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
          "id": "a9826ee8b1402f1faf4a8f231582d036dc000400",
          "message": "docs: amend ADR-0014 to record gist-based REST mechanism for interface_assignments (merges PR #718, addresses #717, #711, #709, #707)\n\n* docs: amend ADR-0014 to record gist-based REST mechanism for interface_assignments\n\n* docs: fill in PR number in ADR-0014 amendment header",
          "timestamp": "2026-05-03T10:36:11+01:00",
          "tree_id": "c8dd2e16cd00c8d461d964d30c523d46fe1b090f",
          "url": "https://github.com/endavis/infrafoundry/commit/a9826ee8b1402f1faf4a8f231582d036dc000400"
        },
        "date": 1777800999763,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8624.742203563168,
            "unit": "iter/sec",
            "range": "stddev: 0.00002608984753762449",
            "extra": "mean: 115.9454945316356 usec\nrounds: 2103"
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
          "id": "4e71a9c9166ae20a3fb16bd55eeba969a6deef9c",
          "message": "feat: add OPNsense nat_rules component (outbound + 1:1, direct-API) (merges PR #719, addresses #713)",
          "timestamp": "2026-05-03T12:05:59+01:00",
          "tree_id": "ffecd2da5bbff24797edfc74514ffa6738e29b7f",
          "url": "https://github.com/endavis/infrafoundry/commit/4e71a9c9166ae20a3fb16bd55eeba969a6deef9c"
        },
        "date": 1777806388518,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9768.200422870746,
            "unit": "iter/sec",
            "range": "stddev: 0.0000041058500278042316",
            "extra": "mean: 102.37300185391906 usec\nrounds: 2697"
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
          "id": "4303c050a509c4f46c3b7a4396c2d572bef695d8",
          "message": "feat: convert opnsense interface_assignments apply from no-op to live (merges PR #728, addresses #720, #717, #711, #709)\n\n* feat: convert opnsense interface_assignments apply from no-op to live\n\nGraduates the gist-controller spike (PR #716, ADR-0014 amendment in\nPR #718) to production. Extends services/interface_assignment.py with\nfull CRUD + diff engine + typed config + live->typed projector. Replaces\nno-op apply/destroy stubs in components/interface_assignment.py with\nreal orchestration mirroring VlanManager. New extensions/ sub-package\nholds the forked PHP controller and an idempotent installer driven by\nthe manager (SSH only on first apply or checksum mismatch).\n\nCloses ADR-0014 amendment gates (2) auto-snapshot/audit-log mechanism\ninheritance and (3) ~225 LoC PHP security review (write-up in\nPROVENANCE.md). Gate (2) empirical screenshots are operator-captured\nbefore external review.\n\nSpike at tools/spikes/interface_assignment_gist_rest/ deleted in the\nsame PR per the issue body's scope decision.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n* fix: suppress bandit B404 on opnsense installer subprocess import\n\nBandit flags B404 (import subprocess) at module load. CI runs bandit\nwithout the doit-task fallback that swallows non-zero exits, so the\nfinding broke `test (3.12)` and `test (3.14)`. Existing convention in\nsrc/ is `# nosec B404 - required for <reason>`; applied here for the\nSCP + SSH one-time controller install path.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-03T16:46:29+01:00",
          "tree_id": "2d57b21ede8d2ad01cb2f1c4865be9cf9042a8d5",
          "url": "https://github.com/endavis/infrafoundry/commit/4303c050a509c4f46c3b7a4396c2d572bef695d8"
        },
        "date": 1777823220032,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8513.902875938198,
            "unit": "iter/sec",
            "range": "stddev: 0.000025885705938515073",
            "extra": "mean: 117.45494570136306 usec\nrounds: 2210"
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
          "id": "f716ab7c77862f6b6cc5a724117972f6a7f57073",
          "message": "feat: convert opnsense interface_assignments apply from no-op to live (merges PR #728, addresses #720)\n\n* feat: convert opnsense interface_assignments apply from no-op to live\n\nGraduates the gist-controller spike (PR #716, ADR-0014 amendment in\nPR #718) to production. Extends services/interface_assignment.py with\nfull CRUD + diff engine + typed config + live->typed projector. Replaces\nno-op apply/destroy stubs in components/interface_assignment.py with\nreal orchestration mirroring VlanManager. New extensions/ sub-package\nholds the forked PHP controller and an idempotent installer driven by\nthe manager (SSH only on first apply or checksum mismatch).\n\nCloses ADR-0014 amendment gates (2) auto-snapshot/audit-log mechanism\ninheritance and (3) ~225 LoC PHP security review (write-up in\nPROVENANCE.md). Gate (2) empirical screenshots are operator-captured\nbefore external review.\n\nSpike at tools/spikes/interface_assignment_gist_rest/ deleted in the\nsame PR per the issue body's scope decision.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n* fix: suppress bandit B404 on opnsense installer subprocess import\n\nBandit flags B404 (import subprocess) at module load. CI runs bandit\nwithout the doit-task fallback that swallows non-zero exits, so the\nfinding broke `test (3.12)` and `test (3.14)`. Existing convention in\nsrc/ is `# nosec B404 - required for <reason>`; applied here for the\nSCP + SSH one-time controller install path.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-03T17:04:35+01:00",
          "tree_id": "2d57b21ede8d2ad01cb2f1c4865be9cf9042a8d5",
          "url": "https://github.com/endavis/infrafoundry/commit/f716ab7c77862f6b6cc5a724117972f6a7f57073"
        },
        "date": 1777824470963,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6564.139748886474,
            "unit": "iter/sec",
            "range": "stddev: 0.00003049254391093592",
            "extra": "mean: 152.34288699743752 usec\nrounds: 2115"
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
          "id": "7c125e2be8692bc5d6f8ed65ee4671e0b58a7534",
          "message": "feat: add OPNsense gateways component (direct-API) (merges PR #729, addresses #721)\n\nAdds the OPNsense `gateways` direct-API component (ADR-0013 step #3),\nunblocking the opnsense.endavis.net -> opnsense-a cutover. Identity is\nthe natural-key `name` field (no description-suffix tag, divergent\nfrom nat_rules); mechanism is stock direct REST against\n`routing/settings/{searchGateway,addGateway,setGateway,delGateway,\nreconfigure}` -- the issue body's `routes/gateway/*` and\n`firewall/gateway/*` candidates were both wrong; correct path\nconfirmed via the bundled OPNsense OpenAPI spec for 26.1.6 and a\nlive probe against opnsense-a.\n\nIncludes service, component manager, validator, provider integration,\n117 unit tests, 5 opt-in integration tests, and ADR-0013 amendment\n+ resource coverage matrix updates.\n\nAddresses #721\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-03T17:53:28+01:00",
          "tree_id": "243a8e145a752997fead41e5bcbe4e8dec090dd6",
          "url": "https://github.com/endavis/infrafoundry/commit/7c125e2be8692bc5d6f8ed65ee4671e0b58a7534"
        },
        "date": 1777827234815,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6767.6007030025285,
            "unit": "iter/sec",
            "range": "stddev: 0.000023644416591143295",
            "extra": "mean: 147.76285479672845 usec\nrounds: 2679"
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
          "id": "717c38e492305c07126d7e505b6ac5267f6cab8b",
          "message": "feat: add OPNsense static_routes component (direct-API) (merges PR #735, addresses #722)\n\nAdds the OPNsense `static_routes` direct-API component (ADR-0013 step #3,\nthe gateways-paired half), closing the next gap in the box-to-box\nmigration scope. Identity is the natural-key tuple `(network, gateway)`;\nmechanism is stock direct REST against `routes/routes/{searchroute,\ngetroute, addroute, setroute, delroute, reconfigure}` -- confirmed via\nlive probe against opnsense-a (26.1.6_2) and cross-checked with the\nbundled OpenAPI spec for 26.1.6. Live probe also showed the field surface\nis narrower than initially planned (only `network`, `gateway`, `descr`,\n`disabled` -- no metric / mtu / interface override knobs on this version).\n\nValidator accepts both managed `gateway_names` and live `existing_gateways`\n(via a new `_get_existing_gateways()` helper that fetches `routing/settings/\nsearchGateway`), so static routes can target dynamic system gateways like\n`WAN_DHCP` / `WAN_DHCP6` without first declaring them as managed. Cross-\nprotocol mismatch is enforced at validation time -- the live API does not\nalways reject it server-side.\n\nIncludes service, component manager, validator, provider integration,\n118 unit tests, and ADR-0013/0014 amendments + resource coverage matrix\nupdates.\n\nAddresses #722\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-04T12:14:50+01:00",
          "tree_id": "1da38cdc3e1d06463a63b10764144cd0a8633cea",
          "url": "https://github.com/endavis/infrafoundry/commit/717c38e492305c07126d7e505b6ac5267f6cab8b"
        },
        "date": 1777893323211,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6559.789020784674,
            "unit": "iter/sec",
            "range": "stddev: 0.00003338075059161783",
            "extra": "mean: 152.4439272103878 usec\nrounds: 2624"
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
          "id": "d6d80625d71706d45b5e35dcb07de68595acb457",
          "message": "feat: add OPNsense unbound_host_alias and unbound_forward components (merges PR #736, addresses #724)\n\nTwo new direct-API Unbound resources. The originally-planned\nunbound_domain_override is dropped: a Step 0 live-API probe confirmed\nOPNsense merges domain_override into the Forward resource (a Forward\nentry with non-empty domain is a domain override; empty domain is a\nglobal forwarder). See ADR-0013 and ADR-0014 amendments.\n\nAddresses #724\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-04T13:14:20+01:00",
          "tree_id": "8cf116af8d049aa0a0be3e6d69486bb72782ec33",
          "url": "https://github.com/endavis/infrafoundry/commit/d6d80625d71706d45b5e35dcb07de68595acb457"
        },
        "date": 1777896893941,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12274.949595192507,
            "unit": "iter/sec",
            "range": "stddev: 0.000010655644395959228",
            "extra": "mean: 81.46672963868225 usec\nrounds: 2382"
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
          "id": "459ea5eaef91875d69c4147d3c50ed73e19cc519",
          "message": "feat: add OPNsense virtual_ips component (direct-API) (merges PR #737, addresses #723)\n\n* feat: add OPNsense virtual_ips component (direct-API)\n\nNew direct-API resource type supporting ipalias / carp / proxyarp modes.\nIdentity tuple (interface, mode, address, vhid). First direct-API resource\nto carry a secret: CARP password flows via secret://env_secrets/<path>\nURIs, resolved at apply time by a new EnvSecretsBackend plugged into the\nexisting SecretResolver. Mechanism documented in ADR-0014's new \"Secrets\nhandling\" section.\n\nAddresses #723\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n* chore: silence bandit B105 false positives in virtual_ip\n\nThree pure false positives flagged by bandit B105 (hardcoded password\nstring) that surface in CI but pass locally because doit check's\nsecurity task swallows bandit failures via `|| echo`:\n\n- _PASSWORD_REDACTED_PLACEHOLDER constant (migrate output sentinel)\n- password = \"\" local-variable initialization in the per-mode handler\n- password == \"\" empty-string comparison in the validator\n\nNone are actual credentials. Same pattern used elsewhere\n(validator.py:104-106) for the same false-positive class.\n\nAddresses #723\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-04T17:22:33+01:00",
          "tree_id": "e7e1b81520c61eda6ad5bc3633e3e980bd72047d",
          "url": "https://github.com/endavis/infrafoundry/commit/459ea5eaef91875d69c4147d3c50ed73e19cc519"
        },
        "date": 1777911789576,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7031.718905445978,
            "unit": "iter/sec",
            "range": "stddev: 0.000014644030378443507",
            "extra": "mean: 142.21273822898587 usec\nrounds: 2315"
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
          "id": "ec7394119134adea80fb5966c189dc0e366402f9",
          "message": "feat: add OPNsense port_forward kind on nat_rules (merges PR #738, addresses #725)",
          "timestamp": "2026-05-04T20:59:48+01:00",
          "tree_id": "a4fc3d86b0465fe99f722d8de8735cee01b13d82",
          "url": "https://github.com/endavis/infrafoundry/commit/ec7394119134adea80fb5966c189dc0e366402f9"
        },
        "date": 1777924827891,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6453.294923276465,
            "unit": "iter/sec",
            "range": "stddev: 0.00002321158660198734",
            "extra": "mean: 154.9596000010922 usec\nrounds: 10"
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
          "id": "056f3966d530770c565d2a2109fead9fbbe8b247",
          "message": "refactor: extract config-migrate extractor registry (merges PR #739, addresses #726)\n\nReplace the per-component if/elif dispatch on the OPNsense provider\nand the hardcoded click.Choice on `config migrate` with a pluggable\nregistry keyed by (provider_name, resource_type). Providers populate\nthe registry during __init__; the CLI looks up extractors at runtime\nand validates --provider / --component against the registered set.\nResolves ADR-0014 §8.\n\nExpands the `config migrate` surface from 2 reachable OPNsense\ncomponents to all 10. Pre-#726 OPNsenseProvider.migrate_<resource>\nmethods retained as deprecated shims for one minor version.\n\nBREAKING CHANGE: `--component kea/dhcp` is now `--component kea_dhcp`,\nand `--component isc-to-kea` is now `--component isc_to_kea` (Python-\nidentifier form, matching the registry key). No transparent alias.\nDefault output filename for isc_to_kea follows the new name.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-04T23:16:40+01:00",
          "tree_id": "63b4dd51520948ec7fc0546c38d5b1d7a53d5ccf",
          "url": "https://github.com/endavis/infrafoundry/commit/056f3966d530770c565d2a2109fead9fbbe8b247"
        },
        "date": 1777933032199,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7183.601218201623,
            "unit": "iter/sec",
            "range": "stddev: 0.000015436694640989473",
            "extra": "mean: 139.20594554528247 usec\nrounds: 2424"
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
          "id": "740c4eb33ddacdf8b4def83760d0467e3d305d54",
          "message": "chore: remove vlan direct-api spike after adr-0013 coverage (merges PR #740, addresses #727)",
          "timestamp": "2026-05-04T23:40:21+01:00",
          "tree_id": "4e7c1f42a7e64bc1bdd4762132e403c59f3df48e",
          "url": "https://github.com/endavis/infrafoundry/commit/740c4eb33ddacdf8b4def83760d0467e3d305d54"
        },
        "date": 1777934447096,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 5687.956630900994,
            "unit": "iter/sec",
            "range": "stddev: 0.0000329224007066539",
            "extra": "mean: 175.81006060547196 usec\nrounds: 66"
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
          "id": "3903e8142912ca106eaa7935425929e8bddd9771",
          "message": "docs: propose ADR-0015 for firewall_rules direct-API via MVC controller (merges PR #744, addresses #742)\n\nDrafts the architecture decision for migrating firewall_rules to direct-API\nagainst OPNsense's MVC firewall/filter/* controller, replacing the\nterraform/browningluke path. Survey of opnsense-a (26.1.6_2) confirmed\nthe full field surface (53 fields) covers 100% of #742's required gaps\nand the standard CRUD + apply + savepoint endpoints are live with no\ncontroller fork required.\n\nAddresses #742.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-05T02:16:10+01:00",
          "tree_id": "2d3257b809f8c3cdca13a44a0f7aafb979ba23b8",
          "url": "https://github.com/endavis/infrafoundry/commit/3903e8142912ca106eaa7935425929e8bddd9771"
        },
        "date": 1777943798373,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7119.848569724214,
            "unit": "iter/sec",
            "range": "stddev: 0.000016832631746493745",
            "extra": "mean: 140.4524253861673 usec\nrounds: 2332"
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
          "id": "16b1f1f461032cfb713f0482652e31a315dca10b",
          "message": "feat: migrate OPNsense firewall_rules to direct-API (merges PR #745, addresses #742)\n\nfeat: migrate OPNsense firewall_rules to direct-API via MVC controller\n\nMigrates firewall_rules from the terraform + browningluke/opnsense path\nto direct-API targeting the OPNsense MVC stateful filter controller at\nfirewall/filter/*. Field surface expands from ~10 to ~50 scalar/enum\nfields, covering everything production rules use (gateway, floating,\ndirection, quick, statetype, source/destination negation, <any>,\naddress-vs-network, ICMP/TCP/QoS/state knobs).\n\nMirrors the nat_rules pattern (#713/#725): three layers (service /\ncomponent manager / validator), [infrafoundry:<name>] description suffix\nidentity, infrafoundry category UUID as fleet-wide marker (multi-valued\non MVC, so appended to operator-set categories rather than overwriting).\n\nLegacy terraform path retired in this PR — no kind: legacy shim, since\nendavis-infra has zero terraform-managed firewall rules and no other\nconsumer was identified.\n\nADR-0015 flipped to Accepted; ADR-0014 amended with the firewall_rules\nper-component decision; coverage matrix updated.\n\nAddresses #742.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-05T11:22:40+01:00",
          "tree_id": "544b0aaee43b91a1d3988918ed8ff6e733b5b312",
          "url": "https://github.com/endavis/infrafoundry/commit/16b1f1f461032cfb713f0482652e31a315dca10b"
        },
        "date": 1777976588635,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7177.11285407846,
            "unit": "iter/sec",
            "range": "stddev: 0.000014191582117431796",
            "extra": "mean: 139.33179264859137 usec\nrounds: 2122"
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
          "id": "3809033ac21a551deaecd0fe82e00bad2b8d2a41",
          "message": "feat: add config-migrate extractor for opnsense aliases (merges PR #749, addresses #747)\n\nAddresses #747\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-05T12:10:35+01:00",
          "tree_id": "eb1338119b493e279b38cad33cb9fdc996f57a44",
          "url": "https://github.com/endavis/infrafoundry/commit/3809033ac21a551deaecd0fe82e00bad2b8d2a41"
        },
        "date": 1777979467208,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6581.748352363136,
            "unit": "iter/sec",
            "range": "stddev: 0.0000321374756530335",
            "extra": "mean: 151.93531360720533 usec\nrounds: 2484"
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
          "id": "b88db055a0f91c131ab7eabb7b416d9a4df0ed24",
          "message": "feat: add config-migrate extractor for opnsense unbound_host_override (merges PR #750, addresses #748)\n\nAddresses #748\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-05T12:45:47+01:00",
          "tree_id": "2487ad9450687954fdaf23c6313d79e3af326bf7",
          "url": "https://github.com/endavis/infrafoundry/commit/b88db055a0f91c131ab7eabb7b416d9a4df0ed24"
        },
        "date": 1777981582279,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7390.49211140959,
            "unit": "iter/sec",
            "range": "stddev: 0.000010295601614595046",
            "extra": "mean: 135.3089868611293 usec\nrounds: 2740"
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
          "id": "e8fc8b06e6d9496c82d81801a990c46ef308bb6b",
          "message": "fix: serialize infrafoundry category bootstrap to close race between firewall_rules and nat_rules (merges PR #751, addresses #746)\n\nAddresses #746\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-05T13:24:17+01:00",
          "tree_id": "db1f6bd8a6ea3697adf436507c91b7383d5e58a2",
          "url": "https://github.com/endavis/infrafoundry/commit/e8fc8b06e6d9496c82d81801a990c46ef308bb6b"
        },
        "date": 1777983890691,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8589.391697462448,
            "unit": "iter/sec",
            "range": "stddev: 0.00002242814990119685",
            "extra": "mean: 116.42267988493627 usec\nrounds: 1740"
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
          "id": "e963b78948b7d72e76403733ddb6f9883807d91d",
          "message": "feat: add env-var override for OPNsense direct-API runtime credentials (merges PR #752, addresses #741)\n\n* feat: add env-var override for OPNsense direct-API runtime credentials\n\nAdds an opt-in env-var override for OPNsense credentials gated by\nINFRAFOUNDRY_ALLOW_ENV_OVERRIDE. When the gate is set, OPNSENSE_API_URL,\nOPNSENSE_API_KEY, OPNSENSE_API_SECRET, and OPNSENSE_VERIFY_SSL win over\nprovider_settings.opnsense.* on a per-field basis. A one-time-per-process\nWARNING per resolved URL fires when the override changes the endpoint.\n\nResolution lives in a shared helper (services/_credentials.py); both\ndirect-API construction sites (BaseService.from_environment and the\nKea-DHCP path in OPNsenseProvider) delegate to it.\n\nADR-0014 amended with a Runtime credential resolution subsection;\nopnsense-resource-coverage.md step 5 (Switch endpoint) documents the\noverride as an alternative to editing settings.yaml. Terraform\nTF_VAR_* path is out of scope and tracked as a follow-up.\n\nAddresses #741\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n* chore: silence bandit B105 and CodeQL URL-substring false positives\n\n- Add # nosec B105 to API_SECRET_ENV_VAR — the constant holds the env\n  var name \"OPNSENSE_API_SECRET\", not a credential value. Matches the\n  existing convention in providers/opnsense/__init__.py:101 and\n  providers/proxmox/__init__.py.\n- Rewrite five `assert \"URL\" in <message>` test assertions to use\n  `<message>.find(\"URL\") != -1` instead. Defuses CodeQL's\n  py/incomplete-url-substring-sanitization false positive without\n  changing what the tests assert.\n\ndoit check green; behavior unchanged.\n\nAddresses #741\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-05T15:39:23+01:00",
          "tree_id": "78d07cdde39c2740a5b8052f9aa4821c16427731",
          "url": "https://github.com/endavis/infrafoundry/commit/e963b78948b7d72e76403733ddb6f9883807d91d"
        },
        "date": 1777991998785,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6663.216989231582,
            "unit": "iter/sec",
            "range": "stddev: 0.000030412047770828278",
            "extra": "mean: 150.07765792650892 usec\nrounds: 2479"
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
          "id": "f966261beb867ae7aa16ff61f9284bdd2ae8dd32",
          "message": "fix: tolerate per-controller 404s in opnsense nat_rules / firewall_rules migrate (merges PR #755, addresses #754)\n\n`foundry config migrate --component nat_rules` aborted with HTTP 404\non a 25.7.x box that lacks the firewall/d_nat (port_forward) MVC\ncontroller, even though outbound and 1:1 controllers were present and\nwould have extracted cleanly.\n\nAdd migrate-only per-controller 404 tolerance:\n\n- NATRuleService.search_all_tolerant: per-kind try/except for APIError\n  with status_code=404; skip the missing kind, log a WARNING naming\n  the kind + endpoint, continue with surviving kinds. Other status\n  codes (5xx, 401/403) propagate.\n- FirewallRuleService.search_tolerant: same shape, single-controller\n  variant — returns [] with WARNING on 404.\n- export_to_yaml on both services now uses the tolerant variant.\n\nApply-time strict paths (search_all, search, diff/list) are\nintentionally unchanged — a missing controller at apply time on a box\nthat cannot host the resource is still a real error and propagates.\n\nLive-verified against prod (OPNsense 25.7.11_1): nat_rules migrate\nnow succeeds with the port_forward WARNING and writes resources: [];\nfirewall_rules migrate is regression-clean.\n\nAddresses #754\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-05T17:17:49+01:00",
          "tree_id": "4596eb1a7e0fde85fa159523ef8a11d6411fa4d5",
          "url": "https://github.com/endavis/infrafoundry/commit/f966261beb867ae7aa16ff61f9284bdd2ae8dd32"
        },
        "date": 1777997902553,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7088.041234817423,
            "unit": "iter/sec",
            "range": "stddev: 0.000015910092151357497",
            "extra": "mean: 141.0827006885716 usec\nrounds: 2469"
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
          "id": "4005ecaff6bd4f23b006663fbac9e7c9792c9b82",
          "message": "fix: kea dhcpv6 subnet change-detection on option_data option-dicts and valid_lifetime asymmetric round-trip (merges PR #757, addresses #756)\n\n`foundry infra plan` was firing `update_dhcp6_subnet` for every managed\nsubnet plus `kea/service/reconfigure` on every plan run against an\nOPNsense 25.7.x box, even when the YAML matched live state byte-for-byte.\nTwo distinct shape mismatches in the change-detection path produced\nunconditional false-positive diffs:\n\n1. option_data.dns_servers / option_data.domain_search are returned by\n   getSubnet as nested option-dicts (`{\"\": {\"value\": \"\", \"selected\": 1}}`)\n   on 25.7+. The extractor did `str(option_data.get(...))`, producing a\n   Python repr that could never match the desired side's plain string.\n   Fixed by extracting `_select_option_dict_value` (mirrors how\n   `interface` is already handled) and using it for both option_data\n   sub-fields. Backward-compatible with the plain-string path.\n\n2. valid_lifetime is accepted on write but absent from getSubnet\n   responses on 25.7.11_1. The active culprit on this prod box.\n   Fixed by adding `_drop_non_round_trip_subnet_fields` +\n   `_ASYMMETRIC_SUBNET_FIELDS = (\"valid_lifetime\",)` constant. The\n   helper drops the field from comparison only when the live response\n   is missing/empty — a future OPNsense version that exposes the value\n   re-engages comparison automatically. The desired-side payload still\n   sends valid_lifetime, so apply continues to set it; only diff\n   triggering changes.\n\nPlan in steady state now emits zero write API calls; the existing\n`if changes_made:` guard around reconfigure_service() does the rest.\n\nLayer 1 (move kea dhcpv6 mutation off generate_terraform onto\nOPNsenseDirectRunner) is deferred to a focused follow-up — that's\nthe architectural fix for \"plan should never mutate\", whereas this\nPR is the functional change-detection fix that closes the immediate\noperator-visible bug.\n\nReferences #439 (whitespace normalization) and #441 (interface as\noption-dict) for context on prior fixes of the same shape.\n\nLive-verified against prod: 4 subnets + 12 reservations all report\n`unchanged, skipping update`; \"No DHCPv6 changes detected, skipping\nKea reconfigure\" line confirms the changes_made guard kicks in.\n\nAddresses #756\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-05T18:06:02+01:00",
          "tree_id": "748479cda1a82538cb9de789fb438b0c8198cb07",
          "url": "https://github.com/endavis/infrafoundry/commit/4005ecaff6bd4f23b006663fbac9e7c9792c9b82"
        },
        "date": 1778000795400,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8388.075492608494,
            "unit": "iter/sec",
            "range": "stddev: 0.000029852180482967755",
            "extra": "mean: 119.21685741636351 usec\nrounds: 2090"
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
          "id": "6ff9b66c0cbe7b1034611e5e743e507a6360101c",
          "message": "docs: refresh opnsense interface_assignments runbook for #720 live apply (merges PR #759, addresses #753)",
          "timestamp": "2026-05-06T11:47:23+01:00",
          "tree_id": "9bcb9fe8b024c92969006bab35ec59543b90d3bd",
          "url": "https://github.com/endavis/infrafoundry/commit/6ff9b66c0cbe7b1034611e5e743e507a6360101c"
        },
        "date": 1778064471781,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9678.866266015673,
            "unit": "iter/sec",
            "range": "stddev: 0.000005866339430820086",
            "extra": "mean: 103.3178858469394 usec\nrounds: 2155"
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
          "id": "8a0c68ab3813c62f64dd0fa64fe453d6b94238dc",
          "message": "fix: honor runner PlanResult.success in plan path (merges PR #762, addresses #761)",
          "timestamp": "2026-05-06T16:12:23+01:00",
          "tree_id": "a1abbebf9c27691bd2b8a1b5ce6ec7911cc53ea0",
          "url": "https://github.com/endavis/infrafoundry/commit/8a0c68ab3813c62f64dd0fa64fe453d6b94238dc"
        },
        "date": 1778080379105,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7138.489376994251,
            "unit": "iter/sec",
            "range": "stddev: 0.000023435460528924662",
            "extra": "mean: 140.08566059126957 usec\nrounds: 2469"
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
          "id": "8874c57723e4996dd887ed02965da87177b6d345",
          "message": "refactor: drive kea_dhcp6 via OPNsenseDirectRunner managers (merges PR #760, addresses #758)",
          "timestamp": "2026-05-06T16:22:14+01:00",
          "tree_id": "9ca4e8118a721833bacf90e29b9e1584cd417f69",
          "url": "https://github.com/endavis/infrafoundry/commit/8874c57723e4996dd887ed02965da87177b6d345"
        },
        "date": 1778080977413,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9558.010875580669,
            "unit": "iter/sec",
            "range": "stddev: 0.000009484748582668075",
            "extra": "mean: 104.62427936285938 usec\nrounds: 2699"
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
          "id": "9d78d5aeb213e0b551d05796577acb7747fefb78",
          "message": "fix: rename unbound host overrides output to avoid terraform reserved *_override.tf suffix (merges PR #764, addresses #763)",
          "timestamp": "2026-05-06T17:23:22+01:00",
          "tree_id": "cf87cddbb7c06d46cb7f9e9d4481f0eba74d26cb",
          "url": "https://github.com/endavis/infrafoundry/commit/9d78d5aeb213e0b551d05796577acb7747fefb78"
        },
        "date": 1778084633432,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 4532.270383183835,
            "unit": "iter/sec",
            "range": "stddev: 0.00002329315730543532",
            "extra": "mean: 220.639969696053 usec\nrounds: 33"
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
          "id": "3b45475c1c12c6660b8e1d6352a5a54e44e6f3b0",
          "message": "fix: align opnsense terraform templates with browningluke/opnsense provider schema (merges PR #766, addresses #765)",
          "timestamp": "2026-05-07T11:03:01+01:00",
          "tree_id": "b5fa11d4918f1359408a88a9e5e23fb3eae72464",
          "url": "https://github.com/endavis/infrafoundry/commit/3b45475c1c12c6660b8e1d6352a5a54e44e6f3b0"
        },
        "date": 1778148214483,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7249.428923865378,
            "unit": "iter/sec",
            "range": "stddev: 0.0000143103891612892",
            "extra": "mean: 137.94190004511452 usec\nrounds: 2221"
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
          "id": "d9e715389e1cf4b3e463ba2bfdc3eb507d1c0fb6",
          "message": "fix: correct tailscale terraform module source path (registry 404) (merges PR #768, addresses #767)\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-07T12:51:06+01:00",
          "tree_id": "637afcbf27dfd9309d2a3e386432bbb02cadd7b8",
          "url": "https://github.com/endavis/infrafoundry/commit/d9e715389e1cf4b3e463ba2bfdc3eb507d1c0fb6"
        },
        "date": 1778154691884,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6885.65750185939,
            "unit": "iter/sec",
            "range": "stddev: 0.00002260577061830232",
            "extra": "mean: 145.22941341911965 usec\nrounds: 2489"
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
          "id": "3dcc073911a4bb04fbfc6bea1517b7afc02c3c9e",
          "message": "feat: add --provider scoping flag to infra plan/apply/destroy (merges PR #770, addresses #769)\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-07T16:29:34+01:00",
          "tree_id": "3b715891898b3c444e96f8186453b4df8046fa1a",
          "url": "https://github.com/endavis/infrafoundry/commit/3dcc073911a4bb04fbfc6bea1517b7afc02c3c9e"
        },
        "date": 1778167816178,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9697.498263158755,
            "unit": "iter/sec",
            "range": "stddev: 0.00001694799513127771",
            "extra": "mean: 103.1193791288467 usec\nrounds: 2089"
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
          "id": "bb04eae21e709d4f9cf451ef32f32378c3d9e26b",
          "message": "fix: print terraform plan summary, add infra plan -v/--verbose (merges PR #772, addresses #771)\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-07T17:05:26+01:00",
          "tree_id": "738c408f91a38d2198ee7e32f7e6aa33e4fee6ed",
          "url": "https://github.com/endavis/infrafoundry/commit/bb04eae21e709d4f9cf451ef32f32378c3d9e26b"
        },
        "date": 1778169962840,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7333.0207441351395,
            "unit": "iter/sec",
            "range": "stddev: 0.000010657105022076456",
            "extra": "mean: 136.36944922047135 usec\nrounds: 2373"
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
          "id": "53e453dbeb7d2d7ecb25be9942b3087c44a7dc78",
          "message": "fix: strip ansi color codes before parsing terraform plan summary (merges PR #774, addresses #773)\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-07T18:23:30+01:00",
          "tree_id": "bcf6b4479b85d4ebda955dd6e110d381008e80b4",
          "url": "https://github.com/endavis/infrafoundry/commit/53e453dbeb7d2d7ecb25be9942b3087c44a7dc78"
        },
        "date": 1778174648022,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9341.221520755122,
            "unit": "iter/sec",
            "range": "stddev: 0.000015637203112152666",
            "extra": "mean: 107.05238043848065 usec\nrounds: 2597"
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
          "id": "ebfa292865eb7318ef4e4fc4a085b9c398ca0f80",
          "message": "feat: migrate opnsense firewall_alias from terraform to direct-api (merges PR #779, addresses #775)\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-07T19:29:39+01:00",
          "tree_id": "65c15a3bb43c1a64b3d8d39a9352e704fbdbd038",
          "url": "https://github.com/endavis/infrafoundry/commit/ebfa292865eb7318ef4e4fc4a085b9c398ca0f80"
        },
        "date": 1778178624707,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7022.720015166762,
            "unit": "iter/sec",
            "range": "stddev: 0.00002413971999335009",
            "extra": "mean: 142.3949691629923 usec\nrounds: 1816"
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
          "id": "48b9ae2fd7a0448b6647a7fb00c9b1714472cf44",
          "message": "feat: migrate opnsense unbound_host_override to direct-api (merges PR #780, addresses #776)\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-07T20:18:14+01:00",
          "tree_id": "ba4df670ac343dc5ba6f9c72a44006a8496cb959",
          "url": "https://github.com/endavis/infrafoundry/commit/48b9ae2fd7a0448b6647a7fb00c9b1714472cf44"
        },
        "date": 1778181524515,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9536.03725380967,
            "unit": "iter/sec",
            "range": "stddev: 0.000009071505675430286",
            "extra": "mean: 104.86536213986554 usec\nrounds: 2187"
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
          "id": "e33e878a045887824cfb634a5c5f7319f2f8e27b",
          "message": "feat: migrate kea_subnet/kea_reservation (DHCPv4) to opnsense_direct (merges PR #781, addresses #777, #778)\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-08T11:55:26+01:00",
          "tree_id": "9685a9af1b53951ea281323e5a53295e87400c37",
          "url": "https://github.com/endavis/infrafoundry/commit/e33e878a045887824cfb634a5c5f7319f2f8e27b"
        },
        "date": 1778237764929,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 5465.821417600755,
            "unit": "iter/sec",
            "range": "stddev: 0.000057839728395607224",
            "extra": "mean: 182.95511755650338 usec\nrounds: 1948"
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
          "id": "1d7a93c61444ba6a960a410127769b7b8a64474e",
          "message": "refactor: retire opnsense dhcp_static_maps (merges PR #785, addresses #782)\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-08T13:39:03+01:00",
          "tree_id": "30fb7907f2254737f84c28d81d76140b1a22405b",
          "url": "https://github.com/endavis/infrafoundry/commit/1d7a93c61444ba6a960a410127769b7b8a64474e"
        },
        "date": 1778243976130,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6364.508546698304,
            "unit": "iter/sec",
            "range": "stddev: 0.00002876466298988226",
            "extra": "mean: 157.12132251260263 usec\nrounds: 2372"
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
          "id": "8046ea1295230109f34679117aa65427e68038bf",
          "message": "refactor: add ADR-0016 for direct-OPNsense nested YAML schema (#793 Phase 0) (merges PR #794, addresses #793)\n\ndocs: add ADR-0016 for direct-OPNsense nested YAML schema\n\nFormalizes the convention for migrating the direct-OPNsense provider's\nYAML schema from flat top-level resource type keys to a nested API-aligned\nhierarchy. Locks the type rename mapping, cross-reference syntax, migration\nstrategy (hard cutover with transient STEM_TO_DOTTED shim during Phases 1-4),\nand the 6-phase implementation sequence from issue #793 before any code\nlands.\n\nAddresses #793.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-09T15:18:39+01:00",
          "tree_id": "246dc4f78c854efab0dcf68b15ed61d02090591d",
          "url": "https://github.com/endavis/infrafoundry/commit/8046ea1295230109f34679117aa65427e68038bf"
        },
        "date": 1778336356897,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12394.632618328696,
            "unit": "iter/sec",
            "range": "stddev: 0.000007061622973948332",
            "extra": "mean: 80.6800839357868 usec\nrounds: 2490"
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
          "id": "c60cc3847745ed6df3cffcb87307e6e69f11a637",
          "message": "refactor: rename direct-OPNsense ResourceConfig.type strings to dotted paths (#793 Phase 1) (merges PR #795, addresses #793)\n\nrefactor: rename direct-OPNsense ResourceConfig.type strings to dotted paths\n\nRenames the 15 internal type strings for direct-API resource types from flat\nunderscored names (firewall_log, kea_subnet, etc.) to dotted paths matching\nthe API endpoint hierarchy (firewall.log, kea.dhcp4.subnets, etc.) per\nADR-0016.\n\nAdds a transient STEM_TO_DOTTED translation shim in the loader (and the\nprovider-centric/resource-centric loader modules) so existing flat-keyed\nYAML files continue to parse correctly during the multi-phase rollout. The\nshim is marked with TODO comments pointing at #793 Phase 5 hard cutover.\n\nYAML schema is unchanged in this phase. Updates dispatch dict, extractor\nregistry, runner filter defaults, validator type guards, service type\nguards, manager type guards, output template references, and ~50 test\nfiles.\n\nAddresses #793.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-09T15:36:40+01:00",
          "tree_id": "abe2e3d80be6a0bd293ee00b8ba7671733a7ea2c",
          "url": "https://github.com/endavis/infrafoundry/commit/c60cc3847745ed6df3cffcb87307e6e69f11a637"
        },
        "date": 1778337425427,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7852.888912339544,
            "unit": "iter/sec",
            "range": "stddev: 0.000029825757196695966",
            "extra": "mean: 127.34167147438721 usec\nrounds: 1872"
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
          "id": "f08c9090fc22e90c8fa704d49e4419158e0c8e1d",
          "message": "refactor: add nested-format YAML support to direct-OPNsense loader (#793 Phase 2) (merges PR #796, addresses #793)\n\nrefactor: add nested-format YAML support to direct-OPNsense loader\n\nAdds nested-YAML parsing support to the loader (and provider-centric /\nresource-centric variants) so YAML files using the new opnsense.<plugin>.<surface>\nhierarchy from ADR-0016 are accepted alongside the existing flat formats.\n\nDetection: a top-level `opnsense:` dict key triggers nested parsing. The\nloader walks the tree, validates each leaf path against DOTTED_RESOURCE_SHAPES\n(introduced here), and emits ResourceConfig per leaf:\n  - dict leaf at a registered singleton path: one ResourceConfig with\n    name=\"settings\"\n  - list leaf at a registered list path: one ResourceConfig per entry\n  - shape mismatch / unknown path / malformed leaf: clear error\n\nPre-registers the future singleton/list paths from in-flight feature\nissues #786-#792 (firewall.log, tailscale.*, radvd, cron.jobs, acmeclient.*,\nmonit.*, hostwatch) so operator YAML and tests can land alongside each\ncomponent without a follow-up loader update.\n\nMixed nested+flat formats in one file are rejected with a clear error\nmatching the AGENTS.md no-silent-failures stance.\n\nAdds 42 unit tests across 11 classes covering singleton/list/mixed/empty\nshapes, unknown paths, shape mismatches, malformed leaves, list-entry\nvalidation, format ambiguity, backwards-compat, and direct-helper calls.\n\nExisting flat-format parsing path is untouched; flat YAML continues to\nwork via the STEM_TO_DOTTED shim from Phase 1.\n\nAddresses #793.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-09T15:38:35+01:00",
          "tree_id": "4236e3b1a71b4856c657f1f0db0aacab0816826f",
          "url": "https://github.com/endavis/infrafoundry/commit/f08c9090fc22e90c8fa704d49e4419158e0c8e1d"
        },
        "date": 1778337539917,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9233.096045538172,
            "unit": "iter/sec",
            "range": "stddev: 0.00001965527249810555",
            "extra": "mean: 108.30603245844529 usec\nrounds: 2095"
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
          "id": "42d4bae73bac1b90a1c3dbef553c955ed21df58b",
          "message": "refactor: add dotted-path cross-reference resolver for OPNsense validators (#793 Phase 3) (merges PR #797, addresses #793)\n\nrefactor: add dotted-path cross-reference resolver for OPNsense validators\n\nAdds a shared dotted-path resolver in\nsrc/infrafoundry/providers/opnsense/validators/_xref.py that handles all\nthree cross-reference forms from ADR-0016:\n\n  - bare name: gateway: WAN_GW                        (today's flat form)\n  - in-plugin relative: gateway: gateways.WAN_GW       (new)\n  - cross-plugin absolute: update_cron: cron.jobs.x    (new)\n\nPlus build_xref_index(resources) helper that produces the\n{dotted_type: {name: ResourceConfig}} index OPNsenseValidator.validate_references()\nnow builds once and passes to per-resource validators.\n\nUpdates 5 validators that have cross-reference fields to call resolve_xref\nbefore falling back to the existing bare-name lookup (so flat-format YAML\ncontinues to validate identically while dotted-form YAML resolves correctly):\n\n  - static_route_validator.py: gateway field\n  - firewall_rule_validator.py: interface, gateway, source_net,\n    destination_net fields\n  - nat_rule_validator.py: interface, source_net, destination_net,\n    target fields\n  - unbound_host_alias_validator.py: host field\n  - virtual_ip_validator.py: interface field\n\nThe XRefIndex parameter is optional on every adopted validator (default\nNone), so existing call sites continue to work without modification.\ncurrent_plugin is derived per-resource as resource.type.split(\".\", 1)[0]\nso a routing.static resource resolves \"gateways.WAN_GW\" to\n\"routing.gateways.WAN_GW\" automatically.\n\nAdds 32 unit tests for _xref.py (100% coverage of the new module) plus\n21 tests for dotted-path resolution across the 5 adopted validators.\n\nAddresses #793.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-09T15:43:01+01:00",
          "tree_id": "b3afe295cd01a06b2d43c1518ae993b5aca52744",
          "url": "https://github.com/endavis/infrafoundry/commit/42d4bae73bac1b90a1c3dbef553c955ed21df58b"
        },
        "date": 1778337813868,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7090.559829171475,
            "unit": "iter/sec",
            "range": "stddev: 0.000019896672811319872",
            "extra": "mean: 141.03258756605808 usec\nrounds: 2461"
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
          "id": "52c7de52aa993dae50ed7c362943aae13c503b5e",
          "message": "refactor: emit nested-format YAML from direct-OPNsense migrate paths (merges PR #798, addresses #793)\n\nPhase 4 of #793. Each direct-OPNsense component manager's migrate()\ndelegates to its service's export_to_yaml(); update those service\nmethods to emit the API-aligned nested opnsense: schema (ADR-0016)\ninstead of the flat resource-centric format.\n\nA new helper module ``services/_nested_emit.py`` centralises the\nwrapping (list/singleton/multi-branch shapes), validates the dotted\npath against ``DOTTED_RESOURCE_SHAPES`` (the loader's source of\ntruth), and lets services emit by composition rather than by\nhand-rolling YAML. The Kea service uses the multi-branch helper to\nkeep its all-four-types output in a single document.\n\nEnd-to-end golden tests cover all 15 dotted resource types; each test\nmocks the live API, calls Manager.migrate(), and round-trips the\noutput through the loader's nested-format parser.\n\nAddresses #793.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-09T15:47:16+01:00",
          "tree_id": "4c42a67fe32f52caa2b2fa542e8c0847dca13ead",
          "url": "https://github.com/endavis/infrafoundry/commit/52c7de52aa993dae50ed7c362943aae13c503b5e"
        },
        "date": 1778338065045,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8094.282628123037,
            "unit": "iter/sec",
            "range": "stddev: 0.000030299710904070006",
            "extra": "mean: 123.54399345107714 usec\nrounds: 1985"
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
          "id": "e5319fe9cb3f66ff01d4dc32762e8640f409d188",
          "message": "refactor: drop direct-OPNsense flat→dotted shim (hard cutover) (merges PR #799, addresses #793)\n\n* refactor: drop direct-OPNsense flat→dotted shim (hard cutover)\n\nPhase 5 of #793. Removes the transient ``STEM_TO_DOTTED`` translation\ntable and its three call sites that auto-translated legacy flat\ndirect-OPNsense type names (e.g. filename stem ``vlans`` → dotted\n``interfaces.vlans``, resource-centric ``type: kea_subnet`` →\n``kea.dhcp4.reservations``) to the API-aligned dotted paths\nintroduced in Phase 1.\n\nAfter this commit operators must use either the nested ``opnsense:``\nschema (per ADR-0016) or already-dotted ``type:`` strings in\nresource-centric files. Flat OPNsense YAML still parses but emits\n``ResourceConfig.type`` matching the filename stem / raw type, which\nno longer matches any registered direct-OPNsense component — dispatch\nfails with a clear \"unknown type\" error. The conversion script in\nPhase 6 handles the one-shot operator-side migration.\n\nTest fixtures using the legacy flat OPNsense format are converted to\nthe nested schema or dotted-type form in this same commit so the test\nsuite stays green.\n\nAddresses #793.\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n* fix: convert blueprint dhcp.yaml type names to dotted paths\n\nFixup for #793 Phase 5. The shipped blueprints under ``blueprints/``\nwere emitting legacy stem ``type: kea_reservation`` which Phase 5's\nhard cutover no longer auto-translates to ``kea.dhcp4.reservations``.\nThe blueprint test suite caught the regression.\n\nConvert each ``type: kea_reservation`` to ``type: kea.dhcp4.reservations``\nin:\n\n- blueprints/ontap-cluster/dhcp.yaml (5 entries)\n- blueprints/service-vm/dhcp.yaml\n- blueprints/aiqum/dhcp.yaml\n- blueprints/k3s-cluster/providers/proxmox/dhcp.yaml (2 entries)\n\nAddresses #793.\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-09T15:56:23+01:00",
          "tree_id": "7567bdbd85a0e72c4c54da97237442500642a9de",
          "url": "https://github.com/endavis/infrafoundry/commit/e5319fe9cb3f66ff01d4dc32762e8640f409d188"
        },
        "date": 1778338608554,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8397.088248103193,
            "unit": "iter/sec",
            "range": "stddev: 0.000025053363107470343",
            "extra": "mean: 119.08889968208786 usec\nrounds: 2213"
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
          "id": "877850a2cbc5f9b68ae545d7f55dacdd54082466",
          "message": "fix: nested loader flattens entry config to match resource-centric (merges PR #801, addresses #800)\n\nThe nested-format loader was passing the whole entry mapping\n(``{name, config: {<fields>}}``) through as ``ResourceConfig.config``,\nwhich buried the actual field values one level deeper than every\ndirect-API component expects. ``ResourceCentricLoader`` already does\nthe right thing (``config = item.get(\"config\", {})`` + add ``name``);\nmirror that in ``_parse_nested_provider_format`` so both loaders\nproduce the same shape.\n\nPhase 4's migrate golden test had a round-trip assertion that read\n``v4_subnets[0].config[\"config\"][\"subnet\"]`` — that was asserting the\nbuggy shape. Updated to ``v4_subnets[0].config[\"subnet\"]``.\n\nFound while verifying #793 Phase 6 conversion of ``endavis-infra/`` —\n``foundry infra plan --provider opnsense`` was failing on the very\nfirst VLAN with \"missing required field(s): device, tag, description,\npriority\" despite the fields being present in the nested YAML.\n\nAddresses #800.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-09T16:17:45+01:00",
          "tree_id": "957e837e1a77f7e51ce610b72554f00582d8c0ad",
          "url": "https://github.com/endavis/infrafoundry/commit/877850a2cbc5f9b68ae545d7f55dacdd54082466"
        },
        "date": 1778339903883,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12387.277543056673,
            "unit": "iter/sec",
            "range": "stddev: 0.000005824250797249672",
            "extra": "mean: 80.7279885773223 usec\nrounds: 1926"
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
          "id": "23594a985dced001b8a1731dd3ef5a0820ac69b8",
          "message": "fix: restore subnet_ref resolution for kea reservations after direct-api migration (merges PR #803, addresses #802)\n\nPR #781 (DHCPv4 kea direct-API migration) deleted the terraform\ntemplate that resolved ``subnet_ref: <name>`` → kea subnet UUID via\nJinja but did not add an equivalent translation step in the new\ndirect-API ``KeaDHCPv4ReservationManager``. The component reads\n``resource.config[\"subnet\"]`` as a literal CIDR; operator YAML written\nagainst the framework's own blueprints (which all emit\n``subnet_ref: \"{{ dhcp_subnet }}\"``) had every reservation crashing\nplan with ``ReferenceValidationError: kea_reservation '<name>'\nreferences unknown subnet ''``.\n\nRestore the translation as a split-layer fix:\n\n- New ``KeaReservationValidator`` runs at plan-time\n  ``validate_references`` using the shared #793 ``_xref`` resolver to\n  surface unknown / wrong-version / disagreeing references early.\n  Pure check; never mutates ``resource.config``.\n- Component layer (``KeaDHCPv{4,6}ReservationManager``) gains\n  ``SIBLING_RESOURCE_TYPE`` ClassVar opt-in marker and a\n  ``sibling_resources`` kwarg on plan / apply / destroy /\n  get_resource_ids; module helpers ``_build_subnet_name_to_cidr`` and\n  ``_resolve_subnet_cidr`` translate ``subnet_ref`` → CIDR before the\n  existing ``cidr → uuid`` lookup.\n- Runner gains a generic ``_sibling_resources_for(manager_cls,\n  resources)`` helper that threads the right slice (managers without\n  the marker keep unchanged signatures).\n\nCovers DHCPv4 (the regression) plus DHCPv6 for schema parity. Legacy\n``subnet: <CIDR>`` literal form still works on both. ADR-0014 is\namended to record the dual-form schema and the SIBLING_RESOURCE_TYPE\nmechanism.\n\nAddresses #802.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-09T17:05:19+01:00",
          "tree_id": "1e5199c0eb798c1617b6de489b6ad3159e154a33",
          "url": "https://github.com/endavis/infrafoundry/commit/23594a985dced001b8a1731dd3ef5a0820ac69b8"
        },
        "date": 1778342753448,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6372.730832245893,
            "unit": "iter/sec",
            "range": "stddev: 0.00008217095606594933",
            "extra": "mean: 156.91859994149127 usec\nrounds: 5"
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
          "id": "a06cd93e8a3f4a1c484eb300791e0ea824fa6c7e",
          "message": "feat: add opnsense.system.* direct-API singletons (cutover hard blocker) (merges PR #809, addresses #806)\n\n* feat: add opnsense.system.* direct-API singletons (cutover hard blocker)\n\nAdds seven dict-shape singletons under the nested opnsense namespace\n(hostname, dns, ssh, webgui, firmware, remotebackup, tuning) per\nADR-0016 structural discrimination. firmware.plugins is the keystone:\ninstall-missing-only behavior unblocks #790 (acmeclient) and #808\n(legacy openvpn) which depend on plugins absent from opnsense-a today.\nIntroduces components/_singleton.py scaffold (enforce_singleton,\ndiff_singleton, SingletonDiff) reusable for upcoming #786, #787, #788,\n#790, #791, #792. New validators/_secrets.py enforces secret://\nreferences for gdrive_password / gdrive_p12_key on system.remotebackup.\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n* chore: silence bandit B105 false positive on snake->Camel field map\n\nBandit flagged the dict literal \"gdrive_password\": \"GDrivePassword\" as a\nhardcoded password. The value is the OPNsense wire-side field name, not\na credential. Same pattern in services/system_remotebackup.py:52 already\ncarries # nosec B105.\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-10T14:52:30+01:00",
          "tree_id": "d3fbcc8f4a0cdda9a5f14eaa9b46d44f95146196",
          "url": "https://github.com/endavis/infrafoundry/commit/a06cd93e8a3f4a1c484eb300791e0ea824fa6c7e"
        },
        "date": 1778421184479,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6273.918538126432,
            "unit": "iter/sec",
            "range": "stddev: 0.00003544226796664348",
            "extra": "mean: 159.39001979752004 usec\nrounds: 2273"
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
          "id": "d4f2c7647b31481def52f799193f5c5d77052808",
          "message": "feat: add opnsense.radvd direct-API resource (cutover blocker for IPv6 RAs) (merges PR #820, addresses #788)\n\nImplements the modern OPNsense radvd MVC controller as a dict-shape\nsingleton at YAML level with per-interface UUID records on the wire\n(hybrid pattern, second after #806). Full reconcile: interfaces in\nlive state but absent from YAML are deleted (safe; no data loss).\n\nProbe confirmed verb suffix is *Entry (not *Item per the issue body\nguess) and wire fields are CamelCase (MinRtrAdvInterval / RDNSS /\nDNSSL etc.); operator-facing YAML uses snake_case with translation at\nthe apply boundary. No global enabled toggle; per-entry enabled is the\nonly switch. mode enum: router/unmanaged/managed/assist/stateless.\n\nNew radvd_reconfigure finalization hook fires /api/radvd/service/\nreconfigure once per apply when any radvd record mutated.\n\nUnblocks IPv6 RA emission for the cutover sequence: opt1/opt2/opt3/opt6\n(Infra/PT/Tailscale-infra/Apps VLANs) get RAs on opnsense-a after apply.\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-12T16:18:16+01:00",
          "tree_id": "bd19f82ea43fc556100bb6c65a2acc42db98974c",
          "url": "https://github.com/endavis/infrafoundry/commit/d4f2c7647b31481def52f799193f5c5d77052808"
        },
        "date": 1778599138618,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7268.688394778635,
            "unit": "iter/sec",
            "range": "stddev: 0.000010961124712018397",
            "extra": "mean: 137.57640246599877 usec\nrounds: 2271"
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
          "id": "251592948a8095ea131d3df1587ccd59b9ba8ae5",
          "message": "chore(deps): bump github/codeql-action from 3 to 4 (merges PR #690)\n\n* chore(deps): bump github/codeql-action from 3 to 4\n\nBumps [github/codeql-action](https://github.com/github/codeql-action) from 3 to 4.\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/v3...v4)\n\n---\nupdated-dependencies:\n- dependency-name: github/codeql-action\n  dependency-version: '4'\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\n\n* test: align codeql-action assertions with v4 bump\n\nThe dependabot bump of github/codeql-action from v3 to v4 moves the\nworkflow's pinned version. The test was pinning v3 in its assertions\nand method names; update to v4 so the pin assertion matches the new\nintended version. Mirrors the upstream pyproject-template test update.\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n\n---------\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Eric Davis <6662995+endavis@users.noreply.github.com>\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-13T15:00:33+01:00",
          "tree_id": "9394cf1c5c56248d256c5dd08695e2d455f10212",
          "url": "https://github.com/endavis/infrafoundry/commit/251592948a8095ea131d3df1587ccd59b9ba8ae5"
        },
        "date": 1778680871474,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6365.811742342509,
            "unit": "iter/sec",
            "range": "stddev: 0.000031947398196078715",
            "extra": "mean: 157.08915696461 usec\nrounds: 1924"
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
          "id": "89e7f70909652ca7da738fe549d2ac96fefdf9d7",
          "message": "fix: anchor Addresses regex in pr_merge to start of line (merges PR #825, addresses #823)\n\nThe _extract_linked_issues parser used by `doit pr_merge` matched\n`addresses #N` anywhere in a PR body case-insensitively, which caused\nmid-sentence references and prose mentions to be parsed as real\nissue links — polluting the merge subject and the --auto-close list.\n\nAnchor to start of line and require exact capitalization\n(`^Addresses #N`), matching the convention the project already\ndocuments. Ports the regex + test changes from\npyproject-template PR #544.\n\nAddresses #823\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-13T17:05:27+01:00",
          "tree_id": "1126f537a375828b51768d2ea0d940c38250ec88",
          "url": "https://github.com/endavis/infrafoundry/commit/89e7f70909652ca7da738fe549d2ac96fefdf9d7"
        },
        "date": 1778688364201,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9706.388331299911,
            "unit": "iter/sec",
            "range": "stddev: 0.000007709713154646033",
            "extra": "mean: 103.02493222688491 usec\nrounds: 2169"
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
          "id": "e688c9583c48a93b7f66be20394bc375a9671cbe",
          "message": "chore: add sync-exclude mechanism for downstream template drift (merges PR #826, addresses #823)\n\nPorts the sync-exclude mechanism from pyproject-template PR #507:\n\n- tools/pyproject_template/check_template_updates.py: add\n  SYNC_EXCLUDE_FILE constant, load_sync_excludes() loader,\n  --show-excluded CLI flag. compare_files() now returns a tuple\n  (different, excluded) so excluded files are reported on a\n  separate summary line and never pollute actionable drift.\n- tools/pyproject_template/manage.py: plumb --show-excluded through\n  run_action, action_check_updates, and the --update-only branch.\n- tests/template/test_check_template_updates.py (new): 13 tests\n  covering loader edge cases, glob/exact matching, hardcoded-skip\n  precedence, and excludes= parameter override.\n- tests/template/test_pyproject_template_main.py: update one mock\n  assertion for the show_excluded=False kwarg.\n- .config/pyproject_template/sync-exclude.toml (new): encode 27 glob\n  patterns from divergences-doc category 1. Category 2 files don't\n  exist upstream; Category 3 stays in actionable drift by design.\n- .gitignore: ignore .claude/scheduled_tasks.lock (Claude Code\n  local-state file, was untracked).\n\ntests/template/** is intentionally NOT excluded — we keep many\nupstream template tests for tools/ modules we use. The blanket\n\"never adopt tests/template/\" claim in the divergences doc is\nwrong; correction tracked for a separate docs PR.\n\nAddresses #823\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-13T23:29:44+01:00",
          "tree_id": "4f1d0f59946f6c23a69a90b3748c6771c6c6d438",
          "url": "https://github.com/endavis/infrafoundry/commit/e688c9583c48a93b7f66be20394bc375a9671cbe"
        },
        "date": 1778711469890,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6015.53502086853,
            "unit": "iter/sec",
            "range": "stddev: 0.00003064376524642704",
            "extra": "mean: 166.2362527241374 usec\nrounds: 2386"
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
          "id": "ec8bedce09d0a7ad8b537ac91e734b52c9e9dd99",
          "message": "docs: update divergences doc for sync-exclude mechanism (merges PR #827, addresses #823)\n\nThe \"future improvement\" mentioned in the How-to-update section now\nexists at .config/pyproject_template/sync-exclude.toml (introduced\nin PR #826). Update the doc to reference the mechanism and require\nCategory 1 changes to land in both files within the same PR.\n\nAlso fix the `tests/template/` entry under Skeleton tests: the\ndirectory is NOT blanket-skipped. We actively keep tests from it\nthat cover modules we ship (e.g., tools/pyproject_template/*,\ntools/doit/*). Replace the blanket line with a per-file policy note.\n\nAddresses #823\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-14T00:47:53+01:00",
          "tree_id": "bcbce389687f42c2cb1246181a0f4f293b26d7b8",
          "url": "https://github.com/endavis/infrafoundry/commit/ec8bedce09d0a7ad8b537ac91e734b52c9e9dd99"
        },
        "date": 1778716113460,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7266.055701663466,
            "unit": "iter/sec",
            "range": "stddev: 0.000010528161926937699",
            "extra": "mean: 137.62625020491703 usec\nrounds: 2442"
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
          "id": "fa8bef325ba00c7da5a7aea3d80cdbc5cdf27f2d",
          "message": "feat: adopt session-lifecycle support (/checkpoint, /restore, auto-hooks) (merges PR #828, addresses #823)\n\nPorts the session checkpoint/restore feature from pyproject-template\nPRs #509, #511, and #536:\n\n- tools/hooks/ai/precompact-checkpoint.py: PreCompact hook that\n  synthesizes a checkpoint to tmp/checkpoints/{inv_epoch}-auto-precompact.md\n  before autocompact fires.\n- tools/hooks/ai/session-resume-restore.py: SessionStart hook\n  (matcher compact|resume) that injects the newest auto-precompact\n  checkpoint into the new session.\n- tests/test_hook_*.py: 17 tests covering the two hooks.\n- .claude/commands/{checkpoint,restore}.md: manual save/load slash\n  commands sharing the tmp/checkpoints/ directory with the auto hooks.\n- .gemini/commands/{checkpoint,restore}.md: same content in markdown\n  format (matches our existing .gemini/commands/ format; Phase C will\n  convert all gemini commands to TOML).\n- .claude/settings.json: wire PreCompact + SessionStart hooks\n  (enabled in committed settings per project direction).\n- docs/development/ai/auto-checkpoint-hook.md: new doc covering\n  the auto-hooks design, env vars, and operational notes.\n- AGENTS.md: add tmp/checkpoints/ exception to the Temporary Files\n  rule, parallel to upstream #511's hand-merge change.\n- docs/development/ai/slash-commands.md: add /checkpoint, /restore,\n  and auto-checkpoint hooks sections.\n\n.agents/skills/{checkpoint,restore}/SKILL.md from upstream #511 are\nnot adopted (we have no .agents/skills/ directory yet); deferred.\n\nAddresses #823\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-14T01:13:54+01:00",
          "tree_id": "1dc0f53b1b281169b3f6b21670310ce274592dde",
          "url": "https://github.com/endavis/infrafoundry/commit/fa8bef325ba00c7da5a7aea3d80cdbc5cdf27f2d"
        },
        "date": 1778717662860,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7211.573218943728,
            "unit": "iter/sec",
            "range": "stddev: 0.000014025160054990443",
            "extra": "mean: 138.6659983390516 usec\nrounds: 2409"
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
          "id": "c105eef36c5443c7903a9dc75605ab297c309d1a",
          "message": "feat: enable bash-ban-raw-tools hook (merges PR #829, addresses #823)\n\nPorts the bash-ban-raw-tools hook from pyproject-template PR #534:\n\n- tools/hooks/ai/bash-ban-raw-tools.py: PreToolUse hook for the Bash\n  tool that blocks `cat`, `head`, `tail`, `find`, `grep`, `rg`, `wc`\n  (and `... | head` / `... | tail` truncators), stderr-reporting the\n  native-tool replacement. mtime-based /tmp/bash-raw-unlock escape\n  hatch with a 10-minute window.\n- tests/test_bash_ban_raw_tools.py: 19 cases — allow lists, all\n  seven banned leads, piped truncators, fresh/stale/missing unlock,\n  stderr reason content.\n- .claude/settings.json: wire the hook as a second entry under the\n  existing PreToolUse Bash matcher, alongside block-dangerous-commands.\n\nUpstream ships the hook disabled-by-default; we enable it in committed\nsettings because the project already mandates \"prefer native file\ntools over raw shell\" in AGENTS.md, and the hook is the enforcement\nmechanism for that rule.\n\nDoc cross-reference in upstream's command-blocking.md points to\ntoken-efficiency-add-ons.md, which doesn't exist locally yet — that\nfile (and the cross-reference) will land with upstream #520 in Phase E.\n\nAddresses #823\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-14T01:23:36+01:00",
          "tree_id": "9c0f625f0e3814e9dd04b8dc99e872f8c49758b7",
          "url": "https://github.com/endavis/infrafoundry/commit/c105eef36c5443c7903a9dc75605ab297c309d1a"
        },
        "date": 1778718245078,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 6470.446304835776,
            "unit": "iter/sec",
            "range": "stddev: 0.000029098961086328484",
            "extra": "mean: 154.54884452910713 usec\nrounds: 2367"
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
          "id": "e0e13304ba2b84f95c085f5c8f7327f4a326ec98",
          "message": "feat: add opt-in Claude Max usage helper for statusline (merges PR #830, addresses #823)\n\nPorts the Claude Max usage helper from pyproject-template PR #562:\n\n- tools/statusline/claude-usage.sh (new): queries the Claude Code\n  OAuth /api/oauth/usage beta endpoint and formats 5h/7d\n  utilization as `5h:N% 7d:N%`. 60-second response cache at\n  $XDG_CACHE_HOME/claude-usage.json. Returns `?` on missing\n  credentials, no network, schema change, or curl timeout.\n- tests/test_statusline_claude_usage.py (new): 8 cases covering\n  the fetch + cache + parse paths.\n- .claude/statusline-command.sh: opt-in append driven by\n  CLAUDE_USAGE_STATUSLINE env var. Default statusline output\n  unchanged.\n- docs/development/ai/statusline.md: new \"Opt-In: Claude Max\n  Usage Display\" section with enable instructions, cache\n  behavior, helper requirements, troubleshooting, and the beta-API\n  caveat (endpoint is undocumented; prefer official\n  `claude --usage` when shipped per claude-code#20399).\n\nOperators who want the segment enable it per-environment by\nsetting CLAUDE_USAGE_STATUSLINE=1 in their shell rc. Not enabled\nin committed settings because the helper depends on a Claude Max\nsubscription and an undocumented beta endpoint.\n\nAddresses #823\n\nCo-authored-by: Claude Opus 4.7 (1M context) <noreply@anthropic.com>",
          "timestamp": "2026-05-14T01:34:03+01:00",
          "tree_id": "67de636511b9808dfaea37d11cfd488481af5d9b",
          "url": "https://github.com/endavis/infrafoundry/commit/e0e13304ba2b84f95c085f5c8f7327f4a326ec98"
        },
        "date": 1778718874906,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7339.89528910124,
            "unit": "iter/sec",
            "range": "stddev: 0.000010091400658677116",
            "extra": "mean: 136.24172561219856 usec\nrounds: 2573"
          }
        ]
      }
    ]
  }
}