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

load("@bazel_skylib//rules:common_settings.bzl", "string_flag")

# ---------------------------------------------------------------------------
# SCTF sandbox backend flag
#
#   Usage:  bazel test //test:foo --//bazel:sctf_backend=docker
#           bazel test //test:foo --config=sctf-docker   (via .bazelrc alias)
# ---------------------------------------------------------------------------

string_flag(
    name = "sctf_backend",
    build_setting_default = "bwrap",
    values = [
        "bwrap",
        "docker",
        "none",
    ],
    visibility = ["//visibility:public"],
)

config_setting(
    name = "sctf_backend_bwrap",
    flag_values = {":sctf_backend": "bwrap"},
    visibility = ["//visibility:public"],
)

config_setting(
    name = "sctf_backend_docker",
    flag_values = {":sctf_backend": "docker"},
    visibility = ["//visibility:public"],
)

config_setting(
    name = "sctf_backend_none",
    flag_values = {":sctf_backend": "none"},
    visibility = ["//visibility:public"],
)
