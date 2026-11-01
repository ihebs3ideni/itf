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

# Starter: a Docker container from an image. Copy this folder and change the values marked `# CHANGE:`.
#
# Two kinds of file say what the target is: the composition (target.itf.yaml) is its structure, what it is
# made of; an override file (bench.itf.yaml) holds the facts of one bench and is merged over the composition
# by role. `bazel build :target` compiles the composition and writes target.plan.json: the roles, the wiring
# and the ordered actions, before anything exists.

DOCKER = "@score_itf//score/itf/packs/docker"

SRCS = [
    "conftest.py",
    "test_hello.py",
]

itf_target(
    name = "target",
    src = "target.itf.yaml",
    srcs = ["conftest.py"],
    # CHANGE: the packs the factory labels name (`docker.platform` names `docker`).
    packs = [DOCKER],
)

# The same composition with the bench's override file.
itf_target(
    name = "target_bench",
    src = "target.itf.yaml",
    srcs = ["conftest.py"],
    overrides = ["bench.itf.yaml"],
    packs = [DOCKER],
)

py_itf_test(
    name = "test",
    srcs = SRCS,
    target = ":target",
)

py_itf_test(
    name = "test_bench",
    srcs = SRCS,
    target = ":target_bench",
)
