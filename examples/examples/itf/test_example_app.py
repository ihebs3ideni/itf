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
"""The example application, whatever machine the recipe provides: tests name contracts, not machines."""

import score.itf as itf
from score.itf.core.process import WrappedProcess

COMMAND = "itf.capabilities.exec.command"
PROCESS = "itf.capabilities.exec.process"
FILES = "itf.capabilities.files.transfer"
CONSOLE = "itf.capabilities.exec.console"


@itf.requires(COMMAND)
def test_example_app_greets(target):
    assert target.command.exec("/example-app") == (0, "Hello!\n")


@itf.requires(PROCESS)
def test_example_app_exits_cleanly_under_a_wrapper(target):
    with WrappedProcess(target.process, "/example-app", wait_on_exit=True) as app:
        pass
    assert app.ret_code == 0 and "Hello!" in app.get_output()


@itf.requires(FILES)
@itf.requires(COMMAND)
def test_a_file_uploaded_from_the_host_is_visible(target, tmp_path):
    (tmp_path / "note.txt").write_text("from the host\n", encoding="utf-8")
    target.files.upload(str(tmp_path / "note.txt"), "/tmp/note.txt")
    assert target.command.exec("cat /tmp/note.txt") == (0, "from the host\n")


@itf.requires(CONSOLE)
def test_the_console_recorded_the_boot(target):
    assert target.console.lines()
