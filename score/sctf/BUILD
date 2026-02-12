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

exports_files([
    "pytest.ini",
])

py_library(
    name = "sctf",
    srcs = [
        "__init__.py",
        "bootstrap.py",
        "config.py",
        "exception/__init__.py",
        "exception/exception.py",
        "plugins/basic_sandbox.py",
        "sandbox/__init__.py",
        "sandbox/async_log_capture.py",
        "sandbox/process.py",
        "sandbox/sandbox.py",
        "sim/__init__.py",
        "sim/base_sim.py",
        "sim/state.py",
        "utils/__init__.py",
        "utils/file_utils.py",
    ],
    imports = ["."],
    visibility = ["//visibility:public"],
    deps = [
        "//score/itf/core/utils",
    ],
)
