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
load("@bazel_skylib//rules:common_settings.bzl", "bool_flag", "string_flag")
load("@rules_python//python:defs.bzl", "py_library")
load("//bazel:py_itf_plugin.bzl", "py_itf_plugin")

py_library(
    name = "lib",
    srcs = glob(["**/*.py"]) + ["//score/itf/packs:init"],
    data = ["README.md"],
    visibility = ["//test/packs:__subpackages__"],
    deps = ["//score/itf/core"],
)

# Toggle with: bazel test --//score/itf/packs/core_dump:extract_core_dumps
bool_flag(
    name = "extract_core_dumps",
    build_setting_default = False,
    visibility = ["//visibility:public"],
)

config_setting(
    name = "extract_core_dumps_enabled",
    flag_values = {":extract_core_dumps": "True"},
)

# Set with: bazel test --//score/itf/packs/core_dump:core_dumps_output_dir=/abs/path
string_flag(
    name = "core_dumps_output_dir",
    build_setting_default = "",
    visibility = ["//visibility:public"],
)

py_itf_plugin(
    name = "core_dump",
    enabled_plugins = ["score.itf.packs.core_dump.plugin"],
    plugin_args = select({
        ":extract_core_dumps_enabled": ["--extract-core-dumps"],
        "//conditions:default": [],
    }),
    py_library = ":lib",
    string_flag_args = {":core_dumps_output_dir": "--core-dumps-output-dir={}"},
    visibility = ["//visibility:public"],
)
