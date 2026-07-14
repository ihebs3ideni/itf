# *******************************************************************************
# Copyright (c) 2025 Contributors to the Eclipse Foundation
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

# ---- ITF plugin targets (used by py_itf_test symbolic macro) ----

py_itf_plugin(
    name = "docker_plugin",
    enabled_plugins = [
        "score.itf.plugins.targets.docker.plugin",
        "score.itf.plugins.capabilities.ping.plugin",
        "score.itf.plugins.capabilities.ssh.plugin",
    ],
    py_library = "//score/itf/plugins/targets/docker",
    visibility = ["//visibility:public"],
)

py_itf_plugin(
    name = "qemu_plugin",
    enabled_plugins = [
        "score.itf.plugins.targets.qemu",
        "score.itf.plugins.capabilities.ping.plugin",
        "score.itf.plugins.capabilities.ssh.plugin",
    ],
    py_library = "//score/itf/plugins/targets/qemu",
    visibility = ["//visibility:public"],
)

py_itf_plugin(
    name = "dlt_plugin",
    enabled_plugins = [
        "score.itf.plugins.capabilities.dlt",
    ],
    plugin_args = [
        "--dlt-receive-path=$(location @score_itf//third_party/dlt:dlt-receive)",
    ],
    plugin_data_as_exec = [
        "@score_itf//third_party/dlt:dlt-receive",
    ],
    py_library = "//score/itf/plugins/capabilities/dlt",
    visibility = ["//visibility:public"],
)

py_itf_plugin(
    name = "dashboard_plugin",
    enabled_plugins = [
        "score.itf.plugins.utility.dashboard.plugin",
    ],
    py_library = "//score/itf/plugins/utility/dashboard",
    visibility = ["//visibility:public"],
)

py_itf_plugin(
    name = "sqlite_logger_plugin",
    enabled_plugins = [
        "score.itf.plugins.domain.sqlite_logger.plugin",
    ],
    py_library = "//score/itf/plugins/domain/sqlite_logger",
    visibility = ["//visibility:public"],
)

py_itf_plugin(
    name = "udp_heartbeat_plugin",
    enabled_plugins = [
        "score.itf.plugins.env.udp_heartbeat.plugin",
    ],
    py_library = "//score/itf/plugins/env/udp_heartbeat",
    visibility = ["//visibility:public"],
)

py_itf_plugin(
    name = "attribute_plugin",
    enabled_plugins = [
        "attribute_plugin",
    ],
    py_library = "@score_tooling//python_basics/score_pytest:attribute_plugin",
    visibility = ["//visibility:public"],
)
