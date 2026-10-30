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

# Network descriptors pack

Static endpoints and credentials other capabilities bind to.

| Bazel label | Loads |
|---|---|
| `//score/itf/packs/net` | `score.itf.packs.net.plugin` |

**Providers**

- `static.endpoint` (descriptor.endpoint): `host`, `port`
- `key.credentials`, `password.credentials` (descriptor.credentials): `user` with `key_path` or `password` (sensitive: redacted from artifacts)

**Actions**

- —

**Host prerequisites:** None.

**Recipe excerpt**

```yaml
    - name: endpoint
      contract: itf.capabilities.descriptor.endpoint
      using: static.endpoint
      config:
        host: 192.0.2.10
        port: 22
    - name: creds
      contract: itf.capabilities.descriptor.credentials
      using: key.credentials
      config:
        user: root
        key_path: keys/id_ed25519
```

Members, signatures and config keys: `bazel run //tools/catalog:query -- sql "SELECT * FROM v_recipe_node WHERE provider LIKE 'net.%'"`.
