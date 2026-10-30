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
load("//bazel:recipe.bzl", "itf_recipe", "node", "relation")
load(":benches.bzl", "dlt_container", "sshd_container")

# Recipes for //test/integration: YAML files (loaded by conftest.py from ITF_RECIPE) and Starlark
# targets (handed to py_itf_test(recipe = ...)). conftest.py also holds the code half of the policy.

exports_files(
    glob(["*.yaml"]) + ["conftest.py"],
    visibility = ["//test/integration:__pkg__"],
)

filegroup(
    name = "yaml",
    srcs = glob(["*.yaml"]),
    visibility = ["//test/integration:__pkg__"],
)

# docker_ssh.yaml, written in Starlark: the same plan, and a hermetic docker_ssh_starlark_plan test.
itf_recipe(
    name = "docker_ssh_starlark",
    conftest = "conftest.py",
    goals = [
        "itf.states.platform.up",
        "itf.states.network.reachable",
        "itf.states.shell.open",
    ],
    nodes = sshd_container("linuxserver/openssh-server:version-10.2_p1-r0", "score", "test/integration/suite"),
    plugins = [
        "//score/itf/packs/docker",
        "//score/itf/packs/net",
        "//score/itf/packs/ssh",
    ],
    visibility = ["//test/integration:__pkg__"],
)

# dlt_base.yaml and dlt_stream.yaml in Starlark: the image's oci_load is a label (location() puts it
# in the runfiles), and the stream recipe extends the base like the YAML pair does.
itf_recipe(
    name = "dlt_base_starlark",
    goals = ["itf.states.logs.active"],
    nodes = dlt_container("score_itf_examples:latest", "//test/resources:image_load"),
    plan_test = False,  # a base: the logs node comes from the recipes extending it
    plugins = ["//score/itf/packs/docker"],
    relations = [relation(
        "itf.states.logs.active",
        requires = ["bench.dlt_daemon.running"],
    )],
    visibility = ["//test/integration:__pkg__"],
)

itf_recipe(
    name = "dlt_stream_starlark",
    conftest = "conftest.py",
    extends = [":dlt_base_starlark"],
    nodes = [node(
        "logs",
        "itf.capabilities.observe.logs",
        config = {"ecu_id": "ECU1"},
        using = "dlt.stream",
    )],
    plugins = ["//score/itf/packs/dlt"],
    visibility = ["//test/integration:__pkg__"],
)
