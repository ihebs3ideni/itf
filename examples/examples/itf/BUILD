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
load("@score_itf//:defs.bzl", "py_itf_test")

# `docker` and `qemu` run one test file on two machines; `dlt` receives a target's DLT logs.
# Each target picks a recipe and the packs its providers come from.

py_itf_test(
    name = "docker",
    srcs = [
        "conftest.py",
        "test_example_app.py",
    ],
    data = [
        "docker.yaml",
        "//examples/docker:image_load",
    ],
    env = {
        "ITF_IMAGE_LOAD": "$(location //examples/docker:image_load)",
        "ITF_RECIPE": "docker.yaml",
    },
    plugins = ["@score_itf//score/itf/packs/docker"],
)

py_itf_test(
    name = "dlt",
    srcs = [
        "conftest.py",
        "test_dlt_logs.py",
    ],
    data = [
        "dlt.yaml",
        "//examples/docker:dlt_image_load",
    ],
    env = {
        "ITF_DLT_IMAGE_LOAD": "$(location //examples/docker:dlt_image_load)",
        "ITF_RECIPE": "dlt.yaml",
    },
    plugins = [
        "@score_itf//score/itf/packs/dlt",
        "@score_itf//score/itf/packs/docker",
    ],
)

py_itf_test(
    name = "qemu",
    srcs = [
        "conftest.py",
        "test_example_app.py",
    ],
    data = [
        "qemu.yaml",
        "qemu_bridge_config.json",
        "//examples/itf/qnx:init",
    ],
    env = {
        "ITF_QEMU_CONFIG": "$(location qemu_bridge_config.json)",
        "ITF_QEMU_KERNEL": "$(location //examples/itf/qnx:init)",
        "ITF_RECIPE": "qemu.yaml",
    },
    plugins = [
        "@score_itf//score/itf/packs/qemu",
        "@score_itf//score/itf/packs/ssh",
    ],
    tags = ["manual"],
)

# Bench configurations of this project (score_itf's test resources are not visible to consumers).
exports_files(
    [
        "qemu_bridge_config.json",
        "qemu_port_forwarding_config.json",
    ],
    visibility = ["//examples/legacy:__pkg__"],
)
