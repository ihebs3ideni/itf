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

"""OCI image build pipeline for SCTF Docker backend.

Creates the Docker-specific targets (sysroot_remapped, oci_image, oci_load).
Assumes the caller has already created the shared targets:
  {name}_solibs_tarball, {name}_tarballs

Prerequisites:
  - @rules_oci  (via MODULE.bazel or WORKSPACE)
  - A base OCI image (e.g. @ubuntu_24_04)
"""

load("@rules_oci//oci:defs.bzl", "oci_image", "oci_tarball")
load(":remap_tar.bzl", "remap_tar")

def create_oci_pipeline(name, base_image):
    """Create Docker-specific OCI image targets for a SCTF test.

    Requires the following targets to already exist:
      :{name}_solibs_tarball  — solibs packed into tar.gz
      :{name}_tarballs        — collected tarballs from deps

    Creates:
      :{name}_sysroot_remapped — sysroot with /sbin → /usr/sbin remap
      :{name}_image            — OCI image
      :{name}_image_tarball    — docker-loadable tarball

    Args:
        name: Test target name.
        base_image: OCI base image label (e.g. ``"@ubuntu_24_04"``).
    """

    # Remap /sbin -> /usr/sbin to avoid overwriting base image symlink
    remap_tar(
        name = "{}_sysroot_remapped".format(name),
        srcs = [":{}_tarballs".format(name)],
        remap_paths = {
            "sbin": "usr/sbin",
        },
        tags = ["manual"],
        testonly = True,
        visibility = ["//visibility:private"],
    )

    oci_image(
        name = "{}_image".format(name),
        base = base_image,
        tars = [
            ":{}_sysroot_remapped".format(name),
            ":{}_solibs_tarball".format(name),
        ],
        env = {"LD_LIBRARY_PATH": "/usr/bazel/lib"},
        tags = ["manual"],
        testonly = True,
        visibility = ["//visibility:private"],
    )

    oci_tarball(
        name = "{}_image_tarball".format(name),
        image = ":{}_image".format(name),
        repo_tags = ["sctf:{}".format(name)],
        tags = ["manual"],
        testonly = True,
        visibility = ["//visibility:private"],
    )
