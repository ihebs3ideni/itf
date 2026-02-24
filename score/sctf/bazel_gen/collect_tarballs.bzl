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

"""Rule to collect tarballs from provided dependencies."""

def _collect_tarballs_impl(ctx):
    """Implementation of the _collect_tarballs rule."""

    all_files_list = depset(
        ctx.files.deps,
        transitive = [
            dep.default_runfiles.files
            for dep in ctx.attr.deps
            if hasattr(dep, "default_runfiles") and dep.default_runfiles
        ],
    ).to_list()

    tarballs = [f for f in all_files_list if f.basename.endswith((".tar", ".tar.gz"))]

    return [DefaultInfo(files = depset(tarballs))]

_collect_tarballs = rule(
    implementation = _collect_tarballs_impl,
    attrs = {
        "deps": attr.label_list(allow_files = True),
    },
)

def collect_tarballs(
        name,
        deps = None,
        **kwargs):
    """Collect tarballs (.tar, .tar.gz) from transitive dependencies.

    Args:
        name: Rule name.
        deps: Label list of targets whose transitive tarballs are collected.
        **kwargs: Forwarded to the filegroup.
    """
    _collect_tarballs(
        name = "{}_collect".format(name),
        deps = deps if deps else [],
        testonly = True,
        tags = ["manual"],
        visibility = ["//visibility:private"],
    )

    native.filegroup(
        name = name,
        srcs = [
            ":{}_collect".format(name),
        ],
        **kwargs
    )
