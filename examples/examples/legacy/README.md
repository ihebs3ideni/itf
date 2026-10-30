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

# Legacy infra: the original ITF API on the new framework

A project-side compatibility layer, to copy into a project that has many tests written for ITF's
original plugins (`target.execute()`, `docker_plugin`, `--docker-image`, `docker_configuration`,
`DltReceive`). It is not part of ITF: ITF ships only the core and packs.

| Piece | Role |
|---|---|
| `recipes/docker.yaml`, `recipes/qemu.yaml` | The declarative half: what the original options declared, parameterised by `${LEGACY_*}` |
| `conftest.py` | The policy: the original options select and fill a recipe; facade fixtures (`target`, `docker_configuration`, `dlt_config`, `dlt`, `dlt_on_target`) |
| `legacy_itf/` | `LegacyTarget` over contracts, the original `Ssh`, `Sftp`, ping and DLT helpers, `requires_capabilities` |
| `test_*.py` | ITF's original integration tests; only `score.itf.plugins.*` imports changed to `legacy_itf.*` |

The container is renewed per test unless `--keep-target`, as the original plugin did. With QEMU,
DLT recording starts once the machine is up. Migrate tests to the new API one by one (see
docs/how-to/migrate.md and `test/integration`), then delete this layer.
