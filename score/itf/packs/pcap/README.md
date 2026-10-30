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

# Packet capture pack

tcpdump captures, built from source with libpcap and shipped with the pack.

| Bazel label | Loads |
|---|---|
| `//score/itf/packs/pcap` | capture started after `platform.up` |
| `//score/itf/packs/pcap:host` | capture on a host interface, started first |
| `//score/itf/packs/pcap:sim` | in-memory capture |

**Providers**

- `tcpdump.capture` (observe.capture): `interface`, `filter`, `out_dir`; `path()`, `running()`, per-test `window(name)`

**Actions**

- `tcpdump.start_capture` / `tcpdump.start_host_capture` → `itf.states.capture.running`

**Host prerequisites:** `CAP_NET_RAW` (or root) and the interface on the host.

**Recipe excerpt**

```yaml
    - name: capture
      contract: itf.capabilities.observe.capture
      using: tcpdump.capture
      config:
        interface: docker0
        filter: tcp port 22
```

Members, signatures and config keys: `bazel run //tools/catalog:query -- sql "SELECT * FROM v_recipe_node WHERE provider LIKE 'pcap.%'"`.
