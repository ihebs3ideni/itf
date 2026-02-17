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

load("//bazel:py_itf_plugin.bzl", "py_itf_plugin")

docker = py_itf_plugin(
    py_library = "@score_itf//score/itf/plugins:docker",
    enabled_plugins = [
        "score.itf.plugins.docker",
    ],
    args = [
    ],
    data = [
    ],
    data_as_exec = [
    ],
    tags = [
    ],
)

qemu = py_itf_plugin(
    py_library = "@score_itf//score/itf/plugins/qemu",
    enabled_plugins = [
        "score.itf.plugins.qemu",
    ],
    args = [
    ],
    data = [
    ],
    data_as_exec = [
    ],
    tags = [
    ],
)

dlt = py_itf_plugin(
    py_library = "@score_itf//score/itf/plugins/dlt",
    enabled_plugins = [
        "score.itf.plugins.dlt",
    ],
    args = [
        "--dlt-receive-path=$(location @score_itf//third_party/dlt:dlt-receive)",
    ],
    data = [
    ],
    data_as_exec = [
        "@score_itf//third_party/dlt:dlt-receive",
    ],
    tags = [
    ],
)

def sctf_docker(image):
    """Create an SCTF Docker plugin wired to a built image.

    This is a plugin factory — it returns a ``py_itf_plugin`` struct that
    enables both the ITF Docker plugin (which registers CLI options) and
    the SCTF plugin (which provides the ``docker_sandbox`` fixture).

    The *image* argument is the name passed to ``sctf_image()``.  The
    factory resolves the corresponding tarball target and generates the
    correct ``--docker-image`` and ``--docker-image-bootstrap`` arguments.

    Example usage in a BUILD file::

        load("@score_itf//:defs.bzl", "py_itf_test", "sctf_image")
        load("@score_itf//score/itf/plugins:plugins.bzl", "sctf_docker")

        sctf_image(name = "my_image", deps = [":my_binary"])

        py_itf_test(
            name = "test_my_component",
            srcs = ["test_my_component.py"],
            plugins = [sctf_docker(image = "my_image")],
        )

    Args:
        image: Name of the ``sctf_image()`` target in the same package.

    Returns:
        A ``py_itf_plugin`` struct with both plugins enabled and image
        args/data pre-configured.
    """
    tarball_label = ":{}_image_tarball".format(image)

    return py_itf_plugin(
        py_library = "@score_itf//score/sctf",
        enabled_plugins = [
            "score.itf.plugins.docker",
            "score.sctf.plugins",
        ],
        args = [
            "--docker-image-bootstrap=$(location {})".format(tarball_label),
            "--docker-image=sctf:{}".format(image),
        ],
        data = [
            tarball_label,
        ],
        data_as_exec = [
        ],
        tags = [
            "sctf",
            "cpu:2",
        ],
    )
