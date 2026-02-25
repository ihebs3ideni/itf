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
# Bazel BUILD file for tcpdump 4.99.5 (Linux/amd64).
#
# config.h is provided via a patch applied by http_archive in MODULE.bazel.
#

cc_binary(
    name = "tcpdump",
    srcs = glob(
        [
            "*.c",
            "*.h",
            "missing/strlcat.c",
            "missing/strlcpy.c",
        ],
        exclude = [
            # Debug instrumentation — requires libbfd
            "instrument-functions.c",
            # Compat shims not needed on Linux (except strlcpy/strlcat above)
            "missing/getopt_long.c",
            "missing/getservent.c",
            "missing/strsep.c",
            "missing/strdup.c",
            "missing/pcap_dump_ftell.c",
            "missing/snprintf.c",
        ],
    ),
    copts = [
        "-DHAVE_CONFIG_H",
        "-Wno-unused-parameter",
        "-Wno-sign-compare",
        "-Wno-implicit-fallthrough",
        "-Wno-format-truncation",
    ],
    includes = ["."],
    linkopts = ["-lpthread"],
    visibility = ["//visibility:public"],
    deps = ["@libpcap"],
)
