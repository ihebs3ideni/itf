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

# Serial console pack

A line-oriented UART console over pyserial, recording every line from when it opens.

| Bazel label | Loads |
|---|---|
| `//score/itf/packs/serial` | `score.itf.packs.serial.plugin` |

**Providers**

- `serial.console` (exec.console): `device` (any pyserial URL, e.g. `loop://`), `baudrate`, `logfile`; `lines(since)`, `mark()`, `wait_for(pattern)`, `write()`, `run()`
- `serial.pty_console` (exec.console): the same console on a shell over a pseudo-terminal (`shell`, `banner`), a UART with something answering, for benches without hardware
- `serial.exec` (exec.command) over the console; the command's output, including a last line without newline, comes back with its exit code

**Actions**

- `serial.open_console` → `itf.states.console.open`

**Host prerequisites:** The serial device.

**Recipe excerpt**

```yaml
    - name: console
      contract: itf.capabilities.exec.console
      using: serial.console
      config:
        device: /dev/ttyUSB0
        baudrate: 115200
```

Members, signatures and config keys: `bazel run //tools/catalog:query -- sql "SELECT * FROM v_recipe_node WHERE provider LIKE 'serial.%'"`.
