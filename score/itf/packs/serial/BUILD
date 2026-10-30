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
load("@itf_pip//:requirements.bzl", "requirement")
load("@rules_python//python:defs.bzl", "py_library")
load("//bazel:py_itf_plugin.bzl", "py_itf_plugin")

py_library(
    name = "lib",
    srcs = glob(["**/*.py"]) + ["//score/itf/packs:init"],
    data = ["README.md"],
    visibility = ["//test/packs:__subpackages__"],
    deps = [
        "//score/itf/core",
        requirement("pyserial"),
    ],
)

py_itf_plugin(
    name = "serial",
    enabled_plugins = ["score.itf.packs.serial.plugin"],
    py_library = ":lib",
    visibility = ["//visibility:public"],
)
