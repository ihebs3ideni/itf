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
"""Every host process goes through ProcessWrapper, so nothing outlives a run."""

import subprocess

import pytest

from score.itf.core.process import ProcessWrapper
from score.itf.core.session import Session


def test_run_returns_code_and_both_streams_and_leaves_nothing_tracked():
    code, out, err = ProcessWrapper.run("/bin/sh", ["-c", "echo out; echo err >&2; exit 3"])
    assert (code, out.strip(), err.strip()) == (3, "out", "err")
    assert ProcessWrapper.live() == ()


def test_run_stops_the_process_on_timeout():
    with pytest.raises(subprocess.TimeoutExpired):
        ProcessWrapper.run("/bin/sleep", ["30"], timeout=0.3)
    assert ProcessWrapper.live() == ()


def test_reap_stops_a_process_nobody_stopped():
    leaked = ProcessWrapper("/bin/sleep", ["30"], logger_name="sleeper")
    leaked.start_process()
    assert leaked in ProcessWrapper.live()
    described = ProcessWrapper.reap()
    assert described and "sleep" in described[0]
    assert not leaked.is_running() and ProcessWrapper.live() == ()


def test_the_session_reaps_and_reports_a_leaked_process(tmp_path):
    session = Session(["shell_recipe"], run_dir=tmp_path)
    session.resolve()
    session.bring_up()
    ProcessWrapper("/bin/sleep", ["30"], logger_name="sleeper").start_process()
    session.close()
    assert ProcessWrapper.live() == ()
    assert "still running at close" in session.close_problems().render(width=100)


def test_keep_output_retains_every_line():
    wrapper = ProcessWrapper(
        "/bin/sh", ["-c", "for i in 1 2 3; do echo line$i; done"], logger_name="t", keep_output=True
    )
    wrapper.start_process()
    wrapper.process.wait(5)
    wrapper.console.line_reader.join(timeout=2)
    assert wrapper.output().split() == ["line1", "line2", "line3"]


def test_stopping_returns_only_after_the_last_line_was_logged(caplog):
    wrapper = ProcessWrapper(
        "/bin/sh", ["-c", "echo first; echo last; sleep 30"], logger_name="drain", keep_output=True
    )
    with caplog.at_level("INFO", logger="drain"):
        wrapper.start_process()
        import time

        time.sleep(0.3)
        wrapper.kill_process()
    assert [r.getMessage() for r in caplog.records if r.name == "drain"] == ["first", "last"]
