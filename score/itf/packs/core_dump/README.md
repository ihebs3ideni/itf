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

# Core dump pack

Copies core files off every scope that has `exec.command` and `files.transfer`, at teardown. It declares no capabilities or actions, so it has no labels; enable it with its Bazel flag.

**Bazel:** `//score/itf/packs/core_dump`. Packs load from the labels of a composition (`core_dump.<name>`); never import one pack from another.

**Host prerequisites**

- enable with --//score/itf/packs/core_dump:extract_core_dumps
- output in $TEST_UNDECLARED_OUTPUTS_DIR/coredumps or --//score/itf/packs/core_dump:core_dumps_output_dir

