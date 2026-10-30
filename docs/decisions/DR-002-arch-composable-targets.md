<!--
*******************************************************************************
Copyright (c) 2025 Contributors to the Eclipse Foundation
See the NOTICE file(s) distributed with this work for additional
information regarding copyright ownership.
This program and the accompanying materials are made available under the
terms of the Apache License Version 2.0 which is available at
https://www.apache.org/licenses/LICENSE-2.0
SPDX-License-Identifier: Apache-2.0
*******************************************************************************
-->

# DR-002-Arch: Composable Targets (ITF core on OCTO, packs and contracts)

**Date:** 2026-10-30
**Status:** Proposed
**Implementation:** branch `ihsa_itf_facelift` (8 commits), reviewable as the series in the [PR plan](../proposals/pr-plan.md)
**Roadmap:** [roadmap](../proposals/roadmap.md)

> This record follows the Decision Record convention established by the
> Eclipse S-CORE project:
> [eclipse-score/score — docs/design_decisions](https://github.com/eclipse-score/score/tree/main/docs/design_decisions).

## Overview

ITF describes a test target as one `Target` class with a fixed set of methods
(`execute`, `execute_async`, `upload`, `download`, `restart`), subclassed per environment (Docker,
QEMU). This record proposes replacing that class with **composition from declarations**:

- **Packs** publish *capability contracts* (what a test can hold: `exec.command`,
  `files.transfer`, `platform.instance`, ...) and *state contracts* (conditions an action makes
  true: `platform.up`, `shell.open`, ...).
- A **recipe** (the test's root `conftest.py`, in Python or YAML) picks providers and states goals.
- **OCTO**, a small pure-Python planner (standard library only), resolves *what must exist* and
  *what must happen, in which order* before any test runs.
- Tests ask for contracts by token. The same test runs on any platform whose recipe provides them.

The planner and engine come from the `itf-core` prototype; this record covers adopting them in ITF,
moving ITF's Docker, QEMU, SSH, DLT and ping code into packs, and keeping existing tests running.

## Problem Statement

1. **The target class is a fork magnet.** Every new device or protocol edits (or subclasses and
   re-implements) a class other environments share. `QemuTarget.ssh()` exists, `DockerTarget.ssh()`
   exists with different defaults; `ping()` exists only on QEMU. Tests discover this at run time
   through `@requires_capabilities` strings.
2. **Bring-up is a hard-coded sequence.** Docker starts a container; QEMU starts a process, then
   pings, then SSHes, then lists SFTP (`pre_tests_phase`). Reordering, adding a console that must
   record the boot, or reusing a step on hardware means editing the plugin.
3. **Tests are coupled to platforms.** Integration tests are written per environment
   (`test_docker.py`, `test_qemu.py`, `test_ssh.py` repeat the same intent), so coverage differs by
   accident, not by what a platform supports.
4. **Errors surface late.** A wrong configuration is found when a container or VM is already up.
5. **Build-system integration is thin.** Binaries (dlt-receive) are built by Bazel, but pytest
   plugins, images and QEMU configurations meet through strings and CLI flags.

## Proposal

### Concepts

| Term | Meaning | Example |
|---|---|---|
| Capability contract | A role an object fills, named by a token, with the members it offers | `itf.capabilities.exec.command` |
| Provider | One implementation of a capability, chosen in the recipe | `docker.exec`, `ssh.exec`, `local.exec` |
| State contract | A condition with an action that establishes it and a probe that checks it | `itf.states.shell.open` |
| Node / scope | A named instance; the root scope plus one scope per device | `target.gw.shell` |
| Recipe | Nodes (`itf_setup`) and goals/relations (`itf_init`), as Python hooks or YAML | `recipe.yaml` |
| Gates | Gate 1 resolves construction, Gate 2 resolves actions; both before test collection | `--itf-plan` |

### What changes for the three audiences

- **Test authors:** write tests against capabilities and gate them with `@itf.requires(token)`.
  A test is selected only when the recipe provides what it uses; otherwise it is deselected with
  the reason. Per-test isolation is a pytest fixture calling `target.renew(node)`.
- **Pack authors:** a pack is a directory of pytest plugin modules (`providers.py`, `steps.py`,
  topic modules), one `py_itf_plugin` target per variant. Packs never import each other: a consumer
  states what it needs with its own `Protocol`, and the planner checks the seam.
- **Infrastructure owners:** a recipe replaces the bring-up function; `bazel run
  //tools/catalog:query` answers what can be provided.

### Layering

```
pytest adapter   score/itf/core/adapters/pytest
ITF core         score/itf/core        (vocabulary-neutral: no ssh/docker/dlt words, gated)
OCTO             score/itf/core/octo   (standard library only, deps = [], gated)
packs            score/itf/packs/*     (depend on the core's public API only)
```

### Backward compatibility

ITF itself ships only the core and packs: the original plugins (`docker_plugin`, `qemu_plugin`,
`dlt_plugin`, `core_dump_plugin`) and the `Target` class are removed. Compatibility is a
**project-side legacy layer**, owned by the project that still has old tests:

- a recipe built from the original command-line options (`--docker-image`, `--qemu-config`, ...);
- a conftest providing the original fixtures (`target`, `docker_configuration`, `dlt_config`,
  `dlt`); `dlt_on_target` comes from the dlt pack itself;
- adapters presenting the recipe's nodes in the original shape (`target.execute`, `ssh()`,
  `sftp()`, `ping()`, `DltWindow`), with no copied implementation.

`examples/legacy` is such a layer, ready to copy: ITF's original integration tests run on it with
only their `score.itf.plugins.*` imports changed. Limits: one SSH login per shell node (another
login needs its own node in the recipe), DLT transport arguments come from the recipe, and with
QEMU, DLT recording starts once the machine is up.

### Evidence from the prototype

- 8 commits on top of `main`; each builds, and every ITF test target passes locally under rootless
  Podman (23 of 23). In `examples/legacy`, the original tests pass except those receiving DLT on
  the host from a container or connecting to container IPs, which rootless Podman does not provide;
  they fail the same way on `main` here, and their new-style equivalents pass.
- One suite of capability-gated tests (`test/integration/suite`) runs against recipes for the host,
  a container, a container with SSH, two DLT benches and four QEMU machines (QEMU not run in the
  prototype; QNX needs a licence). Each recipe selected 12 to 19 of the suite's tests
  automatically (matrix in `test/integration/README.md`).
- The suite found a real provider inconsistency (`ssh.process` reported `-1` where the container
  and host providers report `143`) and a sim variant that violated its published shape; both are
  fixed, and `test/packs:catalog_test` now guards the second class.
- Everything is built hermetically by Bazel, including a C/C++ toolchain, DLT and tcpdump.

## Alternatives Considered

| Option | For | Against |
|---|---|---|
| **A. Contracts, packs and a planner (proposed)** | Removes the god class; order derived, not written; one suite across platforms; errors before bring-up | A new vocabulary to learn; two new concepts (states, probes) |
| B. Keep `Target`, add plugins for new devices | Smallest change | The fork magnet remains; ordering stays hard-coded; no cross-platform suites |
| C. Interface-only: ABCs for exec/files/restart, no planner | Familiar | Does not address bring-up ordering or gating by what a platform provides |
| D. Adopt an existing framework (labgrid, tmt) | Existing community | Neither resolves Bazel-built artifacts, or ITF's pytest-plugin model, and neither gives contract-level gating |

## Risks

| Risk | Mitigation |
|---|---|
| Learning curve of contracts, states and probes | Agent skill and catalog; migration guide with a mapping table; modeling guide |
| Projects with many old tests | A copyable legacy layer (`examples/legacy`) with only import changes to old tests |
| Bazel toolchain change (zig-based C/C++) affects consumers | Only `dev_dependency` in `score_itf`; examples module shows the setup; reviewed as its own PR |
| Rootless Podman limits | Packs publish ports; docs state limits; CI uses Docker |
| Review size | Series of 8 reviewable commits, mergeable as separate PRs (PR plan) |
| Planner correctness | OCTO has its own acceptance suite (deterministic, shuffled-input tests) carried over with it |

## Open Questions

1. Should ITF keep the example legacy layer in its repository, or publish it separately?
2. Is session-scoped bring-up with an explicit `renew` acceptable as the default, or should an
   opt-in per-test mode ship in the core? (The prototype deliberately leaves per-test lifetime to
   pytest fixtures.)
3. Where should `itf-core` live after absorption: archived, or kept as the home of OCTO?
4. Should packs be published as separate Bazel modules (own versions) or stay in one module?
5. Starlark recipes: see [DR-003](DR-003-infra-starlark-recipes.md).
