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
"""SCTF example — run the C++ example-app inside a Docker container.

Demonstrates how to use ``sctf_image()`` + ``sctf_docker()`` to package a
C++ binary into an OCI image and exercise it via the ``docker_sandbox``
fixture.
"""

import pathlib


def test_example_app_runs_successfully(docker_sandbox):
    """Execute the example-app binary and verify it prints 'Hello!'."""
    env = docker_sandbox.environment

    handle = env.execute("/example-app", [])
    env.stop_process(handle, timeout=10)

    assert handle.exit_code == 0, (
        f"example-app exited with code {handle.exit_code}"
    )


def test_example_app_stdout_contains_hello(docker_sandbox):
    """Verify that example-app writes 'Hello!' to stdout."""
    env = docker_sandbox.environment
    workspace = pathlib.Path(docker_sandbox.tmp_workspace)

    # Run the app and redirect stdout to a file inside the container
    handle = env.execute("/bin/sh", ["-c", "/example-app > /tmp/app_output.txt"])
    env.stop_process(handle, timeout=10)
    assert handle.exit_code == 0

    # Copy the output file back to the host and check contents
    dst = workspace / "app_output.txt"
    env.copy_from("/tmp/app_output.txt", str(dst))

    output = dst.read_text().strip()
    assert output == "Hello!", f"unexpected output: {output!r}"


def test_example_app_returns_zero(docker_sandbox):
    """Verify that example-app returns exit code 0 (success)."""
    env = docker_sandbox.environment

    handle = env.execute("/example-app", [])
    env.stop_process(handle, timeout=10)

    assert handle.exit_code == 0
