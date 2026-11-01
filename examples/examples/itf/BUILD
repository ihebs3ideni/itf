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
load("@score_itf//:defs.bzl", "itf_target", "py_itf_test")

# `docker` and `qemu` run one test file on two machines; `dlt` receives a target's DLT logs. Each
# composition (`<name>.itf.yaml`) says what the target is made of; the packs its factory labels name are the
# `itf_target`'s `packs`. conftest.py keeps the code: readiness checks, evidence, and the actions starting
# dlt-daemon and subscribing to its logs.
# `bazel build //examples/itf:target_docker` compiles the docker composition and writes
# `target_docker.plan.json`. Each itf_target supplies the `${NAME}` values its composition uses: `files` names
# the built files (an image loader, a kernel), and its tests inherit them.

DOCKER = "@score_itf//score/itf/packs/docker"

DLT = "@score_itf//score/itf/packs/dlt"

SRCS = [
    "conftest.py",
    "test_example_app.py",
]

itf_target(
    name = "target_docker",
    src = "docker.itf.yaml",
    srcs = ["conftest.py"],
    files = {"ITF_IMAGE_LOAD": "//examples/docker:image_load"},
    packs = [DOCKER],
)

itf_target(
    name = "target_dlt",
    src = "dlt.itf.yaml",
    srcs = ["conftest.py"],
    files = {"ITF_IMAGE_LOAD": "//examples/docker:dlt_image_load"},
    packs = [
        DLT,
        DOCKER,
    ],
)

itf_target(
    name = "target_qemu",
    src = "qemu.itf.yaml",
    srcs = ["conftest.py"],
    files = {
        "ITF_QEMU_CONFIG": "qemu_bridge_config.json",
        "ITF_QEMU_KERNEL": "//examples/itf/qnx:init",
    },
    packs = [
        "@score_itf//score/itf/packs/ping",
        "@score_itf//score/itf/packs/qemu",
        "@score_itf//score/itf/packs/ssh",
    ],
    tags = ["manual"],
)

py_itf_test(
    name = "docker",
    srcs = SRCS,
    target = ":target_docker",
)

py_itf_test(
    name = "dlt",
    srcs = [
        "conftest.py",
        "test_dlt_logs.py",
    ],
    target = ":target_dlt",
)

py_itf_test(
    name = "qemu",
    srcs = SRCS,
    tags = ["manual"],
    target = ":target_qemu",
)

exports_files(
    [
        "qemu_bridge_config.json",
        "qemu_port_forwarding_config.json",
    ],
    visibility = ["//examples/legacy:__pkg__"],
)
