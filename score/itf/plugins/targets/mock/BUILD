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
load("@itf_pip//:requirements.bzl", "requirement")

py_library(
    name = "mock",
    srcs = [
        "__init__.py",
        "plugin.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        "//score/itf/core/ctf",
        "//score/itf/plugins/targets:pkg",
        requirement("pytest"),
    ],
)
