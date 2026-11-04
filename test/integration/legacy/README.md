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

# Legacy API integration tests

These tests exercise the original ITF API through the compatibility layer (`score/itf/compat`) alongside the
other integration suites. The Docker SSH tests use `--docker-ssh` when their image runs an SSH server, since the
compatibility Docker target does not assume SSH. `test/integration/README.md` maps these tests to the new API suite.

Also here: `shims_test` (the original module paths only re-export) and `layer/` (the original target as a facade).
`test_dlt` needs multicast between host and container, which a rootless engine does not route.
