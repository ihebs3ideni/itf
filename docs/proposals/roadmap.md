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

The implementation branch `ihsa_itf_platform` holds the whole design as 6 commits on `main`, one idea each. Every
commit builds and passes its own tests, and the last one passes every test (see [risks and FAQ](risks-faq.md) for
what was verified). Each commit is one pull request.

## Pull requests

Sizes are added and removed lines (code, tests and documentation) on the implementation branch.

| # | Pull request | Contents | Size | Depends on |
|---|---|---|---|---|
| 1 | build: hermetic toolchain and dependencies | zig C/C++ toolchain; tcpdump and libpcap from the Bazel Central Registry; pluggy, PyYAML, pyserial | +245 / −10 | |
| 2 | core (breaking): OCTO, the session and its Bazel rules | `score/itf/core`: OCTO, the target file, the policy, the session, probes, unwind, artifact levels, the pytest adapter, `ProcessWrapper`; the contract library; the `localhost` pack; `itf_target` and `py_itf_test(target=)`; the original plugins, `Target` and their tests removed | +18,165 / −5,255 | 1 |
| 3 | packs | the other 10 packs with their contract definitions and conformance checks; pack, contract and plan tests; the integration suite running one capability-gated suite on many target files | +10,696 | 2 |
| 4 | command line and tools | `itf` lifecycle commands; `itf contracts map\|new\|check\|reference`; the generated contract map and reference, kept current by a test; the planning benchmark | +3,991 | 2, 3 |
| 5 | examples | starters, `exec_everywhere`, `itf`, `vendor_contract`, `plain_python`, the legacy facade running the original tests | +7,166 / −78 | 3 |
| 6 | documentation and CI | concepts, how-to guides, tutorial, glossary, migration guide, DR-002; CI builds every `itf_target` and checks the contract rules of ITF's packs | +2,543 / −1,359 | 4, 5 |

Pull request 2 is breaking: the original plugins cannot run on the new core, so they leave with it, and the
facade that keeps old tests running arrives in pull request 5. Land 2 to 5 close together, or keep `main` on the
previous release until 5 is in.

Pull request 2 is also the largest. If review capacity is short, it splits along its own lines: OCTO
(`score/itf/core/octo`, standard library only, about 2,500 lines), the engine and session, the contract library,
the Bazel rules, and the removal.

## Milestones after the series

| Milestone | Contents | See |
|---|---|---|
| Conformance on every pack | the `sim` pack passes the conformance checks of the contracts it claims; CI runs them | open decision 2 |
| Detached targets for containers | `itf up --detach` and `itf down` for `docker.platform` | open decision 1 |
| Python 3.14 | move the `pydantic` pin to a release with 3.14 wheels | open decision 6 |

## Review aids

- `itf graph` and `itf plan` on the example target files show what the planner does without running anything.
- The integration suite (`test/integration`) runs the same tests on a host, a container, a container over SSH,
  serial and DLT target files; each target file selects the tests it supports.
- The legacy facade shows the original API served from composed roles, test for test.
