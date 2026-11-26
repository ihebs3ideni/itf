<!--
*******************************************************************************
Copyright (c) 2026 Contributors to the Eclipse Foundation

See the NOTICE file(s) distributed with this work for additional
information regarding copyright ownership.

This program and the accompanying materials are made available under the
terms of the Apache License Version 2.0 which is available at
https://www.apache.org/licenses/LICENSE-2.0

SPDX-License-Identifier: Apache-2.0
*******************************************************************************
-->

# Reply to the reviews of eclipse-score/itf#154

To: Piotr Korkus, Dragan Bjedov, and the ETAS review team

Thank you for the reviews. This reply covers every comment on
[eclipse-score/itf#154](https://github.com/eclipse-score/itf/pull/154) and every finding in the review document of
[etas-contrib/score_itf#2](https://github.com/etas-contrib/score_itf/pull/2) (v2, at `8a6c468`), checked against the
code as it now stands.

#154 is now a stack of 14 pull requests, open as drafts in the fork
([ihebs3ideni/itf#18](https://github.com/ihebs3ideni/itf/pull/18) to
[#30](https://github.com/ihebs3ideni/itf/pull/30)) so that each step can be reviewed and run in CI before it goes
upstream. The first four fix the existing code on `main` and can merge on their own. The rest build target
composition step by step. #154 stays open as the overview and links each step.

## 1. What changed

- **The PR is split** into 14 stacked pull requests (section 2). Each one builds and passes its tests on its own,
  so every step can be reviewed, bisected and reverted alone.
- **Fixes to the existing code come first** ([#18](https://github.com/ihebs3ideni/itf/pull/18)–[#21](https://github.com/ihebs3ideni/itf/pull/21)): the QNX image, the Pages deployment, the DLT
  TCP reconnect, and the QEMU port forwarding. They do not depend on target composition.
- **The core is additive.** Until [#27](https://github.com/ihebs3ideni/itf/pull/27), the original plugins and `Target` classes stay as they are on
  `main`, and main's integration suite runs on them unchanged. [#27](https://github.com/ihebs3ideni/itf/pull/27) swaps them for the compatibility layer.
  Three small bridges make this possible, and [#27](https://github.com/ihebs3ideni/itf/pull/27) removes them:
  - [#25](https://github.com/ihebs3ideni/itf/pull/25) adds a `core_plugin` label next to the original plugins;
  - `WrappedProcess` accepts the original `execute_async` as well as `spawn`;
  - in [#26](https://github.com/ihebs3ideni/itf/pull/26), python_dlt finds `libdlt` in either the plugin's or the pack's location.
- **The legacy suite is main's, byte for byte.** `test/integration/legacy` is main's `test/integration`,
  BUILD file included: no `--docker-ssh`, no added tests. The source-hash gate the PR text promised now exists:
  `tools/legacy_unchanged.py` checks pinned sha256 values in CI and fails on any changed or added file. New tests
  of the original API go to `test/integration/compat`, and tests of the native API to the native suites.
- **Packs are self-contained.** The 65 `$ref` stubs are gone. A pack's `contracts/<id>.yaml` is a symlink to the
  shared definition, so Bazel bundles only the pack's own directory, and a wheel or an out-of-tree copy gets real
  files. The loader no longer handles `$ref` at all.
- **The docs are corrected:**
  - the README and skill no longer list the removed DLT multicast labels;
  - "run unchanged" is true again, and the legacy and compat sections are rewritten;
  - the Docker SSH behaviour is documented;
  - the broken anchor, the personal path in `test/integration/README.md` and the `test/unit` pointer in DR-001
    are fixed.
- **Hygiene:** license headers were added to 11 files, and the generated contract map is regenerated.

## 2. The stack

| # | Pull request | Size (lines +/−) | Notes |
|---|---|---|---|
| 01 | [#18](https://github.com/ihebs3ideni/itf/pull/18) fix(qnx): correct emulated timer and guest network setup | +4 / −2 | independent fix |
| 02 | [#19](https://github.com/ihebs3ideni/itf/pull/19) fix(ci): deploy generated documentation through GitHub Pages | +63 / −6 | independent fix; the docs jobs run only from an upstream branch |
| 03 | [#20](https://github.com/ihebs3ideni/itf/pull/20) fix(dlt): reconnect dlt-receive after a TCP disconnect | +72 | independent fix; bounded retries |
| 04 | [#21](https://github.com/ihebs3ideni/itf/pull/21) fix(qemu): bind forwarded host ports to 127.0.0.1 | +2 / −2 | independent fix |
| 05 | [#22](https://github.com/ihebs3ideni/itf/pull/22) docs(decisions): propose DR-002, target composition | +153 / −2 | design only; agree first |
| 06 | [#23](https://github.com/ihebs3ideni/itf/pull/23) build: provide a hermetic C/C++ toolchain and pinned runtime dependencies | +239 / −41 |  |
| 07 | [#24](https://github.com/ihebs3ideni/itf/pull/24) feat(octo): add the target planner | +5.0k | stdlib only, no users yet |
| 08 | [#25](https://github.com/ihebs3ideni/itf/pull/25) feat(core): compose targets from target files | +16.8k / −0.3k | additive; includes the localhost pack |
| 09 | [#26](https://github.com/ihebs3ideni/itf/pull/26) feat(packs): add capability packs for main's existing targets | +10.7k |  |
| 10 | [#33](https://github.com/ihebs3ideni/itf/pull/33) feat(packs): add serial and pcap packs | +1.6k | capabilities main does not have |
| 11 | [#27](https://github.com/ihebs3ideni/itf/pull/27) feat(compat): serve the original plugins and Target API from the packs | +3.3k / −3.8k | the original plugins move onto the packs; legacy gate |
| 12 | [#28](https://github.com/ihebs3ideni/itf/pull/28) feat(contracts): add contract metadata, rules and conformance checks | +3.6k |  |
| 13 | [#29](https://github.com/ihebs3ideni/itf/pull/29) feat(cli): add the itf command line | +3.3k |  |
| 14 | [#30](https://github.com/ihebs3ideni/itf/pull/30) docs: document target composition, examples and CI | +11.5k / −1.5k |  |

Each pull request's base is the one before it (the first one's is `main`), so each shows only its own change.
Pull requests 01–04 do not depend on each other or on the rest.

Sizes include tests. In [#25](https://github.com/ihebs3ideni/itf/pull/25), about 5.8k of the 16.8k lines are tests; the localhost pack, the shared
contract definitions and main's suite moved into `test/integration/legacy` account for another 1.5k.
Every commit is authored and SSH-signed by one identity.

**How each step was checked:**
- From [#23](https://github.com/ihebs3ideni/itf/pull/23) on, every commit was built and tested on its own with `bazel build //...` and
  `bazel test //...`, using rootless Podman.
- [#18](https://github.com/ihebs3ideni/itf/pull/18)–[#22](https://github.com/ihebs3ideni/itf/pull/22) change `main`'s own files. `main` cannot link dlt-daemon with this machine's host compiler,
  so they were checked by diff and by the targets they touch; their CI runs will confirm them.
- Two legacy targets fail locally on every step, the final one included:
  - `legacy:test_dlt` needs multicast between host and container;
  - before [#27](https://github.com/ihebs3ideni/itf/pull/27), `legacy:test_ssh*` reach the container IP, which rootless Podman does not route.

  Both are local environment limits; CI uses Docker. In the final tree, `test_ssh` connects through the published
  port and passes locally too.

**Further checks on the final tree:**
- **Linux QEMU (KVM):** `//test/integration:ubuntu` (native) and `//test/integration/legacy:test_ubuntu` (main's
  test through the compat QEMU plugin) both pass. `ebclfsa` (aarch64) was not run: the machine has no
  `qemu-system-aarch64`.
- **QNX QEMU (licensed, KVM):** 7 of 8 targets pass. They are native `ssh` and `qnx_port_forwarding` on QNX,
  `observability` and `observability_serial`, and legacy `test_ssh_configurable`, `test_qemu_port_forwarding` and
  `test_qemu_bridge_network_no_dlt`. Legacy `test_qemu_bridge_network` passes 18 of 19 tests. `test_restart` fails
  because this host cannot join the DLT multicast group (`MC Join error: No such device`), so `dlt-receive`
  exits. After the reboot, the compatibility `restart()` reaches every goal of the target again, `logs.active`
  among them, and that probe fails. The original `restart()` never checked DLT, so this is an environment
  failure that the stricter restart makes visible.
- **reference_integration `main` (`a5a1e3e`):** run against the stack top with
  `--override_module=score_itf=<this branch>`, through the original plugins, i.e. the compat layer.
  - `//platform_integration_tests:pit` passes 7 of its 8 targets.
  - `//feature_integration_tests/itf` passes 2, skips 2 and fails 2.
  - The three failures (`platform_run` and two DLT logging tests) fail the same way on the pinned ITF 0.6.0:
    rootless Podman reports `MC Join error: No such device` for DLT multicast. They are environment failures,
    not regressions.
  - One difference showed up and is now documented in `docs/how-to/migrate.md`: `DltWindow.record().find()`
    returns `[]` for an empty capture, where 0.6.0 raised python-dlt's `OSError: DLT TRACE FILE IS EMPTY`.

## 3. Replies to the comments on #154

### Piotr Korkus

| Comment | Status | Reply |
|---|---|---|
| Required checks `itf-build-all` / `itf-examples-build-all` disappear | Resolved | The aggregate jobs carry the old names again (`itf.yml`, `itf-examples.yml`), and `itf-qnx-qemu-tests-build-all` is unchanged. Until [#30](https://github.com/ihebs3ideni/itf/pull/30), the workflows are main's apart from label moves, so the stack never drops a required check. |
| DR-002: don't hardcode main links | Resolved | Links to the decision-record index with a relative Sphinx link. |
| DR-002: update the status before merging | Open, by design | Stays `Proposed` until you accept it. [#22](https://github.com/ihebs3ideni/itf/pull/22) exists so that the design can be agreed before the code. |
| SSH `exec` may be doubled | Resolved | `exec` is added only for a simple command. It is not added when the command already starts with `exec`, starts with a variable assignment (`VAR=1 cmd`; `exec VAR=1 cmd` fails in `sh`), or contains shell operators outside quotes. Arguments are always quoted. Unit tests cover each case, and an integration test checks that the PID reported is the program's own. |
| Docker: pass `mem_limit`, `userns` etc. | Resolved | `docker_sdk_kwargs` passes any further SDK argument. Through the original `docker_configuration` fixture, keys ITF does not name go to the SDK again, as main passed them to `containers.run`. ITF refuses only the options it manages itself (name, network, port bindings, auto-remove). |
| Docker `start()` twice on one instance | Resolved | A running container is reused and a stopped one is started again. A named platform finds its container and network again by an owner label, and refuses resources it does not own. Unit tests cover this. |
| `--no-annotate` for the lock file | Resolved | In [#23](https://github.com/ihebs3ideni/itf/pull/23). |
| Contract PR template only works as `pull_request_template.md` | Justified | It is meant for contract proposals only, not as the default template. The docs explain how to select it with `?template=contract_proposal.md`. It moves to [#28](https://github.com/ihebs3ideni/itf/pull/28) with the contract tooling. |
| Did you consider pytest fixtures as the composition mechanism? | Answered | Yes. DR-002 now evaluates this alternative. See section 5.1. |
| OCTO? (glossary) | Resolved | Defined in the glossary in `docs/concepts/model.md`. |
| Hand-written Kahn toposort | Resolved | Uses `graphlib.TopologicalSorter`. The helper keeps its old name, `toposort_kahn`; it will be renamed in [#24](https://github.com/ihebs3ideni/itf/pull/24). |
| The planner re-implements pytest's fixture graph | Answered | See section 5.1. |
| `itf versions`: unnecessary re-parsing of MODULE.bazel? | Open (no reply yet) | It reads the module name and version so that a version report names the build it came from. Bazel already knows these, so the command could take them from a stamped file or `--module` arguments instead. Proposal: drop `itf versions` from [#29](https://github.com/ihebs3ideni/itf/pull/29) and add it back when a downstream project asks for release-tag checks. Tell us whether you agree. |
| Pack `$ref` stubs: isn't a symlink better? | Resolved | Done (section 1). The loader's `$ref` code and its tests are removed. |
| `close()`: set `_closed` last | Resolved | Cleanup runs through nested `finally` blocks, with `_closed` set last. A `closing` phase prevents re-entry. |
| Network leaks when `container.stop` raises | Resolved | Network removal runs from an outer `finally`. |

### Dragan Bjedov

| Comment | Status | Reply |
|---|---|---|
| `*` in the SSH client signature | Answered | It makes the following parameters keyword-only. |
| Remove `examples/evidence/console.txt` | Resolved | Removed. |
| Use the S-CORE C++ toolchain (`score_bazel_cpp_toolchains`) | Justified, open to change | The S-CORE toolchain in ITF is configured for QNX. For Linux, main used the host compiler (and `toolchains_llvm` in the examples). [#23](https://github.com/ihebs3ideni/itf/pull/23) builds dlt-daemon and libpcap with a hermetic GCC so that builds do not depend on the host. On this machine, `main` itself fails to link dlt-daemon with the host compiler. If `score_bazel_cpp_toolchains` offers a Linux x86_64 GCC/Clang, we will switch to it in [#23](https://github.com/ihebs3ideni/itf/pull/23); it is one isolated change. |
| Examples use the same toolchain | Justified | Same reason; one toolchain for the repository and its examples. |

## 4. The review document (etas-contrib/score_itf#2)

Statuses:
- **Resolved:** fixed in the stack.
- **Documented:** a deliberate difference, written down in the docs.
- **Justified:** we keep it, for the reason given.
- **Open:** agreed, not done yet.

### Must-fix items

| Finding | Status | Where it stands |
|---|---|---|
| B1 Required checks renamed | Resolved | See Piotr's first comment above. |
| B2 Compatibility is false in places: `--docker-ssh` | Resolved | The legacy BUILD is main's again. `DockerTarget.ssh()` without SSH roles connects to container port 2222, as main did. It goes through the published host port when there is one, so it works on rootless engines too. `--docker-ssh` remains an opt-in for SSH roles. |
| B2 `docker_configuration` rejects unknown keys | Resolved | Unknown keys go to the SDK, as on main (see Piotr's Docker comment). |
| B2 `ExecResult` | Resolved | `DockerTarget.execute()` returns docker-py's `ExecResult` again. |
| B2 removed qemu modules, `qemu_target()`, `QemuAsyncProcess`, `config` fixture, `guest_panicked`, `DockerTarget.network` | Resolved | All are back as compatibility adapters. `//test/integration/compat:shims_test` keeps the original module paths re-export-only. |
| B2 `pytest_itf_session_created` dropped | Resolved | Re-exported from `score.itf.plugins.core`. |
| B2 named Docker volumes raise | Resolved | Only absolute host paths are checked for existence. |
| B2 remaining behaviour differences | Documented | The list is in `docs/how-to/migrate.md`, section "Differences seen through the layer". For example: DLT recording with QEMU starts after boot, and over SSH stderr follows stdout. |
| B3 No source-hash gate | Resolved | `tools/legacy_unchanged.py` with `tools/gates/legacy_main.sha256` (14 files, BUILD included) runs in CI. The PR text now names the mechanisms that exist. |
| B4 Secrets leak despite masking | Resolved / Documented | Masking now works on the structured record before it is serialized, so JSON and HTML escaping no longer hide values. Numeric values are masked too. Masking is limited to ITF-owned output on purpose (`score/itf/core/engine/secrets.py`): it installs no global logging hook and does not rewrite component logs or command output. `${NAME}` values that are exactly one reference are still read as YAML scalars (documented, so `port: ${SSH_PORT}` is an int). **Open:** wrap a `YAMLError` from such a value in a `TargetFileError` that does not echo the value. |
| B5 Session lifecycle | Resolved | Phase guards (`new → resolved → … → closed`): calling `resolve()` or `bring_up()` out of order raises a clear error. A factory failure during bring-up becomes an `ExecutionError` with the failure report and the retry. `close()` cleans up in nested `finally` blocks and marks the session closed last. **Open:** close the session (teardown hooks, evidence) also for `--itf-plan`, `--collect-only` and resolve failures. |
| B6 Default gating deselects silently | Open | Tests a target cannot run are deselected and listed in the log and in `itf-run/preflight.json`. They do not reach JUnit as skips, so a target that loses a role shrinks the suite without failing it. Proposal for [#25](https://github.com/ihebs3ideni/itf/pull/25): report them as skips with the gating reason, and keep `--itf-strict-gating` for CI that wants a failure. |
| B7 Timeouts and fakes | Resolved / Documented | `ssh.exec` and `docker.exec` raise `TimeoutError` at the timeout (Docker after trying to stop the command; documented). The contract text says enforcement is factory-specific. `sim.exec` honours exit codes and refuses when stopped. `sim` logs return message objects. **Open:** a timeout conformance check. |
| B8 Process and signal handling | Resolved | `RLock`; the handler changes only on the main thread; `run()` kills the child on any `BaseException`; the owner token is restored. |
| B9 OCTO drops a step on a key collision | Resolved | A collision now raises the `STATE_CONFLICT` diagnostic. |
| B10 DLT reconnect keeps `is_active()` true; `lines()` | Resolved | The patch is bounded (8 attempts, about 39 s). `lines()` raises `RuntimeError` on a dead stream. |
| B10 Docker `start()` not re-entrant | Resolved | See Piotr's comment. |
| B10 SSH processes share the shell's connection | Documented | One channel per process on the shared connection. QEMU has `--qemu-async-new-connection` for the original one-connection-per-process behaviour. Re-reaching `shell.open` closes the channels, as documented in the compat README. |
| B10 core_dump downloads every dump to hash it | Open | Dumps are staged in a temporary directory, but each collection still transfers them. Proposal: compare name, size and mtime first, and hash only on a match. |
| B10 pcap `start()` readiness | Resolved | Waits for tcpdump to be ready and keeps its stderr. |

### Questions for the maintainers

| Question | Our position |
|---|---|
| Scope and split | Done as you proposed, with these differences: compat, conformance, CLI and docs are separate steps, and the OCTO planner is its own step. The history is now bisectable: the core is additive and the original plugins are replaced in one step ([#27](https://github.com/ihebs3ideni/itf/pull/27)). |
| Bus factor | Fair. The split and the design record exist so that each part can be reviewed and owned. We ask for a second owner for the engine and OCTO, and for the packs. |
| Contract ownership ("ITF knows no contracts", yet it ships 21 definitions) | Both hold: the engine accepts any contract name without a definition. The 21 definitions are the set the ITF team supports, with conformance checks. They start as `experimental` and become a stable API only by your decision. DR-002 says so. |
| Format versioning (`itf: 1`) | Agreed. Proposal: an optional top-level `itf: 1` in [#25](https://github.com/ihebs3ideni/itf/pull/25). A file without it is read as version 1, and unknown versions are refused. |
| MVP (evidence, HTML report, `itf up`, versioning) | See section 5.3. We propose to drop `itf versions`. The rest stays in separate steps ([#28](https://github.com/ihebs3ideni/itf/pull/28)–[#30](https://github.com/ihebs3ideni/itf/pull/30)) so that you can stop the stack where the value ends. |
| Conformance not cleanly droppable | Resolved: [#28](https://github.com/ihebs3ideni/itf/pull/28) is the only step that adds conformance. The definitions gain their `conformance:` fields there, and the packs' `conformance_*.py` modules come with it. |

### Further findings

**Resolved:**
- Rebase on Python 3.12-only `main`: the stack is based on `118287d`.
- Personal path in the docs.
- Missing license headers: 11 files fixed; `copyright.check` passes.
- `py_itf_test`: the host transition now uses `--host_platform`, so a project's `select()` matches as it did with
  main's `cfg="exec"`. Documented in `bazel/README.md`.
- `--itf-keep` lacked the CLI's `undetachable()` check: shared now, so the run refuses instead of killing QEMU.
- `ping.wait_up(None)` probes once: it now polls for up to 60 s.
- QEMU `hostfwd` binds all interfaces: fixed on `main` ([#21](https://github.com/ihebs3ideni/itf/pull/21)) and in the qemu pack.
- Unchecked `chmod` in the dlt on-target receiver.
- Docker download of a directory: raises again, as on main.
- `artifacts.py` read a `_pre_observation` field that nothing set: it is set now.
- xdist: refused with a clear error.
- The metacharacter check scanned quoted arguments.
- Serial EIO spin: EIO is end of file.
- DR-001 still pointed to `test/unit/`.
- The `platform.md` anchor.
- `Session` was one 900-line class: it is now a package
  ([#25](https://github.com/ihebs3ideni/itf/pull/25)). `Session` keeps the phase and delegates to `Resolution`
  (target file to the two plans, nothing built), `TargetStates` (probe, plan the delta, run it: bring-up with
  retries, `reach`, `discard`, drift) and `RunRecord` (what the run did, only reported). `artifacts.py` and
  `evidence.py` read `session.record` and public properties; the 52 reads of private fields are gone.

**Justified:**
- `tcpdump` as a non-dev `bazel_dep`: the pcap pack needs it at run time for consumers. Bazel fetches and builds it
  only when a consumer's target depends on it.
- A second pluggy manager for `itf_verify` and `itf_teardown`: these hooks also run under `itf up` and plain
  Python, with no pytest.
- Committed generated docs (`docs/_generated/catalog.html`, `docs/reference/contracts.md`): the Sphinx build does
  not run Bazel targets, and a test fails when the committed files are stale. Generating them at docs build time
  is possible once the docs workflow can run the CLI.

**Open (follow-ups):**
- Move the HTML report out of `core/engine` (into an adapter or the CLI).
- Common base exceptions (`ItfUserError`, `ItfRuntimeError`) instead of catching `TypeError`/`ValueError`
  wholesale.
- Pin all GitHub actions by SHA.
- Remaining small failure-path leaks (serial log file, `Sftp.__enter__`, PID-line read), the QEMU console buffer
  bound, and `get_output` line splitting across backends.
- The default `.dlt` path shared by two `logs` roles.
- Fixed ports in parallel Bazel runs (4444, 13490).
- `test_override_values` skips instead of failing.

**Tests named in the review:**
- Bring-up retry, evidence and re-plan are now covered by engine tests.
- `--qemu-boot-attempts` is mapped onto `--itf-bring-up-attempts`; a layer test now covers the mapping.
- **Open:**
  - an engine test and a pytester test that a failed bring-up unwinds what was built;
  - a diamond test (a shared provider built once, closed once);
  - observability targets in a CI workflow, which need a licensed QNX runner.

## 5. Design questions

### 5.1 Why not pytest fixtures

Fixtures are the right tool for test-scoped setup, caching and teardown, and ITF keeps using them: `target` is
a fixture. They do not cover what a target file needs:

- **The target exists without a test run.** `itf_target` compiles a target file during the build, and fails the
  build on a wrong composition. `itf up` holds a target for manual work. A fixture graph exists only inside a
  collected pytest session.
- **States, not just objects.** A target declares goals (`platform.up`, `shell.open`). Probes say which hold, and
  the planner runs only the missing steps. After `discard`, `renew` or a lost state, it plans again (this is what
  the bring-up retry is). Fixtures model "build once per scope, tear down at the end"; they have no notion of a
  state that can stop holding.
- **The check comes before anything is built.** Roles, contracts and slots are matched, and the actions are
  ordered, from declarations alone. Mistakes are reported with the target file's names before any container
  starts. Fixture dependency errors surface while fixtures execute.

We could build this on fixtures and pytest hooks, but then the pytest integration would own a target planner, and
the CLI and Bazel compile step could not use it. DR-002 states this as the deciding requirement: target
composition must work without pytest. If you decide that this requirement is not worth its cost, the parts that
remain useful (packs, roles, `@itf.requires`, conformance) can be served by generated fixtures. That is a smaller
design, and the decision belongs in DR-002 before [#24](https://github.com/ihebs3ideni/itf/pull/24) merges.

### 5.2 The size of OCTO and the state planner

OCTO is about 3k lines of standard-library code with its own tests: deterministic over 200 shuffles and across
hash seeds, and with a third kind plugged in by a test.

The review notes that the shipped target files use no `scopes:`, `assume:` or `breaks:`. We counted, and that is
correct, but it does not mean the features are unneeded: 13 target files use `relations:` and `by:`, one uses `actions:`, and none uses the other three. Our
position on each:

- **`relations:` and `by:` stay.** They order actions across packs and choose between two actions that make the
  same state true. Both are in use.
- **`scopes:` stays.** A scope is one device or core of a multi-device target (a gateway and an ECU behind it,
  two cores of one SoC). Each scope has its own roles and states with the same names, which a single flat
  namespace cannot express. The shipped targets are single-device, so none uses it yet. We will add a two-scope
  example and planner test so that the feature is exercised.
- **`assume:` stays.** It records that a state holds without running its action or its probe, for example that
  a device was flashed by hand before the run (with an owner and a reason, which the evidence shows). The
  examples do not show this because CI images are always built fresh; we will add one to the docs.
- **`breaks:` stays; `after` cannot replace it.** `after` orders two states. `breaks` says that an action makes
  a state false. That matters when a probe found the state holding before bring-up: a step whose state holds is
  skipped. With `flash` breaking `application.running`, the planner puts the application's start step back into
  the plan after flashing, and bring-up drops the earlier observation once the action has run. With `after`
  alone, an application left running by an earlier run would be skipped, reported as running, and be gone after
  flashing. `breaks` is part of `relations:` (`state:` with `after:` and/or `breaks:`) and of `@state(...,
  breaks=)`. `docs/concepts/model.md` now explains the difference. No shipped pack declares it today because the
  shipped targets are built fresh on each run; it is needed on persistent hardware.
- **`idempotent`, `permanent` and `reversible` on `Kind`** are not read today. Each has a use case we expect to
  need:
  - `idempotent`: an action may run again after its probe fails. This is the re-entrancy guarantee the review
    asks the Docker platform to give, and the bring-up retry should check it before running an action again.
  - `permanent`: a state that cannot be undone (flashing, fusing), which unwind must not try to reverse.
  - `reversible`: a state with an undo step that unwind runs.

  We propose to keep them and wire `idempotent` into the retry in [#25](https://github.com/ihebs3ideni/itf/pull/25). `permanent` and `reversible`
  stay as documented, reserved fields until unwind reads them. If you prefer, we drop them until then.

### 5.3 What is optional

The stack is ordered so that you can stop after any step:
- after [#27](https://github.com/ihebs3ideni/itf/pull/27), ITF has target files, packs and full compatibility;
- contract metadata and conformance, the CLI, the docs and examples, and the benchmark each come after that.

For the first release we propose to drop `itf versions` and the planning benchmark, and to keep the HTML target
report behind the artifact level (it is off with `--itf-artifacts=none`).

### 5.4 The compatibility layer

The alternative, keeping the original plugins as a thin facade over the pack factories, is what [#27](https://github.com/ihebs3ideni/itf/pull/27) does:

- the plugin modules only re-export;
- the facade maps the original methods to roles;
- the target files in `score/itf/compat/targets` describe the original plugin combinations.

`os.environ` as the channel for option values is an open point. Passing the values to the `Session` as overrides
is the better design, and we will do it in [#27](https://github.com/ihebs3ideni/itf/pull/27).

## 6. Next steps

1. Agree on DR-002 ([#22](https://github.com/ihebs3ideni/itf/pull/22)), especially section 5.1.
2. Review and merge the four fixes ([#18](https://github.com/ihebs3ideni/itf/pull/18)–[#21](https://github.com/ihebs3ideni/itf/pull/21)); they go upstream first.
3. Review [#23](https://github.com/ihebs3ideni/itf/pull/23)–[#27](https://github.com/ihebs3ideni/itf/pull/27) in order. The open points marked for those steps (gating skips, `itf: 1`, the
   environment channel, the planner feature list) are added to them during review.
4. Decide whether the compatibility `restart()` keeps re-reaching every goal (strict, as now) or only the platform and
   shell goals, as the original effectively did (section 2, QNX results).
5. Each step goes upstream once it is reviewed in the fork.
