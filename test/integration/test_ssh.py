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

import pytest
import score.itf

pytest_plugins = ["score.itf.plugins.capabilities.ssh.plugin"]


@pytest.fixture(scope="session")
def docker_configuration():
    return {
        "environment": {
            "PASSWORD_ACCESS": "true",
            "USER_NAME": "score",
            "USER_PASSWORD": "score",
        },
        "command": None,
        "init": False,
    }


def check_command_exec(exec_interface, message):
    exit_code, output = exec_interface.execute(f"echo -n {message}")
    return f"{message}" == output.decode()


def test_docker_runs_1(exec_interface):
    assert check_command_exec(exec_interface, "hello, world 1")


def test_ssh_with_default_user(exec_interface):
    exit_code, output = exec_interface.execute("/bin/sh -c \"echo 'Username:' $USER && uname -a\"")
    assert exit_code == 0
    assert b"Username:" in output


@score.itf.core.capability_gating.requires_capabilities("ssh")
def test_execute_command_output_separates_stdout_and_stderr(ssh_interface):
    with ssh_interface.ssh() as ssh:
        exit_code, stdout_lines, stderr_lines = ssh.execute_command_output(
            "echo out; echo err 1>&2; exit 7",
            timeout=10,
            max_exec_time=30,
            verbose=False,
            separate_stderr=True,
        )

    assert exit_code == 7
    assert "out" in "".join(stdout_lines)
    assert "err" in "".join(stderr_lines)


@score.itf.core.capability_gating.requires_capabilities("ssh")
def test_execute_command_output_merges_stderr_into_stdout_when_requested(ssh_interface):
    with ssh_interface.ssh() as ssh:
        exit_code, stdout_lines, stderr_lines = ssh.execute_command_output(
            "echo out; echo err 1>&2; exit 7",
            timeout=10,
            max_exec_time=30,
            verbose=False,
            separate_stderr=False,
        )

    assert exit_code == 7
    assert stderr_lines == []
    joined = "".join(stdout_lines)
    assert "out" in joined
    assert "err" in joined


@score.itf.core.capability_gating.requires_capabilities("ssh")
def test_execute_command_output_preserves_line_splitting(ssh_interface):
    with ssh_interface.ssh() as ssh:
        exit_code, stdout_lines, stderr_lines = ssh.execute_command_output(
            "printf 'a\\nb\\n'",
            timeout=10,
            max_exec_time=30,
            verbose=False,
            separate_stderr=True,
        )

    assert exit_code == 0
    assert stderr_lines == []
    assert stdout_lines == ["a\n", "b\n"]


@score.itf.core.capability_gating.requires_capabilities("ssh")
def test_execute_command_output_returns_minus_one_on_timeout(ssh_interface):
    with ssh_interface.ssh() as ssh:
        exit_code, stdout_lines, stderr_lines = ssh.execute_command_output(
            "sleep 2; echo done",
            timeout=10,
            max_exec_time=1,
            verbose=False,
            separate_stderr=True,
        )

    assert exit_code == -1


@score.itf.core.capability_gating.requires_capabilities("ssh")
def test_execute_command_output_captures_large_stdout(ssh_interface):
    # Generate a sizeable amount of stdout without relying on external utilities
    # (works with busybox /bin/sh). 256 bytes per iteration => ~256KB with 1000
    # iterations.  Kept lower than 5000 to stay well within the execution timeout
    # on emulated targets (QNX QEMU).
    line = "0123456789abcdef" * 16  # 256 chars
    cmd = f"i=0; while [ $i -lt 1000 ]; do printf '{line}\\n'; i=$((i+1)); done"

    with ssh_interface.ssh() as ssh:
        exit_code, stdout_lines, stderr_lines = ssh.execute_command_output(
            cmd,
            timeout=10,
            max_exec_time=180,
            verbose=False,
            separate_stderr=True,
        )

    assert exit_code == 0
    assert stderr_lines == []
    stdout = "".join(stdout_lines)
    assert len(stdout) > 200_000
