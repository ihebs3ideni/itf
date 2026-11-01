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
load("@rules_python//python:defs.bzl", "py_binary")
load("//:defs.bzl", "itf_target", "py_itf_unittest")

PACKS = ["//score/itf/packs/sim"]

# A composition compiled during the build: bazel build //test/plans:ok writes ok.plan.json.
itf_target(
    name = "ok",
    src = "ok.itf.yaml",
    packs = PACKS,
)

# The same planner a target uses, run by hand on compositions that must fail the build.
py_binary(
    name = "failing_planner",
    srcs = ["//bazel:itf_plan.py"],
    main = "//bazel:itf_plan.py",
    deps = [
        "//:itf",
        "//score/itf/packs/local",
    ] + PACKS,
)

py_itf_unittest(
    name = "plan_test",
    srcs = ["test_plan.py"],
    data = [
        "no_store.itf.yaml",
        "pack_outside.itf.yaml",
        ":failing_planner",
        ":ok",
    ],
    env = {
        "NO_STORE": "$(rootpath no_store.itf.yaml)",
        "OK_PLAN": "$(rootpath :ok)",
        "OUTSIDE": "$(rootpath pack_outside.itf.yaml)",
        "PLANNER": "$(rootpath :failing_planner)",
    },
)
