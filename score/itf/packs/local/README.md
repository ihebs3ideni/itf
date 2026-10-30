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

# Local host pack

The test host itself as the platform: commands, processes and files through subprocess. Runs anywhere; useful for host-side binaries and for capability suites without a daemon.

| Bazel label | Loads |
|---|---|
| `//score/itf/packs/local` | `score.itf.packs.local.plugin` |

**Providers**

- `local.instance` (platform.instance): a working directory (`root`, default temporary)
- `local.exec` (exec.command), `local.process` (exec.process), `local.files` (files.transfer)

**Actions**

- `local.start_platform` → `itf.states.platform.up`

**Host prerequisites:** None.

**Recipe excerpt**

```yaml
    - name: platform
      contract: itf.capabilities.platform.instance
      using: local.instance
    - name: command
      contract: itf.capabilities.exec.command
      using: local.exec
```

Members, signatures and config keys: `bazel run //tools/catalog:query -- sql "SELECT * FROM v_recipe_node WHERE provider LIKE 'local.%'"`.
