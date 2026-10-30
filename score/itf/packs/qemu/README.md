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

An emulated machine as the target platform, configured by ITF's QEMU JSON (networks, SSH port, login, machine type).

| Bazel label | Loads |
|---|---|
| `//score/itf/packs/qemu` | `score.itf.packs.qemu.plugin` |

**Providers**

- `qemu.instance` (platform.instance): `config_file`, `kernel`, `rootfs`, `disk`; images boot through temporary qcow2 overlays
- `qemu.console` (exec.console): the serial port, recorded from `console.open`
- `qemu.endpoint`, `qemu.credentials` (descriptors): the SSH endpoint and login the JSON names

**Actions**

- `qemu.start_platform` → `itf.states.platform.up`
- `qemu.open_console` → `itf.states.console.open` (relate `platform.up` to it to record the boot)

**Host prerequisites:** `qemu-system-*`, `qemu-img`, `/dev/kvm` for acceleration; tap networking runs under `//scripts:run_under_qemu`.

**Recipe excerpt**

```yaml
setup:
  nodes:
    - name: platform
      contract: itf.capabilities.platform.instance
      using: qemu.instance
      config:
        config_file: ${QEMU_CONFIG}
        kernel: ${QEMU_KERNEL}
    - name: endpoint
      contract: itf.capabilities.descriptor.endpoint
      using: qemu.endpoint
    - name: credentials
      contract: itf.capabilities.descriptor.credentials
      using: qemu.credentials
    - name: shell
      contract: itf.capabilities.exec.shell
      using: ssh.shell
init:
  goals:
    - itf.states.shell.open
```

Members, signatures and config keys: `bazel run //tools/catalog:query -- sql "SELECT * FROM v_recipe_node WHERE provider LIKE 'qemu.%'"`.
