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

# SSH pack

An SSH session to a machine, commands, processes and SFTP over it.

**Bazel:** `//score/itf/packs/ssh`. Packs load from the labels of a composition (`ssh.<name>`); never import one pack from another.

| Label | Kind | Contract | What |
|---|---|---|---|
| `ssh.shell` | capability | `exec.shell` | the session; needs an endpoint and credentials |
| `ssh.exec` | capability | `exec.command` | run a command over the session |
| `ssh.process` | capability | `exec.process` | start a program over the session |
| `ssh.files` | capability | `files.transfer` | SFTP |
| `ssh.open` | state | `shell.open, network.reachable` | connect; each state has its own probe |

**Host prerequisites**

- paramiko (pip, locked)

**Composition excerpt**

```yaml
capabilities:
  endpoint: net.endpoint
  credentials: net.password
  shell: ssh.shell
  command: ssh.exec
goals:
  - shell.open
```
