# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************
"""ITF's compatibility layer: the original API (the core, docker, qemu, dlt and core dump plugins, `Target`, their
fixtures, options and Bazel labels) served by the new engine, so existing tests run unchanged.

It switches on through the entry points a project already uses, never through a setting: the original plugin
labels and options select it, `py_itf_test(target = ...)` does not. Every run on it says so once, with what to
migrate.

- `plugins/`   the original pytest plugins: their options, the target file the options select, the fixtures
- `targets/`   the target files the options fill, one per original plugin combination, and their policy
- `target`     the original `Target` and `UnsupportedTarget` base classes, for a project's own target plugins
- `legacy`     `LegacyTarget`, `DockerTarget`, `QemuTarget`: the original methods over the roles, as a facade
               (`score.itf.Facade`, the core's mechanism, which a project uses for its own API without this layer)
- `utils`      the original small helpers (`padder`, `Bunch`, Bazel output paths)
- `tools`      `itf compat report` and `itf compat target`

The original module paths (`score.itf.plugins.*`, `score.itf.core.com`, `.target`, `.utils`) only re-export, from
here or from the packs, which carry the original classes (`Ssh`, `Sftp`, `DltReceive`, ...). So the whole layer is
this package, and removing it is one change.
"""

from .notice import ItfCompatibilityWarning  # noqa: E402,F401  (the plugins import it from .notice itself)
