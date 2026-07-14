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

py_library(
    name = "config",
    srcs = ["config.py"],
    visibility = ["//visibility:public"],
    deps = [requirement("pydantic")],
)

py_library(
    name = "qemu",
    srcs = [
        "__init__.py",
        "checks.py",
        "plugin.py",
        "process.py",
        "qemu.py",
        "runtime.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        ":config",
        "//score/itf/core/ctf",
        "//score/itf/core/process",
        "//score/itf/core/utils",
        "//score/itf/plugins/capabilities/ping",
        "//score/itf/plugins/capabilities/ssh",
        "//score/itf/plugins/targets:pkg",
        requirement("pytest"),
    ],
)
