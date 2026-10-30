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

# Docker pack

A container as the target platform, reached through the Docker API (works with any image) and, with the ssh pack, over SSH.

| Bazel label | Loads |
|---|---|
| `//score/itf/packs/docker` | `score.itf.packs.docker.plugin` |
| `//score/itf/packs/docker:sim` | in-memory platform for offline runs |

**Providers**

- `docker.instance` (platform.instance): image, command, environment, ports, volumes, its own bridge network, image `bootstrap`, coverage extraction; `ip()`, `gateway()`, `host_port()`, `restart()`
- `docker.exec` (exec.command), `docker.process` (exec.process), `docker.files` (files.transfer)
- `docker.endpoint` (descriptor.endpoint): a service in the container, by IP or published port (`via`)

**Actions**

- `docker.start_platform` → `itf.states.platform.up`

**Config string formats:** `environment` is `KEY=value,KEY2=value2`; `ports` is `22/tcp:2222,3490/tcp` (container port, optional host port, otherwise one is chosen) or just `2222`; `volumes` is `/host:/in/container:rw,...`. `docker.endpoint` `via` is `auto` (published port when published, else the container IP), `ip` or `published`.

**Host prerequisites:** A Docker-compatible daemon (`DOCKER_HOST` for Podman). Under rootless Podman, publish ports and use `docker.endpoint` with `via: published`.

**Recipe excerpt**

```yaml
setup:
  nodes:
    - name: platform
      contract: itf.capabilities.platform.instance
      using: docker.instance
      config:
        image: ubuntu:24.04
    - name: command
      contract: itf.capabilities.exec.command
      using: docker.exec
init:
  goals:
    - itf.states.platform.up
```

Members, signatures and config keys: `bazel run //tools/catalog:query -- sql "SELECT * FROM v_recipe_node WHERE provider LIKE 'docker.%'"`.
