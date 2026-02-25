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

from score.itf.core.com.ssh import execute_command


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


def check_command_exec(target, message):
    exit_code, output = target.exec(f"echo -n {message}", detach=False)
    return f"{message}" == output.decode()


def test_docker_runs_1(target):
    assert check_command_exec(target, "hello, world 1")


def test_ssh_with_default_user(target):
    with target.ssh() as ssh:
        execute_command(ssh, "echo 'Username:' $USER && uname -a")
