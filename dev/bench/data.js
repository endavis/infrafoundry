window.BENCHMARK_DATA = {
  "lastUpdate": 1794161965781,
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
      }
    ]
  }
}