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

# RFC: compose ITF test targets from parts, and keep every existing test running

| | |
|---|---|
| **Status** | Proposed, open for review |
| **Implementation** | six stacked pull requests, one idea each (below); together they are branch `ihsa_itf_platform_bc` |
| **Reading** | the [manifesto](https://github.com/ihebs3ideni/itf/blob/itf-pr/6-docs/docs/concepts/manifesto.md) (principles, who owns what, the workflow), the [decision record](https://github.com/ihebs3ideni/itf/blob/itf-pr/6-docs/docs/decisions/DR-002-arch-target-composition.md), the [migration guide](https://github.com/ihebs3ideni/itf/blob/itf-pr/6-docs/docs/how-to/migrate.md) |

## Summary

Today a test target is a Python class, `Target`, with one subclass and one pytest plugin per environment (Docker,
QEMU); command-line options set it up and the bring-up order lives in each plugin. This RFC proposes that ITF
**composes** the target instead:

- A **target file** (`*.itf.yaml`) lists what a target is made of, by role (`command`, `files`, `shell`, ...),
  and the states that must hold once it is up (`platform.up`, `shell.open`).
- **Packs** contribute the parts: a capability factory builds a thing tests use (`docker.exec`); an action makes
  a state true and comes with a probe that checks it, without changing anything.
- A small planner, **OCTO**, checks the parts against each other and orders the bring-up **before anything
  starts**. A target file that does not fit fails the build (`itf_target`), not the test run.
- Tests ask for roles (`@itf.requires("command")`) and use them (`target.command`). The same test runs on the
  host, a container, a machine over SSH or a QEMU guest; what a target cannot offer is deselected with the reason.

**Nothing breaks.** Tests written for today's API run unchanged, BUILD files included: the original plugins,
options, fixtures and labels are served by a compatibility layer over the same engine. ITF's own tests from
`main` run byte-identical against it in CI.

## Why

1. A new device means a new `Target` subclass with fixed methods; a device with other means forks the class.
2. Bring-up order is code inside each plugin; adding "flash, then wait for the network, then start DLT" means
   editing a plugin or ordering fixtures.
3. Tests are written per environment, and nothing tells the runner before the run that a test cannot run here.
4. Mistakes (a typo in an option, an image without SSH) appear after a machine started, often as a timeout.
5. A target is not data: it cannot be validated, drawn, diffed between branches, or brought up from a terminal.

## Three ways to run tests on the new ITF

| You have | You do | Shown by |
|---|---|---|
| tests on ITF's current API | nothing: the compatibility layer serves the original plugins, options, fixtures and imports | `test/integration/legacy`: `main`'s tests, byte-identical, with `main`'s BUILD |
| tests on your own target API | write target files, and keep your class as an `itf.Facade` over their roles | `examples/examples/facade`, a step-by-step tutorial |
| new tests | use the new API: `itf_target`, `py_itf_test(target = ...)`, `@itf.requires`, `target.<role>` | `test/integration`: the same ground as `legacy/`, rewritten |

The compatibility layer lives in one package (`score/itf/compat`); the original module paths only re-export
from it and from the packs, and a test enforces that. It switches on through the entry points a project already
uses, not through a setting, and says so once per run. `itf compat report` lists what a suite still uses of the
original API; `itf compat target` writes the target file its options make. The facade mechanism is part of the
core, so it stays when the layer is removed.

## What a project gets

- **Plans as build artifacts.** `bazel build //...` compiles every target file through both checks; `itf plan`,
  `itf graph` and `itf diff` show what will run and what a change does to bring-up, with no hardware.
- **One suite, many targets.** Gating decides per target which tests run, from the roles each target file offers.
- **Observed state.** Every state has a probe; what already holds is kept, teardown undoes only what was done.
- **Secrets stay out of files.** `${NAME}` from the environment or a `.env` file, masked in logs and reports.
- **Evidence.** Each run leaves its plan, what the probes saw and a report (`itf evidence`).
- **Coverage of everything.** `bazel coverage //...` measures `score/itf` across unit, integration and legacy
  tests (88% today).

## The pull requests

Each pull request is one idea, builds on its own and passes its own tests. They are stacked: each depends on the
one before. Review in order.

| # | Branch | Title | Depends on | Size | Review focus |
|---|---|---|---|---|---|
| 1 | [`itf-pr/1-build`](https://github.com/ihebs3ideni/itf/compare/main...itf-pr/1-build) | build: hermetic C/C++ toolchain and the new dependencies | `main` | 8 files, +248 −10 | the toolchain and the locked dependencies |
| 2 | [`itf-pr/2-core`](https://github.com/ihebs3ideni/itf/compare/itf-pr/1-build...itf-pr/2-core) | feat(core)!: OCTO, the ITF session and its Bazel rules replace Target and the plugins | PR 1 | 194 files, +19529 −5477 | OCTO, the target file, the session, gating, `itf.Facade`, `itf_target` |
| 3 | [`itf-pr/3-packs`](https://github.com/ihebs3ideni/itf/compare/itf-pr/2-core...itf-pr/3-packs) | feat(packs): packs, contract definitions and conformance | PR 2 | 277 files, +16606 −66 | the packs (with the original classes), the compatibility layer, `test/integration` and `legacy/` |
| 4 | [`itf-pr/4-cli`](https://github.com/ihebs3ideni/itf/compare/itf-pr/3-packs...itf-pr/4-cli) | feat(cli): the itf command line, contract tools and a planning benchmark | PR 3 | 31 files, +4292 | `itf validate/plan/graph/up/down/test/doctor/diff/evidence`, `itf contracts`, `itf compat` |
| 5 | [`itf-pr/5-examples`](https://github.com/ihebs3ideni/itf/compare/itf-pr/4-cli...itf-pr/5-examples) | examples: starters, target files everywhere, a vendor contract, plain Python and a facade | PR 4 | 74 files, +5623 −80 | what a project copies |
| 6 | [`itf-pr/6-docs`](https://github.com/ihebs3ideni/itf/compare/itf-pr/5-examples...itf-pr/6-docs) | docs: target composition, the manifesto, the decision record and CI | PR 5 | 35 files, +3180 −1424 | the manifesto, the guides, CI jobs |

Each commit carries its dependency as a trailer, for tools and reviewers (GitHub does not read it):

```
Proposal: proposal/itf-target-composition-compatible
Depends-On: itf-pr/2-core
```

**PRs 2 and 3 land together.** PR 2 removes the original plugins' implementation; PR 3 serves their API again from
the compatibility layer. Between the two, `main` would have no original API, so they merge back to back (or PR 2
waits for PR 3's approval).

## How it was verified

- Every pull request builds on its own; PRs 2 and 3 pass their tests on their own.
- `main`'s integration tests run byte-identical on the compatibility layer, with `main`'s BUILD file; a test
  checks that they stay byte-identical.
- The new-style suite covers every one of those tests with an equivalent (`test/integration/README.md` maps each).
- Format, license headers and the documentation build (warnings as errors) pass; CI compiles every target file in a
  job of its own and runs the tests under coverage.
- Locally, under rootless Podman, every test passes except `main`'s `test_dlt`, which needs multicast that a
  rootless engine does not route. The QEMU suites run in CI only.

## Costs and risks

| Cost or risk | Answer |
|---|---|
| A large change (about +47k −5k lines) | six pull requests, one idea each, reviewable in order; most lines are packs, tests and docs |
| Two APIs during migration | one engine; the old API is a thin layer in one package, measured by `itf compat report`, removable in one change |
| Small behaviour differences on the old API | listed in the migration guide (for example, QEMU's `target.execute` now includes stderr, as Docker's always did) |
| New concepts to learn | one glossary; the manifesto says what goes where; starters and a facade tutorial to copy |

## Open decisions

1. How long the compatibility layer is supported after it is deprecated: two minor releases, or a date?
2. After removal, is the layer published as a separate package for projects that still need it?
3. Is `itf compat rewrite` (mechanical test rewrites) wanted in the first release?
