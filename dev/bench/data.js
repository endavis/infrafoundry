window.BENCHMARK_DATA = {
  "lastUpdate": 1773240541123,
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
      }
    ]
  }
}