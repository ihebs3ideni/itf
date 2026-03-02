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

import os
import tempfile

import score.itf


def check_command_exec(target, message):
    exit_code, output = target.exec(f"echo -n {message}", detach=False)
    return f"{message}" == output.decode()


def test_docker_runs_1(target):
    assert check_command_exec(target, "hello, world 1")


def test_docker_runs_2(target):
    assert check_command_exec(target, "hello, world 1")


@score.itf.plugins.core.requires_capabilities("exec")
def test_docker_runs_for_exec_capability(target):
    assert check_command_exec(target, "hello, world 1")


@score.itf.plugins.core.requires_capabilities("non-existing-capability")
def test_docker_skipped_for_non_existing_capability(target):
    assert False, "This test should have been skipped due to missing capability"


# -- advanced target tests ----------------------------------------------------

def test_exec_detached(target):
    """Detached exec returns an exec-id that can be waited on."""
    exec_id = target.exec(["/bin/sleep", "60"])
    assert target.is_exec_running(exec_id)
    target.kill_exec(exec_id)
    exit_code = target.wait_exec(exec_id, timeout=5)
    assert not target.is_exec_running(exec_id)


def test_copy_round_trip(target):
    """Copy a file into the container and back out, verify contents."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("itf-target-test")
        host_src = f.name

    try:
        target.copy_to(host_src, "/tmp/round_trip.txt")
        out_path = host_src + ".out"
        target.copy_from("/tmp/round_trip.txt", out_path)
        with open(out_path) as f:
            assert f.read() == "itf-target-test"
    finally:
        os.unlink(host_src)
        if os.path.exists(host_src + ".out"):
            os.unlink(host_src + ".out")
