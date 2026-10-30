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
load("//:defs.bzl", "py_itf_unittest")

# Pack unit tests: each may import its own pack's internals; packs never import each other.

py_itf_unittest(
    name = "qemu_test",
    srcs = glob(["qemu/*.py"]),
    data = [
        "//test/resources:qemu_bridge_config",
        "//test/resources:qemu_port_forwarding_config",
    ],
    target_compatible_with = ["@platforms//os:linux"],
    deps = [
        "//score/itf/packs/qemu:lib",
        "@rules_python//python/runfiles",
    ],
)

py_itf_unittest(
    name = "ping_test",
    srcs = glob(["ping/*.py"]),
    deps = ["//score/itf/packs/ping:lib"],
)

py_itf_unittest(
    name = "serial_test",
    srcs = glob(["serial/*.py"]),
    deps = ["//score/itf/packs/serial:lib"],
)

py_itf_unittest(
    name = "dlt_test",
    srcs = glob(["dlt/*.py"]),
    target_compatible_with = ["@platforms//os:linux"],
    deps = ["//score/itf/packs/dlt:lib"],
)

py_itf_unittest(
    name = "core_dump_test",
    srcs = glob(["core_dump/*.py"]),
    deps = ["//score/itf/packs/core_dump:lib"],
)

py_itf_unittest(
    name = "catalog_test",
    srcs = ["test_catalog.py"],
    deps = ["//tools/catalog"],
)

py_itf_unittest(
    name = "sim_test",
    srcs = glob(["sim/*.py"]),
    deps = [
        "//score/itf/packs/dlt:lib",
        "//score/itf/packs/docker:lib",
        "//score/itf/packs/net:lib",
        "//score/itf/packs/pcap:lib",
        "//score/itf/packs/ssh:lib",
    ],
)
