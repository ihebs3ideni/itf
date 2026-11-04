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

DLT logs over a TCP stream, UDP multicast or the bundled dlt-receive. Each way of receiving has its own action making `logs.active` true: name one with `by:` in a goal.

**Bazel:** `//score/itf/packs/dlt`. Packs load from the labels of a target file (`dlt.<name>`); never import one pack from another.

| Label | Kind | Contract | What |
|---|---|---|---|
| `dlt.stream` | capability factory | `observe.logs` | a TCP stream from an endpoint |
| `dlt.subscribe` | action | `logs.active` | subscribe to the stream |
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
  logs: dlt.stream
goals:
  - state: logs.active
    by: dlt.subscribe
relations:
  - state: logs.active
    after:
      - platform.up
```
