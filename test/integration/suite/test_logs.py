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
"""Any target whose DLT logs the session receives (`logs`).
Messages are emitted with dlt-adaptor-stdin, which DLT targets ship."""

import re
import time

import score.itf as itf


def send(target, message: str) -> None:
    code, output = target.command.exec(f"echo -n '{message}' | dlt-adaptor-stdin")
    assert code == 0, output


def wait_for_text(logs, needle: str, timeout: float = 10.0) -> list:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if hits := [m for m in logs.lines() if needle in m.text()]:
            return hits
        time.sleep(0.3)
    return []


@itf.requires("logs")
@itf.requires("command")
def test_a_message_sent_on_the_target_is_received(target):
    send(target, "secret-session-message")
    assert wait_for_text(target.logs, "secret-session-message"), "message never arrived in the session logs"


@itf.requires("logs", shape=["window", "record"])
@itf.requires("command")
def test_a_window_records_only_its_own_block_and_answers_queries(target):
    send(target, "before-window")
    with target.logs.window() as window:
        time.sleep(1)
        send(target, "inside-window")
        time.sleep(1)
    assert window.record().find(query={"payload_decoded": re.compile(r"inside-window")})
    assert all("before-window" not in m.text() for m in window.record().find())
