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

# Pcap pack

A tcpdump capture of an interface.

**Bazel:** `//score/itf/packs/pcap`. Packs load from the labels of a composition (`pcap.<name>`); never import one pack from another.

| Label | Kind | Contract | What |
|---|---|---|---|
| `pcap.capture` | capability | `observe.capture` | the capture object |
| `pcap.start` | state | `capture.running` | start it once the platform is up |
| `pcap.start_on_host` | state | `capture.running` | start it on a host interface that already exists, before anything else |

**Host prerequisites**

- CAP_NET_RAW (or root) and the interface on the host

**Composition excerpt**

```yaml
capabilities:
  capture: pcap.capture
goals:
  - state: capture.running
    by: pcap.start
```
