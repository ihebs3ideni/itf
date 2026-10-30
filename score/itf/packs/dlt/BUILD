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
load("@bazel_skylib//rules:copy_file.bzl", "copy_file")
load("@rules_python//python:defs.bzl", "py_library")
load("//bazel:py_itf_plugin.bzl", "py_itf_plugin")

# Built from source (third_party/dlt) and shipped beside the pack, found through runfiles.
copy_file(
    name = "libdlt",
    src = "//third_party/dlt:libdlt.so",
    out = "libdlt.so.2",
    allow_symlink = True,
)

copy_file(
    name = "dlt_receive_bin",
    src = "//third_party/dlt:dlt-receive",
    out = "dlt-receive",
    allow_symlink = True,
    is_executable = True,
)

py_library(
    name = "lib",
    srcs = glob(["**/*.py"]) + ["//score/itf/packs:init"],
    data = [
        "README.md",
        ":dlt_receive_bin",
        ":libdlt",
    ],
    visibility = ["//test/packs:__subpackages__"],
    deps = [
        "//score/itf/core",
        "//score/itf/core/process",
        "//third_party/python_dlt",
        "@rules_python//python/runfiles",
    ],
)

# DLT over TCP, stdlib framing.
py_itf_plugin(
    name = "dlt",
    enabled_plugins = ["score.itf.packs.dlt.plugin"],
    py_library = ":lib",
    visibility = ["//visibility:public"],
)

# DLT over UDP multicast, stdlib framing.
py_itf_plugin(
    name = "multicast",
    enabled_plugins = ["score.itf.packs.dlt.multicast.plugin"],
    py_library = ":lib",
    visibility = ["//visibility:public"],
)

# DLT through the bundled dlt-receive, queried with python-dlt.
py_itf_plugin(
    name = "receive",
    enabled_plugins = ["score.itf.packs.dlt.receive.plugin"],
    py_library = ":lib",
    visibility = ["//visibility:public"],
)

# The dlt_on_target fixture: dlt-receive run on the target through files.transfer and exec.process.
py_itf_plugin(
    name = "on_target",
    enabled_plugins = ["score.itf.packs.dlt.on_target"],
    py_library = ":lib",
    visibility = ["//visibility:public"],
)

py_itf_plugin(
    name = "sim",
    enabled_plugins = ["score.itf.packs.dlt.sim.plugin"],
    py_library = ":lib",
    visibility = ["//visibility:public"],
)
