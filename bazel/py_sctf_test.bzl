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
"""Bazel macro for running Docker-based SCTF tests.

This macro creates the OCI image build pipeline (collect solibs, collect
tarballs, remap, oci_image, oci_load) and wraps a ``py_test`` that boots
the image and runs test code against it.

Example usage in a BUILD file::

    load("@score_itf//bazel:py_sctf_test.bzl", "py_sctf_test")

    py_sctf_test(
        name = "my_sctf_test",
        srcs = ["test_my_component.py"],
        deps = [":my_binary_package"],
        base_image = "@ubuntu_24_04",
    )
"""

load("@rules_pkg//:pkg.bzl", "pkg_tar")
load("@rules_python//python:defs.bzl", "py_test")
load("@score_itf//score/sctf/bazel_gen:collect_solibs.bzl", "collect_solibs")
load("@score_itf//score/sctf/bazel_gen:collect_tarballs.bzl", "collect_tarballs")
load("@score_itf//score/sctf/bazel_gen:oci_pipeline.bzl", "create_oci_pipeline")

def py_sctf_test(
        name,
        srcs,
        base_image = "@ubuntu_24_04",
        deps = None,
        data = None,
        args = None,
        env = None,
        plugins = None,
        tags = None,
        timeout = "moderate",
        flaky = False,
        **kwargs):
    """Docker-based Software Component Test.

    Builds an OCI image containing the test's binary dependencies, loads it
    into Docker at test time, and runs *srcs* against the container.

    Args:
        name: Test target name.
        srcs: Python test source files.
        base_image: OCI base image label (default: ``"@ubuntu_24_04"``).
        deps: Additional Bazel dependencies (cc_binary targets, packages, etc.).
        data: Additional data files for the test.
        args: Extra pytest arguments.
        env: Extra environment variables.
        plugins: Additional pytest plugins to enable (beyond the default SCTF docker plugin).
        tags: Extra tags for the test target.
        timeout: Bazel test timeout (default: ``"moderate"``).
        flaky: Whether the test is flaky.
        **kwargs: Forwarded to ``py_test``.
    """
    pytest_bootstrap = Label("@score_itf//:main.py")
    pytest_ini = Label("@score_itf//:pytest.ini")

    deps = [] if deps == None else list(deps)
    data = [] if data == None else list(data)
    args = [] if args == None else list(args)
    tags = [] if tags == None else list(tags)

    # SCTF framework dependency
    deps.append(Label("@score_itf//score/sctf"))

    # Docker SDK
    deps.append(Label("@score_itf//score/itf/plugins:docker"))

    # --- OCI image build pipeline ---
    collect_solibs(
        name = "{}_solibs".format(name),
        deps = deps,
        testonly = True,
        tags = ["manual"],
        visibility = ["//visibility:private"],
    )

    collect_tarballs(
        name = "{}_tarballs".format(name),
        deps = data + deps,
        tags = ["manual"],
        testonly = True,
        visibility = ["//visibility:private"],
    )

    pkg_tar(
        name = "{}_solibs_tarball".format(name),
        srcs = [":{}_solibs".format(name)],
        package_dir = "/usr/bazel/lib",
        strip_prefix = "{}_solibs_collect".format(name),
        tags = ["manual"],
        testonly = True,
        extension = "tar.gz",
        visibility = ["//visibility:private"],
    )

    create_oci_pipeline(name, base_image)

    # --- Pytest plugin args ---
    plugin_args = [
        "-p score.sctf.plugins",
    ]
    if plugins:
        for p in plugins:
            plugin_args.append("-p %s" % p)

    # Docker image args
    docker_args = [
        "--docker-image-bootstrap=$(location :{}_image_tarball)".format(name),
        "--docker-image=sctf:{}".format(name),
    ]

    # Test data includes the OCI image tarball
    test_data = [pytest_ini] + data + [
        ":{}_image_tarball".format(name),
    ]

    # Merge environment
    test_env = {}
    if env:
        test_env.update(env)

    # Tags
    test_tags = ["sctf", "cpu:2"] + tags

    py_test(
        name = name,
        srcs = [pytest_bootstrap] + srcs,
        main = pytest_bootstrap,
        data = test_data,
        deps = deps,
        args = ["-c $(location %s)" % pytest_ini] +
               ["-p no:cacheprovider", "--show-capture=no"] +
               plugin_args + docker_args + args +
               ["$(location %s)" % x for x in srcs],
        env = test_env,
        size = "large",
        timeout = timeout,
        tags = test_tags,
        flaky = flaky,
        **kwargs
    )
