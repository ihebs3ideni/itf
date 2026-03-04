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
import score.itf.plugins.core
from score.itf.core.com.ssh import execute_command


def test_ssh_with_default_user(target):
    with target.ssh() as ssh:
        execute_command(ssh, "echo 'Username:' $USER && uname -a")


def test_ssh_with_qnx_user(target):
    with target.ssh(username="qnxuser") as ssh:
        execute_command(ssh, "echo 'Username:' $USER && uname -a")


@score.itf.plugins.core.requires_capabilities("exec")
def test_exec_via_serial(target):
    """Test command execution via serial channels (requires exec capability)."""
    with target.exec("echo hello") as proc:
        exit_code = proc.wait_for_exit(timeout=10)
        assert exit_code == 0
        assert "hello" in "\n".join(proc.output)


@score.itf.plugins.core.requires_capabilities("exec")
def test_exec_via_serial_with_failure(target):
    """Test that non-zero exit codes are captured correctly."""
    with target.exec("exit 42") as proc:
        exit_code = proc.wait_for_exit(timeout=10)
        assert exit_code == 42
