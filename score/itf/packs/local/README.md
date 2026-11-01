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

# Local pack

The test host as the platform: commands, processes and files through subprocess.

**Bazel:** `//score/itf/packs/local`. Packs load from the labels of a composition (`local.<name>`); never import one pack from another.

| Label | Kind | Contract | What |
|---|---|---|---|
| `local.platform` | capability | `platform.instance` | a working directory on the host |
| `local.exec` | capability | `exec.command` | run a command on the host |
| `local.process` | capability | `exec.process` | start a program on the host |
| `local.files` | capability | `files.transfer` | copy files |
| `local.start` | state | `platform.up` | the working directory exists |

**Host prerequisites**

- none

**Composition excerpt**

```yaml
capabilities:
  platform: local.platform
  command: local.exec
goals:
  - platform.up
```
