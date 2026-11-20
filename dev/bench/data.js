window.BENCHMARK_DATA = {
  "lastUpdate": 1795211467579,
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
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "65db0ca8b092d15d9a632205ed4ac1c5528208e4",
          "message": "fix: resolve kubernetes validator references by the object name templates create (merges PR #1371, addresses #1370)\n\nKubernetesValidator built its known-name sets from the top-level resource\nname, but namespaces, configmaps, deployments and services create their\nKubernetes object under config.name. A config whose two names differed\ngot a false missing-reference warning (or error, for env_from configmap\nrefs).\n\nMove the name rule into providers/kubernetes/names.py\n(kubernetes_object_name: config.name for those four types, falling back\nto name; name for every other type). The validator's API and local\nreference checks and KubernetesProvider._terraform_label now share it,\nso labels, references and validation follow one rule.\n\nAddresses #1370\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-11T15:25:29Z",
          "tree_id": "0ba3a6e150a1549c9752268a6bbb0621d03b619e",
          "url": "https://github.com/endavis/infrafoundry/commit/65db0ca8b092d15d9a632205ed4ac1c5528208e4"
        },
        "date": 1794410787337,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 50.1731221650574,
            "unit": "iter/sec",
            "range": "stddev: 0.0002757598611446161",
            "extra": "mean: 19.93099007692291 msec\nrounds: 52"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7218.401815744228,
            "unit": "iter/sec",
            "range": "stddev: 0.000021393967426235533",
            "extra": "mean: 138.53482052202696 usec\nrounds: 8352"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "eda9a4d316e5bc59e0324d75af685f9b7197cae1",
          "message": "chore: raise minimum python to 3.13 (merges PR #1375, addresses #1372)\n\nRaise the supported floor from 3.12 to 3.13 in all seven settings the\npython-version-bump skill names (requires-python, ruff target-version,\nmypy python_version, pyright pythonVersion, .python-version,\n.github/python-versions.json oldest, classifiers), regenerate uv.lock,\napply the ruff UP rewrites the new target reports, and update prose that\nstates the supported range. ADRs and historical records are unchanged.\n\npynetappfoundry, which the planned native ONTAP provider (#1373) will use,\nrequires Python 3.13.\n\nBREAKING CHANGE: Python 3.12 is no longer supported; 3.12 users stay on\nthe last release that supports it.\n\nAddresses #1372\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-12T11:56:54Z",
          "tree_id": "770b31e0ca5f9c243a111abb8ede20de469e4a97",
          "url": "https://github.com/endavis/infrafoundry/commit/eda9a4d316e5bc59e0324d75af685f9b7197cae1"
        },
        "date": 1794484663069,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 106.4845654107364,
            "unit": "iter/sec",
            "range": "stddev: 0.0005020374940307082",
            "extra": "mean: 9.391032363636562 msec\nrounds: 110"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 16621.33070711777,
            "unit": "iter/sec",
            "range": "stddev: 0.000006306503245892023",
            "extra": "mean: 60.163654620731954 usec\nrounds: 17876"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2f0bbcf807d3176edbbe77ab0c75224da314e291",
          "message": "chore: remove dead nosec suppressions and add missing reasons (merges PR #1381, addresses #1380)\n\nThe template's new suppression guards (adopted in the #1376 sync) flag\nsuppressions in this repository's own code:\n\n- drop B603/B607 from nosec comments in src/ and project tests: both IDs\n  are in [tool.bandit] skips, so the suppressions were dead; the reason\n  text stays as a plain comment\n- drop nosec markers from project test files, which bandit excludes\n- give the three local nosec suppressions in tools/doit/install_tools.py\n  a reason\n- delete tools/pyproject_template/migrate_existing_project.py, which the\n  template no longer ships and nothing references\n\nTemplate-layer files are left to the sync, whose updated copies already\npass the guards. doit check and doit security pass.\n\nAddresses #1380\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-12T13:31:58Z",
          "tree_id": "f5b2f38af78ab057e8bf7f41e6d17017dc94279a",
          "url": "https://github.com/endavis/infrafoundry/commit/2f0bbcf807d3176edbbe77ab0c75224da314e291"
        },
        "date": 1794490362081,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 69.71780405475953,
            "unit": "iter/sec",
            "range": "stddev: 0.0007114525353886219",
            "extra": "mean: 14.343538405405809 msec\nrounds: 74"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12860.201005266388,
            "unit": "iter/sec",
            "range": "stddev: 0.000007700891948540381",
            "extra": "mean: 77.75928226864335 usec\nrounds: 13682"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "7514e3ef4cff0d8c46977e2c65633d3686379091",
          "message": "chore: synchronize with pyproject-template ef82475 (merges PR #1382, addresses #1376)\n\nSyncs the following template improvements (dbe9500...ef82475):\n- endavis/pyproject-template#1213 (keep a merged worktree while anything is mounted inside it)\n- endavis/pyproject-template#1215 (changelog rule depends on update_changelog_on_bump)\n- endavis/pyproject-template#1217 (reject closing keywords in commit messages)\n- endavis/pyproject-template#1219 (Codecov upload opt-in via CODECOV_ENABLED, OIDC auth)\n- endavis/pyproject-template#1222 (Dependabot rebases its own PRs)\n- endavis/pyproject-template#1223, #1232 (group dependabot updates and type stubs)\n- endavis/pyproject-template#1230 (doit issue types feat/fix; title prefix must match --type)\n- endavis/pyproject-template#1237 (document the heredoc mv-plus-pipe false positive)\n- endavis/pyproject-template#1239 (project rebuildable names for pr_merge worktree removal, ADR-9031)\n- endavis/pyproject-template#1243 (shared pre-commit hook cache; .envrc edited by the repo admin)\n- endavis/pyproject-template#1244 (own block reason for unresolvable write targets)\n- endavis/pyproject-template#1246, #1247 (nosec/noqa reason guards)\n- endavis/pyproject-template#1248 (number ADR headings in bodies; add new ADRs to index and nav)\n- endavis/pyproject-template#1250 (anchor bandit exclude_dirs entries)\n- endavis/pyproject-template#1252 (keep the checkout revision out of hook pathspec checks)\n- dev-dependency floor bumps\n\nKept local: Linux-only CI (ADR-0001), so ci.yml keeps ubuntu-latest and\ntest_ci_workflow.py takes only the Codecov tests; ANN401 stays ignored\nproject-wide, so tools/doit/github.py keeps no noqa; AGENTS.md keeps its\nown Breaking Changes section. Local --type=feature/bug mentions updated\nto feat/fix.\n\nBREAKING CHANGE: doit issue --type=feature and --type=bug now exit 1;\nuse --type=feat and --type=fix, with a title that starts with the same\ntype.\n\nAddresses #1376\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-12T13:40:42Z",
          "tree_id": "63e82fdb287a396800a0a65843a751b11cbcfeb9",
          "url": "https://github.com/endavis/infrafoundry/commit/7514e3ef4cff0d8c46977e2c65633d3686379091"
        },
        "date": 1794490891475,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 87.6302430007759,
            "unit": "iter/sec",
            "range": "stddev: 0.0008930661383850029",
            "extra": "mean: 11.411585381443546 msec\nrounds: 97"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 14710.330152235825,
            "unit": "iter/sec",
            "range": "stddev: 0.000003885966486753041",
            "extra": "mean: 67.9794395945634 usec\nrounds: 15785"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "678bb15da389d33a5906f0bc0c9ee429dd48a2d5",
          "message": "feat: show the proxmox 9.2 sdn dry-run in infra plan (merges PR #1386, addresses #1374)\n\ninfra plan now calls GET /cluster/sdn/dry-run on each online node when\nthe run manages SDN zones or vnets, and prints each node's\ninterfaces-diff and frr-diff, or \"no pending SDN changes\".\n\n- New optional provider hook ProviderBase.get_plan_notes(resources),\n  default [], printed by PlanOrchestrator after a provider's runners\n  plan (not on --dry-run) through the guarded provider_plan_notes\n  helper, with console markup off.\n- New service module providers/proxmox/sdn_dry_run.py: version gate\n  (GET version, skip below 9.2), per-node dry-run, 404/501 on the first\n  call treated as \"endpoint not available\" when the version cannot be\n  parsed, offline nodes and per-node API errors reported without\n  stopping the rest.\n- At plan time this run has staged nothing, so every diff is labelled as\n  pending before the run and pushed by the next SDN apply.\n- The check never fails the plan: missing credentials or API errors\n  become a single skip line.\n\nThe optional apply-time dry-run is left out: before terraform apply it\nwould repeat the plan output, and showing it between staging and the\napplier needs a two-phase Terraform apply.\n\nAddresses #1374\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-12T17:03:49Z",
          "tree_id": "f1097631a2d698b35e2a3d14deb4e1e00dd4f8e5",
          "url": "https://github.com/endavis/infrafoundry/commit/678bb15da389d33a5906f0bc0c9ee429dd48a2d5"
        },
        "date": 1794503095929,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 61.08325338238258,
            "unit": "iter/sec",
            "range": "stddev: 0.00043460005632259887",
            "extra": "mean: 16.371099190476592 msec\nrounds: 63"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 10901.164639088276,
            "unit": "iter/sec",
            "range": "stddev: 0.0000057275224894141106",
            "extra": "mean: 91.73331777912084 usec\nrounds: 11851"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "46b6b607fa7379f35e512283fb2f713059d40529",
          "message": "fix: render kubernetes secret data as base64 binary_data (merges PR #1387, addresses #1369)\n\nA secrets resource's config.data went straight into the provider's\nkubernetes_secret.data argument, which takes plain values and encodes\nthem itself, so base64 input (the Kubernetes manifest convention) was\nstored still encoded.\n\n- config.data now takes base64 and renders to binary_data;\n  config.string_data stays plain and renders to data. string_data still\n  wins on a duplicate key, and a key is never set on both arguments.\n- The Kubernetes validator rejects a config.data value that is not\n  strict base64, naming the secret and key.\n- docs/providers/kubernetes.md states the encoding of each field and\n  notes the effect on existing secrets: plain text in data now fails\n  validation (move it to string_data), and base64 text in data changes\n  its stored value to the decoded content on the next apply.\n\nAddresses #1369\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-12T18:23:10Z",
          "tree_id": "45ddb34a4a6507f0e31db84617af646e33f3b8b8",
          "url": "https://github.com/endavis/infrafoundry/commit/46b6b607fa7379f35e512283fb2f713059d40529"
        },
        "date": 1794507858781,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 59.530249165522356,
            "unit": "iter/sec",
            "range": "stddev: 0.00015212253833017214",
            "extra": "mean: 16.79818267213237 msec\nrounds: 61"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 10796.995587719923,
            "unit": "iter/sec",
            "range": "stddev: 0.000006982763349954825",
            "extra": "mean: 92.61835775290679 usec\nrounds: 12176"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "b05ee64ed2c1b1a2b9498502276c9929073abffd",
          "message": "chore: reconcile error catalog, cli help examples and the runner test (merges PR #1388, addresses #1367)\n\n- Add IF-STATE-005 \"Package Move Rollback Failed\" to ERROR_CATALOG and\n  map PackageMoveRollbackError to it, matching docs/reference/errors.md.\n- Error suggestions now name real commands: config doctor (was config\n  validate), infra analyze ... (was a top-level analyze), config create\n  (was config new --env), infra drift detect (infra drift is a group),\n  state prune after state backup (was state reset).\n- config migrate help and the CLI reference use the registered\n  interfaces.vlans component key instead of vlans.\n- test_plan_orchestrator_runs_runners_in_priority_order now gives its\n  runners real is_iac_runner values and asserts the Ansible runner is\n  neither generated nor planned (approved on #1367). Ansible stays out\n  of infra plan/apply and runs through blueprint event scripts, as the\n  runner docs already state.\n- New guard tests: the IF-* codes in errors.md equal ERROR_CATALOG, and\n  every foundry command named in a suggestion resolves in the CLI.\n\nAddresses #1367\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-12T18:46:15Z",
          "tree_id": "161e1831a537edf90ab16563821e2a61501eeca3",
          "url": "https://github.com/endavis/infrafoundry/commit/b05ee64ed2c1b1a2b9498502276c9929073abffd"
        },
        "date": 1794509241943,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 97.4057919115745,
            "unit": "iter/sec",
            "range": "stddev: 0.0005610482308944776",
            "extra": "mean: 10.266329962265544 msec\nrounds: 106"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 16674.84595581242,
            "unit": "iter/sec",
            "range": "stddev: 0.0000028048074484856516",
            "extra": "mean: 59.970569002553574 usec\nrounds: 16782"
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
          "id": "0c43963e6de193f1fac5b8753e4b4f8ff32bed55",
          "message": "chore(deps): bump cyclonedx-bom from 7.6.0 to 8.0.1 (merges PR #1385)\n\nBumps [cyclonedx-bom](https://github.com/CycloneDX/cyclonedx-python) from 7.6.0 to 8.0.1.\n- [Release notes](https://github.com/CycloneDX/cyclonedx-python/releases)\n- [Changelog](https://github.com/CycloneDX/cyclonedx-python/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/CycloneDX/cyclonedx-python/compare/v7.6.0...v8.0.1)\n\n---\nupdated-dependencies:\n- dependency-name: cyclonedx-bom\n  dependency-version: 8.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-11-13T09:33:06Z",
          "tree_id": "4baa55a08ff7226d93c920b37ed9a629e42ea9bd",
          "url": "https://github.com/endavis/infrafoundry/commit/0c43963e6de193f1fac5b8753e4b4f8ff32bed55"
        },
        "date": 1794562436805,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 75.05195031874273,
            "unit": "iter/sec",
            "range": "stddev: 0.0005614338205800325",
            "extra": "mean: 13.324104113924271 msec\nrounds: 79"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 13623.206143465271,
            "unit": "iter/sec",
            "range": "stddev: 0.000004425996757064141",
            "extra": "mean: 73.40415974544115 usec\nrounds: 15556"
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
          "id": "6b69a9cf01fdcead5eb8182398221633cfeeb12f",
          "message": "chore(deps): bump pymdown-extensions from 12.3 to 13.0 (merges PR #1396)\n\nBumps [pymdown-extensions](https://github.com/facelessuser/pymdown-extensions) from 12.3 to 13.0.\n- [Release notes](https://github.com/facelessuser/pymdown-extensions/releases)\n- [Commits](https://github.com/facelessuser/pymdown-extensions/compare/12.3...13.0)\n\n---\nupdated-dependencies:\n- dependency-name: pymdown-extensions\n  dependency-version: '13.0'\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-11-16T10:35:13Z",
          "tree_id": "e6f4121f05630341270abfdcf8bdda62c586745d",
          "url": "https://github.com/endavis/infrafoundry/commit/6b69a9cf01fdcead5eb8182398221633cfeeb12f"
        },
        "date": 1794825366176,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 75.64868213474692,
            "unit": "iter/sec",
            "range": "stddev: 0.0005680998142802723",
            "extra": "mean: 13.219000936708724 msec\nrounds: 79"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 14292.586601402943,
            "unit": "iter/sec",
            "range": "stddev: 0.0000051158935322863414",
            "extra": "mean: 69.96634184478835 usec\nrounds: 15861"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "13c8456b69b9465613f1d7b5d20ea02705065ced",
          "message": "feat: add an aws provider for ec2 instances, security groups and ebs volumes (merges PR #1398, addresses #1397)\n\nAdd an `aws` provider generating hashicorp/aws (~> 6.0) Terraform for\nsecurity_group (with per-rule resources), instance and ebs_volume.\n\n- Credentials come from the standard AWS chain; provider settings accept\n  region and profile only and reject key material.\n- Instances: AMI by ID or SSM public parameter (ignore_changes on ami by\n  default), IPv6-only support, IMDSv2 required and encrypted gp3 root by\n  default, cloud-init and Tailscale join as on OCI.\n- EBS volumes are prevent_destroy by default and are forgotten from\n  state, not deleted, on infra destroy.\n- import_id on every type, plus per-rule and attachment import ids, to\n  adopt existing resources.\n- Config validation without network calls (no boto3).\n- ADR-0021 and docs/providers/aws.md.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T11:02:58Z",
          "tree_id": "ec993a6e6ed17d0ec3f48eacb921a1e00aeb9bd4",
          "url": "https://github.com/endavis/infrafoundry/commit/13c8456b69b9465613f1d7b5d20ea02705065ced"
        },
        "date": 1794827047625,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 61.55669410513246,
            "unit": "iter/sec",
            "range": "stddev: 0.00047138847353393916",
            "extra": "mean: 16.24518688888821 msec\nrounds: 63"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 11043.110055570727,
            "unit": "iter/sec",
            "range": "stddev: 0.00000720641210601081",
            "extra": "mean: 90.55420030841287 usec\nrounds: 12321"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "67a4c43ab10b9fdc6b9b15deeb9874af47def78a",
          "message": "fix: render the dns aaaa record setting for ipv6-only aws instances (merges PR #1400, addresses #1399)\n\nAn ipv6_only instance rendered private_dns_name_options with only\nhostname_type, so the AWS provider sent\nenable_resource_name_dns_aaaa_record = false, which EC2 rejects on a\nsubnet without an IPv4 CIDR. Render it as true for ipv6_only.\n\nAlso correct the documented attachment_import_id order to\n<device>:<volume-id>:<instance-id>.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T11:27:41Z",
          "tree_id": "f542494aec60ad89e626574dd8c7e6b2c06356fd",
          "url": "https://github.com/endavis/infrafoundry/commit/67a4c43ab10b9fdc6b9b15deeb9874af47def78a"
        },
        "date": 1794828563003,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 49.33343494442258,
            "unit": "iter/sec",
            "range": "stddev: 0.0003881167523144444",
            "extra": "mean: 20.270228520000018 msec\nrounds: 50"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7931.171342634229,
            "unit": "iter/sec",
            "range": "stddev: 0.000009199044588542422",
            "extra": "mean: 126.08478077184796 usec\nrounds: 8498"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "323435b71fdb5060e0372891ea96497d08d4c36f",
          "message": "feat: remove an instance's tailnet device when it is destroyed (merges PR #1402, addresses #1401)\n\nAfter `infra destroy` deletes an instance that has a `tailscale:` block,\ndelete its tailnet device through the Tailscale API, so a redeploy joins\nwith the bare hostname instead of `<hostname>-1`.\n\n- Runs after Terraform reports the delete (also for -r/-p/-P destroys),\n  so a failed or blocked destroy never logs a live node out.\n- Matches devices by hostname and one of the block's advertise_tags.\n- Uses the block's OAuth client (needs devices:core); auth-key mode,\n  a missing client_id_secret and `remove_on_destroy: false` skip with a\n  message. API errors only warn; secrets are never logged.\n- Not done on an apply that replaces the instance (old and new devices\n  cannot be told apart afterwards); documented.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T12:28:23Z",
          "tree_id": "036ca4cdccccd6854516bb6ce72ec5a5aafd258e",
          "url": "https://github.com/endavis/infrafoundry/commit/323435b71fdb5060e0372891ea96497d08d4c36f"
        },
        "date": 1794832171009,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 59.553824116531146,
            "unit": "iter/sec",
            "range": "stddev: 0.0004719672571851729",
            "extra": "mean: 16.7915329508188 msec\nrounds: 61"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 10879.987611961897,
            "unit": "iter/sec",
            "range": "stddev: 0.000005215880728758747",
            "extra": "mean: 91.91186935732902 usec\nrounds: 11918"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "b5bb0b5d4bbb7ebfe21e227eb8d0f38c6b738509",
          "message": "fix: scope package event handlers to the operation's packages, resources and providers (merges PR #1406, addresses #1403)\n\nPackage-level handlers were filtered only by -p, so a resource-targeted\ndestroy (-r) or a provider-scoped apply (-P) ran handlers of unrelated\npackages.\n\n- Package loader tags package-level handlers with the package's resource\n  names and providers.\n- EventContext gains provider_filter; BaseHandler.matches_scope combines\n  package, resource and provider scoping, used by the event bus.\n- Plan, apply and destroy emit their workflow events through one helper\n  that passes target_resources, package_filter and provider_filter.\n- Whole-environment operations, environment-level and resource-owned\n  handlers are unchanged.\n\ntest_plan_orchestrator_dry_run_skips_generation now expects the new\nprovider_filter=None argument on BEFORE_PLAN/AFTER_PLAN (approved).\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T13:03:59Z",
          "tree_id": "771692666d23457fc3b7cb2c38fd556dc6d6ac7a",
          "url": "https://github.com/endavis/infrafoundry/commit/b5bb0b5d4bbb7ebfe21e227eb8d0f38c6b738509"
        },
        "date": 1794834302845,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 49.02993941274131,
            "unit": "iter/sec",
            "range": "stddev: 0.00035139373392340136",
            "extra": "mean: 20.395701320000654 msec\nrounds: 50"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7747.452463215172,
            "unit": "iter/sec",
            "range": "stddev: 0.000009302394927012849",
            "extra": "mean: 129.0746867758131 usec\nrounds: 8371"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "550171d69441bec465dbb40fd84dec2c1e71f377",
          "message": "fix: emit before_* events after package handlers are registered (merges PR #1407, addresses #1405)\n\nBEFORE_PLAN, BEFORE_APPLY and BEFORE_DESTROY fired before\n_load_resources registered package event handlers, so package\nbefore_* handlers never ran. Emit each event right after resources\nload, inside the try, so a load failure emits only the *_failed event.\n\nAddresses #1405\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T13:28:17Z",
          "tree_id": "fb502c6ef6e476bdb7c9545408d15b57d1d85688",
          "url": "https://github.com/endavis/infrafoundry/commit/550171d69441bec465dbb40fd84dec2c1e71f377"
        },
        "date": 1794835757818,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 105.15679141938956,
            "unit": "iter/sec",
            "range": "stddev: 0.00015555215984948908",
            "extra": "mean: 9.509609284404362 msec\nrounds: 109"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 16526.355974969865,
            "unit": "iter/sec",
            "range": "stddev: 0.000015469339068210643",
            "extra": "mean: 60.50940700506261 usec\nrounds: 17673"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "4b73f2537e0fcbaf673ffea36b582c2300970243",
          "message": "fix: report an outputs-only terraform plan instead of an unparsable one (merges PR #1409, addresses #1404)\n\nextract_plan_summary now recognises \"Changes to Outputs:\" and returns\n\"Output changes only\"; parse_plan_for_drift treats it as no resource\nchanges. A Plan line still takes precedence.\n\nAddresses #1404\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T13:38:14Z",
          "tree_id": "f3e53dc73eb3cbf544d8ec73f64f028b8222d2c7",
          "url": "https://github.com/endavis/infrafoundry/commit/4b73f2537e0fcbaf673ffea36b582c2300970243"
        },
        "date": 1794836362813,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 49.57898387236805,
            "unit": "iter/sec",
            "range": "stddev: 0.0001568342158468284",
            "extra": "mean: 20.16983652941165 msec\nrounds: 51"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7816.370596433767,
            "unit": "iter/sec",
            "range": "stddev: 0.000008729005766457333",
            "extra": "mean: 127.93661555098883 usec\nrounds: 8321"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "5cc33d947cb5a5e0c670bde37d8ad00f1e89ce9e",
          "message": "feat: manage existing hosts through a host provider (merges PR #1410, addresses #1408)\n\n* feat: manage existing hosts through a host provider\n\nAdd a host provider and HostRunner for machines no provider creates.\nApply writes an Ansible inventory and runs per-host playbooks plus\nTailscale enrollment; hosts are recorded in state so deployed, -r and\n-P work. Destroy only forgets the host and runs cleanup hooks, never\ntouching the machine. Includes docs and ADR-0022.\n\nAddresses #1408\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* fix: drop nosec markers for bandit ids already skipped in config\n\nB603 is in [tool.bandit] skips, so the security-triage guard rejects a\nnosec comment naming it.\n\nAddresses #1408\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T13:58:21Z",
          "tree_id": "ab6a48fa38cedcfb4d6fa00e2c6b09603fd8c9ec",
          "url": "https://github.com/endavis/infrafoundry/commit/5cc33d947cb5a5e0c670bde37d8ad00f1e89ce9e"
        },
        "date": 1794837559419,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 68.66064220801137,
            "unit": "iter/sec",
            "range": "stddev: 0.0004928871848262368",
            "extra": "mean: 14.564384599993142 msec\nrounds: 75"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 13086.310739525028,
            "unit": "iter/sec",
            "range": "stddev: 0.000006772631400436543",
            "extra": "mean: 76.41573090417806 usec\nrounds: 13694"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a4f8ef1c09abe005c9322ceb46c146c94be3de63",
          "message": "fix: generate host inventory through the orchestrator and accept the name key (merges PR #1412, addresses #1411)\n\nThe plan step calls generate_<tool_name> on a provider, but HostProvider\ndefined generate_host_ansible, so no inventory was written and apply\nrecorded hosts without running any playbook. Rename it to generate_host,\nfail HostRunner.apply when a requested host has no generated run, and\naccept name as a known host key so doctor stops warning about it.\n\nAddresses #1411\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T14:17:19Z",
          "tree_id": "f258d39f106eb6a4f7105710696ad8ed3fc30668",
          "url": "https://github.com/endavis/infrafoundry/commit/a4f8ef1c09abe005c9322ceb46c146c94be3de63"
        },
        "date": 1794838689314,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 58.21298516769044,
            "unit": "iter/sec",
            "range": "stddev: 0.0007073227797264725",
            "extra": "mean: 17.17829788524611 msec\nrounds: 61"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 11226.309550605112,
            "unit": "iter/sec",
            "range": "stddev: 0.000005535335275751503",
            "extra": "mean: 89.07646769334796 usec\nrounds: 12273"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ac80ec2e803add157ddffefb2be0b937667d1016",
          "message": "fix: resolve ansible-playbook in the host runner (merges PR #1415, addresses #1413)\n\nHostRunner built its playbook command from BaseRunner.tool_path, which\nlooks up tool_name on PATH, so apply searched for a host_ansible\nexecutable and failed. Resolve ansible-playbook through one lookup that\nboth tool_path and is_available use, keeping tool_name host_ansible.\n\nAddresses #1413\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T14:38:49Z",
          "tree_id": "9d63cb826bab1041965f999d0ae93a4e1bda1b0b",
          "url": "https://github.com/endavis/infrafoundry/commit/ac80ec2e803add157ddffefb2be0b937667d1016"
        },
        "date": 1794839986317,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 49.05571377262973,
            "unit": "iter/sec",
            "range": "stddev: 0.0006397691838290948",
            "extra": "mean: 20.384985215686388 msec\nrounds: 51"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7823.440549209974,
            "unit": "iter/sec",
            "range": "stddev: 0.000012078796393542601",
            "extra": "mean: 127.82100071061214 usec\nrounds: 8444"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "215e9b28dc19cf7df8eb9d3894f4a6083a6f125f",
          "message": "fix: resolve the host enrollment playbook path (merges PR #1418, addresses #1416)\n\nget_host_runs built the enrollment playbook path from the relative\nansible_dir, and the runner starts ansible-playbook with that directory as\nits cwd, so the path was resolved twice and the playbook was not found.\nResolve it to an absolute path, as user playbooks already are.\n\nAddresses #1416\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T15:01:06Z",
          "tree_id": "cb9e70c46bcf77e5cf180d91a84d72a867943a85",
          "url": "https://github.com/endavis/infrafoundry/commit/215e9b28dc19cf7df8eb9d3894f4a6083a6f125f"
        },
        "date": 1794841323985,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 78.42040238043873,
            "unit": "iter/sec",
            "range": "stddev: 0.00033936398660125623",
            "extra": "mean: 12.751783587499688 msec\nrounds: 80"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 14242.510071450391,
            "unit": "iter/sec",
            "range": "stddev: 0.000004159976943522421",
            "extra": "mean: 70.21234283727381 usec\nrounds: 15818"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ce94c7cf001fad21a78cc35279118a2e4fe78939",
          "message": "fix: mark resources error when an apply fails (merges PR #1419, addresses #1414)\n\nDeploymentExecutor.apply_single_provider tracks each resource as CREATING\nbefore the runner runs, and the failure handler re-raised without touching\nthose rows, so infra deployed showed them as creating until the next\nsuccessful apply. Mark the run's rows ERROR and emit RESOURCE_FAILED per\nresource before re-raising. The previous ACTIVE row stays the managed record\nbecause the resource table is append-only. A runner that returns\nsuccess: False takes the same path through raise_on_runner_failure.\n\nAddresses #1414\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T15:12:50Z",
          "tree_id": "91a4afb0d4d009a978a4fbdb9c98fa158d8218b8",
          "url": "https://github.com/endavis/infrafoundry/commit/ce94c7cf001fad21a78cc35279118a2e4fe78939"
        },
        "date": 1794842036919,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 74.459103423018,
            "unit": "iter/sec",
            "range": "stddev: 0.0004053166120696684",
            "extra": "mean: 13.430191259741436 msec\nrounds: 77"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 13734.973170500065,
            "unit": "iter/sec",
            "range": "stddev: 0.000004036475374590509",
            "extra": "mean: 72.80684043473758 usec\nrounds: 14809"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "9cf86153ff98c1c289ec5997d21d2afb4de9173d",
          "message": "fix: plan records only resources that are not yet deployed (merges PR #1421, addresses #1417)\n\nfix: do not record already-deployed resources as planned\n\nPlanOrchestrator._track_planned_resources inserted a PLANNED row for every\nresource on every plan. The resource table is append-only and infra deployed\nshows the newest row per resource, so a no-change plan after an apply made a\ndeployed resource show as planned. Resources already managed (newest\nACTIVE/DELETED row is ACTIVE) are now skipped; only not-yet-deployed\nresources get a PLANNED row. The managed set is fetched once per provider\nand reused for the runner. Rows written by earlier plans are not rewritten.\n\nAddresses #1417\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T15:19:23Z",
          "tree_id": "8f62318c58a9fcf1ff40202c166feb50d3d17b0b",
          "url": "https://github.com/endavis/infrafoundry/commit/9cf86153ff98c1c289ec5997d21d2afb4de9173d"
        },
        "date": 1794842422166,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 77.11210519786876,
            "unit": "iter/sec",
            "range": "stddev: 0.00033741901661633986",
            "extra": "mean: 12.968132531643532 msec\nrounds: 79"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 14077.472542138321,
            "unit": "iter/sec",
            "range": "stddev: 0.000005323562460690715",
            "extra": "mean: 71.03547863486746 usec\nrounds: 15937"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "eb6aa83b06749689c119dc5d7e575129eb6c8591",
          "message": "fix: mark deleting resources as error when a destroy fails (merges PR #1422, addresses #1420)\n\nWhen a runner raised or reported failure during destroy, the rows recorded\nas DELETING were never updated. The destroy failure handler now marks this\nrun's rows ERROR and emits RESOURCE_FAILED per resource, best-effort so a\nstate error never masks the runner's exception. Mirrors the apply-side fix.\n\nAddresses #1420\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T15:24:07Z",
          "tree_id": "bad36f903af8ee97ba74d9f33a561f11bb833704",
          "url": "https://github.com/endavis/infrafoundry/commit/eb6aa83b06749689c119dc5d7e575129eb6c8591"
        },
        "date": 1794842722161,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 73.80739552523066,
            "unit": "iter/sec",
            "range": "stddev: 0.00033126469189431013",
            "extra": "mean: 13.548777773335132 msec\nrounds: 75"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12933.47063523226,
            "unit": "iter/sec",
            "range": "stddev: 0.000005692681446807226",
            "extra": "mean: 77.31876680307954 usec\nrounds: 13688"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f5c84b9ec1abc1160367cb1f6e326f7f39aefd60",
          "message": "feat: make the k3s-cluster tailscale oauth secret references configurable (merges PR #1426, addresses #1425)\n\nThe OCI nodes of the k3s-cluster blueprint read the Tailscale OAuth client\nfrom the hard-coded tailscale.oauth_client_id/secret keys. Add the\nts_oauth_client_id_secret and ts_oauth_client_secret_secret variables,\ndefaulting to those keys, and use them for the control plane and workers.\n\nAddresses #1425\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T15:40:54Z",
          "tree_id": "9db87b09e2bebf6ff31c383d2f74a3a41cc1e604",
          "url": "https://github.com/endavis/infrafoundry/commit/f5c84b9ec1abc1160367cb1f6e326f7f39aefd60"
        },
        "date": 1794843726146,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 72.49887256415191,
            "unit": "iter/sec",
            "range": "stddev: 0.00032743134426614363",
            "extra": "mean: 13.793317945946434 msec\nrounds: 74"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12704.713852190667,
            "unit": "iter/sec",
            "range": "stddev: 0.000006173821739284617",
            "extra": "mean: 78.71094238203331 usec\nrounds: 13711"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a0a17ec2f3a9c0e0c9531e53031bb70529c5f93d",
          "message": "refactor: share the failed-resource marking between apply and destroy (merges PR #1427, addresses #1424)\n\nExtract the duplicated _mark_resources_failed from DeploymentExecutor and\nDestroyOrchestrator into core.failed_resources.mark_resources_failed. The\nonly behavioural difference was the phase word in the warning log, now a\nparameter.\n\nAddresses #1424\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T15:52:54Z",
          "tree_id": "770b5e791bfb22f408b581426ee6e1f7d4c91632",
          "url": "https://github.com/endavis/infrafoundry/commit/a0a17ec2f3a9c0e0c9531e53031bb70529c5f93d"
        },
        "date": 1794844430564,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 58.271115862802425,
            "unit": "iter/sec",
            "range": "stddev: 0.0006649586424925137",
            "extra": "mean: 17.161160983332973 msec\nrounds: 60"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 10728.227106250288,
            "unit": "iter/sec",
            "range": "stddev: 0.00000756672615333176",
            "extra": "mean: 93.21204613737136 usec\nrounds: 12116"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ca06b9ae4376c7f641e5abff43602d59e05379c5",
          "message": "feat: add a state reconcile command for stale planned rows (merges PR #1428, addresses #1423)\n\nfeat: add state reconcile command to supersede stale planned rows\n\nPlans written before #1417 left PLANNED rows on top of ACTIVE rows, so\ninfra deployed showed deployed resources as planned. state reconcile\nappends one ACTIVE row (copying config, terraform_id and extra_data)\nfor each resource whose newest non-PLANNED row is ACTIVE and has newer\nPLANNED rows. The resources table stays append-only (ADR-0018); rows\nare written under one reconcile deployment in a single transaction and\na state_reconciled audit entry is logged. Supports --dry-run and --yes,\nrefuses while a lock is held.\n\nAddresses #1423\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T15:59:29Z",
          "tree_id": "fe19c35926ba8bd2164c4e2d0085ac4fe0f6806a",
          "url": "https://github.com/endavis/infrafoundry/commit/ca06b9ae4376c7f641e5abff43602d59e05379c5"
        },
        "date": 1794844831860,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 46.899269938497085,
            "unit": "iter/sec",
            "range": "stddev: 0.0013336105534493842",
            "extra": "mean: 21.3222935306111 msec\nrounds: 49"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7776.716899423814,
            "unit": "iter/sec",
            "range": "stddev: 0.000009189099842958331",
            "extra": "mean: 128.58896793248206 usec\nrounds: 8295"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "436936262fea3f588267a6d4a2d3a7290c31e3f9",
          "message": "fix: report an aborted confirmation prompt as a cancellation (merges PR #1430, addresses #1429)\n\nclick.confirm raises click.Abort at end of input. with_orchestrator only\nre-raised click.ClickException, so the Abort reached the generic handler\nand was reported as IF-GENERAL-001 Unknown Error with an empty message.\nTreat click.Abort like KeyboardInterrupt: \"Operation cancelled\", non-zero\nexit.\n\nAddresses #1429\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T16:10:52Z",
          "tree_id": "6dfa6d9ef982c34f699765ba6633eafe3f0d6760",
          "url": "https://github.com/endavis/infrafoundry/commit/436936262fea3f588267a6d4a2d3a7290c31e3f9"
        },
        "date": 1794845520960,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 49.51322350970776,
            "unit": "iter/sec",
            "range": "stddev: 0.00041678656213757574",
            "extra": "mean: 20.196624843137833 msec\nrounds: 51"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7932.123319694195,
            "unit": "iter/sec",
            "range": "stddev: 0.000008279438375227244",
            "extra": "mean: 126.06964865475047 usec\nrounds: 8439"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f95b9150dc22d74539b6538e13d0489f32f264d4",
          "message": "feat: support kea dhcpv4 high availability on opnsense (merges PR #1431, addresses #1392)\n\nAdd two direct-API resource types on the kea/dhcpv4 controller:\nkea.dhcp4.ha (singleton: enabled, this_server_name, max_unacked_clients)\nand kea.dhcp4.ha_peers (managed set keyed by peer name: role, url). A new\nKeaHAValidator requires exactly one primary and one standby when HA is\nenabled and that a set this_server_name names a peer; an empty one (each\nnode falls back to its hostname, the CARP-safe choice) is reported as info.\n\nThe HA types dispatch before kea.dhcp4.subnets: saving the dhcpv4 settings\nmakes OPNsense re-run option-data auto-collect on auto_collect subnets,\nand the later subnet write restores explicitly configured options in the\nsame apply.\n\nAddresses #1392\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T16:36:52Z",
          "tree_id": "0dd1702a9b8402c6d9ce1ac578ed74307bfbce37",
          "url": "https://github.com/endavis/infrafoundry/commit/f95b9150dc22d74539b6538e13d0489f32f264d4"
        },
        "date": 1794847069505,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 99.02385615140064,
            "unit": "iter/sec",
            "range": "stddev: 0.00033140229231715785",
            "extra": "mean: 10.098576634614886 msec\nrounds: 104"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 16221.413609787878,
            "unit": "iter/sec",
            "range": "stddev: 0.0000031247200664741793",
            "extra": "mean: 61.64690846651043 usec\nrounds: 16890"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "acb8536e755b1430da34449e30565b31dc7df063",
          "message": "feat: warn when a kea subnet combines auto_collect with explicit options (merges PR #1434, addresses #1432)\n\nOPNsense re-runs Kea option-data auto-collect whenever the Kea DHCPv4\nsettings are saved, overwriting routers, DNS and NTP servers set\nexplicitly on a subnet with auto-collect on. Add a KeaSubnetAutoCollectValidator\nthat warns (never errors) on a kea.dhcp4.subnets entry with\nauto_collect: true and any of routers, dns_servers or ntp_servers set,\nnaming the subnet and keys and suggesting auto_collect: false.\n\nThe warning runs under infra doctor with the other OPNsense validators;\nrunning provider validation on infra plan is tracked in #1433.\n\nAddresses #1432\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T16:50:20Z",
          "tree_id": "4cf1362e5b9b027d7d47c801cbda0619f63344a7",
          "url": "https://github.com/endavis/infrafoundry/commit/acb8536e755b1430da34449e30565b31dc7df063"
        },
        "date": 1794847891275,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 35.1479460325181,
            "unit": "iter/sec",
            "range": "stddev: 0.003521491413783786",
            "extra": "mean: 28.45116465909053 msec\nrounds: 44"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7272.04724591144,
            "unit": "iter/sec",
            "range": "stddev: 0.000019978212213815355",
            "extra": "mean: 137.51285795925344 usec\nrounds: 8399"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "cff4f4aaf86d28aebb63a480aa6225d6d118c015",
          "message": "feat: run providers' offline validation as part of infra plan (merges PR #1436, addresses #1433)\n\ninfra plan, and so infra apply, now runs the network-free part of each\nprovider's validation before any change set is computed. Warnings are\nprinted and the plan continues; errors print the report, mark the\ndeployment failed and raise ConfigValidationError (IF-VALIDATION-007).\n\nProviders opt in through the new ValidatesOffline protocol. OPNsense,\nProxmox, OCI and host split their validate_references into an offline\npart (run on plan) and a live part (doctor only); AWS, ESXi and\nTailscale were already offline. infra doctor runs the same checks as\nbefore. The host SSH probe and OPNsense endpoint support stay out of\nthe plan pass. Kubernetes is left out: its validator was never wired\ninto doctor either (#1435).\n\nRecords the decision in ADR-0023.\n\nAddresses #1433\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T17:25:51Z",
          "tree_id": "ede78daeb335bb2c1dc9bf31eb04390ca42e0f71",
          "url": "https://github.com/endavis/infrafoundry/commit/cff4f4aaf86d28aebb63a480aa6225d6d118c015"
        },
        "date": 1794850010578,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 48.20572019075997,
            "unit": "iter/sec",
            "range": "stddev: 0.0002513125145160559",
            "extra": "mean: 20.744426098039693 msec\nrounds: 51"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7759.021421020285,
            "unit": "iter/sec",
            "range": "stddev: 0.000009505645430869017",
            "extra": "mean: 128.88223214474684 usec\nrounds: 8331"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a9b0f66d3ae0e0fbae1873ea1eee1d6994b8806f",
          "message": "feat: wire kubernetes validation into infra doctor and infra plan (merges PR #1437, addresses #1435)\n\nKubernetesValidator was never called: KubernetesProvider inherited the\nno-op validate_references and validate_connectivity. The provider now\nimplements validate_connectivity, validate_references,\nvalidate_references_in_context and validate_offline (ADR-0023), so\ninfra doctor runs the local and cluster checks and infra plan/apply run\nthe offline ones.\n\nFixes the checks that would otherwise give false errors or crash once\nthey run: a string service selector, non-dict env_from entries, Helm\nrepository required for oci:// and path charts, the CRD check reading\ntop-level apiVersion instead of manifest.apiVersion, and namespaces\ncreated by a Helm release. A kubeconfig that does not exist yet (cluster\ncreated in the same apply) is now a warning.\n\nKubeconfig resolution follows KUBECONFIG, kubeconfig_path, then\n~/.kube/config, as Terraform does. Cluster checks support\nclient-certificate auth (data and file forms) and use inline\ncertificate-authority-data for TLS verification instead of disabling it;\ninline material goes to 0600 files in a private temp directory that is\nremoved after validation.\n\nAddresses #1435\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-16T17:53:51Z",
          "tree_id": "d641227c5eefc558b875b089f962a142a20b695d",
          "url": "https://github.com/endavis/infrafoundry/commit/a9b0f66d3ae0e0fbae1873ea1eee1d6994b8806f"
        },
        "date": 1794851689511,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 106.8529769948324,
            "unit": "iter/sec",
            "range": "stddev: 0.00014188211007978223",
            "extra": "mean: 9.358653620369994 msec\nrounds: 108"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 15958.09960447916,
            "unit": "iter/sec",
            "range": "stddev: 0.00001696122934272291",
            "extra": "mean: 62.66410316923435 usec\nrounds: 17670"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "64893c6053c87b582f030b987149d490d34d2e92",
          "message": "feat: validate carp vhid uniqueness and vip subnet membership (merges PR #1438, addresses #1391)\n\nAdd VirtualIPTopologyValidator, an offline OPNsense validator that runs\non infra plan, apply and doctor (ADR-0023):\n\n- Warn when one CARP VHID is used on more than one interface, naming\n  every VIP involved. The same VHID on one interface is not reported.\n- Error when a CARP VIP address is outside the static network of its\n  interface assignment, unless it is inside an ipalias network on that\n  interface. Skipped when the interface address is not static in config\n  (DHCP, none, track-interface, no assignment), for IPv6 link-local and\n  on an address-family mismatch. ipalias and proxyarp VIPs are not\n  checked, since both are used outside the interface subnet.\n\nVirtualIPValidator is unchanged.\n\nAddresses #1391\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T09:59:12Z",
          "tree_id": "bf7b0b5276cc1a29735a59405d26ed4548ce5dbc",
          "url": "https://github.com/endavis/infrafoundry/commit/64893c6053c87b582f030b987149d490d34d2e92"
        },
        "date": 1794909616705,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 68.38747700488454,
            "unit": "iter/sec",
            "range": "stddev: 0.0010027510109803018",
            "extra": "mean: 14.622560208334276 msec\nrounds: 72"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12822.717987401878,
            "unit": "iter/sec",
            "range": "stddev: 0.000004902712545878663",
            "extra": "mean: 77.98658607188308 usec\nrounds: 13541"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "69fe42df7489223c226924c5a27b34535cf13da1",
          "message": "feat: add opnsense hasync.settings component for ha pairing (merges PR #1439, addresses #1389)\n\nManage System > High Availability > Settings through core/hasync/get,\nset and reconfigure, as the singleton hasync.settings (YAML\nopnsense.hasync.settings, snake_case keys mapped to the 11 wire\nfields). A changed apply writes once and runs one hasync reconfigure\nfrom the hasync_reconfigure finalization hook. Destroy is a no-op.\n\npassword must be a secret:// reference resolved through the shared\nOPNsense secrets helper (a literal is a validation warning); it is\nredacted in plan output, never logged, and exported by config migrate\nonly as a placeholder. If a release stops returning it in clear, it is\ntreated as write-only and is sent with update_password or with another\nchange.\n\nValidation: the offline validator checks keys, types, IPs, the pfsync\nversion and the password form on every plan; infra doctor rejects a\npfsync_interface or sync_items entry the box does not offer, and the\nmanager refuses them at apply before any write.\n\nADR-0013 moves <hasync> into scope; ADR-0014 records the component.\n\nAddresses #1389\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T10:53:39Z",
          "tree_id": "3d09ab268e2a494eb28a9f4ba1471258f8084b6e",
          "url": "https://github.com/endavis/infrafoundry/commit/69fe42df7489223c226924c5a27b34535cf13da1"
        },
        "date": 1794912877917,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 107.01061257232234,
            "unit": "iter/sec",
            "range": "stddev: 0.00015230544165065362",
            "extra": "mean: 9.344867541283882 msec\nrounds: 109"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 16570.991052484915,
            "unit": "iter/sec",
            "range": "stddev: 0.0000030263620450133287",
            "extra": "mean: 60.3464208527253 usec\nrounds: 17638"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f6448a41fc2be49c08c576ea96c26c851b2b3464",
          "message": "feat: trigger opnsense ha config sync after apply (merges PR #1440, addresses #1390)\n\nAfter a successful OPNsense direct-API apply that changed something,\nthe provider's new post_apply_hook reads synchronizetoip from\ncore/hasync/get and, when a backup is set, calls\ncore/hasync_status/version as a preflight and then\ncore/hasync_status/restartAll, the action behind the GUI's\n\"Synchronize and reconfigure all\". It runs once, after the finalization\nhooks, on the success path only. A failure fails the apply with an\nAPIError naming the backup and the endpoint's message.\n\nProvider settings: ha_sync_after_apply (true by default; false turns it\noff; \"always\" also syncs when nothing changed, to re-sync after a failed\nsync) and ha_sync_timeout (300 s; an unreachable backup takes about\n60 s to report). Both are checked by the offline validator.\n\nOPNsense's exec_sync step always reports done, so a failed config push\ninside restartAll is not reported; the docs record this and the source\nand probe evidence. ADR-0014 is amended with the runner's post-apply\nhook.\n\nAddresses #1390\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T11:18:43Z",
          "tree_id": "93ff404503a18477b912a009f49de201f86cd783",
          "url": "https://github.com/endavis/infrafoundry/commit/f6448a41fc2be49c08c576ea96c26c851b2b3464"
        },
        "date": 1794914395049,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 74.6132711279995,
            "unit": "iter/sec",
            "range": "stddev: 0.0004593352204457344",
            "extra": "mean: 13.402441481013401 msec\nrounds: 79"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 14316.822876544593,
            "unit": "iter/sec",
            "range": "stddev: 0.000007643108774453147",
            "extra": "mean: 69.84789912001432 usec\nrounds: 15910"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "adf26ab12f68bb63a9274c163ae74533fd7d61ef",
          "message": "feat: report opnsense carp pair health in infra doctor (merges PR #1443, addresses #1393)\n\ninfra doctor now runs a read-only HA health check for the OPNsense\nprovider. It reads per-VIP CARP state from\ndiagnostics/interface/getVipStatus and synchronizetoip from\ncore/hasync/get and, when a sync target is set, asks the peer for its\nversion through core/hasync_status/version, bounded by ha_sync_timeout.\nIt never calls the carpStatus write endpoint and needs no credentials\nbeyond the primary's.\n\nA node with a sync target is the sync source, so its VIPs are expected\nMASTER. Errors: a sync-source VIP not MASTER, INIT/DISABLED VIPs, mixed\nMASTER/BACKUP on a node of unknown role, CARP disallowed, an unreachable\npeer. Warnings: maintenance mode, demotion, CARP VIPs without a sync\ntarget (role unknown), a peer that answers without a version. A single\nnode with no CARP VIPs and no sync target is silent. A both-MASTER split\ncannot be seen from the primary alone; an unreachable peer while all\nVIPs are MASTER says it cannot be ruled out.\n\nAddresses #1393\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T11:45:28Z",
          "tree_id": "5c6d4556e146d3a06c68614ebd92061a195ea169",
          "url": "https://github.com/endavis/infrafoundry/commit/adf26ab12f68bb63a9274c163ae74533fd7d61ef"
        },
        "date": 1794915987157,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 104.81807190124667,
            "unit": "iter/sec",
            "range": "stddev: 0.00014766867612361106",
            "extra": "mean: 9.540339579439511 msec\nrounds: 107"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 16385.99991700759,
            "unit": "iter/sec",
            "range": "stddev: 0.000006158125487477085",
            "extra": "mean: 61.027706887882125 usec\nrounds: 17843"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "934768c05d6aedbfb4428cf0fa5b1ebfddb64754",
          "message": "fix: resolve opnsense virtual ip interfaces against managed assignments (merges PR #1444, addresses #1441)\n\nVirtualIPValidator read context.managed_interface_names, which the\nvalidator never populated, so a VIP on a config-only interface\nassignment was reported as an unknown interface. Read\ninterface_assignment_names instead and drop the unused context field.\nAdd a regression test that goes through OPNsenseValidator.\n\nAddresses #1441\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T11:55:53Z",
          "tree_id": "b9e19781b99df72cc274761467bc69d18ccbdc51",
          "url": "https://github.com/endavis/infrafoundry/commit/934768c05d6aedbfb4428cf0fa5b1ebfddb64754"
        },
        "date": 1794916621548,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 48.65987090370757,
            "unit": "iter/sec",
            "range": "stddev: 0.0005160357095007269",
            "extra": "mean: 20.550814900000205 msec\nrounds: 50"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7837.823169586497,
            "unit": "iter/sec",
            "range": "stddev: 0.000011259825163611866",
            "extra": "mean: 127.58644567031709 usec\nrounds: 8338"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c445297e3e1db534b726e9fef2354cb1e9683a00",
          "message": "feat: trigger opnsense ha config sync after destroy (merges PR #1445, addresses #1442)\n\nOPNsenseDirectRunner.destroy now calls the provider's post_apply_hook once\nafter all deletes, so the HA backup loses destroyed objects. It honors the\nsame ha_sync_after_apply and ha_sync_timeout settings and skips without a\nsync target. A sync failure fails the destroy with the endpoint's message.\n\nAddresses #1442\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T12:07:14Z",
          "tree_id": "056dc81c7f6f50cfdf34b9ff256b68643822b51f",
          "url": "https://github.com/endavis/infrafoundry/commit/c445297e3e1db534b726e9fef2354cb1e9683a00"
        },
        "date": 1794917310234,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 72.52659552218896,
            "unit": "iter/sec",
            "range": "stddev: 0.0004015574698015804",
            "extra": "mean: 13.788045513511765 msec\nrounds: 74"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12828.084261443984,
            "unit": "iter/sec",
            "range": "stddev: 0.000009844735565400738",
            "extra": "mean: 77.95396254182663 usec\nrounds: 13722"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "0e4023b96f9b506f94205fb0d138a049f9628004",
          "message": "fix: make opnsense ha sync skip line fit destroy (merges PR #1448, addresses #1446)\n\nThe skip line said \"apply changed nothing\" even when the run was a\ndestroy, since both paths share run_ha_sync_after_apply. Reword it to\n\"HA sync skipped: nothing changed\" and update the provider docs list.\n\nAddresses #1446\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T12:18:12Z",
          "tree_id": "c407952d59b5d700a3ad6b72c209fb374b558c71",
          "url": "https://github.com/endavis/infrafoundry/commit/0e4023b96f9b506f94205fb0d138a049f9628004"
        },
        "date": 1794917959884,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 49.912134873520365,
            "unit": "iter/sec",
            "range": "stddev: 0.00018783566276924025",
            "extra": "mean: 20.035207921561476 msec\nrounds: 51"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7951.765390752343,
            "unit": "iter/sec",
            "range": "stddev: 0.00001027299996108404",
            "extra": "mean: 125.75823743026537 usec\nrounds: 8453"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "7c15c84b9a4fd504ba4a11d33ff427ebf30d79ab",
          "message": "fix: report non-terraform runner failures as deployment errors (merges PR #1449, addresses #1447)\n\nraise_on_runner_failure wrapped every failed runner result in\nTerraformError, so a failed opnsense_direct destroy showed\n\"Terraform Execution Failed\" with a terraform init suggestion. It now\ntakes the runner name and raises DeploymentError (IF-RUNNER-003) with a\nrunner-neutral message for runners other than terraform and opentofu.\nTerraform runner failures keep TerraformError.\n\nAddresses #1447\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T12:23:59Z",
          "tree_id": "524758ba52acd44b8a891d7ca436b347bb64d149",
          "url": "https://github.com/endavis/infrafoundry/commit/7c15c84b9a4fd504ba4a11d33ff427ebf30d79ab"
        },
        "date": 1794918310156,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 70.39724721073325,
            "unit": "iter/sec",
            "range": "stddev: 0.0010234632171186029",
            "extra": "mean: 14.205100904109402 msec\nrounds: 73"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12913.786004505133,
            "unit": "iter/sec",
            "range": "stddev: 0.000004387407841856631",
            "extra": "mean: 77.4366246777775 usec\nrounds: 13591"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ea0efa9ea026e44a27faad6b5e5df6e79bcd9316",
          "message": "feat: add an optional sync nic to the opnsense-vm blueprint (merges PR #1454, addresses #1451)\n\nAdd sync_bridge, sync_vlan, sync_ip and sync_prefix inputs. When\nsync_bridge is set, vm.yaml adds a third e1000 NIC (em2) and the\nbootstrap PHP assigns it as opt1 (SYNC) with a static address and pass\nrules for pfsync and HTTPS config sync from the sync subnet. Without\nsync_bridge the VM and bootstrap are unchanged.\n\nAddresses #1451\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T12:51:46Z",
          "tree_id": "fa2cacd14b7f0a56dc840f6e27984fc1a59f1551",
          "url": "https://github.com/endavis/infrafoundry/commit/ea0efa9ea026e44a27faad6b5e5df6e79bcd9316"
        },
        "date": 1794919990663,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 59.695544875442565,
            "unit": "iter/sec",
            "range": "stddev: 0.001045179107299796",
            "extra": "mean: 16.75166885714076 msec\nrounds: 63"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 10696.98642658899,
            "unit": "iter/sec",
            "range": "stddev: 0.000007316989624668761",
            "extra": "mean: 93.4842730579098 usec\nrounds: 12100"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6f6d5b3b4df98f45cec73ce483d4c3c2b9f77c09",
          "message": "docs: use rfc 5737 addresses for every private-range example value (merges PR #1455, addresses #1453)\n\n* docs: use rfc 5737 addresses for example values in blueprints and docs\n\nReplace example addresses from the 172.16.0.0/12 example range with RFC 5737\ndocumentation addresses in 13 blueprint, docs and example-config files, keeping\nsubnets, gateways, DHCP ranges and VIPs consistent within each file.\n\nThe opnsense-vm blueprint's pve_host input no longer has a default: it is a\nper-site value, so a missing value now fails loudly instead of pointing at an\naddress that looks real. The README moves it to the required inputs table.\n\nTest assertions changed to follow the example-config values (no other test\nchanges):\n- tests/unit/test_service_vm_blueprint.py: the two ip_address assertions that\n  load the service-vm example package\n- tests/unit/test_proxmox_k3s_cluster_blueprint.py: the four assertions on the\n  k3s-cluster example package's server_ip and node ip_address values\n\nAddresses #1453\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* docs: use rfc 5737 addresses for every private-range example value\n\nExtends the first commit to all three RFC 1918 ranges across\nblueprints, docs, example-config, source docstrings and test data.\nTest data and the assertions on those values change together; no\ntest was removed, skipped or changed in what it checks. Networks\nlarger than a /24 map to a documentation /24 with their subnets\nsplit inside it.\n\nKept: Unbound private-address list definitions and their tests, the\nk3s default cluster and service CIDRs, and the RFC 1918 block\nadvertised as a Tailscale route.\n\nAddresses #1453\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T13:24:44Z",
          "tree_id": "acaccb576abe41910281abf549fa11395992a8a3",
          "url": "https://github.com/endavis/infrafoundry/commit/6f6d5b3b4df98f45cec73ce483d4c3c2b9f77c09"
        },
        "date": 1794921954279,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 61.291112520462825,
            "unit": "iter/sec",
            "range": "stddev: 0.0005879920548564226",
            "extra": "mean: 16.315579190476225 msec\nrounds: 63"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 11015.84523509577,
            "unit": "iter/sec",
            "range": "stddev: 0.00000955849836185924",
            "extra": "mean: 90.77832691531148 usec\nrounds: 12465"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1ee8c091079e1e9d9638df6e0b7609166ccd1816",
          "message": "feat: support more than one opnsense firewall per environment (merges PR #1456, addresses #1450)\n\nEach extra firewall is a provider instance with id opnsense@<name>; the\nprimary keeps the plain opnsense id, so flat api_url/api_key/api_secret\nconfigs and existing state rows are unchanged and no state migration is\nneeded. Settings take a firewalls map plus primary; resources select a\nfirewall per entry, per file, or per package manifest. Plan, apply,\ndestroy and doctor run once per firewall with labelled output, infra\ncommands gain --firewall, and ha_backup enables a CARP pair check in\ninfra doctor. Adds ADR-0024 and amends ADR-0013/0014/0016/0018/0023.\n\nAddresses #1450\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T13:29:51Z",
          "tree_id": "22cb54ebc15c5262dfe5e378a624d6de3fe3a9ab",
          "url": "https://github.com/endavis/infrafoundry/commit/1ee8c091079e1e9d9638df6e0b7609166ccd1816"
        },
        "date": 1794922249480,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 47.51319791067437,
            "unit": "iter/sec",
            "range": "stddev: 0.00026475787829233",
            "extra": "mean: 21.04678371428539 msec\nrounds: 49"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7794.049199550787,
            "unit": "iter/sec",
            "range": "stddev: 0.000013044414906656877",
            "extra": "mean: 128.30301354238762 usec\nrounds: 8418"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "3cad8c41828ea2643287736097e3bda7e055a3be",
          "message": "feat: update opnsense firmware through system.firmware (merges PR #1457, addresses #1452)\n\nAdd an opt-in minor firmware update to the system.firmware component.\nWith update: true, plan runs a firmware check and shows a pending update\nas a change. Apply starts the update, waits for the job and any reboot\n(update_timeout, default 1800 s), verifies the version, and does this\nbefore plugin installs so a fresh box can install plugins in one run.\nWithout update, behavior is unchanged. Major upgrades are not supported.\n\nAddresses #1452\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T13:35:16Z",
          "tree_id": "6c703949f79a44fae3bc70d4fda15e8bb57300fe",
          "url": "https://github.com/endavis/infrafoundry/commit/3cad8c41828ea2643287736097e3bda7e055a3be"
        },
        "date": 1794922577314,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 73.03316510839332,
            "unit": "iter/sec",
            "range": "stddev: 0.0006099336458690218",
            "extra": "mean: 13.692409448718733 msec\nrounds: 78"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 13909.381516874968,
            "unit": "iter/sec",
            "range": "stddev: 0.000005039335600915736",
            "extra": "mean: 71.89392273026607 usec\nrounds: 15530"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "96f56cca8f281e852d5f95b7e4a32de1d7e733ff",
          "message": "fix: resolve templates by provider type for non-primary opnsense firewalls (merges PR #1463, addresses #1462)\n\nA non-primary firewall's provider is named opnsense@<name> (#1450).\nTemplate lookups used that name, so its Terraform generation failed with\n\"Template not found: opnsense@<name>/provider.tf.j2\". The templates\ndirectory and the default provider, variables and outputs templates now\nresolve by provider type.\n\nget_terraform_env_vars read the flat opnsense settings, which a\nfirewalls: map does not have, so no TF_VAR_opnsense_* was set for any\nfirewall. It now reads each firewall's own settings, and OPNSENSE_* env\noverrides reach only the primary. reset_kea_dhcpv4/6 use the provider's\nown name instead of \"opnsense\".\n\nGenerated directories and local Terraform state stay per instance on\npurpose; the primary keeps generated/<env>/terraform/opnsense/.\n\nAddresses #1462\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T14:20:25Z",
          "tree_id": "bf9c30b0513da39a2f4923cc9e63f018c0038ca9",
          "url": "https://github.com/endavis/infrafoundry/commit/96f56cca8f281e852d5f95b7e4a32de1d7e733ff"
        },
        "date": 1794925282105,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 59.818107780031255,
            "unit": "iter/sec",
            "range": "stddev: 0.00050176834780563",
            "extra": "mean: 16.71734591935428 msec\nrounds: 62"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 11266.642305500965,
            "unit": "iter/sec",
            "range": "stddev: 0.000007607486424509565",
            "extra": "mean: 88.7575883643477 usec\nrounds: 12307"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c3b26fad0505d302d9cd0c5a5078147cc7835557",
          "message": "fix: target the sync interface address in the opnsense-vm sync https rule (merges PR #1468, addresses #1466)\n\nfix: use the symbolic opt1ip destination for the opnsense-vm sync https rule\n\nThe bootstrap's HTTPS rule on the sync interface wrote the node's sync\naddress as a literal destination. With rules in sync_items, the primary's\nrule replaced the backup's, so the backup stopped accepting config sync on\nits own address. Use the symbolic opt1ip network, as the LAN rule does with\nlanip, so the rule means \"this node's sync address\" on both nodes.\n\nExisting VMs need a rebuild or a managed replacement rule; the README says so.\n\nAddresses #1466\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T15:38:23Z",
          "tree_id": "90ed14b5cf2a4967990e359893a30b82b8b1209c",
          "url": "https://github.com/endavis/infrafoundry/commit/c3b26fad0505d302d9cd0c5a5078147cc7835557"
        },
        "date": 1794929973153,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 68.08129176697047,
            "unit": "iter/sec",
            "range": "stddev: 0.0008688155346630287",
            "extra": "mean: 14.688322945205169 msec\nrounds: 73"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12783.45962347607,
            "unit": "iter/sec",
            "range": "stddev: 0.000005216725283264503",
            "extra": "mean: 78.2260850703951 usec\nrounds: 13624"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "9d3c58a0d55bc90638fa3391414d9470d393e795",
          "message": "fix: send combined network and check results for opnsense virtual ip writes (merges PR #1469, addresses #1465)\n\nOPNsense's VipSettingsController reads vip.network as \"<address>/<bits>\"\nand splits it into the subnet and subnet_bits model fields. The service\nsent the bare prefix length, so adds were rejected, and because add,\nupdate and delete never checked the result the apply reported success\nand the plan never converged.\n\n- send network as \"<address>/<bits>\" in to_payload (YAML shape unchanged)\n- read live rows via subnet/subnet_bits (searchItem address is combined)\n  and getItem network, so the diff key uses the bare address\n- compare network in combined form in _needs_update\n- raise APIError with the validations when add, update or delete fail\n\nExisting tests changed (wire/row format only, same behavior tested):\n- test_virtual_ip_service.py _live helper raw row: address \"A\" -> \"A/24\";\n  network \"24\" -> subnet \"A\" + subnet_bits \"24\"\n- TestPayloadProxyArp.test_proxyarp_minimal_fields: network == \"24\" ->\n  \"192.0.2.10/24\"\n- TestExportToYaml.test_ipalias_exports: searchItem row address\n  \"192.0.2.10\" -> \"192.0.2.10/24\", network \"24\" -> subnet + subnet_bits;\n  getItem network \"24\" -> \"192.0.2.10/24\"\n- TestExportToYaml.test_carp_export_redacts_password: same reshaping with\n  192.0.2.1 (row) and getItem network \"24\" -> \"192.0.2.1/24\"\n- TestLiveToExportConfig.test_ipalias_decoding, ...proxyarp_no_extra_fields:\n  getItem network \"24\" -> \"192.0.2.10/24\"\n- TestLiveToExportConfig.test_carp_decoding_password_placeholder: getItem\n  network \"24\" -> \"192.0.2.1/24\"\n- test_virtual_ip_manager.py _live helper raw row: address \"A\" -> \"A/24\";\n  network \"24\" -> subnet \"A\" + subnet_bits \"24\"\n\nAddresses #1465\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T15:43:14Z",
          "tree_id": "940c2262f1501094c142749060a9cd5d59545700",
          "url": "https://github.com/endavis/infrafoundry/commit/9d3c58a0d55bc90638fa3391414d9470d393e795"
        },
        "date": 1794930256521,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 48.82811365126272,
            "unit": "iter/sec",
            "range": "stddev: 0.0002150512689564955",
            "extra": "mean: 20.480004760006523 msec\nrounds: 50"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7863.175302665192,
            "unit": "iter/sec",
            "range": "stddev: 0.000009636027706480924",
            "extra": "mean: 127.17508659142496 usec\nrounds: 8338"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "5fcfd4b0c2979108834b1be9ef9de8611582b443",
          "message": "fix: run terraform non-interactively so missing variables fail fast (merges PR #1471, addresses #1467)\n\nfix: pass -input=false and close stdin for terraform runner commands\n\nTerraform prompts on stdin for a required variable with no value, so a\nplan or apply with a missing TF_VAR hung and held the state lock. Add\n-input=false to init, plan, apply and destroy, and give every runner\nsubprocess stdin=DEVNULL as defence in depth. Commands that reject the\nflag (state, validate, show, version) get only the stdin change.\n\nAddresses #1467\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T17:31:33Z",
          "tree_id": "f6253618e094debb70e0644df6451648ba4f6085",
          "url": "https://github.com/endavis/infrafoundry/commit/5fcfd4b0c2979108834b1be9ef9de8611582b443"
        },
        "date": 1794936761140,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 73.72536588220413,
            "unit": "iter/sec",
            "range": "stddev: 0.0006616068435950887",
            "extra": "mean: 13.563852658225745 msec\nrounds: 79"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 14520.211121140983,
            "unit": "iter/sec",
            "range": "stddev: 0.000003999845438132879",
            "extra": "mean: 68.86952205151003 usec\nrounds: 16144"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "43ac354740fd27671e963f60a2dd3cab5a7b6a24",
          "message": "feat: apply a fresh opnsense box in one run with a firmware update (merges PR #1472, addresses #1458)\n\n* feat: defer version-gated opnsense types behind a firmware update\n\nWith system.firmware update: true in the run, a type the box's current\nversion cannot serve (an endpoint-support error or an\nUnsupportedVersionError from its manager) no longer fails the whole\nplan. The plan lists it as deferred, apply runs every other type first,\nthen re-checks the deferred types against the updated box and applies\nthem; one still unsupported fails with the normal error. Without\nupdate: true behaviour is unchanged. Gateway ordering is not changed:\na firmware update ran fine before the gateway existed.\n\nAddresses #1458\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* feat: set the gateway before a firmware update in one apply\n\nWith system.firmware update: true in the run, the forward pass applies\ninterfaces.vlans, interfaces.assignments and routing.gateways first, then\nsystem.firmware, then every other type in table order, then the deferred\ntypes. The update needs internet access, which the gateway provides.\nWithout update: true the order is unchanged, and the delete pass keeps\nreverse table order.\n\nAddresses #1458\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T17:41:18Z",
          "tree_id": "785fd21419cd6bf3d6afe15fc3df888774066329",
          "url": "https://github.com/endavis/infrafoundry/commit/43ac354740fd27671e963f60a2dd3cab5a7b6a24"
        },
        "date": 1794937342121,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 70.77962318989941,
            "unit": "iter/sec",
            "range": "stddev: 0.000383228533402573",
            "extra": "mean: 14.128360041095906 msec\nrounds: 73"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12717.618103965853,
            "unit": "iter/sec",
            "range": "stddev: 0.000005093286251529089",
            "extra": "mean: 78.631076340322 usec\nrounds: 13597"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c5b4a6a239f18a1d00bb854e5c9edf33fb823c58",
          "message": "fix: check a declared ha_backup node as a carp backup in doctor (merges PR #1473, addresses #1470)\n\nA firewall that another entry names as its ha_backup now has every CARP\nVIP expected BACKUP (MASTER is an error) and no longer gets the\nrole-unknown warning. Single firewalls and primaries are unchanged.\n\nAddresses #1470\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T17:46:42Z",
          "tree_id": "b2a369b858159302caa7331ae0cb1ede2fb77c4d",
          "url": "https://github.com/endavis/infrafoundry/commit/c5b4a6a239f18a1d00bb854e5c9edf33fb823c58"
        },
        "date": 1794937670400,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 44.22600253629417,
            "unit": "iter/sec",
            "range": "stddev: 0.0004136369909907259",
            "extra": "mean: 22.61113242553061 msec\nrounds: 47"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7750.423318537343,
            "unit": "iter/sec",
            "range": "stddev: 0.00000988976573526522",
            "extra": "mean: 129.02521048214427 usec\nrounds: 8338"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "063c86be758c41c54e8a6b6cf010c8f69ad61291",
          "message": "fix: scope the blueprint requirements check to the targeted resources (merges PR #1475, addresses #1461)\n\nfix: scope the blueprint requirements check to targeted resources\n\nThe requirements preflight narrowed by package and provider only, so\n`-r/--resource` still checked every blueprint in the environment and an\nunrelated blueprint's missing package blocked the run. Pass the resource\nfilter through ensure/check/sync and keep only blueprints whose packages\ndeclare a targeted resource. `deps check` and `deps sync` gain -r/--resource.\n\nAddresses #1461\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T18:25:58Z",
          "tree_id": "4a7cc243e5812022f63bffd5b255389f5943a395",
          "url": "https://github.com/endavis/infrafoundry/commit/063c86be758c41c54e8a6b6cf010c8f69ad61291"
        },
        "date": 1794940021769,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 92.63312929008782,
            "unit": "iter/sec",
            "range": "stddev: 0.0008967869676032461",
            "extra": "mean: 10.795273868687113 msec\nrounds: 99"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 15642.244954402031,
            "unit": "iter/sec",
            "range": "stddev: 0.000003335638552713203",
            "extra": "mean: 63.929442539421466 usec\nrounds: 16681"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "864973e9e12f8bedce549115a09e02593d935127",
          "message": "fix: give each provider its own remote terraform state location (merges PR #1476, addresses #1464)\n\nProviders in one environment all rendered the same backend key, prefix\nor workspace name, so they overwrote or locked each other's state.\n\nWith one backend-rendering provider the configured location is\nunchanged. With several, the provider id is inserted per backend type\n(s3/azurerm key path, gcs prefix, remote workspace, postgres schema).\nbackend.bare_key_provider pins one provider to the bare location, and a\n{provider} placeholder overrides the automatic rule. A warning names the\nprovider, old and new location and the terraform init -migrate-state\nsteps whenever the automatic rule moves a location. State is never moved\nsilently. The local backend is unaffected.\n\nAdds ADR-0025 and documents the rule, the pin, the placeholder and the\nmigration steps.\n\nAddresses #1464\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-17T18:55:16Z",
          "tree_id": "abd190aae0cdb805a5109068f9476f3e9768431e",
          "url": "https://github.com/endavis/infrafoundry/commit/864973e9e12f8bedce549115a09e02593d935127"
        },
        "date": 1794941767308,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 105.7184186024581,
            "unit": "iter/sec",
            "range": "stddev: 0.0003126074210270902",
            "extra": "mean: 9.459089657407613 msec\nrounds: 108"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 16768.14398001911,
            "unit": "iter/sec",
            "range": "stddev: 0.0000033604862941220772",
            "extra": "mean: 59.6368925023305 usec\nrounds: 17405"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "b18a2cc2dbfaf8c51af537d9f588e99add9440f9",
          "message": "fix: refuse a plan that reuses an orphaned resource's vm id (merges PR #1477, addresses #1459)\n\nRenaming a blueprint VM package left the old resource in Terraform state:\na scoped plan showed only an add, and the apply collided on the vmid while\nthe old VM kept running.\n\nPlan now compares the provider's state with the addresses the current\npackages generate. State entries no package declares are reported as\norphans, with a warning on both filtered and unfiltered runs. When a new\nresource would take the VM id of an orphan, plan (and so apply) stops with\nIF-VALIDATION-008, naming both addresses and the destroy command. The check\nonly reads state (state list, and show -json when needed); drift detection\ndoes not run it.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-18T09:42:06Z",
          "tree_id": "d38348d9bc21bacfe32fd2fb5c333273e6fe9b5b",
          "url": "https://github.com/endavis/infrafoundry/commit/b18a2cc2dbfaf8c51af537d9f588e99add9440f9"
        },
        "date": 1794994997448,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 69.13315302201295,
            "unit": "iter/sec",
            "range": "stddev: 0.0008019845551157208",
            "extra": "mean: 14.464840041095568 msec\nrounds: 73"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12627.285440841122,
            "unit": "iter/sec",
            "range": "stddev: 0.00000923751183329936",
            "extra": "mean: 79.19358477204017 usec\nrounds: 13554"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c2c1e1e965348b1053ab1d972f940d8c413161a9",
          "message": "feat: let hasync.settings reset a node to ha sync off (merges PR #1478, addresses #1460)\n\nAdd a `reset: true` key to hasync.settings. It writes the defaults for the\nsync target, credentials, pfsync peer and interface, pfsync version and sync\nitems, and clears the stored password. A node already at defaults plans clean.\nThe password is only ever shown as [REDACTED]. Removing the block does not\nreset; `reset: true` is the explicit form.\n\nAddresses #1460\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-18T10:09:22Z",
          "tree_id": "39174045b9c7122ce44f5d03d06b41e6b8dd4939",
          "url": "https://github.com/endavis/infrafoundry/commit/c2c1e1e965348b1053ab1d972f940d8c413161a9"
        },
        "date": 1794996625962,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 49.330800510767574,
            "unit": "iter/sec",
            "range": "stddev: 0.0007657782948440093",
            "extra": "mean: 20.271311019607865 msec\nrounds: 51"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7957.625781460773,
            "unit": "iter/sec",
            "range": "stddev: 0.000010382784306327701",
            "extra": "mean: 125.66562282053317 usec\nrounds: 8431"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "412384760f52b6bd8d31347f5275bbae1c5ae0d2",
          "message": "feat: sync a rebuilt opnsense ha backup when the primary is unchanged (merges PR #1479, addresses #1474)\n\nWith ha_sync_after_apply: true and a no-op apply, compare the primary's\nCARP VIPs (vhid and subnet) with the declared ha_backup firewall. Sync\nwhen the backup is missing one, and skip with a message naming the case\notherwise. An unreadable backup skips with a warning. false and \"always\"\nare unchanged.\n\nAddresses #1474\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-18T10:18:13Z",
          "tree_id": "384fe177e4475bc9907999468fe9b42057b96627",
          "url": "https://github.com/endavis/infrafoundry/commit/412384760f52b6bd8d31347f5275bbae1c5ae0d2"
        },
        "date": 1794997156390,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 67.79519866936505,
            "unit": "iter/sec",
            "range": "stddev: 0.0008164170795493688",
            "extra": "mean: 14.75030709588989 msec\nrounds: 73"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12945.511497088604,
            "unit": "iter/sec",
            "range": "stddev: 0.00000529637788661689",
            "extra": "mean: 77.24685117501122 usec\nrounds: 13788"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "b84038cba928486402120706e650447d37ee3fec",
          "message": "feat: add a read-only mikrotik routeros provider (merges PR #1484, addresses #1480)\n\n* feat: add a read-only mikrotik routeros provider\n\nAdd a `mikrotik` provider for RouterOS 7, managed natively over the REST\nAPI by a new direct runner (`mikrotik_rest`). ADR-0026 records why it is\nnative rather than generated Terraform: enabling bridge vlan-filtering\nsafely needs phased ordering that one parallel Terraform graph cannot\nexpress, and existing objects are adopted without imports.\n\nThis first part covers settings and secrets, the REST client, offline\nand doctor validation, and a read-only `infra plan` for seven resource\ntypes. The plan shows the diff, the apply phase order and the lock-out\nrefusals, including for a management address held by a DHCP lease. It\nalso wires `infra drift detect` to direct runners that support drift.\n`infra apply` and `infra destroy` fail with a pointer to #1483, which\nadds the write side.\n\nAddresses #1480\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* test: assert the exact unresolvable-host refusal message\n\nAddresses #1480\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-18T12:39:44Z",
          "tree_id": "08df3ae5b511a59b1fd78833ff1a07fb7421a74a",
          "url": "https://github.com/endavis/infrafoundry/commit/b84038cba928486402120706e650447d37ee3fec"
        },
        "date": 1795005641279,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 57.97785655203291,
            "unit": "iter/sec",
            "range": "stddev: 0.0009150202438149155",
            "extra": "mean: 17.247964300000262 msec\nrounds: 60"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 10682.830635943368,
            "unit": "iter/sec",
            "range": "stddev: 0.000006710229265369921",
            "extra": "mean: 93.60814882110064 usec\nrounds: 11282"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "12dcd5fca6b7b6d271d17586f344b7615f5d066b",
          "message": "feat: add apply and destroy to the mikrotik routeros provider (merges PR #1486, addresses #1483)\n\nApply runs the plan's phased steps (filtering off, creates and member\nunions, filtering on, narrowing and updates, deletes, services) over the\nRouterOS REST write verbs and stops at the first error, naming the failed\nstep and the steps already done. Refusals are re-checked before any write.\nabsent: true and managed-set deletes follow ADR-0018, and released rows\nare reported. Destroy deletes only declared, deletable objects and is\nrefused whole when it would remove the management path. The runner gains\nmanaged-set dispatch and resource ids.\n\nUnit-tested against a fake RouterOS client for #1483; live verification\nagainst a CHR VM follows separately.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-18T13:02:25Z",
          "tree_id": "c96326a8b847a59af8a92c58f7ca40650d9f8754",
          "url": "https://github.com/endavis/infrafoundry/commit/12dcd5fca6b7b6d271d17586f344b7615f5d066b"
        },
        "date": 1795007017366,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 67.94914294829431,
            "unit": "iter/sec",
            "range": "stddev: 0.00154500229035672",
            "extra": "mean: 14.716889082191175 msec\nrounds: 73"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 13038.882497734772,
            "unit": "iter/sec",
            "range": "stddev: 0.000005233149452120284",
            "extra": "mean: 76.69368906221287 usec\nrounds: 13842"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "41c6f9402123ef049b042c4ac52c1a6fbaf2177c",
          "message": "feat: add a routeros chr test blueprint with .img.zip disk import (merges PR #1487, addresses #1485)\n\nProxmox disk-image import accepts .img.zip: the validator allows it, and\nthe image phase extracts the single .img member with python3 zipfile on\nthe host (no unzip there), with sha256 checked against the archive. The\n.bz2 render is unchanged.\n\nThe routeros-chr blueprint imports MikroTik's CHR image, attaches a\nmanagement NIC and trunk NICs, and bootstraps over the serial console:\nadmin password, identity, optional static address, www service. The\nexpect script answers each password prompt once, because RouterOS\nredraws the new-password line; it runs with log_user 0 and scrubs the\npassword from its log file, and the role shows only status lines.\n\nVerified live for #1485 against RouterOS 7.25.1 CHR: apply, REST with the\nbootstrapped credentials, destroy.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-18T14:53:43Z",
          "tree_id": "388bc6e65158802a9714a6f95b80f6c0361733b0",
          "url": "https://github.com/endavis/infrafoundry/commit/41c6f9402123ef049b042c4ac52c1a6fbaf2177c"
        },
        "date": 1795013684402,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 63.11773917422827,
            "unit": "iter/sec",
            "range": "stddev: 0.0010654511643833939",
            "extra": "mean: 15.84340651428643 msec\nrounds: 70"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12492.360049999876,
            "unit": "iter/sec",
            "range": "stddev: 0.000010644556007788994",
            "extra": "mean: 80.04892558312149 usec\nrounds: 13720"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2c4bdc0aa126869cf41a1058a6a436f8f21a53de",
          "message": "docs: record live verification of the mikrotik provider (merges PR #1490, addresses #1489)\n\nThe provider page and ADR-0026 said live verification on a RouterOS CHR\nwas pending. It ran (#1483, on the routeros-chr blueprint from #1485), so\nthe note now lists what was verified and keeps console access only as a\nprecaution for new hardware. Addresses #1489.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-18T15:10:53Z",
          "tree_id": "1eab55bcf49815a51d30eaa612313b2568eb6a05",
          "url": "https://github.com/endavis/infrafoundry/commit/2c4bdc0aa126869cf41a1058a6a436f8f21a53de"
        },
        "date": 1795014724719,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 49.349360122338105,
            "unit": "iter/sec",
            "range": "stddev: 0.00013106604144472108",
            "extra": "mean: 20.26368725999646 msec\nrounds: 50"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7768.695369197507,
            "unit": "iter/sec",
            "range": "stddev: 0.000009727292919533966",
            "extra": "mean: 128.7217418725093 usec\nrounds: 8275"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "71457a314113800ae4fa5ab618cbb04eb1a982f9",
          "message": "fix: plan drift in the environment's terraform dir and isolate provider failures (merges PR #1491, addresses #1488)\n\nDriftDetector called set_environment only on the direct-runner path, so\nevery Terraform provider was planned in the env-less generated/terraform/\n<provider> directory and failed. One try block also wrapped the whole\nprovider loop, so the first failure stopped drift detection for every\nprovider after it.\n\nThe Terraform path now sets the environment before planning, and each\nprovider is checked in its own handler: a failure is recorded as that\nprovider's result (parsed False, has_changes False) with a warning, and\nthe loop continues. KeyboardInterrupt and SystemExit still propagate.\n\nTwo existing tests in test_drift_detector.py get set_environment on their\nSimpleNamespace provider stubs (approved); their assertions are unchanged.\n\nAddresses #1488.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-18T15:29:07Z",
          "tree_id": "6fc4754e81e3952c7dadd2678349f0e3d4821bb0",
          "url": "https://github.com/endavis/infrafoundry/commit/71457a314113800ae4fa5ab618cbb04eb1a982f9"
        },
        "date": 1795015818682,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 48.74339512738474,
            "unit": "iter/sec",
            "range": "stddev: 0.0004206657862148111",
            "extra": "mean: 20.515600060000452 msec\nrounds: 50"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7926.5271377394265,
            "unit": "iter/sec",
            "range": "stddev: 0.000008443040605072993",
            "extra": "mean: 126.15865468230655 usec\nrounds: 8372"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f1f9a52930972418fdff489f85b330ff1fe6ecb5",
          "message": "feat: back up unmanaged network device configs with read-only collectors (merges PR #1492, addresses #1481)\n\nAdd `foundry infra collect --env <env> [-d <device>]`. It reads the\nconfiguration of devices InfraFoundry does not manage and writes it to the\nconfig repo. It never writes to a device.\n\n- Collectors:\n  - huawei-ont-web: one login attempt per run, never retried, always logs out.\n  - routeros-rest: /export terse, reusing the MikroTik client.\n  - openwrt-ssh: uci export with keys redacted, ip addr/route, system facts;\n    key auth with strict host-key checking.\n- Config: a `collectors:` section in envs/<env>/settings.yaml, with\n  secret://env_secrets/... credential references resolved per device.\n- Output: device-configs/<env>/<device>/. Secret-bearing exports are\n  SOPS-encrypted whole-file (binary); plaintext exists only in a temp dir\n  that is always removed. A missing .sops.yaml creation rule gives a clear\n  error.\n- Change detection: compares plaintext hashes, decrypting the previous\n  file in memory, so unchanged files are not rewritten. Volatile content is\n  masked for the comparison: the RouterOS export timestamp, ip addr\n  lifetimes, and the ONT's re-salted $2...$ secrets and host-table runtime\n  attributes.\n- One device's failure does not stop the others.\n- ADR-0027, a guide, the CLI reference and AGENTS.md describe the feature.\n\nAddresses #1481.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-18T15:59:21Z",
          "tree_id": "a94707f4c7235e3104c32af815b9036376e1a479",
          "url": "https://github.com/endavis/infrafoundry/commit/f1f9a52930972418fdff489f85b330ff1fe6ecb5"
        },
        "date": 1795017619035,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 98.01780297355688,
            "unit": "iter/sec",
            "range": "stddev: 0.00044686782441929053",
            "extra": "mean: 10.20222826530583 msec\nrounds: 98"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 16415.362321389497,
            "unit": "iter/sec",
            "range": "stddev: 0.000005681747341418997",
            "extra": "mean: 60.91854571476519 usec\nrounds: 18167"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "4f52dc4d76e88201778624a01acedafe229b9bc2",
          "message": "feat: add an openwrt test vm blueprint with .img.gz disk import (merges PR #1494, addresses #1493)\n\n* feat: add an openwrt test vm blueprint with .img.gz disk import\n\nBuild a stock OpenWrt test VM through InfraFoundry (#1493):\n\n- disk_image_source accepts .img.gz; the template derives the raw image\n  name from the suffix and decompresses with gunzip\n- new openwrt-vm blueprint: imports the stock x86-64 image, bootstraps\n  over the serial console with expect (LAN address, SSH key, key-only\n  dropbear, LAN DHCP/RA/DHCPv6/NDP off) and waits for the SSH banner\n- the bootstrap reconnects while the serial socket refuses connections,\n  waits for procd init complete before changing anything, and sends the\n  SSH key in 64-character chunks with a length check, because the\n  console drops characters from long lines\n- log_file -a, so the expect transcript is actually recorded\n- example consumer, README and Proxmox docs\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* fix: press enter again when the openwrt console drops the first keypress\n\nOn a rebuild the bootstrap timed out after boot: the Enter sent once the\nconsole went quiet produced no output, so no prompt ever came (#1493).\nPress Enter again every 10 seconds until the prompt shows or the boot\ndeadline passes; covered by a fake console that drops the first Enter.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-19T10:33:04Z",
          "tree_id": "7d84366796d0c541b51fce2c58a672c9cf4b6d6d",
          "url": "https://github.com/endavis/infrafoundry/commit/4f52dc4d76e88201778624a01acedafe229b9bc2"
        },
        "date": 1795084439748,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 97.54250725374438,
            "unit": "iter/sec",
            "range": "stddev: 0.0002129962087104053",
            "extra": "mean: 10.251940699029067 msec\nrounds: 103"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 15221.269928819567,
            "unit": "iter/sec",
            "range": "stddev: 0.00001532171128111255",
            "extra": "mean: 65.69754065701346 usec\nrounds: 17168"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "745f08a214a45ec8060db234e6957ff0cf40cf12",
          "message": "feat: add an openwrt provider driven by community.openwrt playbooks (merges PR #1496, addresses #1482)\n\n* feat: add an openwrt provider driven by community.openwrt playbooks\n\nManage an OpenWrt device through generated community.openwrt playbooks\nrun by a dedicated OpenWrtAnsibleRunner (#1482):\n\n- network.interface, dhcp.pool, dhcp.host and firewall.redirect\n  resources, staged with the uci module and matched without renaming\n  sections made in the vendor UI\n- plan and drift run the playbook with --check --diff and parse the\n  ansible.posix.json callback output\n- apply commits through an rpcd session with ubus uci apply rollback,\n  reconnects, then confirms; an unreachable device reverts by itself\n- management-path changes are refused unless confirmed\n- providers can declare Ansible collections; deps check and deps sync\n  report and install them\n- host-key checking is forced on over the environment\n- ADR-0028 and the provider docs\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* fix: replay staged openwrt changes into the rpcd session over ubus\n\nThe commit tail handed CLI-staged changes to the rpcd session by copying\nthem into /var/run/rpcd/uci-<session id>. On stock OpenWrt 25.12 rpcd no\nlonger names that directory after the session id and does not expose it,\nso apply committed nothing (#1482).\n\n- a packaged ucode helper replays cursor().changes() as ubus uci\n  add/set/delete calls on the session, maps anonymous sections, rebuilds\n  lists, refuses unsupported ops and reverts the CLI staging\n- the helper is named after the session id and removes itself before the\n  apply; the rescue reverts CLI and session staging\n- every connection checks the host key under the settings address\n  (HostKeyAlias), so the reconnect after a management-address change\n  stays strictly checked; the address must be a plain host name or IP\n- docs and ADR-0028 record the 25.12 finding and the live verification\n  on stock OpenWrt 25.12.6\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* test: add check-mode output recorded on stock openwrt as fixtures\n\nTwo ansible.posix.json documents recorded with --check --diff against\nstock OpenWrt 25.12.6, addresses and paths replaced with documentation\nvalues (#1482): a pool change, new lease and new port forward, and a LAN\naddress change that the management check must refuse without the flag.\nThe recording shows the collection reports an empty `before` for a\nsection matched with `find` in check mode, and full sections in the diff.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-19T10:40:29Z",
          "tree_id": "cde5cfb8e8103fb8b5d0a5aa897f75810657cbe5",
          "url": "https://github.com/endavis/infrafoundry/commit/745f08a214a45ec8060db234e6957ff0cf40cf12"
        },
        "date": 1795084904620,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 70.46075668494916,
            "unit": "iter/sec",
            "range": "stddev: 0.0004373480981440357",
            "extra": "mean: 14.192297202701003 msec\nrounds: 74"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12962.85330260542,
            "unit": "iter/sec",
            "range": "stddev: 0.0000047252386415564845",
            "extra": "mean: 77.14350973940351 usec\nrounds: 13707"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "63c3263f31c83b64c090b4636826b77cadeeaa2f",
          "message": "fix: see opnsense interface assignments whose device is absent (merges PR #1500, addresses #1499)\n\nInterfaceAssignmentService.list() read only interfaces/overview/interfacesInfo,\nwhich omits an assignment whose device does not currently exist (a stopped\nTailscale, OpenVPN or WireGuard tunnel). Plan then showed the existing\nassignment as an add and destroy skipped it, leaving it in config.xml.\n\nlist() now keeps the interfacesInfo rows unchanged and appends every\nlan/wan/optN assignment the controller's config-backed searchItem returns that\ninterfacesInfo lacks. Without the controller (a 404 or 403 from searchItem) it\nlogs a warning and falls back to interfacesInfo alone, so plan still needs only\nthe API. The two TestServiceList tests that asserted a single interfacesInfo\ncall now assert both calls, as approved.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-19T14:05:57Z",
          "tree_id": "b08a96baad766676f602dbda4bb6c53759a52da7",
          "url": "https://github.com/endavis/infrafoundry/commit/63c3263f31c83b64c090b4636826b77cadeeaa2f"
        },
        "date": 1795097216490,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 57.50155064626595,
            "unit": "iter/sec",
            "range": "stddev: 0.00053145803016603",
            "extra": "mean: 17.39083535593206 msec\nrounds: 59"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 10824.548800469676,
            "unit": "iter/sec",
            "range": "stddev: 0.000005361795205173726",
            "extra": "mean: 92.38260350922064 usec\nrounds: 11342"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "5fbdea1a1b3bbe986359430cc446eee6010e04c5",
          "message": "docs: correct the stale tailscale endpoint verification comment (merges PR #1501, addresses #1498)\n\nThe subnet add, set and del actions and service/reconfigure were confirmed\nlive, so drop the \"ASSUMED\" note and point at the resource coverage doc.\n\nAddresses #1498\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-19T16:21:19Z",
          "tree_id": "6bda829a294430ce5dcf3cf87a4b323edc7542d8",
          "url": "https://github.com/endavis/infrafoundry/commit/5fbdea1a1b3bbe986359430cc446eee6010e04c5"
        },
        "date": 1795105357143,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 67.3157901509223,
            "unit": "iter/sec",
            "range": "stddev: 0.0009065808441367432",
            "extra": "mean: 14.855355597223111 msec\nrounds: 72"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 13005.867627714444,
            "unit": "iter/sec",
            "range": "stddev: 0.000006230791767393323",
            "extra": "mean: 76.88837289632885 usec\nrounds: 13607"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "085ae3f608d4d33eafcc039d7ecbeaecb73b3e2c",
          "message": "fix: label drift on adopted managed resources as update, not create (merges PR #1502, addresses #1495)\n\ninfra drift detect planned through a direct runner without the\nenvironment's managed rows, so a resource an earlier apply adopted was\nlabelled create. DriftDetector now takes the state manager and passes the\nmanaged set to plan, as infra plan does.\n\nAddresses #1495\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-19T16:53:33Z",
          "tree_id": "2222af7af7db4baa814238701b259f1078f4c015",
          "url": "https://github.com/endavis/infrafoundry/commit/085ae3f608d4d33eafcc039d7ecbeaecb73b3e2c"
        },
        "date": 1795107276289,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 66.68619506421119,
            "unit": "iter/sec",
            "range": "stddev: 0.0014895166062429775",
            "extra": "mean: 14.995607397259871 msec\nrounds: 73"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 13064.679274120575,
            "unit": "iter/sec",
            "range": "stddev: 0.000004781653637252696",
            "extra": "mean: 76.54225404376129 usec\nrounds: 13663"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "423d3229d78d5e60e0edd4a31f08f5fd6b48c96c",
          "message": "feat: export legacy opnsense filter rules to infrafoundry yaml (merges PR #1503, addresses #1497)\n\nAdd --include-legacy and --allow-partial to config migrate for the\nopnsense firewall.rules component. The legacy rules are read from the\nconfiguration backup (core/backup/download, read-only GET), parsed with\ndefusedxml, and mapped to the firewall.rules schema in document order.\nFields the schema cannot express are reported per rule, and the command\nexits non-zero unless --allow-partial is passed.\n\nAdd defusedxml as a runtime dependency (hardened parsing of the\ndownloaded config.xml) and types-defusedxml to the dev extra. Document\nthe migration guide, the relation to the GUI-only migration page and the\nmeasured cutover order; amend ADR-0015.\n\nAddresses #1497\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-19T17:08:27Z",
          "tree_id": "00b53a3b08c77b96d7b51508c631801e4462eb3e",
          "url": "https://github.com/endavis/infrafoundry/commit/423d3229d78d5e60e0edd4a31f08f5fd6b48c96c"
        },
        "date": 1795108177371,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 73.2810327839078,
            "unit": "iter/sec",
            "range": "stddev: 0.0006324500649585616",
            "extra": "mean: 13.646095886077573 msec\nrounds: 79"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 14373.547203365466,
            "unit": "iter/sec",
            "range": "stddev: 0.000004516842849923541",
            "extra": "mean: 69.57224864895264 usec\nrounds: 15729"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "269b5dac1377d0b854b3e2d7f0bac7a84c533ce7",
          "message": "fix: give each package loader test its own blueprints directory (merges PR #1505, addresses #1504)\n\nThe package loader tests pointed BlueprintResolver.blueprints_dir and the\n_create_blueprint helper at temp_dir.parent / \"blueprints\", which is one\ndirectory in the system temp dir shared by every test and xdist worker.\nParallel runs could read a manifest another test was writing, and the\ndirectory was never cleaned up. Use temp_dir / \"blueprints\" instead.\n\nAddresses #1504\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-19T17:19:22Z",
          "tree_id": "fc114d5388586e0fd70b41ec3fc9ceeabccf4791",
          "url": "https://github.com/endavis/infrafoundry/commit/269b5dac1377d0b854b3e2d7f0bac7a84c533ce7"
        },
        "date": 1795108840269,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 49.94579950387842,
            "unit": "iter/sec",
            "range": "stddev: 0.00016249355429077028",
            "extra": "mean: 20.02170372550243 msec\nrounds: 51"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7946.854161835709,
            "unit": "iter/sec",
            "range": "stddev: 0.000008291095392222983",
            "extra": "mean: 125.83595717692165 usec\nrounds: 8430"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "c5c62c3bb649a81fd205682179275f45ea54004a",
          "message": "fix: skip the empty legacy rule placeholder in the legacy rule export (merges PR #1507, addresses #1506)\n\nOPNsense leaves an empty <rule/> under <filter> once every legacy filter\nrule is deleted. parse_legacy_rules treated it as a rule without an\ninterface, so config migrate --include-legacy reported it as unexportable\nand exited 1 on a box whose legacy cutover was complete. Elements with no\nchildren are now skipped silently. They still count toward the rule\nnumber used in reports, so a reported rule keeps its document position.\n\nAddresses #1506\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-19T18:59:26Z",
          "tree_id": "1290fb11845a8cb837e5e8e9014fde86f7370662",
          "url": "https://github.com/endavis/infrafoundry/commit/c5c62c3bb649a81fd205682179275f45ea54004a"
        },
        "date": 1795114852913,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 101.7693300041072,
            "unit": "iter/sec",
            "range": "stddev: 0.0009245576495155011",
            "extra": "mean: 9.826143101852415 msec\nrounds: 108"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 16809.426462531716,
            "unit": "iter/sec",
            "range": "stddev: 0.0000026474248810508035",
            "extra": "mean: 59.49042950567078 usec\nrounds: 18044"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6a3b741f1c94f434b4d28aa5d1657f09b7adb76a",
          "message": "fix: let config migrate export radvd, system.firmware and operator-set tunables (merges PR #1511, addresses #1508)\n\n* fix: register radvd, system.firmware and system.tuning config migrate extractors\n\nEach service already implements export_to_yaml(), but the types were\nmissing from _register_extractors(), so `config migrate -p opnsense`\nrejected them as unsupported components. system.tuning already exports\nonly tunables that differ from the defaults.\n\nAddresses #1508\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* fix: skip empty-value tunables in the system.tuning export\n\nOPNsense treats an empty tunable value as \"use the default\", so those\nrows are not operator settings and only add noise to the exported YAML.\n\nAddresses #1508\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* fix: export only stored tunables from the system.tuning export\n\ncore/tunables/get returns a static child (key md5(tunable)) for every\nshipped tunable that is not stored in config; its value is the current\nkernel value, not an operator setting. Skip those rows, and stored rows\nwhose value is empty, the deprecated \"default\", or the shipped default.\n\nAddresses #1508\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-19T22:23:07Z",
          "tree_id": "bc05e742c5a23f3d3a6f69dde498883995049d96",
          "url": "https://github.com/endavis/infrafoundry/commit/6a3b741f1c94f434b4d28aa5d1657f09b7adb76a"
        },
        "date": 1795127073993,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 71.84396247072267,
            "unit": "iter/sec",
            "range": "stddev: 0.00036014622707073644",
            "extra": "mean: 13.919054094594415 msec\nrounds: 74"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12873.009674677482,
            "unit": "iter/sec",
            "range": "stddev: 0.000005313693792961475",
            "extra": "mean: 77.68191163307378 usec\nrounds: 13625"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "cea35fadca4681180628278a793ea5130cd911de",
          "message": "feat: export legacy opnsense outbound nat rules with --include-legacy (merges PR #1512, addresses #1509)\n\nExtend --include-legacy to config migrate -c firewall.nat. Rules from the\nlegacy Outbound NAT page (<nat><outbound><rule> in config.xml) are not listed\nby the firewall/source_nat API, so the export omitted them. They are now read\nfrom the config backup and mapped to nat_rules (kind: outbound) entries.\nAn empty legacy target maps to <interface>ip, sequences follow the highest\nlive outbound sequence, empty <rule/> placeholders are skipped, and\nunmappable elements are reported with --allow-partial as for filter rules.\n\nAddresses #1509\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T08:56:09Z",
          "tree_id": "23ea2c80d1d263ec529f0759ffb702d97e8079ed",
          "url": "https://github.com/endavis/infrafoundry/commit/cea35fadca4681180628278a793ea5130cd911de"
        },
        "date": 1795165042024,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 104.29610900217459,
            "unit": "iter/sec",
            "range": "stddev: 0.00006723941688859565",
            "extra": "mean: 9.588085399994643 msec\nrounds: 110"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 15992.501300272246,
            "unit": "iter/sec",
            "range": "stddev: 0.000014353943939151806",
            "extra": "mean: 62.52930553039734 usec\nrounds: 17648"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "0e9b52c71226be2bce40660e2d9811d3ff6c0784",
          "message": "feat: mint the opnsense tailscale pre-auth key from an oauth client at apply time (merges PR #1513, addresses #1510)\n\nAdd a tailscale.auth.mint block. When the node is not Running, apply gets an\nOAuth token, creates a single-use tagged pre-auth key, writes it, reconfigures\nand polls status, with the documented recovery. A Running node mints nothing.\nThe key is never logged, planned or stored. mint excludes pre_auth_key.\n\nAddresses #1510\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T09:10:01Z",
          "tree_id": "0e1c3237081ebd653800985ab1896b904c332d2f",
          "url": "https://github.com/endavis/infrafoundry/commit/0e9b52c71226be2bce40660e2d9811d3ff6c0784"
        },
        "date": 1795165896113,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 62.30295449448815,
            "unit": "iter/sec",
            "range": "stddev: 0.0004885058799632044",
            "extra": "mean: 16.050603187501622 msec\nrounds: 64"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 10842.066827631006,
            "unit": "iter/sec",
            "range": "stddev: 0.00000873315338104265",
            "extra": "mean: 92.23333667815994 usec\nrounds: 12457"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "d0893053f7f2a1b5d6d729933cffaba08c149cf5",
          "message": "fix: make the tailscale mint key description valid and surface api errors (merges PR #1515, addresses #1514)\n\nThe mint key description contained a '.', which the Tailscale API rejects,\nso every mint failed with HTTP 400. Use letters, spaces and hyphens only,\npinned by a test.\n\nToken and key-create errors now append the API's error message, with any\ntskey-* token redacted, instead of the bare HTTP status.\n\nAddresses #1514\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T13:08:14Z",
          "tree_id": "700537088984e5f2206a584d9c2b17d96eb0354b",
          "url": "https://github.com/endavis/infrafoundry/commit/d0893053f7f2a1b5d6d729933cffaba08c149cf5"
        },
        "date": 1795180150352,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 76.4437755529116,
            "unit": "iter/sec",
            "range": "stddev: 0.0007132140159549192",
            "extra": "mean: 13.081509812500514 msec\nrounds: 80"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 14357.962831821234,
            "unit": "iter/sec",
            "range": "stddev: 0.0000041028626216343014",
            "extra": "mean: 69.6477635242043 usec\nrounds: 15879"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "00158f5e13301122b363f5ed79c17350ba331918",
          "message": "docs: record the live verification of tailscale.auth.mint (merges PR #1517, addresses #1516)\n\nThe provider guide and the coverage doc still said mint had not been run\nlive. Record the #1510 live test and that the auth_keys-only scope is still\nunverified. Also correct the error-content sentence after #1514, which\nadded the API's message (with tskey- tokens redacted) to failures.\n\nAddresses #1516\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T13:26:21Z",
          "tree_id": "48c96d36fbe24d3d01b74431a6bf4025207d5cbc",
          "url": "https://github.com/endavis/infrafoundry/commit/00158f5e13301122b363f5ed79c17350ba331918"
        },
        "date": 1795181268168,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 70.16821609450768,
            "unit": "iter/sec",
            "range": "stddev: 0.0005522647783225978",
            "extra": "mean: 14.251466770269987 msec\nrounds: 74"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12820.660873403891,
            "unit": "iter/sec",
            "range": "stddev: 0.000004603727272994399",
            "extra": "mean: 77.99909925661262 usec\nrounds: 13722"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "9133dd9f6c691b34c5e5f86f31df2a6a0e94aca5",
          "message": "feat: add an oci compartment resource type (merges PR #1519, addresses #1518)\n\nAdd a `compartment` resource type to the OCI provider, rendered as\noci_identity_compartment, with an optional parent (resource name or\nOCID, default the tenancy root) and enable_delete (default false).\nvcn, subnet and instance take an optional `compartment` (name or OCID)\nand otherwise fall back to provider_settings.oci.compartment_ocid, so\nexisting configs render unchanged. compartment_ocid is now optional when\nevery resource names a compartment.\n\nThe validator reports unknown references, missing descriptions, parent\ncycles and resources with no compartment at all; infra doctor checks\nthat the configured region is the tenancy's home region. The k3s-cluster\nblueprint gains a `compartment` input.\n\nAddresses #1518\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T15:10:55Z",
          "tree_id": "11ac7e7afb7cfe2a74029580693597cf0aa822d8",
          "url": "https://github.com/endavis/infrafoundry/commit/9133dd9f6c691b34c5e5f86f31df2a6a0e94aca5"
        },
        "date": 1795187511267,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 48.992677833927225,
            "unit": "iter/sec",
            "range": "stddev: 0.0005344982744311898",
            "extra": "mean: 20.411213352937082 msec\nrounds: 51"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7874.683982803366,
            "unit": "iter/sec",
            "range": "stddev: 0.00001216805097868782",
            "extra": "mean: 126.98922295596715 usec\nrounds: 8477"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "88fd29bad2426077192097a26c4410d0531c632e",
          "message": "feat: ship the k3s ansible roles with the k3s-cluster blueprint (merges PR #1523, addresses #1522)\n\nThe OCI k3s-install script loaded the k3s-server and k3s-agent roles from\n${INFRAFOUNDRY_CONFIG_DIR}/roles, which is the env directory and never has\nthem, so k3s-install failed on any config repo that had not copied the\nroles in.\n\nMove both roles into blueprints/k3s-cluster/roles/ and the playbook into\nplaybooks/k3s.yml, so a roles/ next to the playbook cannot shadow an\noverride. The script uses the blueprint roles by default and puts\n<env>/roles first when it exists (local runs only). Jumphost runs now\nwork because the roles travel with the blueprint, and the script's\nBLUEPRINT_DIR fallback resolves to the blueprint root. Docs state that\nINFRAFOUNDRY_CONFIG_DIR is <config>/envs/<env>.\n\nAddresses #1522\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T15:51:41Z",
          "tree_id": "42aa4baf619d3f559034d9b7d2f39f1e1bd81ef2",
          "url": "https://github.com/endavis/infrafoundry/commit/88fd29bad2426077192097a26c4410d0531c632e"
        },
        "date": 1795189967477,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 77.74705214277857,
            "unit": "iter/sec",
            "range": "stddev: 0.00036144725693233406",
            "extra": "mean: 12.86222399999874 msec\nrounds: 79"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 13599.660406924153,
            "unit": "iter/sec",
            "range": "stddev: 0.000007751989037610217",
            "extra": "mean: 73.53124784578138 usec\nrounds: 15667"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2375193bed29a40280e4c06f49424341812e5ee1",
          "message": "fix: remove the k3s-cluster tailscale-cleanup destroy handler (merges PR #1527, addresses #1525)\n\nThe OCI k3s-cluster blueprint's before_destroy tailscale-cleanup handler\nrequired TAILSCALE_API_KEY, which nothing sets (nodes enrol through an\nOAuth client), and filtered devices by a k3s- hostname prefix that the\nblueprint's own node names do not match.\n\nThe framework's destroy path already removes the tailnet devices of\ninstances with a tailscale: OAuth block, matching on hostname and tag. A\ndestroy of an OCI k3s package printed \"Removed tailnet device\" for each\nnode, while the handler failed on the missing key. Remove the handler and\nits script, and update the blueprint README, the OCI k3s example and the\nscript portability doc.\n\nAddresses #1525\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T16:23:28Z",
          "tree_id": "7f67a38bb33c16130211e0484f815c31e076947c",
          "url": "https://github.com/endavis/infrafoundry/commit/2375193bed29a40280e4c06f49424341812e5ee1"
        },
        "date": 1795191889768,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 46.77019771083846,
            "unit": "iter/sec",
            "range": "stddev: 0.00040293902102713137",
            "extra": "mean: 21.381136897958022 msec\nrounds: 49"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7819.365582067876,
            "unit": "iter/sec",
            "range": "stddev: 0.000008517842385172496",
            "extra": "mean: 127.88761306841779 usec\nrounds: 8402"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2fb3d983fd6b7a22e03478cd7cfad4abddf801fd",
          "message": "fix: run pending on_create handlers on the next apply after a failed create (merges PR #1528, addresses #1524)\n\nRecord an on_create obligation in an append-only ledger of deployment_events\nrows when terraform creates a resource, before the runner failure is raised,\nand clear it only when the handlers run without an aborting result. The next\napply runs pending resource-level handlers and folds pending package-level\nnames into the aggregate resource_created event. No state schema change.\n\nAddresses #1524\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T16:34:49Z",
          "tree_id": "3326a1bf140f76fd071cc34403db7a58befeba5f",
          "url": "https://github.com/endavis/infrafoundry/commit/2fb3d983fd6b7a22e03478cd7cfad4abddf801fd"
        },
        "date": 1795192565398,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 92.68069657907319,
            "unit": "iter/sec",
            "range": "stddev: 0.0019031988812649079",
            "extra": "mean: 10.789733319999613 msec\nrounds: 100"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 15836.511394201847,
            "unit": "iter/sec",
            "range": "stddev: 0.000005376814327170427",
            "extra": "mean: 63.14522025135698 usec\nrounds: 16631"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "b9f32c565094279c78f2f08e96d1a946797cc45e",
          "message": "fix: wait for k3s nodes to join the tailnet instead of probing ssh in preflight (merges PR #1529, addresses #1526)\n\nThe OCI post-terraform script ran a one-shot remote ssh probe in Phase 0.\nOn first create the nodes have not joined the tailnet yet, so the name does\nnot resolve and the handler always failed before the wait loop.\n\nPhase 0 now checks only the local ssh-agent. Phase 1 keeps waiting on\nresolution, refused and timeout errors, and fails fast on authentication\nand host-key errors. Also fixes the EXIT trap dropping the inventory file\ncleanup.\n\nAddresses #1526\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T16:39:06Z",
          "tree_id": "634120fbe40c16e9c7b21cb2a018e55c09f271c2",
          "url": "https://github.com/endavis/infrafoundry/commit/b9f32c565094279c78f2f08e96d1a946797cc45e"
        },
        "date": 1795192822038,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 78.06175899777458,
            "unit": "iter/sec",
            "range": "stddev: 0.0003320467416231016",
            "extra": "mean: 12.810369800000387 msec\nrounds: 80"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 14293.679396914538,
            "unit": "iter/sec",
            "range": "stddev: 0.000004483452320672409",
            "extra": "mean: 69.96099270394032 usec\nrounds: 15899"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "51c87e2787eb42e3861eca30b03ada4cbc103144",
          "message": "fix: fail fast when a tailscale ssh policy denies the k3s install (merges PR #1532, addresses #1530)\n\n* fix: fail fast when a tailscale ssh policy denies the k3s ssh wait\n\nwait_for_ssh kept polling for the full timeout when the tailnet policy\nrefused the session. Add the denial text to the fast-fail patterns with\nan error pointing at the policy's ssh rules, test it, and document the\nrequired ssh rule in the k3s-cluster blueprint README.\n\nAddresses #1530\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* test: check the host in the tailscale-deny test with a regex\n\nCodeQL flagged `\"ctl.example.net\" in result.stderr` as incomplete URL\nsubstring sanitization; the test only checks that the error names the\nhost. Use a word-bounded regex instead, with the same meaning.\n\nAddresses #1530\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T17:25:55Z",
          "tree_id": "f8edad4a00b47c2ee8e5235bbcfc7573a3c1d84b",
          "url": "https://github.com/endavis/infrafoundry/commit/51c87e2787eb42e3861eca30b03ada4cbc103144"
        },
        "date": 1795195626635,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 49.56207051672115,
            "unit": "iter/sec",
            "range": "stddev: 0.0002894051413312768",
            "extra": "mean: 20.176719607842493 msec\nrounds: 51"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7912.148895861706,
            "unit": "iter/sec",
            "range": "stddev: 0.000009470140894731374",
            "extra": "mean: 126.38791473237193 usec\nrounds: 8315"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "3a1f48b4c0f0bb5f27d83165b6929b45cec3c2ad",
          "message": "fix: fire package-level on_create handlers under infra apply --parallel (merges PR #1533, addresses #1531)\n\napply_parallel never emitted the aggregate RESOURCE_CREATED event, so\npackage-level on_create handlers (those with requires) never ran, and\npending package obligations were neither recorded nor retried.\n\nExtract the aggregate block of apply_serial into _emit_aggregate_created\nand call it from both apply paths. apply_parallel also records package\npending entries now. Remove the docs caveat.\n\nThe existing test test_apply_parallel_records_no_package_pending asserted\nthe old behaviour; it is renamed and inverted. The inversion was approved\nby the maintainer. It also aborts the aggregate event, because a\nper-resource abort is swallowed into an error result under parallel apply.\n\nAddresses #1531\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T17:33:36Z",
          "tree_id": "668df28f0e6a2bce195ebd33ec0de134e365e54d",
          "url": "https://github.com/endavis/infrafoundry/commit/3a1f48b4c0f0bb5f27d83165b6929b45cec3c2ad"
        },
        "date": 1795196092641,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 100.18640893160061,
            "unit": "iter/sec",
            "range": "stddev: 0.0007656803512610298",
            "extra": "mean: 9.981393790476323 msec\nrounds: 105"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 16124.915271180453,
            "unit": "iter/sec",
            "range": "stddev: 0.0000043031025151769006",
            "extra": "mean: 62.01582973817345 usec\nrounds: 17755"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6e9fa9146aaea6614830966c691f2bb9dd6f70b9",
          "message": "fix: validate oci subnet cidrs against their vcn and fix k3s defaults (merges PR #1534, addresses #1521)\n\nThe k3s-cluster blueprint defaulted worker_subnet_cidr to a range outside\nthe default VCN, and nothing caught it before apply, which failed after\ncreating part of the stack.\n\n- blueprint: worker_subnet_cidr defaults to 192.0.2.128/25, beside the\n  192.0.2.0/25 control subnet in the 192.0.2.0/24 VCN\n- OCI validator: offline ERROR when a subnet's cidr_block is outside its\n  VCN's cidr_block, or when two subnets of one VCN overlap\n- example config and docs updated to match\n- tests for the validator and for the blueprint defaults; three existing\n  tests that pinned the out-of-VCN CIDR now use valid ranges (approved)\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T18:18:10Z",
          "tree_id": "da40725dbcbc625a1390f7eab922924edbecef04",
          "url": "https://github.com/endavis/infrafoundry/commit/6e9fa9146aaea6614830966c691f2bb9dd6f70b9"
        },
        "date": 1795198764132,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 49.44311204952066,
            "unit": "iter/sec",
            "range": "stddev: 0.0006096523588831734",
            "extra": "mean: 20.225264117647605 msec\nrounds: 51"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 8000.561540007423,
            "unit": "iter/sec",
            "range": "stddev: 0.00000800931155020901",
            "extra": "mean: 124.9912265532142 usec\nrounds: 8466"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "816e7402e4b08a66d81552ac34f51a3d5f5071c0",
          "message": "feat: let the kubernetes provider take secret values from sops (merges PR #1537, addresses #1535)\n\nSecret and Helm values in the kubernetes provider had to be written\nliterally in config YAML and were rendered into the generated .tf files.\nThey can now name a dotted secret reference, reusing the terraform_secrets\nbridge the aws, oci and proxmox providers already use.\n\n- secrets: string_data_secrets and data_secrets map a key to a ref and\n  render as sensitive variables in data / binary_data\n- helm_releases: a set_sensitive entry takes value_secret instead of value\n- the refs fold into terraform_secrets, declare sensitive variables and\n  are injected through TF_VAR_* at apply\n- offline validation reports malformed entries, unresolved refs, and\n  data_secrets values that are not base64 (never printing the value)\n- docs for the kubernetes provider and the validation reference\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T19:03:38Z",
          "tree_id": "13259ed212229d9d83ed6be763962d5b3046f915",
          "url": "https://github.com/endavis/infrafoundry/commit/816e7402e4b08a66d81552ac34f51a3d5f5071c0"
        },
        "date": 1795201507091,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 72.93745843130885,
            "unit": "iter/sec",
            "range": "stddev: 0.0004218164171102928",
            "extra": "mean: 13.710376279998588 msec\nrounds: 75"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 12833.962101688161,
            "unit": "iter/sec",
            "range": "stddev: 0.000006082301729251653",
            "extra": "mean: 77.91826032184258 usec\nrounds: 13733"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "a105dc555e346d5e2f013f10c1de1003651b43ec",
          "message": "feat: add a tailscale oauth_client resource whose credentials other providers can consume (merges PR #1538, addresses #1536)\n\nfeat: add a tailscale oauth_client whose credentials other providers can consume\n\nA tailscale OAuth client can now be created by InfraFoundry and its\nsecret handed to a kubernetes secret or Helm value with no manual copy.\n\noauth_client resource type:\n- renders tailscale_oauth_client (description, scopes, tags), depending on\n  the ACL; tags are checked against tagOwners as tailnet_key does\n- sensitive outputs oauth_client_<name>_id and oauth_client_<name>_secret\n- the existing resource-type list test gains oauth_client (approved)\n\noutput references:\n- a kubernetes secret or Helm value can reference another provider's\n  Terraform output as outputs.<provider>.<output>\n- the runner reads the producer's outputs with `terraform output -json`\n  and injects them as TF_VAR_* for that one call; values are never logged\n  or written to the config repo or generated files\n- a reference orders the producer before the consumer on apply (reversed\n  on destroy) through a stable topological provider sort\n- apply fails on a missing output (IF-DEPENDENCY-003); plan, destroy and\n  validate use a masked placeholder and warn\n- only the kubernetes provider accepts these refs, and not in data_secrets\n- a protocol-only provider without the new hook has no output refs\n- ADR-0029 records the design; the SOPS write-back alternative is rejected\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T19:27:02Z",
          "tree_id": "1676714870deaf48ebec48e9e0f9af7057f37680",
          "url": "https://github.com/endavis/infrafoundry/commit/a105dc555e346d5e2f013f10c1de1003651b43ec"
        },
        "date": 1795202894074,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 55.65580723281905,
            "unit": "iter/sec",
            "range": "stddev: 0.000148051124554858",
            "extra": "mean: 17.96757696491232 msec\nrounds: 57"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 9920.102950324072,
            "unit": "iter/sec",
            "range": "stddev: 0.00000690401958441141",
            "extra": "mean: 100.8054054486735 usec\nrounds: 10608"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "50d5eb2f04d849a7b319b6d9b977b0f481250d7d",
          "message": "feat: support several kubernetes clusters per environment as provider instances (merges PR #1540, addresses #1539)\n\n* refactor: make the provider-instance machinery generic\n\nPrepares provider instances for more than one provider family (#1539).\nBehaviour is unchanged for OPNsense firewalls; all existing tests pass\nunmodified.\n\n- INSTANCE_SETTINGS becomes an InstanceSpec registry (map key, primary\n  key, selector key, noun); messages are built from it, so the OPNsense\n  wording is byte-identical\n- the settings merge, primary check, settings-shape validation and\n  entry/file/manifest selection move from providers/opnsense/firewalls.py\n  into core/provider_instances.py; firewalls.py wraps them and keeps the\n  HA backup checks\n- a package manifest's firewall: now stamps only opnsense resources\n- the CLI -P expansion helper is generic over the instance family\n- tests for the new generic helpers\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n* feat: support several kubernetes clusters per environment as provider instances\n\nAn environment can now describe more than one Kubernetes cluster. The\nprimary keeps the provider id `kubernetes`; every other cluster is\n`kubernetes@<name>` with its own generated directory, Terraform state,\napply batch and validation, as OPNsense firewalls are (ADR-0024).\n\n- provider_settings.kubernetes.clusters maps a name to kubeconfig_path\n  and an optional context, with primary; the flat kubeconfig_path shape\n  is unchanged and keeps its state\n- a resource picks its cluster by its own cluster: key, then a file-level\n  cluster:, then the package manifest's cluster:, then the primary, so a\n  blueprint package can be pinned to a cluster\n- infra plan/apply/destroy/doctor take --cluster; -P kubernetes covers\n  every cluster\n- with clusters: declared, KUBECONFIG is ignored for every cluster (with a\n  warning) so the shell cannot retarget the primary\n- kubeconfig context now reaches Terraform (config_context), matching\n  what validation already used\n- outputs.* references resolve into a non-primary cluster's resources\n- ADR-0030 records the decision\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\n---------\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T20:02:01Z",
          "tree_id": "ddce3f98ba4d0c1e54cdc3985a6026c9cc83f994",
          "url": "https://github.com/endavis/infrafoundry/commit/50d5eb2f04d849a7b319b6d9b977b0f481250d7d"
        },
        "date": 1795204972034,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 105.42711064379543,
            "unit": "iter/sec",
            "range": "stddev: 0.0003795580342228004",
            "extra": "mean: 9.485226275228968 msec\nrounds: 109"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 17147.908575951074,
            "unit": "iter/sec",
            "range": "stddev: 0.0000026884252105726893",
            "extra": "mean: 58.31614949256499 usec\nrounds: 17827"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2155416f109d3dc6b1d555536616226c62131da8",
          "message": "fix: attach a vcn's security list to its subnets that set none (merges PR #1543, addresses #1542)\n\nA VCN's security_list was created but never attached: a subnet only got\nsecurity_list_ids when it set security_list_id itself, so it fell back to\nthe VCN's default security list and the declared rules never applied. In\nthe k3s-cluster blueprint this blocked flannel VXLAN and kubelet traffic\nbetween nodes.\n\nA subnet with no security_list_id now uses its VCN's security list when\nthe VCN declares one; an explicit security_list_id still wins.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T20:26:29Z",
          "tree_id": "735ffdc07c81bad5f861eaa279e9c2e47bcd4ceb",
          "url": "https://github.com/endavis/infrafoundry/commit/2155416f109d3dc6b1d555536616226c62131da8"
        },
        "date": 1795206466114,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 68.04909534911961,
            "unit": "iter/sec",
            "range": "stddev: 0.0009054371047388964",
            "extra": "mean: 14.695272506851007 msec\nrounds: 73"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 13096.037627310403,
            "unit": "iter/sec",
            "range": "stddev: 0.000004516564763140558",
            "extra": "mean: 76.35897425299127 usec\nrounds: 13788"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "db826a216633d6ab31a62ac953998e6eb111a528",
          "message": "fix: keep an explicit config.name in the resource-centric loader (merges PR #1546, addresses #1544)\n\nThe loader overwrote config.name with the entry's top-level name, so a\nDeployment and a Service could not share an object name. Set it only\nwhen the entry's config has none, add tests, and document that a\ndiffering object name needs the resource-centric format.\n\nAddresses #1544\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T20:48:26Z",
          "tree_id": "1ac065d28cbb62a28851d3ac9c6de48c8d3ff248",
          "url": "https://github.com/endavis/infrafoundry/commit/db826a216633d6ab31a62ac953998e6eb111a528"
        },
        "date": 1795207777440,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 49.03880187057295,
            "unit": "iter/sec",
            "range": "stddev: 0.0002493242907769787",
            "extra": "mean: 20.392015340001137 msec\nrounds: 50"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7843.9907552787545,
            "unit": "iter/sec",
            "range": "stddev: 0.000009813545347207621",
            "extra": "mean: 127.4861267942 usec\nrounds: 8360"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "4f2ff3c5476024d97cd09b8ac748766ba5734f71",
          "message": "feat: add oci object storage buckets and scoped iam access keys (merges PR #1547, addresses #1545)\n\nAdd bucket, iam_user, iam_group, iam_policy and customer_secret_key\nresource types to the oci provider, with a lifecycle policy per bucket,\ngroup memberships, offline validation and an objectstorage_namespace\noutput. Customer secret key id and secret are sensitive outputs consumed\nthrough outputs.oci.* references (ADR-0029). Documented in\ndocs/providers/oci.md.\n\nAddresses #1545\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T20:58:59Z",
          "tree_id": "fe5f174255542fa74728b1dc2d27c26c41b9323c",
          "url": "https://github.com/endavis/infrafoundry/commit/4f2ff3c5476024d97cd09b8ac748766ba5734f71"
        },
        "date": 1795208422183,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 45.32515980697202,
            "unit": "iter/sec",
            "range": "stddev: 0.0009472045369909611",
            "extra": "mean: 22.06280141666876 msec\nrounds: 48"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7636.267260039635,
            "unit": "iter/sec",
            "range": "stddev: 0.000014007595857247154",
            "extra": "mean: 130.95403368514496 usec\nrounds: 8342"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1abd42aeb160dc8313aad398fe76db2b80384670",
          "message": "feat: support volumes, secret env and update strategy in kubernetes deployments (merges PR #1549, addresses #1548)\n\nDeployments now render what jobs and cronjobs already support:\n- container command and args;\n- env value_from with secret_key_ref or config_map_key_ref;\n- volume_mounts;\n- pod volumes (persistent_volume_claim, secret, config_map with optional\n  items, empty_dir);\n- strategy.type.\n\nExisting deployment configs render byte-for-byte as before, pinned by a\ngolden file generated from the previous template.\n\nOffline validation, scoped to deployments, rejects:\n- a mount that names an undeclared volume;\n- an env entry with both or neither of value and value_from;\n- a strategy.type other than RollingUpdate or Recreate.\n\nThe deployments -> persistentvolumeclaims dependency edge already existed;\nit is now covered by a test and shown in the docs diagram.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T21:12:11Z",
          "tree_id": "d7c5f6b4e592faf8294d8a3c6317179e04a6d14d",
          "url": "https://github.com/endavis/infrafoundry/commit/1abd42aeb160dc8313aad398fe76db2b80384670"
        },
        "date": 1795209219482,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 59.38932423037377,
            "unit": "iter/sec",
            "range": "stddev: 0.00047892972179681514",
            "extra": "mean: 16.838043081968006 msec\nrounds: 61"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 10791.375931458897,
            "unit": "iter/sec",
            "range": "stddev: 0.0000054446208038372375",
            "extra": "mean: 92.66658916819043 usec\nrounds: 11854"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "52ce68e45f18873d02b0a2c9d3f6dae327241e9d",
          "message": "fix: render the kubernetes cronjob timezone as timezone, not time_zone (merges PR #1551, addresses #1550)\n\nThe cronjob template rendered config.timezone as `time_zone`, which the\nkubernetes_cron_job_v1 spec does not accept, so terraform plan failed for\nany cronjob with a timezone. Render it as `timezone`, correct the docs, and\nadd regression tests for both the set and unset cases.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T21:38:23Z",
          "tree_id": "4301d19a5f90755cb83bf25e3abd4cf7547cb445",
          "url": "https://github.com/endavis/infrafoundry/commit/52ce68e45f18873d02b0a2c9d3f6dae327241e9d"
        },
        "date": 1795210773067,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 55.612152479934906,
            "unit": "iter/sec",
            "range": "stddev: 0.00021342456853546145",
            "extra": "mean: 17.981681258620657 msec\nrounds: 58"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 10705.52989589075,
            "unit": "iter/sec",
            "range": "stddev: 0.0000053167106801012146",
            "extra": "mean: 93.40966862218035 usec\nrounds: 11250"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "6662995+endavis@users.noreply.github.com",
            "name": "Eric Davis",
            "username": "endavis"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "93488a172b885d98ed2466e627f2d20174b33f18",
          "message": "feat: support email on oci iam_user for identity domain tenancies (merges PR #1553, addresses #1552)\n\nTenancies that use Identity Domains reject a user without a primary\nemail (\"The primary email must be specified.\"), so iam_user could not be\ncreated there. Add an optional email field, rendered only when set,\nvalidated as a non-empty string containing \"@\", and documented with the\nIdentity Domains requirement. Users without email render as before.\n\n\nClaude-Session: https://claude.ai/code/session_01NXu1satPZzcTqThwpZAogj\n\nCo-authored-by: Claude Opus 5.5 <noreply@anthropic.com>",
          "timestamp": "2026-11-20T21:49:48Z",
          "tree_id": "11b83b1a55faab4752a43dacb36d63122c17c5eb",
          "url": "https://github.com/endavis/infrafoundry/commit/93488a172b885d98ed2466e627f2d20174b33f18"
        },
        "date": 1795211467057,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/benchmarks/test_bench_config.py::test_bench_config_load_environment",
            "value": 43.205905120420596,
            "unit": "iter/sec",
            "range": "stddev: 0.002698731475992211",
            "extra": "mean: 23.144984399999657 msec\nrounds: 50"
          },
          {
            "name": "tests/benchmarks/test_placeholder.py::test_import_time",
            "value": 7717.801033455976,
            "unit": "iter/sec",
            "range": "stddev: 0.000009655061662237204",
            "extra": "mean: 129.5705856713706 usec\nrounds: 8235"
          }
        ]
      }
    ]
  }
}