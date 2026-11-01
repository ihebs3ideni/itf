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
load("//:defs.bzl", "itf_target", "py_itf_test")

# One generic suite, many compositions. Every test in suite/ (and specific/) is gated with @itf.requires on the
# roles it uses (`command`, `files`, ...): each target runs exactly the tests its composition's platform supports,
# and lists the others as deselected with the reason. Adding a platform is adding a composition.

SUITE = glob(["suite/*.py"])

CONFTEST = "targets/conftest.py"

DOCKER_TAGS = ["requires-docker"]

QEMU_TAGS = ["manual"]  # qemu-system-*, /dev/kvm; run with --config=qemu-integration[-linux]

PACKS = "//score/itf/packs/"

QEMU_PACKS = [
    PACKS + "ping",
    PACKS + "qemu",
    PACKS + "ssh",
]

# (name, composition, packs, specific tests, built files, other ${NAME} values, tags, plugins). The itf_target
# supplies both to the compile and to every test of the target.
TARGETS = [
    (
        "local",
        "local.itf.yaml",
        [PACKS + "local"],
        [],
        {},
        {},
        [],
        [],
    ),
    (
        "serial",
        "serial.itf.yaml",
        [PACKS + "serial"],
        [],
        {},
        {},
        [],
        [],
    ),
    (
        "docker",
        "docker.itf.yaml",
        [PACKS + "docker"],
        ["specific/test_container.py"],
        {},
        {"ITF_EXTRA_MOUNT": "test/integration/suite"},
        DOCKER_TAGS,
        [],
    ),
    (
        "docker_ssh",
        "docker_ssh.itf.yaml",
        [
            PACKS + "docker",
            PACKS + "net",
            PACKS + "ssh",
        ],
        ["specific/test_container.py"],
        {},
        {"ITF_EXTRA_MOUNT": "test/integration/suite"},
        DOCKER_TAGS,
        [],
    ),
    (
        "dlt_stream",
        "dlt_stream.itf.yaml",
        [
            PACKS + "docker",
            PACKS + "dlt",
        ],
        ["specific/test_dlt_on_target.py"],
        {"ITF_IMAGE_LOAD": "//test/resources:image_load"},
        {"ITF_DLT_PORT": ""},  # any free host port
        DOCKER_TAGS,
        [PACKS + "dlt:on_target"],
    ),
    (
        "dlt_receive",
        "dlt_receive.itf.yaml",
        [
            PACKS + "docker",
            PACKS + "dlt",
        ],
        ["specific/test_dlt_on_target.py"],
        {"ITF_IMAGE_LOAD": "//test/resources:image_load"},
        {"ITF_DLT_PORT": "13490"},  # dlt-receive's TCP mode always connects to 13490
        DOCKER_TAGS,
        [PACKS + "dlt:on_target"],
    ),
    (
        "qnx_bridge",
        "qemu.itf.yaml",
        QEMU_PACKS,
        [],
        {
            "ITF_QEMU_CONFIG": "//test/resources:qemu_bridge_config",
            "ITF_QEMU_KERNEL": "//test/resources/qnx:init",
        },
        {},
        QEMU_TAGS,
        [],
    ),
    (
        "qnx_port_forwarding",
        "qemu.itf.yaml",
        QEMU_PACKS,
        [],
        {
            "ITF_QEMU_CONFIG": "//test/resources:qemu_port_forwarding_config",
            "ITF_QEMU_KERNEL": "//test/resources/qnx:init",
        },
        {},
        QEMU_TAGS,
        [],
    ),
    (
        "ubuntu",
        "qemu.itf.yaml",
        QEMU_PACKS,
        ["specific/test_disk.py"],
        {
            "ITF_QEMU_CONFIG": "@os_images//ubuntu_x86_64:qemu_config",
            "ITF_QEMU_DISK": "//test/resources:qemu_disk_image",
            "ITF_QEMU_ROOTFS": "@os_images//ubuntu_x86_64:image",
        },
        {},
        QEMU_TAGS,
        [],
    ),
    (
        "ebclfsa",
        "qemu.itf.yaml",
        QEMU_PACKS,
        ["specific/test_disk.py"],
        {
            "ITF_QEMU_CONFIG": "@os_images//ebclfsa_aarch64:qemu_config",
            "ITF_QEMU_DISK": "//test/resources:qemu_disk_image",
            "ITF_QEMU_KERNEL": "@os_images//ebclfsa_aarch64:kernel",
            "ITF_QEMU_ROOTFS": "@os_images//ebclfsa_aarch64:image",
        },
        {},
        QEMU_TAGS,
        [],
    ),
]

# One composition per platform, compiled during the build (`bazel build //test/integration:docker` writes
# docker.plan.json and fails with ITF's diagnostics), and the same suite run against each.
[itf_target(
    name = "target_" + name,
    src = "targets/" + composition,
    srcs = [CONFTEST],
    data = glob(["targets/*.itf.yaml"]),
    env = env,
    files = files,
    packs = packs,
    tags = tags,
) for name, composition, packs, specific, files, env, tags, plugins in TARGETS]

[py_itf_test(
    name = name,
    timeout = "long",  # QEMU machines reboot in the restart and renew tests
    srcs = [CONFTEST] + SUITE + specific,
    plugins = plugins,
    tags = tags,
    target = ":target_" + name,
    target_compatible_with = ["@platforms//os:linux"],
) for name, composition, packs, specific, files, env, tags, plugins in TARGETS]

CONFORMANCE = [
    "local",
    "serial",
    "docker",
    "docker_ssh",
]

[py_itf_test(
    name = "conformance_" + name,
    timeout = "long",
    srcs = [
        CONFTEST,
        "conformance/test_conformance.py",
    ],
    plugins = ["//score/itf/contracts:conformance"],
    tags = tags,
    target = ":target_" + name,
    target_compatible_with = ["@platforms//os:linux"],
) for name, composition, packs, specific, files, env, tags, plugins in TARGETS if name in CONFORMANCE]

# The same local composition with an override file: the facts of one setup (the platform's working directory).
itf_target(
    name = "target_local_override",
    src = "targets/local.itf.yaml",
    overrides = ["overrides/local.itf.yaml"],
    packs = [PACKS + "local"],
)

py_itf_test(
    name = "local_override",
    srcs = [CONFTEST] + SUITE + ["specific/test_override_values.py"],
    target = ":target_local_override",
    target_compatible_with = ["@platforms//os:linux"],
)

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
