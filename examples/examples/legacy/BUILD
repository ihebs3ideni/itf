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
load("@score_itf//:defs.bzl", "py_itf_test")

# Legacy infra: ITF's original test cases, unchanged apart from imports, running on the new
# framework through this project's recipes (recipes/) and facade (conftest.py, legacy_itf/).

# The facade: adapters over the recipe's nodes; it imports no pack.
py_library(
    name = "legacy_itf",
    srcs = glob(["legacy_itf/**/*.py"]),
    imports = ["."],
)

RECIPES = glob(["recipes/*.yaml"])

DOCKER_PACKS = [
    "@score_itf//score/itf/packs/docker",
    "@score_itf//score/itf/packs/net",
    "@score_itf//score/itf/packs/ssh",
]

QEMU_PACKS = [
    "@score_itf//score/itf/packs/ping",
    "@score_itf//score/itf/packs/qemu",
    "@score_itf//score/itf/packs/ssh",
]

DLT_PACKS = [
    "@score_itf//score/itf/packs/dlt:on_target",
    "@score_itf//score/itf/packs/dlt:receive",
]

py_itf_test(
    name = "test_docker",
    srcs = [
        "conftest.py",
        "test_async_exec.py",
        "test_docker.py",
    ],
    args = ["--docker-image=ubuntu:24.04"],
    data = RECIPES,
    plugins = DOCKER_PACKS,
    deps = [":legacy_itf"],
)

py_itf_test(
    name = "test_ssh",
    srcs = [
        "conftest.py",
        "test_ssh.py",
    ],
    args = ["--docker-image=linuxserver/openssh-server:version-10.2_p1-r0"],
    data = RECIPES,
    plugins = DOCKER_PACKS,
    deps = [":legacy_itf"],
)

[py_itf_test(
    name = name,
    srcs = [
        "conftest.py",
        name + ".py",
    ],
    args = [
        "--docker-image-bootstrap=$(location //examples/docker:dlt_image_load)",
        "--docker-image=score_itf_dlt:latest",
        "--dlt-config=$(location dlt_config.json)",
        "--dlt-on-target-files=files",
        "--dlt-on-target-process=process",
    ],
    data = RECIPES + [
        "dlt_config.json",
        "//examples/docker:dlt_image_load",
    ],
    plugins = DOCKER_PACKS + DLT_PACKS,
    deps = [":legacy_itf"],
) for name in [
    "test_dlt",
    "test_dlt_on_target",
]]

[py_itf_test(
    name = name,
    srcs = [
        "conftest.py",
        "test_async_exec.py",
        "test_qemu.py",
    ],
    args = [
        "--qemu-config=$(location //examples/itf:%s.json)" % config,
        "--qemu-image=$(location //examples/itf/qnx:init)",
    ],
    data = RECIPES + [
        "//examples/itf/qnx:init",
        "//examples/itf:%s.json" % config,
    ],
    plugins = QEMU_PACKS,
    tags = ["manual"],
    deps = [":legacy_itf"],
) for name, config in [
    ("test_qemu_bridge_network", "qemu_bridge_config"),
    ("test_qemu_port_forwarding", "qemu_port_forwarding_config"),
]]

# The adapter's own logic, without a container.
py_itf_test(
    name = "test_legacy_dlt_adapter",
    srcs = ["test_legacy_dlt_adapter.py"],
    deps = [":legacy_itf"],
)
