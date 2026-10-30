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

# One generic test file, four targets: each runs it against its own recipe, with the packs that recipe uses.

DOCKER = "@score_itf//score/itf/packs/docker"

[
    py_itf_test(
        name = name,
        srcs = [
            "conftest.py",
            "test_exec.py",
        ],
        data = [recipe] + data,
        env = {"ITF_CONFIG": "$(location %s)" % recipe} | env,
        plugins = plugins,
    )
    for name, recipe, plugins, data, env in [
        # A plain container, through the container API.
        (
            "container",
            "a_container.yaml",
            [DOCKER],
            [],
            {},
        ),
        # A container running sshd, over SSH.
        (
            "ssh",
            "b_ssh.yaml",
            [
                DOCKER,
                "@score_itf//score/itf/packs/net",
                "@score_itf//score/itf/packs/ssh",
            ],
            [],
            {},
        ),
        # A serial console on a shell over a pseudo-terminal: no container, no hardware.
        (
            "serial",
            "c_serial.yaml",
            ["@score_itf//score/itf/packs/serial"],
            [],
            {},
        ),
        # A serial device in a container: fake_ecu.py answers on a TCP port, reached with pyserial's socket:// URL.
        (
            "serial_device",
            "d_serial_device.yaml",
            [
                DOCKER,
                "@score_itf//score/itf/packs/serial",
            ],
            ["fake_ecu.py"],
            {"FAKE_ECU_SCRIPT": "$(location fake_ecu.py)"},
        ),
    ]
]
