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
load("@rules_python//python:defs.bzl", "py_library")
load("//bazel:py_itf_plugin.bzl", "py_itf_plugin")

py_library(
    name = "lib",
    srcs = glob(["**/*.py"]) + ["//score/itf/packs:init"],
    data = ["README.md"],
    visibility = ["//test/packs:__subpackages__"],
    deps = ["//score/itf/core"],
)

py_itf_plugin(
    name = "ping",
    enabled_plugins = ["score.itf.packs.ping.plugin"],
    py_library = ":lib",
    visibility = ["//visibility:public"],
)

# Platform up = answers ping; for machines no pack starts (hardware, an externally run VM).
py_itf_plugin(
    name = "boot",
    enabled_plugins = ["score.itf.packs.ping.boot"],
    py_library = ":lib",
    visibility = ["//visibility:public"],
)
