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
# target file (`targets/<name>.itf.yaml`) says what the target is made of; the packs its factory labels name are the
# `itf_target`'s `packs`, and its targets/policy.py (`srcs`) keeps the code: readiness checks, evidence, and the
# starting of dlt-daemon. Tests do not list the policy; they list conftest.py (pytest fixtures).
# `bazel build //examples/itf:target_docker` compiles the docker target file and writes
# `target_docker.plan.json`. Each itf_target supplies the `${NAME}` values its target file uses: `files`
# names the built files (an image loader, a kernel), and its tests inherit them.

DOCKER = "@score_itf//score/itf/packs/docker"

DLT = "@score_itf//score/itf/packs/dlt"

itf_target(
    name = "target_docker",
    src = "targets/docker.itf.yaml",
    srcs = ["targets/policy.py"],
    files = {"ITF_IMAGE_LOAD": "//examples/docker:image_load"},
    packs = [DOCKER],
)

itf_target(
    name = "target_dlt",
    src = "targets/dlt.itf.yaml",
    srcs = ["targets/policy.py"],
    files = {"ITF_IMAGE_LOAD": "//examples/docker:dlt_image_load"},
    packs = [
        DLT,
        DOCKER,
    ],
)

itf_target(
    name = "target_qemu",
    src = "targets/qemu.itf.yaml",
    srcs = ["targets/policy.py"],
    files = {
        "ITF_QEMU_CONFIG": "targets/qemu_bridge_config.json",
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
    srcs = [
        "conftest.py",
        "test_example_app.py",
    ],
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
    srcs = [
        "conftest.py",
        "test_example_app.py",
    ],
    tags = ["manual"],
    target = ":target_qemu",
)

exports_files(
    [
        "targets/qemu_bridge_config.json",
        "targets/qemu_port_forwarding_config.json",
    ],
    visibility = ["//examples/legacy:__pkg__"],
)
