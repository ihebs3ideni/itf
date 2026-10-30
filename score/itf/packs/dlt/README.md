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

DLT logs from the target: a stdlib TCP stream or UDP multicast receiver, the bundled `dlt-receive` with python-dlt queries, and `dlt-receive` run on the target.

| Bazel label | Loads |
|---|---|
| `//score/itf/packs/dlt` | TCP stream, stdlib framing |
| `//score/itf/packs/dlt:multicast` | UDP multicast, stdlib framing |
| `//score/itf/packs/dlt:receive` | the Bazel-built dlt-receive, recorded to a file |
| `//score/itf/packs/dlt:on_target` | the `dlt_on_target` fixture |
| `//score/itf/packs/dlt:sim` | in-memory logs |

**Providers**

- `dlt.stream`, `dlt.multicast`, `dlt.receive`, `dlt.receive_tcp` (observe.logs): `lines()`, `filter(apid, ctid)`; dlt-receive variants add `record()` (python-dlt `find(query)`) and per-test `window()`

**Actions**

- `dlt.subscribe_stream`, `dlt.join_multicast`, `dlt.start_receive` → `itf.states.logs.active` (load one variant)

**Host prerequisites:** None: dlt-receive and libdlt are built from source. The patched DLT build listens on TCP 13490.

**Recipe excerpt**

```yaml
    - name: logs
      contract: itf.capabilities.observe.logs
      using: dlt.stream
```

Members, signatures and config keys: `bazel run //tools/catalog:query -- sql "SELECT * FROM v_recipe_node WHERE provider LIKE 'dlt.%'"`.
