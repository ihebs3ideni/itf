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

# Roadmap and pull request plan

## Where the implementation stands

The implementation branch `ihsa_itf_platform` holds the whole design as 12 commits on `main`. The first 8 are an
earlier stage of the same work (with recipes and providers); the last 4 move it to target
target file. Every commit passes Bazel analysis, and the last one passes every test (see
[risks and FAQ](risks-faq.md) for what was verified).

Because the first 8 commits introduce words and files that the last 4 replace (recipes, providers, Starlark
recipes), reviewing them in order means reviewing code that does not survive. The plan below therefore proposes
to **re-cut the series** so that every pull request shows only the final design. This is open decision 1 in
[open decisions](open-decisions.md).

## Pull requests

Each pull request builds, passes its own tests, and leaves `main` usable. Sizes are lines of code, tests and
documentation on the implementation branch, rounded.

| # | Pull request | Contents | Size | Depends on |
|---|---|---|---|---|
| 1 | build: hermetic toolchain and dependencies | zig C/C++ toolchain; tcpdump and libpcap from the Bazel Central Registry; pluggy, PyYAML, pyserial | small | |
| 2 | core: OCTO and the session | `score/itf/core`: OCTO, target file frontend, registry, realization, bring-up, probes, unwind, evidence, the pytest adapter, `ProcessWrapper`; unit tests | ~10,000 code, ~6,000 tests | 1 |
| 3 | Bazel: `itf_target` and `py_itf_test(target=)` | `bazel/`, `defs.bzl`; the compile action; analysis tests | ~900 | 2 |
| 4 | packs | the 11 packs with their contract definitions and conformance checks; pack tests; the integration suite running one capability-gated suite on many target files | ~7,700 code, ~3,000 tests | 2, 3 |
| 5 | command line and contract tools | `itf` lifecycle commands; `itf contracts map\|new\|check\|reference`; the generated contract map and reference, kept current by a test; the planning benchmark (`tools/benchmark`) | ~3,300 | 2, 4 |
| 6 | examples | starters, `exec_everywhere`, `vendor_contract`, `plain_python`, the legacy facade running the original tests | ~4,500 | 4 |
| 7 | remove the original plugins and `Target` | `score/itf/plugins` removed; breaking change, pointing at the migration guide and the facade from 6 | removal | 6 |
| 8 | documentation and CI | concepts, how-to guides, tutorial, glossary, DR-002; CI builds every `itf_target` and checks the contract rules of ITF's packs | ~3,900 | 5, 6 |

Pull requests 2 and 4 are the largest. If review capacity is short, 2 splits at the line between OCTO
(`score/itf/core/octo`, standard library only, about 2,500 lines) and the engine, and 4 splits per pack.

## Milestones after the series

| Milestone | Contents | See |
|---|---|---|
| Conformance on every pack | the `sim` pack passes the conformance checks of the contracts it claims; CI runs them | open decision 4 |
| Detached targets for containers | `itf up --detach` and `itf down` for `docker.platform` | open decision 3 |
| Python 3.14 | move the `pydantic` pin to a release with 3.14 wheels | open decision 8 |

## Review aids

- `itf graph` and `itf plan` on the example target files show what the planner does without running anything.
- The integration suite (`test/integration`) runs the same tests on a host, a container, a container over SSH,
  serial and DLT target files; each target file selects the tests it supports.
- The legacy facade shows the original API served from composed roles, test for test.
