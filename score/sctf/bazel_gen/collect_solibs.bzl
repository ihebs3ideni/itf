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

"""Rule to collect x86_64 shared libraries from transitive dependencies."""

def _collect_solibs_impl(ctx):
    """Implementation of the _collect_solibs rule."""

    solib_dir_path = ctx.bin_dir.path + "/_solib_x86_64"
    output_dir = ctx.actions.declare_directory(ctx.attr.name)

    all_transitive_files = depset(
        ctx.files.deps,
        transitive = [
            dep.default_runfiles.files
            for dep in ctx.attr.deps
            if hasattr(dep, "default_runfiles") and dep.default_runfiles
        ],
    )

    all_files_list = all_transitive_files.to_list()

    solibs = [f for f in all_files_list if solib_dir_path in f.path]

    command = ["mkdir -p {}".format(output_dir.path)]

    for solib in solibs:
        # Copy preserving the symlink
        command.append("cp -P {src} {dst}".format(src = solib.path, dst = output_dir.path))

    ctx.actions.run_shell(
        outputs = [output_dir],
        inputs = all_transitive_files,
        command = " && ".join(command),
        progress_message = "Collecting solibs for {}".format(ctx.label),
    )

    return [DefaultInfo(files = depset([output_dir]))]

_collect_solibs = rule(
    implementation = _collect_solibs_impl,
    attrs = {
        "deps": attr.label_list(allow_files = True),
    },
)

def collect_solibs(
        name,
        deps = None,
        **kwargs):
    """Collect x86_64 shared libraries from transitive dependencies.

    Creates a directory tree containing all ``_solib_x86_64`` shared libraries
    found in the transitive closure of *deps*.

    Args:
        name: Rule name.
        deps: Label list of targets whose transitive solibs are collected.
        **kwargs: Forwarded to the filegroup.
    """
    _collect_solibs(
        name = "{}_collect".format(name),
        deps = deps if deps else [],
        testonly = True,
        tags = ["manual"],
        visibility = ["//visibility:private"],
    )

    native.filegroup(
        name = name,
        srcs = [":{}_collect".format(name)],
        **kwargs
    )
