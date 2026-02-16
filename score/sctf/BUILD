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
    name = "sctf",
    srcs = [
        "__init__.py",
        "environment/__init__.py",
        "environment/base.py",
        "environment/docker_env.py",
        "exception/__init__.py",
        "exception/exception.py",
        "plugins/__init__.py",
    ],
    imports = [".."],
    visibility = ["//visibility:public"],
    deps = [
        "//score/itf/core/docker",
        "//score/itf/core/utils",
        "//score/itf/plugins:docker",
        requirement("pytest"),
    ],
)
