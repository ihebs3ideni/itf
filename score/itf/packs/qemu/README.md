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

# QEMU pack

A QEMU machine as the platform, with its console, endpoint and login.

**Bazel:** `//score/itf/packs/qemu`. Packs load from the labels of a composition (`qemu.<name>`); never import one pack from another.

| Label | Kind | Contract | What |
|---|---|---|---|
| `qemu.platform` | capability | `platform.instance` | the machine |
| `qemu.endpoint` | capability | `descriptor.endpoint` | where the machine is reached |
| `qemu.credentials` | capability | `descriptor.credentials` | the machine's login |
| `qemu.console` | capability | `exec.console` | the serial console |
| `qemu.start` | state | `platform.up` | boot the machine |
| `qemu.open_console` | state | `console.open` | open the console |

**Host prerequisites**

- qemu-system-* and qemu-img
- /dev/kvm for acceleration
- tap networking runs under //scripts:run_under_qemu

**Composition excerpt**

```yaml
capabilities:
  platform:
    factory: qemu.platform
    with:
      config_file: qemu.json
  console: qemu.console
goals:
  - console.open
  - platform.up
```
