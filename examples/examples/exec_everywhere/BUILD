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

# One test file (test_exec.py) on four targets. Each test asks for the roles it uses (`command`, `files`,
# `console`), so a target runs the tests its target file supports and lists the others as deselected, with
# the reason. A target file per target says what the target is made of (`targets/<name>.itf.yaml`); its targets/policy.py
# keeps the code (readiness checks, evidence, the action that waits for the fake ECU) and is not listed by tests.
#
# `bazel build //examples/exec_everywhere:target_container` compiles a target file and writes
# `target_container.plan.json`: the roles, the wiring and the ordered actions, before anything exists.

DOCKER = "@score_itf//score/itf/packs/docker"

NET = "@score_itf//score/itf/packs/net"

SERIAL = "@score_itf//score/itf/packs/serial"

SSH = "@score_itf//score/itf/packs/ssh"

# (name, packs, data, test environment, stand-ins while the target file compiles, files the target file includes)
# The SSH demo container's own account (the ssh starter's): not a secret.
DEMO_LOGIN = {
    "SSH_PASSWORD": "score",
    "SSH_USER": "score",
}

TARGETS = [
    (
        "container",
        [DOCKER],
        [],
        {},
        {},
        [],
    ),
    (
        "ssh",
        [
            DOCKER,
            NET,
            SSH,
        ],
        [],
        DEMO_LOGIN,
        DEMO_LOGIN,
        ["//examples/starter/ssh:targets/target.itf.yaml"],  # ssh.itf.yaml includes the ssh starter
    ),
    (
        "serial",
        [SERIAL],
        [],
        {},
        {},
        [],
    ),
    (
        "serial_device",
        [
            DOCKER,
            SERIAL,
        ],
        ["targets/fake_ecu.py"],
        {"FAKE_ECU_SCRIPT": "$(rootpath targets/fake_ecu.py)"},
        {"FAKE_ECU_SCRIPT": "targets/fake_ecu.py"},
        [],
    ),
]

[itf_target(
    name = "target_" + name,
    src = "targets/" + name + ".itf.yaml",
    srcs = ["targets/policy.py"],
    data = includes,
    env = stand_ins,
    packs = packs,
) for name, packs, data, env, stand_ins, includes in TARGETS]

[py_itf_test(
    name = name,
    srcs = ["test_exec.py"],
    data = data,
    env = env,
    target = ":target_" + name,
) for name, packs, data, env, stand_ins, includes in TARGETS]
