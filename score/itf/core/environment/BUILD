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
    name = "environment",
    srcs = [
        "__init__.py",
        "base.py",
        "bwrap.py",
        "docker_env.py",
        "noop.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        requirement("psutil"),
        requirement("tenacity"),
        requirement("docker"),
    ],
)

# Lighter target without docker dependency — for environments that only need bwrap/noop
py_library(
    name = "environment_lite",
    srcs = [
        "__init__.py",
        "base.py",
        "bwrap.py",
        "noop.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        requirement("psutil"),
        requirement("tenacity"),
    ],
)
