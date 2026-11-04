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

# DLT pack

DLT logs over UDP multicast or the bundled `dlt-receive` tool (host UDP or target TCP). Each receive mode has its own action making `logs.active` true: name the intended action with `by:` in the target goal.

## Structure

| Location | Responsibility |
|---|---|
| `receive/process.py` | canonical `DltReceive`: arguments and host process lifecycle |
| `receive/window.py` | canonical `DltWindow` and `DltLogRecord`: bounded recordings and record searches |
| `receive/capture.py` | configured `DltCapture`: the object assembled by receive factories |
| `receive/providers.py`, `receive/steps.py` | register receive factories and the start action |
| `on_target/receiver.py`, `on_target/providers.py` | `dlt.on_target`: upload and run dlt-receive on the target, through its files and process roles |
| `multicast/receiver.py` | receive UDP datagrams directly, without dlt-receive |
| `protocol/framing.py` | encode/decode DLT wire headers; no sockets or processes |
| `plugin.py` | register the receive, on-target and multicast parts |

A window searches a recorded file; it is not another transport implementation. Remote
execution uses the same process arguments, but its lifecycle belongs to the target.
The original `score.itf.plugins.dlt.*` paths re-export the canonical receive objects (`score/itf/compat`).

**Bazel:** `//score/itf/packs/dlt`. Packs load from the labels of a target file (`dlt.<name>`); never import one pack from another.

| Label | Kind | Contract | What |
|---|---|---|---|
| `dlt.multicast` | capability factory | `observe.logs` | UDP multicast |
| `dlt.join` | action | `logs.active` | join the multicast groups |
| `dlt.receive` | capability factory | `observe.logs` | dlt-receive recorded to a file |
| `dlt.receive_tcp` | capability factory | `observe.logs` | dlt-receive over an endpoint |
| `dlt.start_receive` | action | `logs.active` | start dlt-receive |

**Host prerequisites**

- none beyond the build (dlt-receive and libdlt are built from source)
- the patched DLT build listens on TCP 13490

No action here names an order: the target file says what must run first (`relations:`).

**Target file excerpt**

```yaml
packs:
  docker: score.itf.packs.docker.plugin
  dlt: score.itf.packs.dlt.plugin
capabilities:
  platform:
    factory: docker.platform
    with:
      image: score_itf_dlt:latest
      ports: 13490/tcp
  endpoint:
    factory: docker.endpoint
    with:
      port: 13490
  logs: dlt.receive_tcp
goals:
  - state: logs.active
    by: dlt.start_receive
relations:
  - state: logs.active
    after:
      - platform.up
```
