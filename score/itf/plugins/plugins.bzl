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
load("//bazel:sctf_image.bzl", "sctf_image")

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

def sctf_docker(image = None, name = None, deps = None, base_image = "@ubuntu_24_04", data = None):
    """Create an SCTF Docker plugin wired to a built image.

    This is a plugin factory — it returns a ``py_itf_plugin`` struct that
    enables both the ITF Docker plugin (which registers CLI options) and
    the SCTF plugin (which provides the ``docker_sandbox`` fixture).

    Usage patterns
    ==============

    **1. Single test, single image (recommended for one-off tests):**

    Use ``name`` to create the image inline — simplest, no extra
    declarations needed::

        py_itf_test(
            name = "test_my_component",
            srcs = ["test_my_component.py"],
            plugins = [sctf_docker(
                name = "my_image",
                deps = [":my_binary"],
            )],
        )

    ``deps``, ``base_image``, and ``data`` are all optional::

        py_itf_test(
            name = "test_base_only",
            srcs = ["test_base_only.py"],
            plugins = [sctf_docker(name = "base_image")],
        )

    **2. Shared image across multiple tests (recommended for shared images):**

    Declare the image once with ``sctf_image()``, then reference it by
    name via the ``image`` parameter.  This keeps target creation visible
    at the top level and is the idiomatic Bazel pattern::

        sctf_image(
            name = "shared_image",
            deps = [":my_binary"],
        )

        py_itf_test(
            name = "test_a",
            srcs = ["test_a.py"],
            plugins = [sctf_docker(image = "shared_image")],
        )

        py_itf_test(
            name = "test_b",
            srcs = ["test_b.py"],
            plugins = [sctf_docker(image = "shared_image")],
        )

    .. note::

       Do **not** call ``sctf_docker(name=...)`` once, store the result
       in a variable, and pass it to multiple ``py_itf_test`` targets.
       While that works, it hides Bazel target creation inside a variable
       assignment, making the BUILD file harder to read.  Prefer
       ``sctf_image()`` + ``sctf_docker(image=...)`` for the shared case.

    Args:
        image: Name of an existing ``sctf_image()`` target in the same
            package.  Mutually exclusive with *name*.
        name: Image name for a new ``sctf_image()`` that will be created
            automatically.  Best for single-test use.  Mutually exclusive
            with *image*.
        deps: Binary dependencies to bake into the image (cc_binary,
            pkg_tar, etc.).  Only used with *name*.
        base_image: OCI base image label (default ``"@ubuntu_24_04"``).
            Only used with *name*.
        data: Additional data files whose tarballs should be included.
            Only used with *name*.

    Returns:
        A ``py_itf_plugin`` struct with both plugins enabled and image
        args/data pre-configured.
    """
    if image and name:
        fail("sctf_docker: 'image' and 'name' are mutually exclusive — use 'image' to reference an existing sctf_image target, or 'name' to create one")
    if not image and not name:
        fail("sctf_docker: specify either 'image' (existing sctf_image target) or 'name' (auto-create one)")
    if image and (deps or data):
        fail("sctf_docker: 'deps' and 'data' can only be used with 'name', not 'image'")

    if name:
        sctf_image(
            name = name,
            base_image = base_image,
            deps = deps,
            data = data,
        )
        image = name

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
