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
load("@itf_pip//:requirements.bzl", "requirement")

copy_file(
    name = "libdlt",
    src = "//third_party/dlt:libdlt.so",
    out = "libdlt.so.2",
    allow_symlink = True,
)

py_library(
    name = "dlt",
    srcs = [
        "__init__.py",
        "components.py",
        "dlt_receive.py",
        "dlt_window.py",
        "plugin.py",
    ],
    data = [
        ":libdlt",
    ],
    visibility = ["//visibility:public"],
    deps = [
        "//score/itf/core/ctf",
        "//score/itf/core/process",
        "//score/itf/core/utils",
        "//score/itf/plugins/capabilities:pkg",
        "//third_party/python_dlt",
        requirement("pytest"),
    ],
)
