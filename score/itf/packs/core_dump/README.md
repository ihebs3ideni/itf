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

# Core dumps pack

Copies core files off every scope that offers `exec.command` and `files.transfer`, at teardown while the target still runs.

| Bazel label | Loads |
|---|---|
| `//score/itf/packs/core_dump` | `score.itf.packs.core_dump.plugin` (an `itf_teardown` hook) |

**Providers**

- —

**Actions**

- —

**Host prerequisites:** Enable with `--//score/itf/packs/core_dump:extract_core_dumps`; output in `$TEST_UNDECLARED_OUTPUTS_DIR/coredumps` or `--//score/itf/packs/core_dump:core_dumps_output_dir`.

Members, signatures and config keys: `bazel run //tools/catalog:query -- sql "SELECT * FROM v_recipe_node WHERE provider LIKE 'core.%'"`.
