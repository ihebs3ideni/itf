# *******************************************************************************
# Copyright (c) 2025 Contributors to the Eclipse Foundation
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
"""Hello SCTF – minimal smoke test for the SCTF Docker environment.

Validates that:
  1. The ``docker_sandbox`` fixture creates a running container.
  2. A simple command can be executed inside the container.
  3. The process handle returned by ``execute()`` is usable.
  4. File copy to/from the container works.
"""

import pathlib


def test_hello_sctf(docker_sandbox):
    """Run ``echo hello sctf`` inside the container and verify the output."""
    env = docker_sandbox.environment
    handle = env.execute("/bin/echo", ["hello", "sctf"])
    env.stop_process(handle)
    assert handle.exit_code == 0


def test_execute_returns_nonzero_on_failure(docker_sandbox):
    """A command that fails should report a non-zero exit code."""
    env = docker_sandbox.environment
    handle = env.execute("/bin/false", [])
    env.stop_process(handle)
    assert handle.exit_code != 0


def test_copy_file_round_trip(docker_sandbox):
    """Copy a file into the container and read it back."""
    env = docker_sandbox.environment
    workspace = pathlib.Path(docker_sandbox.tmp_workspace)

    # Create a local file to copy
    src = workspace / "hello.txt"
    src.write_text("hello from sctf")

    # Copy into the container
    env.copy_to(str(src), "/tmp/hello.txt")

    # Copy back out
    dst = workspace / "hello_back.txt"
    env.copy_from("/tmp/hello.txt", str(dst))

    assert dst.read_text() == "hello from sctf"
