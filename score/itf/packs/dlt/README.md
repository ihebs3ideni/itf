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

DLT logs over a TCP stream, UDP multicast or the bundled dlt-receive. Every variant has its own action making `logs.active` true: name one with `by:` in a goal.

**Bazel:** `//score/itf/packs/dlt`. Packs load from the labels of a composition (`dlt.<name>`); never import one pack from another.

| Label | Kind | Contract | What |
|---|---|---|---|
| `dlt.stream` | capability | `observe.logs` | a TCP stream from an endpoint |
| `dlt.subscribe` | state | `logs.active` | subscribe to the stream (after `platform.up`) |
| `dlt.multicast` | capability | `observe.logs` | UDP multicast |
| `dlt.join` | state | `logs.active` | join the multicast groups |
| `dlt.receive` | capability | `observe.logs` | dlt-receive recorded to a file |
| `dlt.receive_tcp` | capability | `observe.logs` | dlt-receive over an endpoint |
| `dlt.start_receive` | state | `logs.active` | start dlt-receive |

**Host prerequisites**

- none beyond the build (dlt-receive and libdlt are built from source)
- the patched DLT build listens on TCP 13490

**Composition excerpt**

```yaml
capabilities:
  endpoint: docker.endpoint
  logs: dlt.stream
goals:
  - state: logs.active
    by: dlt.subscribe
```
