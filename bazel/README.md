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

# Bazel rules

Loaded through `@score_itf//:defs.bzl`.

| File | Rule | Does |
|---|---|---|
| `itf_target.bzl` | `itf_target` | compiles a target file in a build action (both gates, nothing constructed); carries its packs, policy, `env` and `files` to the tests that use it |
| `itf_plan.py` | | the planner the build action runs |
| `py_itf_test.bzl` | `py_itf_test` | a pytest run with the ITF adapter: `target = ":x"` (or a `select()` of targets), or ITF's original API through `plugins` and `args` |
| `py_itf_plugin.bzl` | `py_itf_plugin` | a pack or pytest plugin: its library, the plugins to enable, its arguments and data |
| `py_itf_unittest.bzl` | `py_itf_unittest` | a plain pytest run, for unit tests that need no target |
| `target_info.bzl` | `ItfTargetInfo` | what an `itf_target` hands its tests |

Two details of `py_itf_test`: a test without a target loads the compatibility core plugin first (the original
rule did); the wrapped `py_test` is built for `--host_platform`, as the original rule's `cfg = "exec"` was, so a
`select()` on its deps or plugins sees the same constraints, but with the target configuration's coverage settings,
so `bazel coverage` measures every test, also when the target is built for another platform. Reference:
`docs/reference/bazel_macros.rst`.
