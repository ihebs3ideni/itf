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

# Integration tests: one suite, many target files

The words are defined in the glossary of [the model](../../docs/concepts/model.md#the-vocabulary).

Tests are written once, against roles, and gated on them with `@itf.requires("<role>", contract=..., shape=[...])`;
the test uses the role as `target.<role>` (`"command"`, `"files"`, `"platform"`). Each `py_itf_test` in `BUILD` runs the
**same** suite against a different target file (`itf_target`, compiled during the build); the planner knows what each
target file's platform provides, so every target file runs exactly the tests its platform supports and lists the others as
deselected, with the reason (`--test_output=all`). Supporting a new platform is adding a target file, not touching a test.

```
suite/       generic tests, one file per area (command, process, files, shell, platform, ping, console, logs)
specific/    tests needing one platform's equipment, still gated by shape: a container, a VM's second disk, DLT on the
             target, and the override file's values
targets/     one target file per platform (*.itf.yaml) and the shared policy.py (the project's dlt-daemon, the
             readiness checks); the target file itself comes from configuration (`py_itf_test(target = ...)`)
conftest.py  pytest's part: one log line per scenario and verdict
overrides/   an override file: the facts of one setup, merged by role into a target file
```

| Test | Target file | Platform |
|---|---|---|
| `:localhost` | `localhost.itf.yaml` | the test host (runs anywhere, no daemon) |
| `:localhost_override` | `localhost.itf.yaml` + `overrides/localhost.itf.yaml` | the same host, with the platform's working directory from an override file |
| `:serial` | `serial.itf.yaml` | a serial console on a pty shell; `command` goes through it (runs anywhere, no hardware) |
| `:docker` | `docker.itf.yaml` | a container through the Docker API only |
| `:docker_ssh` | `docker_ssh.itf.yaml` | a container running sshd: SSH, SFTP, a shell session |
| `:dlt_stream`, `:dlt_receive` | `dlt_stream.itf.yaml`, `dlt_receive.itf.yaml` | a dlt-daemon container; stdlib stream or dlt-receive |
| `:qnx_bridge`, `:qnx_port_forwarding`, `:ubuntu`, `:ebclfsa` | `qemu.itf.yaml` | QEMU machines (manual) |

Packs state no ordering between their actions and another pack's, so each target file says its own with `relations:`
(for instance `shell.open` after `platform.up` in `docker_ssh.itf.yaml`).

What each target file selects (✓ ran, · deselected by gating, — file not in that test's target file), from a run
against Podman:

| Test | `local` | `docker` | `docker_ssh` | `dlt_stream` | `dlt_receive` |
|---|---|---|---|---|---|
| command: a failing command reports its exit code without raising | ✓ | ✓ | ✓ | ✓ | ✓ |
| command: output and exit code are returned | ✓ | ✓ | ✓ | ✓ | ✓ |
| command: stderr is part of the output | ✓ | ✓ | ✓ | ✓ | ✓ |
| console: the console recorded output since it opened | · | · | · | · | · |
| container: renew starts from a clean container | — | ✓ | ✓ | — | — |
| container: the target file's volume is mounted | — | ✓ | ✓ | — | — |
| dlt on target: a custom output file is used | — | — | — | ✓ | ✓ |
| dlt on target: receivers stop when their block ends | — | — | — | ✓ | ✓ |
| dlt on target: receives over tcp | — | — | — | ✓ | ✓ |
| dlt on target: receives over udp multicast | — | — | — | ✓ | ✓ |
| files: an uploaded file is visible to commands | ✓ | ✓ | ✓ | ✓ | ✓ |
| files: remote file management | · | · | ✓ | · | · |
| files: upload then download round trips | ✓ | ✓ | ✓ | ✓ | ✓ |
| logs: a message sent on the target is received | · | · | · | ✓ | ✓ |
| logs: a window records only its own block and answers queries | · | · | · | · | ✓ |
| ping: the host pings the target | · | · | · | · | · |
| ping: the target pings its gateway | · | · | · | · | · |
| platform: after a restart reach brings every goal back | ✓ | ✓ | ✓ | ✓ | ✓ |
| platform: renew gives a new platform and reaches the goals again | ✓ | ✓ | ✓ | ✓ | ✓ |
| process: a process reports pid running and exit code | ✓ | ✓ | ✓ | ✓ | ✓ |
| process: cwd is honoured | ✓ | ✓ | ✓ | ✓ | ✓ |
| process: output is captured | ✓ | ✓ | ✓ | ✓ | ✓ |
| process: stop terminates a long running process | ✓ | ✓ | ✓ | ✓ | ✓ |
| process: wrapped processes coordinate | ✓ | ✓ | ✓ | ✓ | ✓ |
| shell: a command running too long reports minus one | · | · | ✓ | · | · |
| shell: line splitting is preserved | · | · | ✓ | · | · |
| shell: run returns stdout and raises on failure | · | · | ✓ | · | · |
| shell: stdout and stderr can be kept apart or merged | · | · | ✓ | · | · |
| **selected** | **12** | **14** | **19** | **17** | **18** |

On the QEMU target files the console and ping tests are selected too (`console: qemu.console`, `ping: ping.pinger`), and
the second-disk test on `:ubuntu` and `:ebclfsa`.

The suite also caught a bug while this matrix was built: the ssh `process` reported `-1` for a
stopped process where the container and host `process` factories report `143`. Generic tests hold the factories
of one contract to one behaviour.

## Running

```bash
bazel test //test/integration:localhost                                  # anywhere
bazel test //test/integration:docker_ssh --test_output=all            # gating decisions in the log
bazel build //test/integration:target_docker_ssh                 # compile a target file, no hardware
bazel test //test/integration:linux_qemu_tests --config=qemu-integration-linux
```

With rootless Podman: `--test_env=DOCKER_HOST=unix:///run/user/$UID/podman/podman.sock`; the DLT
tests load their image with `oci_load`, which needs a `docker` CLI (or a podman shim) and, with
rootless Podman, `--strategy=TestRunner=local`.
