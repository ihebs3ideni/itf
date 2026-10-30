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

ICMP reachability without a ping binary (unprivileged or raw ICMP sockets, the system `ping` as a last resort).

| Bazel label | Loads |
|---|---|
| `//score/itf/packs/ping` | `score.itf.packs.ping.plugin` (provider only) |
| `//score/itf/packs/ping:boot` | `score.itf.packs.ping.boot` (adds `icmp.await_boot`) |

**Providers**

- `icmp.ping` (net.ping): `ping()`, `wait_up(timeout)`, `wait_down(timeout)` for the bound endpoint's host

**Actions**

- `icmp.await_boot` → `itf.states.platform.up` (`:boot` only): for machines no pack starts, e.g. hardware

**Host prerequisites:** `net.ipv4.ping_group_range` covering the user, or `CAP_NET_RAW`, or a `ping` binary.

**Recipe excerpt**

```yaml
    - name: ping
      contract: itf.capabilities.net.ping
      using: icmp.ping
      config:
        boot_timeout: 180
```

Members, signatures and config keys: `bazel run //tools/catalog:query -- sql "SELECT * FROM v_recipe_node WHERE provider LIKE 'ping.%'"`.
