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

"""Genrule-based macro that re-tars input tarballs with ``--transform``
to remap paths (e.g. ``sbin`` -> ``usr/sbin``).

This is needed because OCI base images (e.g. ubuntu:24.04) may have
``/sbin -> /usr/sbin`` as a symlink.  Overlaying a ``/sbin`` directory
from the sysroot would overwrite that symlink and break the image.
"""

def remap_tar(name, srcs, remap_paths, **kwargs):
    """Re-tar input tarballs with path remapping.

    Args:
        name: Rule name.
        srcs: Input tarball targets.
        remap_paths: Dict of ``{from_prefix: to_prefix}`` path remappings.
        **kwargs: Passed through to ``genrule``.
    """
    transforms = " ".join([
        "--transform 's|^{from_p}|{to_p}|'".format(from_p = k, to_p = v)
        for k, v in remap_paths.items()
    ])

    # For each input tarball, extract and re-tar with transforms
    native.genrule(
        name = name,
        srcs = srcs,
        outs = [name + ".tar.gz"],
        cmd = """
            TMPDIR=$$(mktemp -d)
            for f in $(SRCS); do
                tar xf $$f -C $$TMPDIR 2>/dev/null || true
            done
            tar czf $@ -C $$TMPDIR {transforms} .
            rm -rf $$TMPDIR
        """.format(transforms = transforms),
        **kwargs
    )
