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

# Starters

Three copy-and-edit starters. Copy one folder, change what is marked `# CHANGE:`, and you have a target.

| Starter | Demo target (local) | Roles | Contracts used |
|---|---|---|---|
| `container/` | `ubuntu:24.04` container | `platform`, `command`, `files` | `platform.instance`, `exec.command`, `files.transfer` |
| `ssh/` | container running sshd | `platform`, `endpoint`, `credentials`, `shell`, `command` | `exec.shell`, `exec.command` |
| `serial/` | shell on a pseudo-terminal | `console`, `command` | `exec.console`, `exec.command` |

Every starter has the same files:

| File | What it is |
|---|---|
| `target.itf.yaml` | the composition: what the target is made of, by role |
| `bench.itf.yaml` | an override file: the facts of one bench, merged by role over the composition |
| `conftest.py` | code only: `itf_verify` (readiness after bring-up) and `itf_teardown` (evidence) |
| `test_hello.py` | one test file that asks for roles (`@itf.requires("command")`) and uses `target.command` |
| `BUILD` | `itf_target` (compiles the composition at build time) and `py_itf_test(target = ...)` |

Targets: `:target` and `:target_bench` (the composition without and with the override file), `:test` and
`:test_bench`. Evidence (container log, console transcript) goes to `$TEST_UNDECLARED_OUTPUTS_DIR/evidence`.
The `container` and `ssh` demos need a Docker-compatible daemon.

## Composition or override

- The **composition** is the structure: which factory fills which role, and the goals. Swapping how commands run
  is changing one word (`command: docker.exec` becomes `command: ssh.exec`); the test does not change.
- An **override file** holds the values of one bench and has the composition's own shape, with only what
  differs. It is merged by role: `with:` keys are merged, any other key replaces. It cannot remove a role.
