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

# Status

Where the implementation stands, what is verified, and what is open. The code is the 8-commit series on
`ihsa_itf_facelift`; this page is updated as that branch changes.

## Delivered

| Area | State |
|---|---|
| Core, OCTO planner, YAML and Starlark recipe frontends, pytest adapter | Done. `renew`, per-state probes, plan-only mode (`--itf-plan --itf-strict-shapes`). |
| Packs | docker, qemu, ssh, net, ping, dlt, pcap, serial (real console and pty console), local, core_dump, with sim variants. |
| Catalog and marketplace | SQLite catalog with a query tool, published with the docs as `catalog.html`. Contract and state pages show a description, providers, consumers and configuration. A docs workflow job regenerates it and fails when the checked-in copy is stale. |
| Failure reports | Bring-up, startup-check and teardown failures print a pytest-style `=== ITF: ... failed ===` section: what failed, how far the run got, the original cause, the run directory and hints. |
| Hooks and logging | `itf_verify` and `itf_teardown` in every example and the integration suite (readiness checks, evidence saved at teardown). INFO is one line per milestone, DEBUG is detail; the convention is in the agent skill. |
| One way to start a process | Every host process goes through `ProcessWrapper`: tracked, stopped on a test timeout and at session close, and reported if it leaked. A gate test fails the build on direct `subprocess`, `os.system`, `os.fork` or `pty.fork`. |
| Examples | docker, qemu and dlt recipes; a legacy layer that runs the original tests with only their imports changed; `exec_everywhere`, one test file run against a container, SSH, a pty serial console and a serial device (a fake ECU in the container). |
| Docs and agent skill | Concepts, how-to guides, migration guide, DR-002 and DR-003, and a skill that teaches an agent to discover and use ITF. |
| CI | Build, then plan check, then tests; format and copyright checks pass. |

## Verified

- All local ITF test targets pass under rootless Podman except the three DLT integration recipes, whose image load fails in the Bazel sandbox (a local limitation, also failing without these changes).
- All `exec_everywhere` targets and `examples/itf:docker` pass under rootless Podman, repeated.
- The legacy layer passes except `test_dlt`, which needs multicast and container IPs that rootless Podman does not provide.
- Not run anywhere locally: the QEMU and QNX suites (they need a licence). The Linux QEMU CI job passed on an earlier commit.

## Open

| Item | Notes |
|---|---|
| Legacy `test_dlt` on CI | The tcp and multicast tests failed on an older commit. A race between stopping `dlt-receive` and its output reader was fixed since; confirm on the next CI run. |
| Pack kinds | Name four kinds (capability pack, policy pack, ITF pytest plugin, pure pytest plugin), add a `kind` field to the catalog and a gate that keeps capability packs free of pytest. Split `core_dump` (hook logic versus CLI flags) and `dlt` (providers versus the `dlt_on_target` fixture). |
| `core_dump` as a declared consumer | Declare its expectations so the catalog lists it and plan-only mode can warn when a scope cannot be served. |
| Local process stdin | A locally spawned process now has a piped stdin instead of inheriting the host's. Decide whether that is acceptable. |
| Log noise | Process output lines and file transfers log at INFO; revisit if runs are too noisy. |
| QEMU and QNX suites | Run before merging. |
| Pages | The fork's Pages site serves 404 until its source is set to the `gh-pages` branch; deploys happen only from `main`. |

## Changes to the plan

- The PR plan still holds: 8 commits, same order. The series gained observability, `ProcessWrapper` tracking and the marketplace without adding commits (they were folded into their phases).
- Phase 2 (packs) now also covers the pack catalog's marketplace page and the pack-kind separation listed above.
