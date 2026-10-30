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
"""Any target with a session shell (itf.capabilities.exec.shell)."""

import pytest

import score.itf as itf

SHELL = "itf.capabilities.exec.shell"


@itf.requires(SHELL)
def test_run_returns_stdout_and_raises_on_failure(target):
    assert target.shell.run("echo -n ok") == "ok"
    with pytest.raises(RuntimeError):
        target.shell.run("exit 1")


@itf.requires(SHELL, shape=["exec_lines"])
def test_stdout_and_stderr_can_be_kept_apart_or_merged(target):
    code, out, err = target.shell.exec_lines("echo out; echo err 1>&2; exit 7", separate_stderr=True)
    assert code == 7 and "out" in "".join(out) and "err" in "".join(err)
    code, out, err = target.shell.exec_lines("echo out; echo err 1>&2; exit 7", separate_stderr=False)
    assert err == [] and "err" in "".join(out)


@itf.requires(SHELL, shape=["exec_lines"])
def test_line_splitting_is_preserved(target):
    assert target.shell.exec_lines("printf 'a\\nb\\n'") == (0, ["a\n", "b\n"], [])


@itf.requires(SHELL, shape=["exec_lines"])
def test_a_command_running_too_long_reports_minus_one(target):
    assert target.shell.exec_lines("sleep 5", max_exec_time=1)[0] == -1
