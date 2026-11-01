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

# ITF examples

ITF composes a test target from self-describing parts. Each example is a Bazel package with a composition
(`*.itf.yaml`), a conftest that holds only code, and tests. A composition lists capabilities by **role**
(`command: docker.exec`), the goals to reach, and settings; tests ask for roles
(`@itf.requires("command")`, `target.command`). `itf_target` compiles a composition during the build and
`py_itf_test(target = ...)` runs tests against it.

| Example | What it shows |
|---|---|
| `starter/` | three copy-and-edit starters (`container`, `ssh`, `serial`): a composition with `# CHANGE:` marks, an override file for a bench, a conftest, one test; start here |
| `exec_everywhere/` | one test file on four compositions (`container`, `ssh`, `serial`, `serial_device`); the fake ECU's readiness is a project action in the conftest |
| `itf/` | `docker`, `dlt` and `qemu` (the qemu target is manual): the same tests on a container and on a QEMU machine; a project action starts the DLT daemon |
| `vendor_contract/` | a vendor defines its own contract `acme/power.relay` (no registry), ships a definition and a conformance check in its pack; a factory fulfils it, a test requires the role; `itf contracts map` shows it |
| `plain_python/` | compose and run a target from a script with `Session(target=...)`, without pytest |
| `legacy/` | a facade over the original API: adapters map composed roles onto the old classes; the compatibility check (`test_dlt` fails locally on multicast under rootless Podman) |
| `cpp/`, `docker/` | the example application and the images the examples run |

## Reading a plan

`itf_target` compiles the composition in a build action and writes `<name>.plan.json`; building the
`py_itf_test` builds its target first, so a bad composition fails the build before any image is built:

```
bazel build //examples/itf:target_docker
cat bazel-bin/examples/itf/target_docker.plan.json
```

The file has three top-level keys: `target` (the roles, the factory chosen for each, and their redacted
settings), `action` (the ordered steps that bring the goals up, each naming the action that runs it) and
`assumptions` (states taken as holding). The output is deterministic, so two plans compare as text.

## The command line

From a folder with a composition (with Bazel, `itf` is `bazel run @score_itf//score/itf/cli:itf --`):

```
itf validate target.itf.yaml            # every metadata rule, no hardware
itf plan target.itf.yaml                # the plan, readable (--json for tools)
itf graph target.itf.yaml               # roles, wiring and bring-up sequence, as Mermaid
itf up --detach target.itf.yaml         # bring up and leave it running
itf down target.itf.yaml                # unwind from what the probes observe
itf test target.itf.yaml                # bring up, run the tests, tear down
itf contracts map target.itf.yaml       # which contract names are in use, by whom
```

## Running

From this folder, with a Docker-compatible daemon for the container examples (`DOCKER_HOST` for Podman):

```
bazel build //...
bazel test //...
```
