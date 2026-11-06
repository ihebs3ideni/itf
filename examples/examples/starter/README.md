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

Three copy-and-edit starters. Copy one folder, change what is marked `# CHANGE:`, and you have a target file for your own software.

| Starter | Demo target (local) | Roles | Contracts used |
|---|---|---|---|
| `container/` | `ubuntu:24.04` container | `platform`, `command`, `files` | `platform.instance`, `exec.command`, `files.transfer` |
| `ssh/` | container running sshd | `platform`, `endpoint`, `credentials`, `shell`, `command` | `exec.shell`, `exec.command` |
| `serial/` | shell on a pseudo-terminal | `console`, `command` | `exec.console`, `exec.command` |

Every starter has the same files. Everything ITF reads is in `targets/`; the tests and pytest's files stay
beside the `BUILD`:

| File | What it is |
|---|---|
| `targets/target.itf.yaml` | the target file: what the target is made of, by role |
| `targets/override.itf.yaml` | an override file: only what differs in one setup, merged by role over the target file |
| `targets/policy.py` | ITF code only: `itf_verify` (readiness after bring-up) and, for `ssh` and `serial`, `itf_teardown` (evidence) |
| `test_hello.py` | one test file that asks for roles (`@itf.requires("command")`) and uses `target.command` |
| `BUILD` | `itf_target` (compiles the target file at build time) and `py_itf_test(target = ...)` |

Bazel targets: `:target` and `:target_override` (the target file without and with the override file), `:test` and
`:test_override`. Evidence (the machine's identity, the console transcript) goes to `$TEST_UNDECLARED_OUTPUTS_DIR/evidence`.
The `container` and `ssh` demos need a Docker-compatible daemon.

## Target file or override

- The **target file** is the structure: which factory fills which role, and the goals. Swapping how commands run
  is changing one word (`command: docker.exec` becomes `command: ssh.exec`); the test does not change.
- An **override file** holds what differs in one setup and has the target file's own shape, with only what
  differs. It is merged by role: `with:` keys are merged, any other key replaces, and `remove: true` takes a role out.

The words are defined in the glossary of [the model](../../../docs/concepts/model.md#the-vocabulary).
