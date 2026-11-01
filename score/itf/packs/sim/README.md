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

# Sim pack

In-memory stand-ins for the platform, shell, log stream and capture, for offline runs.

**Bazel:** `//score/itf/packs/sim`. Packs load from the labels of a composition (`sim.<name>`); never import one pack from another.

| Label | Kind | Contract | What |
|---|---|---|---|
| `sim.docker_platform` | capability | `platform.instance` | an in-memory platform |
| `sim.docker_exec` | capability | `exec.command` | run a command on it |
| `sim.docker_start` | state | `platform.up` | start it |
| `sim.ssh_shell` | capability | `exec.shell` | an in-memory shell |
| `sim.ssh_open` | state | `shell.open, network.reachable` | connect it |
| `sim.dlt_logs` | capability | `observe.logs` | an in-memory log stream |
| `sim.dlt_subscribe` | state | `logs.active` | subscribe to it |
| `sim.pcap_capture` | capability | `observe.capture` | an in-memory capture |
| `sim.pcap_start` | state | `capture.running` | start it |

**Host prerequisites**

- none

**Composition excerpt**

```yaml
capabilities:
  platform: sim.docker_platform
  command: sim.docker_exec
goals:
  - platform.up
```
