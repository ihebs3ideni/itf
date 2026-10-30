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

# Integration tests: one suite, many recipes

Tests are written once, against capabilities, and gated on them with `@itf.requires(token,
shape=[...])`. Each `py_itf_test` in `BUILD` runs the **same** suite against a different recipe;
the planner knows what each recipe's platform provides, so every target runs exactly the tests its
platform supports and lists the others as deselected, with the reason (`--test_output=all`).
Supporting a new platform is adding a recipe, not touching a test.

```
suite/      generic tests, one file per capability area (command, process, files, shell, platform,
            ping, console, logs)
specific/   tests needing one platform's equipment, still gated by shape: a container
            (`shape=["container"]`), a VM's second disk (`shape=["disk"]`), DLT on the target
            (loads the YAML recipe, bench-local actions, itf_verify checks)
```

| Target | Recipe | Platform |
|---|---|---|
| `:local` | `local.yaml` | the test host (runs anywhere, no daemon) |
| `:serial` | `serial.yaml` | a serial console on a pty shell: commands go through `serial.exec` (runs anywhere, no hardware) |
| `:docker` | `docker.yaml` | a container through the Docker API only |
| `:docker_ssh` | `docker_ssh.yaml` | a container running sshd: SSH, SFTP, a shell session |
| `:dlt_stream`, `:dlt_receive` | `dlt_stream.yaml`, `dlt_receive.yaml` | a dlt-daemon container; stdlib stream or dlt-receive |
| `:qnx_bridge`, `:qnx_port_forwarding`, `:ubuntu`, `:ebclfsa` | `qemu.yaml` | QEMU machines (manual) |

What each recipe selects (✓ ran, · deselected by gating, — file not in that target), from a run
against Podman:

| Test | `local` | `docker` | `docker_ssh` | `dlt_stream` | `dlt_receive` |
|---|---|---|---|---|---|
| command: a failing command reports its exit code without raising | ✓ | ✓ | ✓ | ✓ | ✓ |
| command: output and exit code are returned | ✓ | ✓ | ✓ | ✓ | ✓ |
| command: stderr is part of the output | ✓ | ✓ | ✓ | ✓ | ✓ |
| console: the console recorded output since it opened | · | · | · | · | · |
| container: renew starts from a clean container | — | ✓ | ✓ | — | — |
| container: the recipe volume is mounted | — | ✓ | ✓ | — | — |
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

On the QEMU recipes the console and ping tests are selected too (`qemu.console`, `icmp.ping`), and
the second-disk test on `:ubuntu` and `:ebclfsa`.

The suite also caught a provider bug while this matrix was built: `ssh.process` reported `-1` for a
stopped process where the container and host providers report `143`. Generic tests hold providers
of one contract to one behaviour.

## Running

```bash
bazel test //test/integration:local                                  # anywhere
bazel test //test/integration:docker_ssh --test_output=all            # gating decisions in the log
bazel test //test/integration:linux_qemu_tests --config=qemu-integration-linux
```

With rootless Podman: `--test_env=DOCKER_HOST=unix:///run/user/$UID/podman/podman.sock`; the DLT
targets load their image with `oci_load`, which needs a `docker` CLI (or a podman shim) and, with
rootless Podman, `--strategy=TestRunner=local`.
