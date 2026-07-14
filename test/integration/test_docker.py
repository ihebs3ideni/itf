# *******************************************************************************
# Copyright (c) 2025-2026 Contributors to the Eclipse Foundation
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
import pytest


def check_command_exec(exec_interface, message):
    exit_code, output = exec_interface.execute(f"echo -n {message}")
    return f"{message}" == output.decode()


def test_docker_runs_1(exec_interface):
    assert check_command_exec(exec_interface, "hello, world 1")


def test_docker_runs_2(exec_interface):
    assert check_command_exec(exec_interface, "hello, world 1")


def test_docker_runs_for_exec_capability(exec_interface):
    assert check_command_exec(exec_interface, "hello, world 1")


def test_dut_reports_missing_non_existing_capability(dut):
    assert not dut.available("itf/cap/non-existing-capability")


def test_target_file_transfer_and_restart(exec_interface, file_transfer_interface, tmp_path):
    local_src = tmp_path / "src.txt"
    local_dst = tmp_path / "dst.txt"
    remote_path = "/tmp/itf_upload_test.txt"

    content = "hello from host\n"
    local_src.write_text(content, encoding="utf-8")

    file_transfer_interface.upload(str(local_src), remote_path)
    exit_code, output = exec_interface.execute(f"/bin/sh -c 'cat {remote_path}'")
    assert exit_code == 0
    assert output.decode() == content

    file_transfer_interface.download(remote_path, str(local_dst))
    assert local_dst.read_text(encoding="utf-8") == content


def test_restart(restart_interface, exec_interface, tmp_path):
    restart_interface.restart()
    exit_code, output = exec_interface.execute("echo -n restarted")
    assert exit_code == 0
    assert output == b"restarted"


CONTAINER_EXTRA_MNT_PATH = "/extra/mount/directory"


def test_extra_mount(exec_interface):
    exit_code, _ = exec_interface.execute(f"ls -al {CONTAINER_EXTRA_MNT_PATH}")
    assert exit_code == 0, "Extra volume not mounted!"
