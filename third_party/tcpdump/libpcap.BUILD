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
#
# Bazel BUILD file for libpcap 1.10.5 (Linux/amd64).
#
# The flex/bison-generated files (scanner.c, grammar.c, grammar.h) and
# config.h are added via a patch applied by http_archive in MODULE.bazel.
#

cc_library(
    name = "libpcap",
    # Core sources — Linux capture backend.
    # scanner.c and grammar.c are provided by the patch.
    srcs = [
        "bpf_dump.c",
        "bpf_filter.c",
        "bpf_image.c",
        "etherent.c",
        "fad-getad.c",
        "fmtutils.c",
        "gencode.c",
        "grammar.c",
        "missing/strlcat.c",
        "missing/strlcpy.c",
        "nametoaddr.c",
        "optimize.c",
        "pcap-common.c",
        "pcap-linux.c",
        "pcap-netfilter-linux.c",
        "pcap-util.c",
        "pcap.c",
        "savefile.c",
        "scanner.c",
        "sf-pcap.c",
        "sf-pcapng.c",
    ],
    hdrs = glob(["*.h", "pcap/*.h"]),
    copts = [
        "-DHAVE_CONFIG_H",
        "-Wno-unused-parameter",
        "-Wno-sign-compare",
        "-Wno-implicit-fallthrough",
    ],
    includes = ["."],
    linkopts = ["-lpthread"],
    visibility = ["//visibility:public"],
)
