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

# Starter: a machine reached over SSH. For the local demo it is a container running sshd; for a real machine
# see target.itf.yaml. The composition is the structure; bench.itf.yaml holds the facts of one bench.

SRCS = [
    "conftest.py",
    "test_hello.py",
]

# CHANGE: the packs the factory labels name; drop docker for a real machine.
PACKS = [
    "@score_itf//score/itf/packs/docker",
    "@score_itf//score/itf/packs/net",
    "@score_itf//score/itf/packs/ssh",
]

itf_target(
    name = "target",
    src = "target.itf.yaml",
    srcs = ["conftest.py"],
    packs = PACKS,
)

itf_target(
    name = "target_bench",
    src = "target.itf.yaml",
    srcs = ["conftest.py"],
    overrides = ["bench.itf.yaml"],
    packs = PACKS,
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
