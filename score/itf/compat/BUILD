# *******************************************************************************
# Copyright (c) 2025 Contributors to the Eclipse Foundation
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
load("@itf_pip//:requirements.bzl", "requirement")
load("@rules_python//python:defs.bzl", "py_library")
load("//:defs.bzl", "itf_target")

# The compatibility layer: ITF's original API served by the new engine and the packs. The original module paths
# (//score/itf/plugins, //score/itf/core/com, //score/itf/core/target, //score/itf/core/utils) only re-export from
# here and from the packs.
py_library(
    name = "compat",
    srcs = glob(["**/*.py"]),
    data = glob(["targets/*"]),
    visibility = ["//visibility:public"],
    deps = [
        "//score/itf/core",
        "//score/itf/core/process",
        "//score/itf/packs/core_dump",
        "//score/itf/packs/dlt",
        "//score/itf/packs/docker",
        "//score/itf/packs/net",
        "//score/itf/packs/ping",
        "//score/itf/packs/qemu",
        "//score/itf/packs/ssh",
        requirement("pytest"),
    ],
)

# The target files the original options select, compiled at build time like a project's own: one that stops
# compiling fails the build, also for the QEMU ones no CI run brings up. Their ${NAME} values only exist at test
# time (the options fill them), so the compile keeps them as placeholders.
PACKS = {
    "docker": [
        "//score/itf/packs/docker",
        "//score/itf/packs/net",
        "//score/itf/packs/ssh",
    ],
    "qemu": [
        "//score/itf/packs/ping",
        "//score/itf/packs/qemu",
        "//score/itf/packs/ssh",
    ],
}

[itf_target(
    name = kind + dlt,
    src = "targets/{}{}.itf.yaml".format(kind, dlt),
    srcs = ["targets/policy.py"],
    data = glob(["targets/*.itf.yaml"]),
    packs = PACKS[kind] + (["//score/itf/packs/dlt"] if dlt else []),
) for kind in PACKS for dlt in [
    "",
    "_dlt",
]]

# The shipped target files and their policy, for //test/plans:shipped_targets_test.
filegroup(
    name = "target_files",
    srcs = glob(["targets/*"]),
    visibility = ["//test/plans:__pkg__"],
)
