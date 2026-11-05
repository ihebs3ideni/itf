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

# Ping pack

ICMP echo to an address; also how a machine nobody here starts counts as up.

**Bazel:** `//score/itf/packs/ping`. Packs load from the labels of a target file (`ping.<name>`); never import one pack from another.

| Label | Kind | Contract | What |
|---|---|---|---|
| `ping.pinger` | capability factory | `net.ping` | ping an endpoint, wait for it to come up or go down |
| `ping.await_boot` | action | `platform.up` | up once the address answers; not beside another platform start |

**Host prerequisites**

- net.ipv4.ping_group_range covering the user, or CAP_NET_RAW, or a ping binary

**Target file excerpt**

```yaml
capabilities:
  endpoint:
    factory: net.endpoint
    with:
      host: 192.168.0.10
      port: 22
  ping: ping.pinger
goals:
  - platform.up
```
