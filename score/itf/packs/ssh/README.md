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

# SSH pack

A paramiko session to the target, and commands, processes and SFTP file transfer over it.

| Bazel label | Loads |
|---|---|
| `//score/itf/packs/ssh` | `score.itf.packs.ssh.plugin` |
| `//score/itf/packs/ssh:sim` | in-memory shell for offline runs |

**Providers**

- `ssh.shell` (exec.shell): password or key login, retries, keep-alive; `run`, `exec`, `exec_lines` (separate stderr, start and run timeouts), `client()`
- `ssh.exec` (exec.command), `ssh.process` (exec.process), `sftp.files` (files.transfer, plus `exists`, `listdir`, `remove`, `upload_dir`, `download_dir`)

**Actions**

- `ssh.open_session` → `itf.states.shell.open` and `itf.states.network.reachable`, each with its own probe (connected; endpoint accepts TCP)

**Host prerequisites:** None beyond paramiko (pip, locked).

**Recipe excerpt**

```yaml
    - name: shell
      contract: itf.capabilities.exec.shell
      using: ssh.shell
      config:
        n_retries: 20
    - name: command
      contract: itf.capabilities.exec.command
      using: ssh.exec
```

Members, signatures and config keys: `bazel run //tools/catalog:query -- sql "SELECT * FROM v_recipe_node WHERE provider LIKE 'ssh.%'"`.
