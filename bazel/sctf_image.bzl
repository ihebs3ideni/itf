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
"""Standalone Bazel macro for building SCTF Docker images.

This macro creates an OCI image from binary dependencies (cc_binary, pkg_tar,
etc.) without coupling to any test framework.  The resulting tarball can be
loaded into Docker at test time.

The image pipeline:

    deps ──► collect_solibs ──► pkg_tar (solibs)  ──┐
    deps ──► collect_tarballs ──► remap_tar ────────┤
                                                     ├──► oci_image ──► oci_tarball
                                     base_image ────┘

Produces **{name}_tarball** — a self-extracting shell script that loads the
image into Docker when executed.

Example usage::

    load("@score_itf//bazel:sctf_image.bzl", "sctf_image")

    sctf_image(
        name = "my_image",
        base_image = "@ubuntu_24_04",
        deps = [":my_binary_package"],
    )

    # The resulting target :{name}_tarball can be passed to py_itf_test
    # via the sctf_docker() plugin.
"""

load("@rules_pkg//:pkg.bzl", "pkg_tar")
load("@score_itf//score/sctf/bazel_gen:collect_solibs.bzl", "collect_solibs")
load("@score_itf//score/sctf/bazel_gen:collect_tarballs.bzl", "collect_tarballs")
load("@score_itf//score/sctf/bazel_gen:oci_pipeline.bzl", "create_oci_pipeline")

def sctf_image(
        name,
        base_image = "@ubuntu_24_04",
        deps = None,
        data = None,
        tags = None,
        visibility = None):
    """Build an OCI Docker image for SCTF tests.

    Collects shared libraries and tarballs from *deps*, layers them onto
    *base_image*, and produces a Docker-loadable tarball.

    Creates the following targets:

    - ``:{name}_solibs``          — collected shared libraries
    - ``:{name}_solibs_tarball``  — solibs packed into tar.gz
    - ``:{name}_tarballs``        — collected tarballs from deps
    - ``:{name}_sysroot_remapped``— sysroot with /sbin→/usr/sbin remap
    - ``:{name}_image``           — OCI image
    - ``:{name}_image_tarball``   — Docker-loadable tarball (main output)

    Args:
        name: Image name.  Also used as the Docker tag: ``sctf:{name}``.
        base_image: OCI base image label (default: ``"@ubuntu_24_04"``).
        deps: Binary dependencies to bake into the image (cc_binary, pkg_tar, etc.).
        data: Additional data files whose tarballs should be included.
        tags: Bazel tags for all generated targets.
        visibility: Bazel visibility for the tarball target.
    """
    deps = [] if deps == None else list(deps)
    data = [] if data == None else list(data)
    tags = [] if tags == None else list(tags)

    common_kwargs = {
        "testonly": True,
        "tags": ["manual"] + tags,
        "visibility": ["//visibility:private"],
    }

    # ---- Step 1: Collect shared libraries ----
    collect_solibs(
        name = "{}_solibs".format(name),
        deps = deps,
        **common_kwargs
    )

    # ---- Step 2: Pack solibs into a tarball ----
    pkg_tar(
        name = "{}_solibs_tarball".format(name),
        srcs = [":{}_solibs".format(name)],
        package_dir = "/usr/bazel/lib",
        strip_prefix = "{}_solibs_collect".format(name),
        extension = "tar.gz",
        **common_kwargs
    )

    # ---- Step 3: Collect tarballs from deps + data ----
    collect_tarballs(
        name = "{}_tarballs".format(name),
        deps = data + deps,
        **common_kwargs
    )

    # ---- Step 4: OCI pipeline (remap → oci_image → oci_tarball) ----
    create_oci_pipeline(name, base_image)
