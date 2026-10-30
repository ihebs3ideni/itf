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
load("//:defs.bzl", "py_itf_test")

# One generic suite, many recipes. Every test in suite/ (and specific/) is gated with
# @itf.requires on the contracts it uses: each target runs exactly the tests its recipe's platform
# supports, and lists the others as deselected with the reason. Adding a platform is adding a recipe.

SUITE = glob(["suite/*.py"])

CONFTEST = "//test/integration/recipes:conftest.py"

DOCKER_TAGS = ["requires-docker"]

QEMU_TAGS = ["manual"]  # qemu-system-*, /dev/kvm; run with --config=qemu-integration[-linux]

QEMU_PACKS = [
    "//score/itf/packs/ping",
    "//score/itf/packs/qemu",
    "//score/itf/packs/ssh",
]

# (name, recipe, packs, recipe-specific tests, data, env, tags)
RECIPES = [
    (
        "local",
        "local.yaml",
        ["//score/itf/packs/local"],
        [],
        [],
        {},
        [],
    ),
    (
        "serial",
        "serial.yaml",
        ["//score/itf/packs/serial"],
        [],
        [],
        {},
        [],
    ),
    (
        "docker",
        "docker.yaml",
        ["//score/itf/packs/docker"],
        ["specific/test_container.py"],
        [],
        {"ITF_EXTRA_MOUNT": "test/integration/suite"},
        DOCKER_TAGS,
    ),
    (
        "docker_ssh",
        "docker_ssh.yaml",
        [
            "//score/itf/packs/docker",
            "//score/itf/packs/net",
            "//score/itf/packs/ssh",
        ],
        ["specific/test_container.py"],
        [],
        {"ITF_EXTRA_MOUNT": "test/integration/suite"},
        DOCKER_TAGS,
    ),
    (
        "dlt_stream",
        "dlt_stream.yaml",
        [
            "//score/itf/packs/docker",
            "//score/itf/packs/dlt",
            "//score/itf/packs/dlt:on_target",
        ],
        ["specific/test_dlt_on_target.py"],
        ["//test/resources:image_load"],
        {
            "ITF_DLT_PORT": "",  # any free host port
            "ITF_IMAGE_LOAD": "$(location //test/resources:image_load)",
        },
        DOCKER_TAGS,
    ),
    (
        "dlt_receive",
        "dlt_receive.yaml",
        [
            "//score/itf/packs/docker",
            "//score/itf/packs/dlt:on_target",
            "//score/itf/packs/dlt:receive",
        ],
        ["specific/test_dlt_on_target.py"],
        ["//test/resources:image_load"],
        {
            "ITF_DLT_PORT": "13490",  # dlt-receive's TCP mode always connects to 13490
            "ITF_IMAGE_LOAD": "$(location //test/resources:image_load)",
        },
        DOCKER_TAGS,
    ),
    (
        "qnx_bridge",
        "qemu.yaml",
        QEMU_PACKS,
        [],
        [
            "//test/resources:qemu_bridge_config",
            "//test/resources/qnx:init",
        ],
        {
            "ITF_QEMU_CONFIG": "$(location //test/resources:qemu_bridge_config)",
            "ITF_QEMU_KERNEL": "$(location //test/resources/qnx:init)",
        },
        QEMU_TAGS,
    ),
    (
        "qnx_port_forwarding",
        "qemu.yaml",
        QEMU_PACKS,
        [],
        [
            "//test/resources:qemu_port_forwarding_config",
            "//test/resources/qnx:init",
        ],
        {
            "ITF_QEMU_CONFIG": "$(location //test/resources:qemu_port_forwarding_config)",
            "ITF_QEMU_KERNEL": "$(location //test/resources/qnx:init)",
        },
        QEMU_TAGS,
    ),
    (
        "ubuntu",
        "qemu.yaml",
        QEMU_PACKS,
        ["specific/test_disk.py"],
        [
            "//test/resources:qemu_disk_image",
            "@os_images//ubuntu_x86_64:image",
            "@os_images//ubuntu_x86_64:qemu_config",
        ],
        {
            "ITF_QEMU_CONFIG": "$(location @os_images//ubuntu_x86_64:qemu_config)",
            "ITF_QEMU_DISK": "$(location //test/resources:qemu_disk_image)",
            "ITF_QEMU_ROOTFS": "$(location @os_images//ubuntu_x86_64:image)",
        },
        QEMU_TAGS,
    ),
    (
        "ebclfsa",
        "qemu.yaml",
        QEMU_PACKS,
        ["specific/test_disk.py"],
        [
            "//test/resources:qemu_disk_image",
            "@os_images//ebclfsa_aarch64:image",
            "@os_images//ebclfsa_aarch64:kernel",
            "@os_images//ebclfsa_aarch64:qemu_config",
        ],
        {
            "ITF_QEMU_CONFIG": "$(location @os_images//ebclfsa_aarch64:qemu_config)",
            "ITF_QEMU_DISK": "$(location //test/resources:qemu_disk_image)",
            "ITF_QEMU_KERNEL": "$(location @os_images//ebclfsa_aarch64:kernel)",
            "ITF_QEMU_ROOTFS": "$(location @os_images//ebclfsa_aarch64:image)",
        },
        QEMU_TAGS,
    ),
]

[py_itf_test(
    name = name,
    timeout = "long",  # QEMU machines reboot in the restart and renew tests
    srcs = [CONFTEST] + SUITE + specific,
    data = ["//test/integration/recipes:yaml"] + data,
    env = env | {"ITF_RECIPE": recipe},
    plugins = packs,
    tags = tags,
    target_compatible_with = ["@platforms//os:linux"],
) for name, recipe, packs, specific, data, env, tags in RECIPES]

test_suite(
    name = "linux_qemu_tests",
    tags = ["manual"],
    tests = [
        ":ebclfsa",
        ":ubuntu",
    ],
)

test_suite(
    name = "qnx_qemu_tests",
    tags = ["manual"],
    tests = [
        ":qnx_bridge",
        ":qnx_port_forwarding",
    ],
)
