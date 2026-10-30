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
load("@rules_python//python:defs.bzl", "py_binary", "py_library")

# Every pack, loaded the way a recipe would: the catalog is built from their own decorators.
PACKS = [
    "//score/itf/packs/core_dump",
    "//score/itf/packs/dlt",
    "//score/itf/packs/local",
    "//score/itf/packs/docker",
    "//score/itf/packs/net",
    "//score/itf/packs/pcap",
    "//score/itf/packs/ping",
    "//score/itf/packs/qemu",
    "//score/itf/packs/serial",
    "//score/itf/packs/ssh",
]

py_library(
    name = "catalog",
    srcs = ["build_catalog.py"],
    data = [
        "schema.sql",
        "template.html",
    ],
    visibility = ["//test/packs:__pkg__"],
    deps = ["//score/itf/core"] + PACKS,
)

# bazel run //tools/catalog:query -- schema | sql "..." | search WORDS | serve
py_binary(
    name = "query",
    srcs = ["query.py"],
    deps = [":catalog"],
)

# bazel run //tools/catalog:build -- --out catalog.html --db catalog.db
py_binary(
    name = "build",
    srcs = ["build_catalog.py"],
    main = "build_catalog.py",
    deps = [":catalog"],
)
