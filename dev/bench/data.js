window.BENCHMARK_DATA = {
  "lastUpdate": 1794409659535,
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
          "id": "502ec7f10fe658b238348150db3989cbe1903abb",
          "message": "chore: reformat test files that fail format and lint checks (merges PR #1306, addresses #1305)\n\n* chore: reformat test files that fail format and lint checks\n\nRun ruff format on 8 test files whose lines no longer fit the format and\nline-length rules. Formatting only.\n\nAddresses #1305\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* chore: retrigger ci after enabling actions\n\nEmpty commit: the PR was opened while Actions was disabled, so no\npull_request workflow ran.\n\nAddresses #1305\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-08T12:04:05Z",
          "tree_id": "2c5fe6d8fd2c3fc3a5f6544d7fa6d121b93b6722",
          "url": "https://github.com/endavis/infrafoundry/commit/502ec7f10fe658b238348150db3989cbe1903abb"
        },
        "date": 1794139493035,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7092.4362746477345,
            "unit": "iter/sec",
            "range": "stddev: 0.00002414798036294064",
            "extra": "mean: 140.99527458209948 usec\nrounds: 8136"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "cab40a033cfb04dec4902a1b8719983b540f3932",
          "message": "feat: make blueprint base tags and cloud-init snippets storage configurable (merges PR #1304, addresses #1303)\n\nAdd a base_tags input to the ontap-cluster and opnsense-vm blueprints,\ndefaulting to the tags each vm.yaml hardcoded; extra_tags still appends.\nAdd a cloud_init_snippets_storage input to aiqum, console-connector and\nservice-vm, emitted on the VM only when set so the template default still\napplies. With neither input set the rendered VM config is unchanged.\n\nAddresses #1303\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-08T12:18:25Z",
          "tree_id": "8507258af4aaa5e139fb92a48648b55fb58db3dc",
          "url": "https://github.com/endavis/infrafoundry/commit/cab40a033cfb04dec4902a1b8719983b540f3932"
        },
        "date": 1794140341322,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 14598.340504123635,
            "unit": "iter/sec",
            "range": "stddev: 0.000017535318201459103",
            "extra": "mean: 68.50093678233681 usec\nrounds: 15850"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "3692ad7c06ba107589c053a090d164408fd63322",
          "message": "refactor: give provider validators a shared validate(context) contract (merges PR #1308, addresses #1307)\n\n* refactor: add a shared validation context and validator protocol\n\nAdd ValidationContext and run_validators to core.validation and the\ngeneric SpecializedValidator protocol to core.protocols: every provider\nsub-validator will take one typed, frozen context object.\n\nAddresses #1307\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* refactor: remove the unused resource validator helper\n\nResourceValidator and BaseProviderValidator.validate_resource_exists\nhad no callers in the package. BaseProviderValidator itself stays: the\nAPI validators build on it.\n\nBREAKING CHANGE: ResourceValidator is no longer exported from\ninfrafoundry.core.validation_helpers, and\nBaseProviderValidator.validate_resource_exists is removed.\n\nAddresses #1307\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* refactor: move esxi validators to the shared validate(context) contract\n\nEach esxi sub-validator subclasses SpecializedValidator and takes a typed\ncontext; the provider validator builds the context and runs them with\nrun_validators in the existing order. Test changes are limited to how\nvalidate() is called.\n\nAddresses #1307\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* refactor: move kubernetes validators to the shared validate(context) contract\n\nEach kubernetes sub-validator subclasses SpecializedValidator and takes a typed\ncontext; the provider validator builds the context and runs them with\nrun_validators in the existing order. Test changes are limited to how\nvalidate() is called.\n\nAddresses #1307\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* refactor: move oci validators to the shared validate(context) contract\n\nEach oci sub-validator subclasses SpecializedValidator and takes a typed\ncontext; the provider validator builds the context and runs them with\nrun_validators in the existing order. Test changes are limited to how\nvalidate() is called.\n\nAddresses #1307\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* refactor: move opnsense validators to the shared validate(context) contract\n\nEach opnsense sub-validator subclasses SpecializedValidator and takes a typed\ncontext; the provider validator builds the context and runs them with\nrun_validators in the existing order. Test changes are limited to how\nvalidate() is called.\n\nAddresses #1307\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* refactor: move proxmox validators to the shared validate(context) contract\n\nEach proxmox sub-validator subclasses SpecializedValidator and takes a typed\ncontext; the provider validator builds the context and runs them with\nrun_validators in the existing order. Test changes are limited to how\nvalidate() is called.\n\nAddresses #1307\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* test: enforce the validator contract for every provider validator\n\nDiscover every class under providers/*/validators and assert it\nsubclasses SpecializedValidator with validate(self, context).\n\nAddresses #1307\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* docs: record the validator contract in an adr and the provider guide\n\nAddresses #1307\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-08T13:58:34Z",
          "tree_id": "f16908f0bde4b6af845dd76bf3ff3474c2580713",
          "url": "https://github.com/endavis/infrafoundry/commit/3692ad7c06ba107589c053a090d164408fd63322"
        },
        "date": 1794146354971,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 14648.611387971343,
            "unit": "iter/sec",
            "range": "stddev: 0.000017973601165972792",
            "extra": "mean: 68.26585629960438 usec\nrounds: 16263"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "3b1a3ef39af1e71f0d4a30714d7edaad801103b2",
          "message": "chore: tighten url and host assertions that code scanning flags (merges PR #1310, addresses #1309)\n\nCheck the exact URL host, CRD check name and rendered ingress host line\ninstead of a substring match.\n\nAddresses #1309\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-08T14:08:48Z",
          "tree_id": "b4842a77c6eb22466a8515f4608564a9967fa72d",
          "url": "https://github.com/endavis/infrafoundry/commit/3b1a3ef39af1e71f0d4a30714d7edaad801103b2"
        },
        "date": 1794146964139,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 14857.096896955089,
            "unit": "iter/sec",
            "range": "stddev: 0.000017774589042885767",
            "extra": "mean: 67.30790052294446 usec\nrounds: 16064"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c7c78735d0b72116745a26edf3c543f29be94490",
          "message": "fix: pass tailscale oauth client secret to the cloudinit module as auth_key (merges PR #1312, addresses #1311)\n\nThe tailscale/tailscale/cloudinit 0.0.11 module accepts client_id and\nclient_secret only together with id_token or audience, so OAuth mode\nfailed its precondition on every instance. OAuth mode now passes the\nclient secret as the module's auth_key and no longer renders client_id\nor client_secret.\n\n- OAuth mode requires a non-empty advertise_tags, since Tailscale\n  requires tags for OAuth-generated keys.\n- oauth.client_id_secret is optional and unused; it is still\n  type-checked when present and is no longer a terraform secret.\n- The OAuth provider tests that asserted the old module arguments now\n  assert the fixed output. New tests evaluate the module precondition\n  over the rendered block and check that no secret value lands in the\n  generated .tf files.\n\nAddresses #1311\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-08T14:29:01Z",
          "tree_id": "236701221b8e29bcdfa2253c0b4aadea41fa6fef",
          "url": "https://github.com/endavis/infrafoundry/commit/c7c78735d0b72116745a26edf3c543f29be94490"
        },
        "date": 1794148181811,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7845.568278975872,
            "unit": "iter/sec",
            "range": "stddev: 0.000009632106336161917",
            "extra": "mean: 127.46049291034096 usec\nrounds: 8322"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "acfc56b05d8636b0c0dea533499ecbaf278307f7",
          "message": "refactor: consolidate opnsense identity helpers into a shared module (merges PR #1313, addresses #908)\n\nThe description-suffix identity helpers were copied into the firewall\nrule, NAT rule and cron job services, and the marker probe regex into\ntheir three validators. They now live once in services/_identity.py:\n_IDENTITY_PATTERN, _IDENTITY_PROBE, OpnsenseDriftError, encode_identity,\nparse_identity, plus a new has_identity_marker() that the six guard\nsites call instead of the private probe regex.\n\n- parse_identity takes a keyword-only record_label so each service's\n  drift-error message keeps its exact text.\n- The services re-export OpnsenseDriftError, encode_identity and\n  parse_identity, so existing imports and tests are unchanged, and\n  OpnsenseDriftError is now a single class object.\n- New test_identity.py covers the shared contract and the type\n  identity across the three service modules.\n\nAddresses #908\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-08T14:45:27Z",
          "tree_id": "4ab4c5fc16ed730218c15fe62fde6e53c18dab96",
          "url": "https://github.com/endavis/infrafoundry/commit/acfc56b05d8636b0c0dea533499ecbaf278307f7"
        },
        "date": 1794149177165,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7806.870155089919,
            "unit": "iter/sec",
            "range": "stddev: 0.00001000253315565545",
            "extra": "mean: 128.09230589649562 usec\nrounds: 8310"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "925a25e623e2a33e668a22dc5750ad377b7aee7d",
          "message": "fix: register secret backend plugins before secret resolver lookups (merges PR #1315, addresses #1314)\n\nSecretResolver looked backends up in the plugin registry, but nothing\never discovered the secret_backend plugins declared under the\ninfrafoundry.secrets entry points, so every secret:// URI failed with\n\"No plugins of type 'secret_backend' are registered\".\n\nensure_secret_backends_registered() discovers the installed backends\nand registers the ones missing from the registry; _get_backend calls it\nbefore the lookup. It is idempotent and serialised by a lock, and it\nleaves backends a caller registered explicitly untouched.\n\nA regression test resolves secret://env_secrets/... through the real\nregistry with no patching.\n\nAddresses #1314\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-08T15:32:10Z",
          "tree_id": "77fb1ff4c57c93e5cec4a9f24b147844f4f47771",
          "url": "https://github.com/endavis/infrafoundry/commit/925a25e623e2a33e668a22dc5750ad377b7aee7d"
        },
        "date": 1794151974973,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12868.777075447735,
            "unit": "iter/sec",
            "range": "stddev: 0.000021048114311293117",
            "extra": "mean: 77.707461566639 usec\nrounds: 13660"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1fb362f249c59b48a55be106e11466d0f0d07fb1",
          "message": "feat: add system.users and system.groups direct-API resources for opnsense (merges PR #1316, addresses #805)\n\n* feat: add system.users and system.groups direct-API resources for OPNsense\n\nAdd list-shape opnsense.system.users and opnsense.system.groups with\nservices, managers, validators, endpoints and loader registration.\nGroup member_refs resolve to live uids through the sibling-resource\npattern. Secret fields must be secret:// references, and uid 0 is never\ndeleted. ADR-0014 and the resource coverage doc are updated, including\nthe write semantics still unverified against a live firewall.\n\nAddresses #805\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* fix: apply live-test findings to opnsense system users and groups\n\nA live plan/apply against a test firewall showed that the API never\nreturns a user's password and that the box assigns uid and gid itself,\nso every plan showed an update and every apply re-sent the password.\n\n- password is a secret:// URI holding the plaintext; the box hashes it.\n  It is written on add only, or on update when update_password: true is\n  set, and never compared. A bcrypt-looking value is rejected.\n- uid and gid are rejected by the validator as box-assigned and are no\n  longer written or compared. The uid 0 guard keys off the live uid.\n- Users take description (wire descr), matching groups.\n- The validator reports unknown keys at validation time.\n- The uid 0 warning is logged only when a delete was otherwise planned.\n- ADR-0014 and the coverage doc record the measured behaviour.\n\nAddresses #805\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-08T15:46:46Z",
          "tree_id": "473236570f0536a538858a7541c33776fbf8a026",
          "url": "https://github.com/endavis/infrafoundry/commit/1fb362f249c59b48a55be106e11466d0f0d07fb1"
        },
        "date": 1794152852428,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9449.999872408516,
            "unit": "iter/sec",
            "range": "stddev: 0.000014327408592809188",
            "extra": "mean: 105.82010724886186 usec\nrounds: 10443"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "04da5346a63940dbdabac29da73c087b9d09c315",
          "message": "feat: add trust.cas and trust.certs direct-API resources for opnsense (merges PR #1317, addresses #807)\n\n* feat: add trust.cas and trust.certs direct-API resources for opnsense\n\nManage the OPNsense Trust System CAs and certificates as list-shape\ndirect-API types. Identity is the live descr; secrets resolve from\nsecret:// URIs in the managers only. Certs resolve ca_ref to the CA\nrefid through the sibling-resource pattern (ca_refids_by_name is\nreusable). Rows in use, and CAs that look ACME-issued, are never\ndeleted. Amends ADR-0014 and ADR-0018 and the coverage doc.\n\nAddresses #807\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* docs: record live-test results for opnsense trust cas and certs\n\nA live plan and apply on a test firewall, with a throwaway CA and\ncertificate that were removed afterwards, verified the import action\nvalues, caref linking, idempotent re-plans, in-place re-import of a\nchanged crt on set, and cert-before-CA deletes. The box ignores\ncert_type on import; the stored type follows the certificate.\n\nAlso fix the coverage doc's YAML example: entry fields go under\nconfig:, which the nested loader requires.\n\nAddresses #807\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-08T15:58:58Z",
          "tree_id": "ab0eb707c7fbeb917499387904f1b36b5da8e24d",
          "url": "https://github.com/endavis/infrafoundry/commit/04da5346a63940dbdabac29da73c087b9d09c315"
        },
        "date": 1794153576945,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12196.149637215416,
            "unit": "iter/sec",
            "range": "stddev: 0.000024865465173524635",
            "extra": "mean: 81.99309042163546 usec\nrounds: 13614"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "b8ab0ea5d3b99d5e0c3b622f88b3870e572eeac8",
          "message": "feat: add openvpn.instances client resource for opnsense direct-API (merges PR #1318, addresses #808)\n\n* feat: add openvpn.instances client resource for opnsense direct-API\n\nManage OpenVPN client instances on the modern MVC API\n(openvpn/instances/*) as a list-shape openvpn.instances type, identified\nby description. ca_ref resolves to a trust.cas refid; username and\npassword are secret:// URIs, the password is write-only and sent on\nupdate only with update_password. Server instances are never matched or\ndeleted. The legacy os-openvpn-legacy surface has no REST API and stays\nunmanaged; ADR-0013/0014/0018 and the coverage doc record that cutover\nrecreates the client on the modern API.\n\nAddresses #808\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* fix: apply live-test findings to opnsense openvpn instances\n\nA live plan and apply on a test firewall, with a throwaway disabled\nclient and CA that were removed afterwards, found two problems:\n\n- Every config failed to parse: the nested loader copies the entry\n  name into config, and name was not an allowed key. It is now, with a\n  regression test that parses through the real loader.\n- add was rejected with \"instance.vpnid: A value is required\". vpnid is\n  now an optional YAML integer: when set it is written and compared,\n  when omitted add allocates max(live and explicit ids) + 1, and update\n  payloads always carry one. The validator rejects duplicates.\n\nThe docs now record the measured behaviour: set keeps omitted fields,\nre-plans are idempotent, the password reads back but is not compared,\nand deletes run instance, certificates, CAs.\n\nAddresses #808\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-08T16:48:50Z",
          "tree_id": "143964d1be5f8ed1f1b0d34df90b8ffca348ead8",
          "url": "https://github.com/endavis/infrafoundry/commit/b8ab0ea5d3b99d5e0c3b622f88b3870e572eeac8"
        },
        "date": 1794156578321,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7594.773795916368,
            "unit": "iter/sec",
            "range": "stddev: 0.000012253201604903703",
            "extra": "mean: 131.66949100415468 usec\nrounds: 8226"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6312a1a890ba7492fdc1733276b288135768370f",
          "message": "feat: add syslog.settings direct-API singleton for opnsense (merges PR #1323, addresses #804)\n\n* feat: add syslog.settings direct-API singleton for opnsense\n\nManage the general section of the OPNsense syslog settings (enabled,\nlog_local, max_preserve, max_file_size) as the dict singleton\nopnsense.syslog.settings. Sparse comparison, whole live section echoed\non write, destroy is a no-op, and a syslog_reconfigure finalization\nhook reconfigures the service once per apply. Remote destinations stay\nout of scope.\n\nAddresses #804\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* docs: record live verification of syslog.settings set and reconfigure\n\nApplied a max_preserve change on a test firewall and restored it. The set\ncall with the syslog envelope and syslog/service/reconfigure both worked,\nthe destinations list was left alone, and a re-plan showed no update.\n\nAddresses #804\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-08T18:10:29Z",
          "tree_id": "1b8bc403b17a35cf359783ad2a6649ea0f346b18",
          "url": "https://github.com/endavis/infrafoundry/commit/6312a1a890ba7492fdc1733276b288135768370f"
        },
        "date": 1794161477995,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7578.276066590207,
            "unit": "iter/sec",
            "range": "stddev: 0.00001846050252987994",
            "extra": "mean: 131.95613239911214 usec\nrounds: 8278"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2e7be21e8ec4f11aa9bb378db6fe8c395a5cd9b1",
          "message": "feat: add unbound.settings direct-API singleton for opnsense (merges PR #1324, addresses #1091)\n\n* feat: add unbound.settings resource for opnsense unbound general and advanced settings\n\nAdd a direct-API singleton covering the Unbound general and advanced\nsettings. The three advanced fields owned by unbound.advanced are\nrejected here, so the two types never write the same field. Includes\nvalidator, config migrate extractor, docs and ADR-0014 amendment.\n\nAddresses #1091\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* docs: record live verification of unbound.settings set and reconfigure\n\nToggled an advanced field on a test firewall and restored it. The set call\nwith the unbound envelope and unbound/service/reconfigure both worked, and a\nre-plan showed no update. The same envelope is what unbound.advanced writes,\nso its unverified note is updated too.\n\nAddresses #1091\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-08T18:18:44Z",
          "tree_id": "9244004ec2138a341fd391706db188328d2d68c8",
          "url": "https://github.com/endavis/infrafoundry/commit/2e7be21e8ec4f11aa9bb378db6fe8c395a5cd9b1"
        },
        "date": 1794161964983,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 15705.36874778418,
            "unit": "iter/sec",
            "range": "stddev: 0.00001599862429175935",
            "extra": "mean: 63.67249416802689 usec\nrounds: 16804"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "078bb284df51930353dc2efa427556111c345957",
          "message": "feat: add hostdiscovery direct-API singleton for opnsense (merges PR #1325, addresses #792)\n\n* feat: add hostdiscovery direct-API singleton for opnsense\n\nAdd opnsense.hostdiscovery (renamed from the proposed hostwatch to match the\n/api/hostdiscovery/ wire API): enabled, promisc, verbose, skip_nets,\ninterface, expire4_interval and expire6_interval, with a validator,\nreconfigure finalization hook, extractor, docs and ADR-0014/0016 updates.\n\nAddresses #792\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* fix: accept deletes_only in HostDiscoveryManager.apply\n\nHostDiscoveryManager sets SPLIT_DELETE_PHASE, so the direct runner calls\napply() with deletes_only. The method did not accept it, and a live apply\nfailed with a TypeError before writing anything. The delete phase is now a\nno-op that neither reads nor writes the box.\n\nA registry-wide test checks that every SPLIT_DELETE_PHASE manager's apply()\ntakes deletes_only, so this mismatch is caught in unit tests.\n\nAddresses #792\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* docs: record live verification of hostdiscovery set and reconfigure\n\nOn a test firewall, config migrate output planned with no update, and a\nverbose change went through set and reconfigure, re-planned clean, and was\nrestored. The wire field names are confirmed by the same run.\n\nAddresses #792\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-08T18:28:56Z",
          "tree_id": "a96eda1b058c1e79c8c64ceb7557090b9c129e1c",
          "url": "https://github.com/endavis/infrafoundry/commit/078bb284df51930353dc2efa427556111c345957"
        },
        "date": 1794162573531,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7843.513397102886,
            "unit": "iter/sec",
            "range": "stddev: 0.000008283177652925946",
            "extra": "mean: 127.49388563157989 usec\nrounds: 8289"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "36b2fd9774291042f21a32141cad86bd7248d706",
          "message": "chore: record live login verification for opnsense system.users (merges PR #1326, addresses #1322)\n\nOn a test firewall, a throwaway user with the dashboard privilege and a\nsecret:// password could log in to the web GUI, and a wrong password was\nrejected. After a rotation with update_password, the new password logged in\nand the old one was rejected. The user was then removed and the box returned\nto its starting state.\n\nRecorded in the system.users section of ADR-0014 and in the coverage doc.\n\nAddresses #1322\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-09T10:16:41Z",
          "tree_id": "3e32d36b049445145c3c98c33c5ee7a549500d3f",
          "url": "https://github.com/endavis/infrafoundry/commit/36b2fd9774291042f21a32141cad86bd7248d706"
        },
        "date": 1794219442683,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12823.412321875385,
            "unit": "iter/sec",
            "range": "stddev: 0.000022028556335205256",
            "extra": "mean: 77.98236342241806 usec\nrounds: 14446"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "7937f3cfa1269ad284d30dbd10c4085995287274",
          "message": "fix: add migrate for opnsense syslog.settings so config migrate works (merges PR #1330, addresses #1328)\n\nfix: add migrate to opnsense syslog.settings manager\n\nSyslogSettingsManager had no migrate(), so config migrate for\nsyslog.settings crashed with AttributeError. Add it, following\nUnboundSettingsManager, exporting the general settings as\nopnsense.syslog.settings YAML. Add extractor round-trip tests and a\nguard that every registered OPNsense extractor manager has migrate.\n\nAddresses #1328\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-09T12:09:03Z",
          "tree_id": "fb8899892d0d848d8e2a082ea06f14cbd0758958",
          "url": "https://github.com/endavis/infrafoundry/commit/7937f3cfa1269ad284d30dbd10c4085995287274"
        },
        "date": 1794226187665,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 10582.96644561185,
            "unit": "iter/sec",
            "range": "stddev: 0.000004691968953184645",
            "extra": "mean: 94.49146467006354 usec\nrounds: 11152"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ae602128a1f7b370cf5ec41d4fd34bfb68f0905a",
          "message": "feat: add a disk_size option to the opnsense-vm blueprint (merges PR #1331, addresses #1329)\n\nAdd an optional disk_size (GiB) to the opnsense-vm blueprint, passed to the\nProxmox provider as a disk_size VM field for disk-image VMs.\n\n- ova_vms.tf.j2: disk_size joins triggers_replace; after the image is imported\n  and before first boot, qm resize runs only when disk_size is larger than the\n  image's virtual size (qemu-img info), otherwise a skip is logged. The\n  \"at least the image size\" check lives at apply time, not in the validator,\n  by decision: the validator cannot know the remote image's size.\n- VMConfigValidator: disk_size must be a positive integer; a warning is given\n  when it is set on a VM without disk_image_source.\n- Blueprint: disk_size input (default 0 keeps the image size); the bootstrap\n  expect script runs an idempotent gpart recover/resize + growfs step only\n  when disk_size is set, never failing the bootstrap.\n- Without disk_size the generated Terraform is byte-for-byte unchanged\n  (pinned by a digest test).\n\nUnverified: whether the nano image grows its root filesystem on first boot by\nitself, and the bootstrap grow step, are untested until a live rebuild.\n\nAddresses #1329\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-09T12:15:16Z",
          "tree_id": "e0382d528e72f9f79cdda2bf74eee25f2802f7c3",
          "url": "https://github.com/endavis/infrafoundry/commit/ae602128a1f7b370cf5ec41d4fd34bfb68f0905a"
        },
        "date": 1794226563111,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12683.529272295224,
            "unit": "iter/sec",
            "range": "stddev: 0.00002620655708557622",
            "extra": "mean: 78.84240880685404 usec\nrounds: 13762"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "d3db672bbd19d060b40f95421bb0c218db4590e8",
          "message": "fix: let the opnsense-vm bootstrap open the api on the lan address (merges PR #1334, addresses #1332)\n\nA fresh box only passes TCP 443 to its WAN address, so an environment whose\napi_url is the LAN address cannot reach it after a rebuild until the declared\nrules are restored through that same API.\n\nAdd an opt-in api_allow_lan blueprint input (default false). When set, the\nbootstrap adds a second WAN pass rule from api_allow_cidr to the LAN address.\nThe README documents the input and the WAN-address override for boxes built\nwithout it.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-09T12:41:02Z",
          "tree_id": "f542d4397f4c7166506c787527016cde411f531b",
          "url": "https://github.com/endavis/infrafoundry/commit/d3db672bbd19d060b40f95421bb0c218db4590e8"
        },
        "date": 1794228102037,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 11194.884813534318,
            "unit": "iter/sec",
            "range": "stddev: 0.000005565002023639638",
            "extra": "mean: 89.3265108713782 usec\nrounds: 12326"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "d808d7d8b68444740aa790af73a58540943deade",
          "message": "feat: add acmeclient direct-api resources for the opnsense acme client plugin (merges PR #1335, addresses #790)\n\nAdd five direct-API types for os-acme-client: acmeclient.settings (singleton)\nand acmeclient.accounts, .validations, .actions and .certs (lists). The four\nlists share one table-driven engine, delete only managed rows, and have\nconfig migrate extractors. Certs reference accounts, validations and actions\nby handle; the runner now accepts a tuple SIBLING_RESOURCE_TYPE so one manager\ncan resolve several sibling types. One acmeclient_reconfigure hook fires per\napply.\n\nThe renewal cron job is plugin-managed: UpdateCron is never diffed, and a\nsettings apply with the plugin and auto-renewal on calls fetchCronIntegration.\nDNS credential fields pass through verbatim as secret:// URIs; the validator\nrejects another provider's fields and requires dns_cf_token for dns_cf.\nPlugin endpoints are a new EndpointKind.PLUGIN, exempt from the core spec\ncheck. Apply never registers accounts or signs certificates.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-09T13:22:54Z",
          "tree_id": "e35236542fc62da6d6088006a535de20994a6742",
          "url": "https://github.com/endavis/infrafoundry/commit/d808d7d8b68444740aa790af73a58540943deade"
        },
        "date": 1794230615728,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7690.6307593084375,
            "unit": "iter/sec",
            "range": "stddev: 0.00001843843192026428",
            "extra": "mean: 130.02834634722765 usec\nrounds: 8350"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "d55ab32fc4bd24e690dbe059c9c94a771ad2cff3",
          "message": "fix: read hidden opnsense outbound nat rules and manage the snat mode (merges PR #1336, addresses #1333)\n\nOn OPNsense 26.1, firewall/source_nat/searchRule omits manual outbound rules\nwhile the outbound NAT mode is automatic or disabled. InfraFoundry saw every\ndeclared outbound rule as absent and added it again on each apply.\n\nThe outbound read now checks the mode first and, when the search would hide\nmanual rules, reads them from the model (firewall/source_nat/get). Hybrid,\nadvanced and pre-26.1 boxes keep the search, which carries raw port ranges.\n\nAdd a firewall.source_nat singleton with snat_mode, applied before\nfirewall.nat through a source_nat_apply finalization hook, with a validator\nand a config migrate extractor. It fails clearly on boxes without the 26.1\nmodel field. Plan warns when enabled outbound rules are declared and the\neffective mode leaves them inert. NAT rule add and update now raise on a\nfailed write.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-09T14:15:38Z",
          "tree_id": "654c911f6dcbe5f750d4e01edb4f5fd6f2f61c04",
          "url": "https://github.com/endavis/infrafoundry/commit/d55ab32fc4bd24e690dbe059c9c94a771ad2cff3"
        },
        "date": 1794233777471,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 15730.331779186672,
            "unit": "iter/sec",
            "range": "stddev: 0.00001536188187967614",
            "extra": "mean: 63.571449988304344 usec\nrounds: 16876"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "d0311da3490eab47e965b547bc928e1aa19113b3",
          "message": "fix: keep migrated opnsense names clear of names already in the env (merges PR #1338, addresses #1337)\n\nconfig migrate for the acmeclient list types derived handles from the live\nrows and de-duplicated them only within one type, but resource names must be\nunique across the whole opnsense provider. A certificate CN slug could match\nan unbound host override name, and the env then failed to load.\n\nThe four acmeclient migrates now share one handle assignment over all four\ntypes, in dependency order. A row whose identity already has an entry of its\nown type in the env keeps that entry's name, so re-running migrate and\nhand-renamed handles are stable and certificate references follow them. Every\nother row gets a slug that skips all opnsense names in the env, suffixed -2,\n-3 and so on. Host override migrate, which synthesizes names in the same\nslug space, reserves the other types' names the same way and also\nde-duplicates within its own type.\n\nA duplicate resource name now raises DuplicateResourceNameError (a\nconfiguration error, IF-CONFIG-002, still a ValueError) and names each\nlocation's resource type, instead of surfacing as IF-GENERAL-001.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-09T14:53:57Z",
          "tree_id": "6e2af3d350ab8227e931ebb3608923bc976a478e",
          "url": "https://github.com/endavis/infrafoundry/commit/d0311da3490eab47e965b547bc928e1aa19113b3"
        },
        "date": 1794236080794,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 10261.632344353933,
            "unit": "iter/sec",
            "range": "stddev: 0.000011056042951928009",
            "extra": "mean: 97.45038278926562 usec\nrounds: 11121"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "69024f41746de30f3255bbcc11af15fbb0a5ca93",
          "message": "fix: keep one live copy of duplicate managed opnsense nat rules and delete the rest (merges PR #1341, addresses #1339)\n\n_compute_diff_for_kind keyed live rows by managed name in a dict, so when\nseveral rows carried the same InfraFoundry tag only the last was compared,\nupdated or deleted. The others stayed on the box unreported.\n\nThe diff now groups live rows per name, keeps the first copy whose fields\nmatch the desired rule (else the first copy) and plans the other copies as\ndeletes. add_only and locked rules leave the extra copies alone and warn.\nDuplicate deletes of a still-desired rule get a uuid-based outcome name so\nthe kept rule's on_destroy handlers do not fire, and destroy now removes\nevery copy.\n\nAddresses #1339\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-09T15:11:14Z",
          "tree_id": "6d9823d02febbc4b8686a572f0003329ab501e30",
          "url": "https://github.com/endavis/infrafoundry/commit/69024f41746de30f3255bbcc11af15fbb0a5ca93"
        },
        "date": 1794237119552,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9929.68447104992,
            "unit": "iter/sec",
            "range": "stddev: 0.000015859444974488952",
            "extra": "mean: 100.70813457522326 usec\nrounds: 10522"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "021ba2fe6a6ebfb8d65a09d89091fbe4d21fd470",
          "message": "fix: keep migrated kea dhcp names unique, non-empty and clear of env names (merges PR #1342, addresses #1340)\n\n* fix: keep migrated kea dhcp names unique, non-empty and clear of env names\n\nKea config migrate synthesized names from description and hostname without\nchecking them, so empty slugs and same-type collisions were emitted as is.\nNames are now assigned across all four kea types with the #1338 helpers:\nnames reserved by other opnsense types are avoided, collisions get -2, -3\nsuffixes, empty slugs fall back to the identity or an indexed name, and\nentries already in the env keep their names on a re-run.\n\nAddresses #1340\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* fix: match kea reservations by mac or duid and ip when migrating names\n\nKea allows one MAC (or DUID) to be reserved in several subnets, one\nreservation per subnet with its own IP. Pinning existing names by MAC alone\nkept only the first live reservation's name and renamed the others on every\nre-run of config migrate. The identity is now the (MAC, IP) pair for DHCPv4\nand the (DUID, IP) pair for DHCPv6, falling back to the MAC or DUID alone when\neither side has no IP.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-09T15:20:07Z",
          "tree_id": "0c2875e2777a0d90a1ee246fb7b7bfbf54db0e56",
          "url": "https://github.com/endavis/infrafoundry/commit/021ba2fe6a6ebfb8d65a09d89091fbe4d21fd470"
        },
        "date": 1794237650042,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7546.613790101841,
            "unit": "iter/sec",
            "range": "stddev: 0.00001915070759718376",
            "extra": "mean: 132.50976236674555 usec\nrounds: 8349"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "4a9d3defd413ae315be9c2a383c2c2787708d139",
          "message": "refactor: resolve virtual ip secrets through the shared opnsense helper (merges PR #1343, addresses #1321)\n\nVirtualIPManager._resolve_and_parse now calls\n_secrets.resolve_resource_secrets instead of carrying its own copy of the\nenv-secrets loading and SecretResolver setup. The virtual IP tests patch\nthe ConfigManager the helper uses; no assertion changed.\n\nNo other direct-API manager had an inline copy.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-09T15:32:04Z",
          "tree_id": "d3b4ef11777f774c5201708f58c46aa22e35b172",
          "url": "https://github.com/endavis/infrafoundry/commit/4a9d3defd413ae315be9c2a383c2c2787708d139"
        },
        "date": 1794238375612,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 15855.221087877495,
            "unit": "iter/sec",
            "range": "stddev: 0.00001971532874353035",
            "extra": "mean: 63.07070676955586 usec\nrounds: 17106"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "285b44237c273050098bfefe083af7322438eb9e",
          "message": "feat: support a client cert_ref on opnsense openvpn.instances (merges PR #1344, addresses #1320)\n\nopenvpn.instances gains an optional cert_ref naming a trust.certs\nresource. It resolves to the live certificate refid through the new\ncert_refids_by_name (which shares its lookup with ca_refids_by_name) and\nis sent as the wire cert. Omitted, cert is neither sent nor compared, and\nthe trust.certs search runs only when an instance sets cert_ref.\n\nA pending certificate is an add plus a warning at plan; an unresolved\ncert_ref at apply raises before any write. The validator requires\ncert_ref to name a declared trust.certs entry. The manager declares the\ntuple SIBLING_RESOURCE_TYPE (\"trust.cas\", \"trust.certs\"); the runner\nalready accepted a tuple, so it is unchanged. Dependencies and the\nendpoint registry list trust.certs and trust/cert/search.\n\nVerified live on a test firewall; ADR-0014 and the coverage doc record\nthe results.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-10T09:54:38Z",
          "tree_id": "d4fe537e90d3c16a7693af330fbab1f9563a72d8",
          "url": "https://github.com/endavis/infrafoundry/commit/285b44237c273050098bfefe083af7322438eb9e"
        },
        "date": 1794304517415,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7789.973821513324,
            "unit": "iter/sec",
            "range": "stddev: 0.00000921138901553702",
            "extra": "mean: 128.3701361406802 usec\nrounds: 8359"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ad00509415329ee276a6094bb2de13d58446d2b2",
          "message": "feat: add openvpn.static_keys and tls_key_ref for opnsense openvpn instances (merges PR #1345, addresses #1319)\n\nAdd a list-shape, managed-set direct-API type opnsense.openvpn.static_keys\nover openvpn/instances/*StaticKey. Identity is the description; mode\n(auth, crypt, crypt-v2) is required; key must be a secret:// URI and is\nnever logged, put in an error or shown in a repr. key is compared on its\nBEGIN..END block only, so the '#' header genKey writes causes no drift,\nand only when the box returns it; update_key forces a re-send otherwise.\nA managed key that a live instance still references is kept with a\nwarning. Static keys share the openvpn_reconfigure hook.\n\nopenvpn.instances gains an optional tls_key_ref, resolved to the static\nkey's uuid and sent as tls_key; omitted, tls_key is neither sent nor\ncompared. Static keys apply before instances, and instances delete first.\n\nVerified live on a test firewall; ADR-0014, ADR-0018 and the coverage doc\nrecord the results.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-10T10:21:28Z",
          "tree_id": "f864291000bde0a7269d9e8eb41aa3c65a962d74",
          "url": "https://github.com/endavis/infrafoundry/commit/ad00509415329ee276a6094bb2de13d58446d2b2"
        },
        "date": 1794306126946,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 15638.33571935314,
            "unit": "iter/sec",
            "range": "stddev: 0.00001688060659838726",
            "extra": "mean: 63.94542347383266 usec\nrounds: 17151"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "db71ee4959e0f35c6bf22539df27d0fccbdac18f",
          "message": "feat: manage opnsense firewall categories (merges PR #1346, addresses #1286)\n\nAdd firewall.categories, a list-shape, managed-set direct-API type over\nfirewall/category/*Item, with a validator, a config migrate extractor and\ndocs. Identity is the wire name (config.name, default the resource name);\nauto and color are compared, color without '#' and lowercase, which is\nhow the box stores it.\n\nThe provider's own infrafoundry marker category is dropped from every\ndiff, export and resource-id lookup, so it is never deleted or reported,\nand a resource may not use that name.\n\nRules and aliases reference categories by uuid, so only delete order\nmatters: the type is registered after rules, NAT and aliases and deletes\nafter them without a split phase. A category the box reports in use\n(HTTP 500, errorTitle \"... in use by:\") is kept with a warning, stays\nmanaged and is retried; any other delete failure raises.\n\nVerified live on a test firewall; ADR-0014, ADR-0018 and the coverage\ndoc record the results.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-10T10:58:24Z",
          "tree_id": "a3d8a846dc55b36c143b868b715b2f06ba046095",
          "url": "https://github.com/endavis/infrafoundry/commit/db71ee4959e0f35c6bf22539df27d0fccbdac18f"
        },
        "date": 1794308342457,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12672.186250532633,
            "unit": "iter/sec",
            "range": "stddev: 0.000022002043448293524",
            "extra": "mean: 78.91298156685224 usec\nrounds: 13888"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "05fc2438a836b0203ff54c99b0871d8cda205edb",
          "message": "feat: manage the opnsense os-tailscale plugin (settings, auth, subnets) (merges PR #1347, addresses #787)\n\nAdd three direct-API types for the os-tailscale plugin, all plugin-kind\nendpoints under tailscale/*:\n\n- tailscale.settings: singleton; snake_case YAML mapped to the wire, only\n  declared fields compared, enable_snat inverting disableSNAT. The write\n  drops the nested subnets node so the subnet list is never clobbered;\n  use_exit_node is checked against the live offers.\n- tailscale.auth: singleton; pre_auth_key must be a secret:// URI (a literal\n  is a validator error). The live key is echoed by the box and compared;\n  update_pre_auth_key forces a re-send. The write never echoes the live key,\n  and the key is never logged, raised or shown (plan shows [REDACTED]).\n- tailscale.subnets: managed-set list keyed by the normalized CIDR, with\n  description compared; IPv4 and IPv6 share the subnet4 envelope.\n\nThe three share a tailscale_reconfigure finalization hook, run after\nsystem.firmware, tolerate a missing plugin at plan with a warning, and\nhave config migrate extractors (auth writes only a secret placeholder).\n\nVerified live on a test firewall with the plugin installed for the test,\nTailscale disabled and a throwaway key; ADR-0014, ADR-0018 and the\ncoverage doc record the results.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-10T11:34:51Z",
          "tree_id": "7af43e93fadbe79bac849159abc7dbfbc32635d4",
          "url": "https://github.com/endavis/infrafoundry/commit/05fc2438a836b0203ff54c99b0871d8cda205edb"
        },
        "date": 1794310532585,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 14835.818872103622,
            "unit": "iter/sec",
            "range": "stddev: 0.000022740625585907413",
            "extra": "mean: 67.40443575247065 usec\nrounds: 16273"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "5967285fc44491ddb82dc3d017ff1c6193dd0855",
          "message": "feat: add tailscale control-plane provider wrapping the official terraform provider (merges PR #1348, addresses #870)\n\nAdd a `tailscale` provider that generates Terraform for the official\ntailscale/tailscale provider (pinned ~> 0.29.3) and manages a tailnet's\ncontrol plane: acl, tailnet_key, device_subnet_routes, device_tags,\ndns_nameservers, dns_preferences and dns_search_paths.\n\n- Credentials (OAuth client or API key) come from\n  provider_settings.tailscale; secret:// URIs are resolved and reach\n  Terraform only as sensitive TF_VAR_* variables, never in .tf files.\n  build_terraform_env_vars gains a keyword-only resolve_secret_uris flag.\n- acl takes a structured `policy` or verbatim `hujson`, imports with\n  `import_id: acl`; overwrite and reset-on-destroy are opt-in.\n- tailnet_key exposes the key as a sensitive output; under OAuth a key\n  without tags is an error, a tag missing from tagOwners a warning.\n- device_subnet_routes and device_tags look a device up by hostname or\n  name (data source, node_id) or take a raw device_id.\n- Validators for naming, ACL, keys, device references, DNS and\n  credentials; ADR-0020 and a provider guide.\n\nLive-tested on a throwaway tailnet: every type applied, re-planned clean\nand destroyed; a test firewall joined with a minted key through the\nopnsense.tailscale types and its route was approved.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-10T12:27:32Z",
          "tree_id": "3a647caa9fd9724dc759b257d18d7fb8306b81d8",
          "url": "https://github.com/endavis/infrafoundry/commit/5967285fc44491ddb82dc3d017ff1c6193dd0855"
        },
        "date": 1794313695375,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7743.673116738691,
            "unit": "iter/sec",
            "range": "stddev: 0.000009499361289255129",
            "extra": "mean: 129.13768245697307 usec\nrounds: 8254"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "88ce6855d253134bd6786961038ed62428f3eff6",
          "message": "fix: let tailscale device_tags opt out of clearing tags on destroy (merges PR #1350, addresses #1349)\n\nA node that joined with a tagged auth key cannot be untagged: the\nTailscale API answers \"tagged nodes cannot be untagged without reauth\n(400)\", so `infra destroy -P tailscale` stopped at tailscale_device_tags.\n\ndevice_tags now accepts an opt-in `keep_tags_on_destroy: true`. Destroy\nthen removes that resource from Terraform state before `terraform\ndestroy`, so the device keeps its tags and the destroy completes.\nWithout the field nothing changes.\n\n- ProviderBase.get_state_addresses_kept_on_destroy: additive hook,\n  default []; the tailscale provider returns the opted-in device_tags\n  addresses.\n- TerraformRunner.forget_kept_on_destroy: inits, lists state and runs\n  `state rm` on each returned address in state; a failed init or\n  state rm raises before destroy. A provider without the hook, or one\n  returning no list, keeps nothing.\n- DestroyOrchestrator calls it through the new ForgetsKeptOnDestroy\n  protocol just before runner.destroy, with the filtered resources.\n- The validator requires the field to be a boolean; docs, the\n  implementing-providers guide and ADR-0020 describe it.\n\nVerified live: with the field set, destroy printed the \"Keeping ...\"\nline, completed, and the node kept its tag.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-10T14:33:52Z",
          "tree_id": "c56909eb28e68179da882d54c7cb527898f2bd6f",
          "url": "https://github.com/endavis/infrafoundry/commit/88ce6855d253134bd6786961038ed62428f3eff6"
        },
        "date": 1794321272956,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 16122.669687341182,
            "unit": "iter/sec",
            "range": "stddev: 0.00001563092206132753",
            "extra": "mean: 62.024467373735035 usec\nrounds: 17348"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6bf753db3383cf7cecc527a6b005f04f48fbc884",
          "message": "docs: troubleshoot os-tailscale nodes that stay logged out after the auth key is set (merges PR #1352, addresses #1351)\n\nAdd a \"Node stays logged out after the key is set\" section to the\nTailscale part of the OPNsense coverage page (#1351). The os-tailscale\nplugin passes --auth-key only when tailscaled.state exists and holds no\nprofile, so a missing state file skips the key on the first start, and\na stale profile left after a plugin removal or a deleted node skips it\nfor good. The section gives the status check, the second apply or\nreconfigure, and the SSH reset of the state file.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-10T14:46:09Z",
          "tree_id": "b61a09309cd106a7c028bc89fe7d8a82a12178e9",
          "url": "https://github.com/endavis/infrafoundry/commit/6bf753db3383cf7cecc527a6b005f04f48fbc884"
        },
        "date": 1794322009122,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 14507.526182091036,
            "unit": "iter/sec",
            "range": "stddev: 0.00001702327602432288",
            "extra": "mean: 68.92973946409005 usec\nrounds: 15898"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f47d8aec67a05cd49ebb063556a49a17ce2fc7e2",
          "message": "docs: link the upstream os-tailscale auth-key report from the troubleshooting section (merges PR #1355, addresses #1354)\n\nPoint the \"Node stays logged out after the key is set\" section at the\nupstream os-tailscale report, so readers can follow the fix and drop\nthe recovery steps once a plugin release ships it (#1354).\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-10T14:55:48Z",
          "tree_id": "9badaf7ff8b60bf29c0b6dc821e0cfbc59429d87",
          "url": "https://github.com/endavis/infrafoundry/commit/f47d8aec67a05cd49ebb063556a49a17ce2fc7e2"
        },
        "date": 1794322592589,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7851.536163827301,
            "unit": "iter/sec",
            "range": "stddev: 0.00000904485550308424",
            "extra": "mean: 127.36361129011742 usec\nrounds: 8379"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "b5bcf94125735de6a89f02c2fee9659d09cff54c",
          "message": "fix: parse terraform plans with a pending import (merges PR #1356, addresses #1353)\n\nWith an import pending, Terraform prints \"Plan: N to import, A to add,\nC to change, D to destroy.\" The runner's regex required \"to add\" right\nafter \"Plan:\", so extract_plan_summary returned \"Unable to parse plan\noutput\" and parse_plan_for_drift reported no changes at all, even when\nthe plan added and changed resources (#1353).\n\n- One module-level regex accepts the optional \"N to import, \" part; the\n  installed Terraform (v1.13.5) has only these two summary formats.\n- The summary lists non-zero counts in Terraform's order, import first.\n- DriftInfo gains to_import (NotRequired, additive); has_changes counts\n  a pending import, since apply would perform it.\n- parse_plan_for_drift strips ANSI colour codes before matching, as\n  extract_plan_summary already did: real terraform output is coloured,\n  so without it the drift counts were still unparsable.\n- The tailscale guide's note describing the symptom is removed.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-10T15:48:10Z",
          "tree_id": "f786a92a992c824deec1bbea1a96e74cfe18ee68",
          "url": "https://github.com/endavis/infrafoundry/commit/b5bcf94125735de6a89f02c2fee9659d09cff54c"
        },
        "date": 1794325731748,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9820.773143460705,
            "unit": "iter/sec",
            "range": "stddev: 0.000006697823397866848",
            "extra": "mean: 101.82497705548404 usec\nrounds: 10460"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "3a5087be023dd91a0df11a9f3cfd8b557cc7402c",
          "message": "perf: parse config yaml with libyaml when available (merges PR #1357, addresses #243)\n\nProfiling config loading showed ~94% of the time in PyYAML's pure-Python\nparser; only the requested environment is read, no file is parsed twice,\nand glob() is negligible, so the lazy loading and glob caching #243 first\nproposed would save nothing. The issue was re-scoped to the parser.\n\n- New core/config/yaml_loader.load_config_yaml parses with\n  yaml.CSafeLoader when PyYAML has libyaml, else yaml.SafeLoader. The\n  choice is made per call so tests can simulate a build without libyaml.\n- The eight parse sites under core/config/ (sops, provider- and\n  resource-centric loaders, package loader, blueprint resolver,\n  inventory generator) use it. core/secrets is unchanged.\n- Callers still get yaml.YAMLError; libyaml's error text has no source\n  snippet or caret but keeps line and column.\n- New config-loading benchmark (20 envs, 250 resources): mean 62.96 ms\n  -> 11.48 ms against the saved baseline.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-10T17:12:53Z",
          "tree_id": "0a3c434f7225770888b386c56405641be9207809",
          "url": "https://github.com/endavis/infrafoundry/commit/3a5087be023dd91a0df11a9f3cfd8b557cc7402c"
        },
        "date": 1794330816421,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 65.99803111230324,
            "unit": "iter/sec",
            "range": "stddev: 0.00025157906213473967",
            "extra": "mean: 15.151967159420028 msec\nrounds: 69"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 10558.443651287242,
            "unit": "iter/sec",
            "range": "stddev: 0.000026019468107006485",
            "extra": "mean: 94.71092833630685 usec\nrounds: 10940"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6acf0252e0d4d6c97e08717663d6d9529cbcb62e",
          "message": "perf: configure sqlalchemy connection pooling for non-sqlite state backends (merges PR #1358, addresses #239)\n\nAddresses #239\n\nAdd build_engine_kwargs, which returns pool_size, max_overflow,\npool_recycle and pool_pre_ping for non-SQLite connection strings and\nnothing for SQLite. StateManager passes them to create_engine. Values\ncome from INFRAFOUNDRY_STATE_POOL_SIZE, INFRAFOUNDRY_STATE_MAX_OVERFLOW\nand INFRAFOUNDRY_STATE_POOL_RECYCLE; invalid values warn and fall back\nto the defaults (5, 10, 1800). Documented in the state management docs.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-11T10:34:32Z",
          "tree_id": "b20bf11fe9c09623fd6ceebe5da5d1b062779af6",
          "url": "https://github.com/endavis/infrafoundry/commit/6acf0252e0d4d6c97e08717663d6d9529cbcb62e"
        },
        "date": 1794393317119,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 62.81799096360311,
            "unit": "iter/sec",
            "range": "stddev: 0.0015917598337671218",
            "extra": "mean: 15.919006397059121 msec\nrounds: 68"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 10523.481699659376,
            "unit": "iter/sec",
            "range": "stddev: 0.00002795482593820693",
            "extra": "mean: 95.02558454892053 usec\nrounds: 11106"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a3ea8bdba15ccb678eb748f4aca1363d7f42b168",
          "message": "perf: make apply worker count configurable (merges PR #1359, addresses #240)\n\nDefault --max-workers to os.cpu_count() (4 when unknown) instead of a\nfixed 4, and read INFRAFOUNDRY_MAX_WORKERS. Precedence is flag, env var,\nCPU count, 4. Values below 1 are rejected. Orchestrator.apply and the\nrollback path use the same default.\n\ninfra destroy gets no --max-workers: it runs providers sequentially and\nhas no thread pool, so the option would be accepted and ignored.\n\nAddresses #240\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-11T10:41:06Z",
          "tree_id": "a27fdae55fe57c6cffc28a0c701eb04f06066079",
          "url": "https://github.com/endavis/infrafoundry/commit/a3ea8bdba15ccb678eb748f4aca1363d7f42b168"
        },
        "date": 1794393713760,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 85.29500793936447,
            "unit": "iter/sec",
            "range": "stddev: 0.00019504988679526803",
            "extra": "mean: 11.724015556817719 msec\nrounds: 88"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12717.498375714793,
            "unit": "iter/sec",
            "range": "stddev: 0.000008042250323773268",
            "extra": "mean: 78.63181660864922 usec\nrounds: 13463"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "8b185e326743af59ba071d965aaef8f0f21faa85",
          "message": "perf: add composite indexes to the state database (merges PR #1360, addresses #242)\n\nAdd ix_resources_env_provider_name on resources (environment, provider,\nname), matching the resource lookup by name, and\nix_deployments_env_started_at on deployments (environment, started_at),\nmatching the per-environment history query ordered by start time.\n\nThere is no migration tool and create_all skips existing tables, so a\nnew ensure_indexes() step in StateManager.initialize() creates any named\nmodel index an existing SQLite or PostgreSQL database lacks. Existing\nsingle-column indexes are kept.\n\nAddresses #242\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-11T10:53:13Z",
          "tree_id": "64826a7d2cf6277c1e931471aa7fe9fc094bd285",
          "url": "https://github.com/endavis/infrafoundry/commit/8b185e326743af59ba071d965aaef8f0f21faa85"
        },
        "date": 1794394439168,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 57.14483764733281,
            "unit": "iter/sec",
            "range": "stddev: 0.0003690121356441562",
            "extra": "mean: 17.4993934915252 msec\nrounds: 59"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7824.278706232536,
            "unit": "iter/sec",
            "range": "stddev: 0.00003692774128676077",
            "extra": "mean: 127.80730819358932 usec\nrounds: 8287"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "af4765f01b6f2aa72dba0f81a621caa3046011bb",
          "message": "perf: memoize environment and resource loads per config manager (merges PR #1361, addresses #244)\n\nOne run loaded the full resource list twice and the environment settings\n(with SOPS decryption) three times. ConfigManager now memoizes\nload_environment and get_all_resources_all_providers per instance:\n\n- results are returned as deep copies, so callers cannot mutate the cache\n- the environment key includes INFRAFOUNDRY_IAC_TOOL, which is read per call\n- a resource cache hit replays the pending package events of that load\n- errors are not cached\n- hit/miss counts are logged at debug level and exposed by cache_stats();\n  clear_cache() forces a reload and cleanup() calls it\n\nThere is no file-change invalidation: config does not change mid-run and\neach run builds a new manager.\n\nAddresses #244\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-11T11:12:57Z",
          "tree_id": "1e1907072beec65ace41cca902cd102c89f3c268",
          "url": "https://github.com/endavis/infrafoundry/commit/af4765f01b6f2aa72dba0f81a621caa3046011bb"
        },
        "date": 1794395617278,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 101.63774338764208,
            "unit": "iter/sec",
            "range": "stddev: 0.0010054055965557983",
            "extra": "mean: 9.838864644859756 msec\nrounds: 107"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 15952.781800607603,
            "unit": "iter/sec",
            "range": "stddev: 0.000006517876324813777",
            "extra": "mean: 62.68499202828139 usec\nrounds: 16684"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "86571054d710ce2537cd45d8e0eb600fb154ccf0",
          "message": "feat: manage opnsense monit settings, alerts, tests and services (merges PR #1362, addresses #791)\n\nAdd four direct-API resource types for OPNsense's core monit subsystem,\non the ADR-0016 nested paths opnsense.monit.settings (singleton) and\nopnsense.monit.alerts / tests / services (managed-set lists):\n\n- monit.settings: singleton over the general node; password,\n  httpd_password and mmonit_url accept secret:// URIs, are redacted in\n  plan output, and an undeclared secret is never echoed back on write\n- monit.alerts: identity is the recipient; events as a YAML list\n- monit.tests: identity is the wire name; type and action enums from the\n  live model (wire spelling Permisssion kept)\n- monit.services: identity is the wire name; tests[] and depends[]\n  resolve operator handles to UUIDs, depends in the same apply ordered\n  topologically; per-type path requirements; services delete before\n  tests and referenced rows are blocked from deletion\n- one monit_reconfigure finalization hook per apply, config migrate\n  extractors for all four, validator wiring and endpoint registry\n  entries (stock, camelCase actions)\n\nVerified live on a test firewall: export, zero-drift re-plan, destroy\nand rebuild of the stock set with one reconfigure, secret echo, and\n--add-only. Docs: coverage matrix rows and a Monit section, ADR-0014\nmonit.* section and seventh hook, ADR-0013 scope row.\n\nAddresses #791\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-11T11:54:26Z",
          "tree_id": "43f406f176d6b0f06a756e6a2a425bfabb30c806",
          "url": "https://github.com/endavis/infrafoundry/commit/86571054d710ce2537cd45d8e0eb600fb154ccf0"
        },
        "date": 1794398107729,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 59.918533681117154,
            "unit": "iter/sec",
            "range": "stddev: 0.00026970155905480604",
            "extra": "mean: 16.689326967210846 msec\nrounds: 61"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 10478.369594757129,
            "unit": "iter/sec",
            "range": "stddev: 0.000026470128645919955",
            "extra": "mean: 95.43469439180231 usec\nrounds: 11145"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a1c2a8a6b9db273be9f2079290fff7b3f11eb1eb",
          "message": "chore: audit nosec and noqa suppressions in project-owned code (merges PR #1363, addresses #595)\n\nReview every bandit nosec and ruff noqa in src/, blueprints/,\ntools/opnsense-parser.py, tests/unit/ and tests/helpers/:\n\n- remove stale suppressions, measured with bandit --ignore-nosec: a\n  B108 on a NamedTemporaryFile call, two blueprint B501 lines and ten\n  test B105 lines whose names do not trigger the check\n- replace try/except/pass (B110) with contextlib.suppress in config envs\n  and the CLI welcome screen, and hoist the subprocess import in the\n  secrets commands to one module-level import\n- give every remaining suppression a reason after the ID list\n  (# nosec <ID>  # <reason>, # noqa: <CODE>  # <reason>); this also\n  clears the 37 bandit \"Test in comment\" warnings from blueprint scripts\n- add tests/unit/test_suppression_reasons.py, which fails on a bare or\n  reasonless nosec/noqa in those project-owned paths, and two behaviour\n  tests for the B110 sites\n\nTemplate-shipped files are left unchanged; their findings are reported\nupstream.\n\nAddresses #595\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-11T12:14:03Z",
          "tree_id": "a3dd85f4be522cd47f73c8ca38a0e50b209380d6",
          "url": "https://github.com/endavis/infrafoundry/commit/a1c2a8a6b9db273be9f2079290fff7b3f11eb1eb"
        },
        "date": 1794399292878,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 55.40870229675563,
            "unit": "iter/sec",
            "range": "stddev: 0.0006323272513642094",
            "extra": "mean: 18.047706561403324 msec\nrounds: 57"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9538.379446678002,
            "unit": "iter/sec",
            "range": "stddev: 0.00003315083558531205",
            "extra": "mean: 104.83961196870575 usec\nrounds: 10494"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "119abf1dfa6aaf82163ffb26f78f9f846eaa6d31",
          "message": "chore: enable ruff plw1514 and pass explicit utf-8 encoding to file i/o (merges PR #1364, addresses #687)\n\nAdd encoding=\"utf-8\" to all 191 text-mode open(), read_text() and\nwrite_text() calls ruff's PLW1514 flagged in src/, tests/,\ntools/opnsense-parser.py and one blueprint script, then enable the rule\nin the ruff select list with the same line the upstream template uses\nand drop the deferral note above preview = true.\n\nBinary-mode opens are unchanged, no call site reads a non-UTF-8 file, and\nno test assertion changed. Template-shipped tooling had no flagged sites.\n\nAddresses #687\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-11T12:23:09Z",
          "tree_id": "e8e2b2cb0df645745f5bbd8474d2cf1339d3b76e",
          "url": "https://github.com/endavis/infrafoundry/commit/119abf1dfa6aaf82163ffb26f78f9f846eaa6d31"
        },
        "date": 1794399833123,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 72.0168398341082,
            "unit": "iter/sec",
            "range": "stddev: 0.0004667266764426413",
            "extra": "mean: 13.885641223684823 msec\nrounds: 76"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12686.372295623973,
            "unit": "iter/sec",
            "range": "stddev: 0.000005440836187337358",
            "extra": "mean: 78.82474017768966 usec\nrounds: 13617"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "d59f0cd46295318526e7b2da20528b265e557dc3",
          "message": "docs: expand provider, ordering, troubleshooting and workflow docs (merges PR #1365, addresses #191)\n\n- add an OPNsense provider page: credentials, the ADR-0016 nested YAML\n  schema, the resource type catalog linked to the coverage document,\n  unsupported types, apply order and managed-set deletes, --add-only,\n  config migrate, finalization hooks, validation and troubleshooting\n- complete the Kubernetes reference: Terraform resource per type,\n  KUBECONFIG and provider pins, per-type config keys from the templates,\n  the config.name naming rule, the jobs/cronjobs namespace and secret\n  data/string_data limitations, common use cases, and the Ansible\n  playbook and inventory it generates\n- add a dependency-ordering page (provider_order, per-provider\n  get_dependencies rules, depends_on, no cross-provider edges, the\n  analyze commands) and a provider_order entry in the settings reference\n- add a troubleshooting guide organised by symptom, linked to the error\n  reference, and add IF-VALIDATION-005 and IF-VALIDATION-006 there\n- add a Common Workflows section to the CLI reference\n- correct claims the code contradicts: infra plan/apply do not generate\n  or run Ansible (overview, orchestrator architecture, Ansible runner\n  guide), and analyze graph has no DOT format or cross-resource edges\n- wire the new pages into mkdocs nav and the docs index\n\nAddresses #191\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-11T14:43:17Z",
          "tree_id": "83b561b1e57f2367a08f6476546a675f3de20098",
          "url": "https://github.com/endavis/infrafoundry/commit/d59f0cd46295318526e7b2da20528b265e557dc3"
        },
        "date": 1794408245863,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 48.760725724958284,
            "unit": "iter/sec",
            "range": "stddev: 0.0006216381435369865",
            "extra": "mean: 20.508308379999107 msec\nrounds: 50"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7866.346028376117,
            "unit": "iter/sec",
            "range": "stddev: 0.000009899870891300869",
            "extra": "mean: 127.12382552111482 usec\nrounds: 8299"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "e74f766247630e396bc6149d5d2ec3b1a84a3653",
          "message": "fix: correct kubernetes job namespace, depends_on labels and secret data (merges PR #1368, addresses #1366)\n\n- jobs and cronjobs take their namespace from config.namespace (default\n  \"default\"); the templates read a namespace attribute ResourceConfig\n  does not have, so every job and cronjob landed in \"default\"\n- automatic depends_on references use the label each template declares:\n  config.name for namespaces, configmaps, deployments and services, the\n  top-level name for every other type; references no longer point at an\n  undeclared resource when name and config.name differ\n- a secret renders one data map: config.data first, then string_data as\n  plain values (string_data wins on a duplicate key); this removes the\n  duplicate data argument and the base64encode that double-encoded\n  string_data, since the provider's data field takes plain values\n\nMigration effects:\n- a job or cronjob that sets config.namespace to anything but \"default\"\n  is replaced on the next apply, moving into that namespace\n- a secret that uses string_data gets an in-place update on the next\n  apply: the stored value becomes the plain string instead of its\n  base64 text\n\nAddresses #1366\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-11T15:06:50Z",
          "tree_id": "dbd088dc687ef512ad49d1cd37d80f87b51a33ea",
          "url": "https://github.com/endavis/infrafoundry/commit/e74f766247630e396bc6149d5d2ec3b1a84a3653"
        },
        "date": 1794409658662,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 106.34744159339891,
            "unit": "iter/sec",
            "range": "stddev: 0.0007771912695335941",
            "extra": "mean: 9.403141110092026 msec\nrounds: 109"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 15817.906200559513,
            "unit": "iter/sec",
            "range": "stddev: 0.000003852432538906826",
            "extra": "mean: 63.219492347516116 usec\nrounds: 16988"
          }
        ]
      }
    ]
  }
}